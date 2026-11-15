"""Two-channel Prisma v3.0 streaming client.

Prisma does not diarize on the realtime API and takes mono only. Dialers record
recovery calls dual-channel (agent on one leg, borrower on the other), so we open
one WebSocket session per channel and get perfect speaker attribution for free.

Protocol facts this file encodes (docs.gnani.ai/api/STT/stt-websocket):
  * wss://api.vachana.ai/stt/v3/stream, all config in handshake headers
  * raw PCM signed 16-bit LE, mono, exactly 1,024 bytes per binary frame
  * frames go out at real-time cadence (64 ms per frame at 8 kHz); bursting hurts VAD
  * server sends speech_start / processing / transcript; one transcript per VAD segment
  * no word timestamps, so segment times are rebuilt from our own send clock
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import numpy as np
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidMessage, InvalidStatus

from ..common import config
from ..common.audio import float_to_pcm16, read_wav, resample
from ..common.schema import AGENT, BORROWER, CHANNELS, CallMeta, Segment

FRAME_BYTES = 1024
SR = config.SAMPLE_RATE
FRAME_MS = FRAME_BYTES // 2 * 1000 // SR  # 64 ms at 8 kHz
MIN_SILENCE_MS = int(os.environ.get("STT_MIN_SILENCE_MS", "500"))
TAIL_SILENCE_MS = 1500  # lets VAD close the last utterance
# Voice-activity settings for a noisy line. On a call-centre floor the background chatter is
# speech too, so the docs' telephony preset (0.7, no cap) never sees a pause and holds the agent's
# whole side of the call in one segment. A stricter threshold and a cap on segment length keep
# transcripts, and therefore alerts, arriving while the call is still in progress.
VAD_THRESHOLD = "0.85"
MAX_SPEECH_S = "10"

DOMAIN_KEYTERMS = [
    "EMI", "late fee", "late charges", "outstanding", "overdue", "pending", "payment link", "part payment",
    "statement", "record", "recording", "credit score", "legal notice", "NACH", "bounce", "restructuring",
    "बकाया", "किस्त", "ਬਕਾਇਆ", "ਕਿਸ਼ਤ",
]
TOPIC = "A loan recovery phone call between a lender's collection agent and a borrower about overdue EMI payments."

_sessions: dict[int, asyncio.Semaphore] = {}


def _session_slots() -> asyncio.Semaphore:
    loop = id(asyncio.get_running_loop())
    if loop not in _sessions:
        _sessions[loop] = asyncio.Semaphore(config.MAX_STT_SESSIONS)
    return _sessions[loop]


def headers_for(meta: CallMeta, channel: str, model: str | None = None) -> dict[str, str]:
    """Handshake headers. Non-ASCII values must be JSON-escaped, which json.dumps does by default."""
    model = model or config.STT_MODEL
    native = "hi-IN" if meta.language == "hi-en" else meta.language  # Hinglish calls are sent as hi-IN
    h = {
        "x-api-key-id": config.require_gnani(),
        "model": model,
        "x-sample-rate": str(SR),
        # digits for amounts and clock times, English words left in Latin script
        "format": "transcribe",
        "x-vad-threshold": os.environ.get("STT_VAD_THRESHOLD", VAD_THRESHOLD),
        "x-min-speech-ms": "200",
        "x-min-silence-ms": str(MIN_SILENCE_MS),
        "x-max-speech-s": os.environ.get("STT_MAX_SPEECH_S", MAX_SPEECH_S),
        "x-idle-timeout-sec": "300",  # one side of a call can be quiet for a long time
        "x-api-request-id": f"maryada-{meta.call_id}-{channel}",
    }
    if model == "prisma-v3.0":
        # The docs describe a list of 1-4 languages here, but on 14 Nov 2026 the live endpoint
        # accepted only one locale or indic-auto. We send the borrower's language from the CRM:
        # it is a hint, not a lock, and English words still come back in Latin script.
        h["language_code"] = native
        h["keyterms"] = json.dumps(DOMAIN_KEYTERMS + [meta.lender, meta.loan.product])
        h["topic"] = TOPIC
        h["speaker_names"] = json.dumps([meta.agent_name, meta.borrower_name])
    else:  # prisma-v2.5: one language, no context
        h["language_code"] = native
    return h


@dataclass
class ChannelStream:
    channel: str
    pcm: bytes
    headers: dict[str, str]
    out: asyncio.Queue
    pace: float = 1.0  # 1.0 = real time
    pos_ms: int = 0  # how much of this channel's audio has been sent
    errors: list[str] = field(default_factory=list)
    _index: int = 0
    _sent: int = 0
    _ends: list[int] = field(default_factory=list)

    async def run(self) -> None:
        frames = [self.pcm[i:i + FRAME_BYTES].ljust(FRAME_BYTES, b"\0") for i in range(0, len(self.pcm), FRAME_BYTES)]
        frames += [bytes(FRAME_BYTES)] * (TAIL_SILENCE_MS // FRAME_MS + 1)
        attempt = 0
        async with _session_slots():
            while self._sent < len(frames) and attempt < 6:
                attempt += 1
                try:
                    async with connect(config.STT_WS_URL, additional_headers=self.headers,
                                       open_timeout=30, max_size=None) as ws:
                        reader = asyncio.create_task(self._read(ws))
                        try:
                            await self._send(ws, frames, self._sent)
                            await ws.send(json.dumps({"type": "commit"}))
                            await asyncio.sleep(3.0 / self.pace if self.pace > 1 else 3.0)  # last transcript
                        finally:
                            reader.cancel()
                            await asyncio.gather(reader, return_exceptions=True)
                except InvalidStatus as e:  # 401 / 429 before the socket opens
                    code = e.response.status_code
                    self.errors.append(f"handshake {code}")
                    if code in (401, 403):
                        raise
                    await asyncio.sleep(2 * attempt)
                except (ConnectionClosed, InvalidMessage, OSError, asyncio.TimeoutError) as e:
                    self.errors.append(f"dropped at {self.pos_ms} ms: {type(e).__name__}")
                    await asyncio.sleep(1.0)  # reconnect and resume from the same frame

    async def _send(self, ws, frames: list[bytes], start: int) -> None:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        for i in range(start, len(frames)):
            await ws.send(frames[i])
            self._sent = i + 1  # a reconnect resumes from here, so the call clock never rewinds
            self.pos_ms = self._sent * FRAME_MS
            delay = t0 + (i - start + 1) * FRAME_MS / 1000 / self.pace - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

    async def _read(self, ws) -> None:
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "processing":
                self._ends.append(self.pos_ms)
            elif kind == "transcript":
                text = (msg.get("text") or "").strip()
                dur = int(float(msg.get("audio_duration_ms") or 0))
                # VAD closes a segment MIN_SILENCE after speech stops; "processing" marks that instant.
                closed_at = self._ends.pop(0) if self._ends else self.pos_ms - int(msg.get("latency") or 0)
                end = max(0, closed_at - MIN_SILENCE_MS)
                if not text:
                    continue
                self._index += 1
                await self.out.put(Segment(
                    channel=self.channel, text=text, start_ms=max(0, end - dur), end_ms=end,
                    lang=msg.get("detected_language_code"), latency_ms=msg.get("latency"), index=self._index,
                ))
            elif kind == "error":
                self.errors.append(str(msg.get("message")))


def load_channels(wav_path: Path) -> dict[str, bytes]:
    chans, sr = read_wav(wav_path)
    if len(chans) != 2:
        raise ValueError(f"{wav_path}: need a dual-channel recording (L = agent, R = borrower)")
    return {name: float_to_pcm16(resample(x, sr, SR)).tobytes() for name, x in zip(CHANNELS, chans)}


async def stream_call(wav_path: Path, meta: CallMeta, *, pace: float = 1.0,
                      model: str | None = None) -> AsyncIterator[tuple[Segment, int]]:
    """Yields (segment, clock_ms) as Prisma commits them; clock_ms is the call clock at arrival."""
    pcm = load_channels(wav_path)
    q: asyncio.Queue = asyncio.Queue()
    streams = [ChannelStream(ch, pcm[ch], headers_for(meta, ch, model), q, pace) for ch in CHANNELS]
    tasks = [asyncio.create_task(s.run()) for s in streams]

    async def supervise() -> None:
        try:
            await asyncio.gather(*tasks)
        finally:
            await q.put(None)  # both channels finished (or one failed): end the stream

    sup = asyncio.create_task(supervise())
    try:
        while (seg := await q.get()) is not None:
            yield seg, max(s.pos_ms for s in streams)
        await sup  # surfaces a handshake failure such as a bad API key
    finally:
        for t in (*tasks, sup):
            t.cancel()
        await asyncio.gather(*tasks, sup, return_exceptions=True)
        errs = [f"{s.channel}: {e}" for s in streams for e in s.errors]
        if errs:
            print(f"[stt] {meta.call_id}: " + "; ".join(errs[:6]), flush=True)


def segment_to_dict(seg: Segment, clock_ms: int) -> dict:
    return {"channel": seg.channel, "text": seg.text, "start_ms": seg.start_ms, "end_ms": seg.end_ms,
            "lang": seg.lang, "latency_ms": seg.latency_ms, "index": seg.index, "clock_ms": clock_ms}


def segment_from_dict(d: dict) -> tuple[Segment, int]:
    d = dict(d)
    clock = d.pop("clock_ms")
    return Segment(**d), clock


__all__ = ["stream_call", "headers_for", "segment_to_dict", "segment_from_dict", "AGENT", "BORROWER"]
