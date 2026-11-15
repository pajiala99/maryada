"""Voice every turn of every script with Timbre v3.0.

    python -m maryada.bench.voice [--ids C01 C02]

Each turn is one Timbre request (two distinct voices per call, audio tags
inline). Audio comes back as G.711 mu-law at 8 kHz and is cached, so this step
is paid for once.
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np

from ..common import config, timbre
from ..common.schema import CallMeta, CallTruth


def call_ids() -> list[str]:
    return sorted(p.name.split(".")[0] for p in config.CALLS_DIR.glob("C*.meta.json"))


def voice_call(call_id: str, client: httpx.Client | None = None) -> list[np.ndarray]:
    """Returns one float32 array per turn, in script order."""
    meta = CallMeta.load(config.CALLS_DIR / f"{call_id}.meta.json")
    truth = CallTruth.load(config.CALLS_DIR / f"{call_id}.truth.json")
    return [
        timbre.synthesize(t.text, truth.voices[t.speaker], meta.language, client=client)
        for t in truth.turns
    ]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--workers", type=int, default=3, help="concurrent Timbre requests (429s back off on their own)")
    a = ap.parse_args()
    ids = a.ids or call_ids()
    total, t0 = 0.0, time.monotonic()
    with httpx.Client(timeout=120) as client, ThreadPoolExecutor(a.workers) as pool:
        # A call finishes when its last turn does; calls are voiced `workers` at a time.
        for cid, clips in zip(ids, pool.map(lambda c: voice_call(c, client), ids)):
            secs = sum(len(c) for c in clips) / config.SAMPLE_RATE
            total += secs
            print(f"{cid}: {len(clips)} turns, {secs:.1f}s of speech  ({time.monotonic() - t0:.0f}s elapsed)", flush=True)
    print(f"voiced {len(ids)} calls, {total / 60:.1f} min of speech")
