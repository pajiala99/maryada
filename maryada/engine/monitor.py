"""The compliance monitor: one call in, a stream of events out.

    python -m maryada.engine.monitor C30 --variant snr10            # live, real time
    python -m maryada.engine.monitor C30 --variant snr10 --recorded # re-judge saved transcripts

It reads calls/<id>.meta.json (what the dialer knows) and the dual-channel
audio. It never opens the .truth.json file.

Events (one JSON object per line in out/events/<judge>/<variant>/<id>.events.jsonl):
  call_start  the call's metadata
  segment     one Prisma utterance: channel, text, start_ms, end_ms, lang
  alert       a rule breach: type, clause, evidence, ms (where in the call), source
  info        non-violations worth recording, e.g. the borrower's preferred calling time
  nudge       the whisper sent to the agent
  summary     verdict for the call
`clock_ms` on every event is the call clock when the event was emitted, which is
what makes a saved run replayable in sync with the audio.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import AsyncIterator, Callable

from ..common import config
from ..common.schema import AGENT, BORROWER, VIOLATION_TYPES, Alert, CallMeta, Segment
from ..extras.audit_log import AuditLog
from . import mock, rules, stt_stream
from .classifier import LLMJudge

Emit = Callable[[dict], None]
CONTEXT_LINES = 10
REPEAT_GAP_MS = 8000
TURN_GAP_MS = 1500


def stt_label() -> str:
    return "mock" if os.environ.get("MARYADA_MOCK") == "1" else config.STT_MODEL


def segments_path(variant: str, call_id: str, model: str | None = None) -> Path:
    return config.OUT_DIR / "stt" / (model or stt_label()) / variant / f"{call_id}.segments.jsonl"


def events_path(judge: str, variant: str, call_id: str, model: str | None = None) -> Path:
    return config.OUT_DIR / "events" / (model or stt_label()) / judge / variant / f"{call_id}.events.jsonl"


class Monitor:
    def __init__(self, meta: CallMeta, *, judge: str = "auto", emit: Emit | None = None, nudges: bool = False,
                 live: bool = True, policy: dict | None = None):
        self.live = live
        self.policy = policy or {}  # a lender's settings: calling_window ["HH:MM","HH:MM"], recording_grace_s
        if judge == "auto":
            judge = "llm" if config.LLM_ENABLED else "lexicon"
        if judge == "llm" and not config.LLM_ENABLED:
            raise SystemExit("judge=llm needs LLM_BASE_URL and LLM_MODEL in .env")
        self.meta, self.judge, self.nudges = meta, judge, nudges
        self._emit = emit or (lambda e: None)
        self.disclosure = rules.DisclosureTracker(deadline_ms=int(1000 * self.policy.get("recording_grace_s", 20)))
        self.dues = rules.DuesChecker(meta)
        self.lexicon = rules.LexiconJudge()
        self.llm = LLMJudge(meta) if judge == "llm" else None
        self.transcript: list[str] = []
        self.turn: list = []  # agent segments waiting to be judged together
        self._turn_timer: asyncio.Task | None = None
        self.turn_context: list[str] = []
        self.alerts: list[Alert] = []
        self.pending: set[asyncio.Task] = set()
        self.preferred_time: str | None = None
        self.clock = 0
        self.segments = 0
        self.latencies: list[int] = []
        self._last: dict[str, int] = {}

    # ---------------------------------------------------------------- output
    def emit(self, event: dict, clock_ms: int | None = None) -> None:
        event["clock_ms"] = self.clock if clock_ms is None else clock_ms
        self._emit(event)

    def raise_alert(self, alert: Alert, clock_ms: int | None = None) -> None:
        last = self._last.get(alert.type)
        if last is not None and alert.at_ms - last < REPEAT_GAP_MS:
            return  # same breach, still in progress
        self._last[alert.type] = alert.at_ms
        self.alerts.append(alert)
        ev = alert.to_event()
        ev["ms"] = ev.pop("at_ms")
        self.emit(ev, clock_ms)
        if self.nudges:
            self._spawn(self._nudge(alert.type))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    async def _nudge(self, violation: str) -> None:
        from ..extras import nudge
        try:
            text, path = await asyncio.to_thread(nudge.render, violation, self.meta)
            self.emit({"t": "nudge", "type": violation, "text": text, "audio": path.name})
        except Exception as e:  # a nudge must never take the monitor down
            self.emit({"t": "info", "kind": "NUDGE_FAILED", "detail": str(e)[:160]})

    # ----------------------------------------------------------------- input
    def start(self) -> None:
        m = self.meta
        self.emit({"t": "call_start", "call_id": m.call_id, "call_time": m.call_time, "language": m.language,
                   "lender": m.lender, "judge": self.judge, "stt": stt_label(),
                   **({"llm_redaction": True} if self.llm and self.llm.redactor else {}),
                   **({"policy": self.policy} if self.policy else {})})
        window = self.policy.get("calling_window") or [rules.OPEN, rules.CLOSE]
        if alert := rules.check_hours(m, window[0], window[1]):
            self.raise_alert(alert)

    async def on_segment(self, seg: Segment, clock_ms: int) -> None:
        self.clock = max(self.clock, clock_ms)
        self.segments += 1
        if seg.latency_ms:
            self.latencies.append(int(seg.latency_ms))
        self.emit({"t": "segment", "channel": seg.channel, "text": seg.text, "start_ms": seg.start_ms,
                   "end_ms": seg.end_ms, "lang": seg.lang, "latency_ms": seg.latency_ms, "index": seg.index})
        # Prisma returns one segment per pause, so an agent's turn often arrives as two or three
        # segments. The LLM judges the turn as a whole: it is flushed when the borrower speaks,
        # when the agent pauses for more than TURN_GAP_MS, or when the call ends.
        if self.turn and (seg.channel == BORROWER or seg.start_ms - self.turn[-1][0].end_ms > TURN_GAP_MS):
            self._flush_turn()
        if not self.turn:
            self.turn_context = self.transcript[-CONTEXT_LINES:]
        self.transcript.append(f"{seg.channel.upper()}: {seg.text}")

        amounts, dues_alert = self.dues.on_segment(seg)
        if dues_alert:
            self.raise_alert(dues_alert)
        lex_alerts = self.lexicon.on_segment(seg)

        if seg.channel == BORROWER:
            if t := rules.preferred_time(seg.text):
                self._note_preference(t, "rule")
            return

        if self.llm:
            self.turn.append((seg, lex_alerts, bool(amounts)))
            if self.live:  # judge the turn as soon as the agent pauses, even if nobody else speaks
                if self._turn_timer:
                    self._turn_timer.cancel()
                self._turn_timer = asyncio.create_task(self._flush_after_pause(len(self.turn)))
        else:
            for a in lex_alerts:
                self.raise_alert(a)

        if self.disclosure.on_segment(seg):
            # Deadline reached with no keyword match. Let the LLM's reading of the opening lines
            # settle it first: it catches paraphrases ("yeh baat-cheet save ho rahi hai").
            self._flush_turn()
            if self.pending:
                await asyncio.gather(*self.pending, return_exceptions=True)
            if not self.disclosure.disclosed:
                self.raise_alert(self.disclosure.alert(seg.end_ms))

    async def _flush_after_pause(self, size: int) -> None:
        await asyncio.sleep(TURN_GAP_MS / 1000)
        if len(self.turn) == size:  # no new agent segment arrived meanwhile
            self._flush_turn()

    def _flush_turn(self) -> None:
        if self.turn:
            self._spawn(self._judge(self.turn, self.turn_context))
            self.turn = []

    async def _judge(self, turn: list, context: list[str]) -> None:
        segs = [s for s, _, _ in turn]
        lex_alerts = [a for _, alerts, _ in turn for a in alerts]
        heard_amounts = any(h for _, _, h in turn)
        seg = segs[-1]
        t0 = time.monotonic()
        verdict = await self.llm.judge(context, " ".join(s.text for s in segs))
        waited = int((time.monotonic() - t0) * 1000)
        # When re-judging saved transcripts the wait is mostly rate-limit queueing, not detection
        # time, so it must not be written into the call clock.
        clock = max(self.clock if self.live else 0, seg.end_ms) + (waited if self.live else min(waited, 2000))
        if verdict and verdict["evidence"]:  # point the alert at the segment the quoted words came from
            seg = next((s for s in segs if verdict["evidence"][:25] in s.text), seg)
        if verdict is None:  # LLM unavailable for this utterance: keyword baseline stands in
            for a in lex_alerts:
                self.raise_alert(a, clock)
            return
        if verdict["recording_disclosed"]:
            self.disclosure.disclosed = True
        if verdict["borrower_preferred_time"]:
            self._note_preference(verdict["borrower_preferred_time"], "llm")
        ev = verdict["evidence"] or seg.text[:120]
        for key, vtype in (("threat_or_abuse", "THREAT_OR_ABUSE"), ("third_party", "THIRD_PARTY"),
                           ("ignored_sensitive", "IGNORED_SENSITIVE_SITUATION")):
            if verdict[key]:
                self.raise_alert(Alert(vtype, seg.end_ms, ev, "llm", 0.85, seg.index), clock)
        # Digits are checked exactly by the rule. The LLM only covers amounts that came through as words.
        if verdict["wrong_dues"] and not heard_amounts and "WRONG_DUES" not in self._last:
            self.raise_alert(Alert("WRONG_DUES", seg.end_ms, ev, "llm", 0.7, seg.index), clock)

    def _note_preference(self, hhmm: str, source: str) -> None:
        if self.preferred_time:
            return
        self.preferred_time = hhmm
        self.emit({"t": "info", "kind": "PREFERRED_TIME", "time": hhmm, "source": source,
                   "detail": f"Borrower asked to be called after {hhmm}; store as consent for future calls"})

    async def finish(self) -> dict:
        if self._turn_timer:
            self._turn_timer.cancel()
        self._flush_turn()
        while self.pending:
            await asyncio.gather(*list(self.pending), return_exceptions=True)
        if self.disclosure.pending_at_end():
            self.raise_alert(self.disclosure.alert(self.clock))
        found = sorted({a.type for a in self.alerts}, key=VIOLATION_TYPES.index)
        summary = {
            "t": "summary", "call_id": self.meta.call_id, "compliant": not found, "violations": found,
            "alerts": len(self.alerts), "preferred_time": self.preferred_time, "segments": self.segments,
            "stt_latency_ms": round(sum(self.latencies) / len(self.latencies)) if self.latencies else None,
            "judge": self.judge, "stt": stt_label(),
            "llm_calls": self.llm.calls if self.llm else 0, "llm_failures": self.llm.failures if self.llm else 0,
        }
        if self.llm and self.llm.redactor:  # recorded in the evidence log: what was masked before the LLM saw it
            summary["redacted"] = self.llm.redactor.summary()
        self.emit(summary)
        if self.llm:
            await self.llm.close()
        return summary


# ------------------------------------------------------------------ drivers
async def _source(call_id: str, variant: str, meta: CallMeta, pace: float, recorded: bool,
                  out_dir: Path | None = None) -> AsyncIterator[tuple[Segment, int]]:
    path = out_dir / f"{call_id}.segments.jsonl" if out_dir and not recorded else segments_path(variant, call_id)
    if recorded:
        for line in path.read_text().splitlines():
            yield stt_stream.segment_from_dict(json.loads(line))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    live = (mock.stream_call(variant, meta, pace=pace) if stt_label() == "mock"
            else stt_stream.stream_call(config.CALLS_DIR / variant / f"{call_id}.wav", meta, pace=pace))
    tmp = path.with_suffix(".partial")
    with tmp.open("w") as f:
        async for seg, clock in live:
            f.write(json.dumps(stt_stream.segment_to_dict(seg, clock), ensure_ascii=False) + "\n")
            f.flush()
            yield seg, clock
    tmp.replace(path)  # only complete transcripts are kept for re-judging


async def run_call(call_id: str, variant: str = "clean", *, judge: str = "auto", pace: float = 1.0,
                   recorded: bool = False, on_event: Emit | None = None, nudges: bool = False,
                   policy: dict | None = None, out_dir: Path | None = None) -> dict:
    """Monitor one call. recorded=True re-judges a saved transcript without touching the STT API.
    out_dir keeps a live or API session apart from the benchmark's saved runs (which it must never overwrite)."""
    meta = CallMeta.load(config.CALLS_DIR / f"{call_id}.meta.json")
    resolved = ("llm" if config.LLM_ENABLED else "lexicon") if judge == "auto" else judge
    out = out_dir / f"{call_id}.events.jsonl" if out_dir else events_path(resolved, variant, call_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(out.with_name(f"{call_id}.audit.jsonl"))
    tmp = out.with_suffix(".partial")
    with tmp.open("w") as f:
        def emit(event: dict) -> None:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            if event["t"] in ("call_start", "alert", "segment", "summary"):
                audit.append(event)
            if on_event:
                on_event(event)

        mon = Monitor(meta, judge=resolved, emit=emit, nudges=nudges, live=not recorded, policy=policy)
        mon.start()
        async for seg, clock in _source(call_id, variant, meta, pace, recorded, out_dir):
            await mon.on_segment(seg, clock)
        summary = await mon.finish()
    tmp.replace(out)
    return summary


def _print(event: dict) -> None:
    t, clock = event["t"], event["clock_ms"] / 1000
    if t == "segment":
        print(f"{clock:6.1f}s  {event['channel'][:1].upper()}  {event['text']}")
    elif t == "alert":
        print(f"{clock:6.1f}s  !! {event['type']}  [{event['source']}]  {event['evidence']}")
    elif t == "info":
        print(f"{clock:6.1f}s  -- {event.get('kind')}: {event.get('detail')}")
    elif t == "nudge":
        print(f"{clock:6.1f}s  >> whisper to agent: {event['text']}")
    elif t == "summary":
        print(f"\n{'COMPLIANT' if event['compliant'] else 'VIOLATIONS: ' + ', '.join(event['violations'])}"
              f"   ({event['segments']} segments, judge={event['judge']}, stt={event['stt']})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("call_id")
    ap.add_argument("--variant", default="clean", choices=list(config.VARIANTS))
    ap.add_argument("--judge", default="auto", choices=["auto", "llm", "lexicon"])
    ap.add_argument("--pace", type=float, default=1.0)
    ap.add_argument("--recorded", action="store_true")
    ap.add_argument("--nudges", action="store_true")
    a = ap.parse_args()
    asyncio.run(run_call(a.call_id, a.variant, judge=a.judge, pace=a.pace, recorded=a.recorded,
                         on_event=_print, nudges=a.nudges))
