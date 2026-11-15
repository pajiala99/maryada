"""Offline stand-in for Prisma, for development and tests only (MARYADA_MOCK=1).

It replays the script as if it had been transcribed, dropping and garbling words
at a rate that grows with the noise level. It reads the ground truth, so nothing
produced in mock mode is a result: the bench labels such runs "mock" and the
evaluator refuses to mix them with real ones.
"""
from __future__ import annotations

import asyncio
import random
from typing import AsyncIterator

from ..common import config
from ..common.schema import CallMeta, CallTruth, Segment

WORD_LOSS = {"clean": 0.02, "snr20": 0.05, "snr10": 0.12, "snr5": 0.22, "snr0": 0.40}


def _garble(text: str, p: float, rng: random.Random) -> str:
    words = text.replace("₹", "").split()
    kept = [w for w in words if rng.random() > p]
    return " ".join(kept)


async def stream_call(variant: str, meta: CallMeta, *, pace: float = 1.0) -> AsyncIterator[tuple[Segment, int]]:
    truth = CallTruth.load(config.CALLS_DIR / f"{meta.call_id}.truth.json")
    rng = random.Random(f"{meta.call_id}-{variant}")
    p = WORD_LOSS.get(variant, 0.1)
    clock, counts = 0, {}
    for turn in truth.turns:
        arrive = turn.end_ms + 900  # VAD hang-over plus transcription
        if pace < 50:
            await asyncio.sleep(max(0, arrive - clock) / 1000 / pace)
        clock = arrive
        text = _garble(turn.ref, p, rng)
        if not text:
            continue
        counts[turn.speaker] = counts.get(turn.speaker, 0) + 1
        yield Segment(turn.speaker, text, turn.start_ms, turn.end_ms, None, 400, counts[turn.speaker]), clock
