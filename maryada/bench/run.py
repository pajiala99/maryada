"""Run the monitor over the whole bench.

    python -m maryada.bench.run                                   # every variant, default judge
    python -m maryada.bench.run --variants clean snr10 --judges llm lexicon --parallel 2

Speech-to-text is the slow, paid, real-time part, so it happens once per
(call, variant) and the transcript is saved under out/stt/. Every judge is then
run on the same saved transcript, which is what makes "keyword baseline vs LLM"
a fair comparison. Finished work is skipped, so the run can be stopped and resumed.
"""
from __future__ import annotations

import argparse
import asyncio
import time

import os

os.environ.setdefault("LLM_MAX_WAIT_S", "90")  # batch runs can wait out per-minute limits
# The published benchmark was judged without masking; keep reruns identical (and cached) unless asked.
os.environ.setdefault("LLM_REDACT", "0")

from ..common import config
from ..engine.monitor import events_path, run_call, segments_path
from .voice import call_ids


async def main(ids: list[str], variants: list[str], judges: list[str], parallel: int, pace: float, force: bool) -> None:
    live_slots = asyncio.Semaphore(parallel)
    judge_slots = asyncio.Semaphore(6)
    t0 = time.monotonic()
    done = 0

    async def one(cid: str, variant: str) -> None:
        nonlocal done
        for judge in judges:
            if events_path(judge, variant, cid).exists() and not force:
                continue
            recorded = segments_path(variant, cid).exists()
            async with (judge_slots if recorded else live_slots):
                try:
                    s = await run_call(cid, variant, judge=judge, pace=pace, recorded=recorded)
                except Exception as e:
                    print(f"  FAILED {variant}/{cid} [{judge}]: {type(e).__name__}: {e}", flush=True)
                    continue
            done += 1
            verdict = "compliant" if s["compliant"] else ",".join(s["violations"])
            print(f"  {variant:6s} {cid} [{judge:7s}] {'saved' if recorded else 'live '}  {verdict}"
                  f"   ({time.monotonic() - t0:.0f}s elapsed)", flush=True)

    todo = [(c, v) for v in variants for c in ids]
    print(f"{len(ids)} calls × {len(variants)} variants × {len(judges)} judges; {parallel} live calls at a time", flush=True)
    await asyncio.gather(*(one(c, v) for c, v in todo))
    print(f"finished {done} runs in {time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--variants", nargs="*", default=list(config.VARIANTS))
    # Keyword judge first: it runs live with the stream and saves the transcript. The LLM judge then
    # re-reads the saved transcript, so a rate-limited LLM never holds a streaming session open.
    ap.add_argument("--judges", nargs="*", default=["lexicon", "llm"] if config.LLM_ENABLED else ["lexicon"])
    ap.add_argument("--parallel", type=int, default=max(1, config.MAX_STT_SESSIONS // 2))
    ap.add_argument("--pace", type=float, default=1.0, help="1.0 = real time, as a live call would arrive")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.ids or call_ids(), a.variants, a.judges, a.parallel, a.pace, a.force))
