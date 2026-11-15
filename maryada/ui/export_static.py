"""Export the dashboard as a static site for GitHub Pages: no server, no API keys.

    python -m maryada.ui.export_static            # writes site/

Everything the replay needs is pre-computed with the same functions the server uses: the calls,
every saved Prisma v3.0 run (re-timed, with whispers), each run's evidence-log check, the results
grid and the benchmark. Call audio is resampled to 16 kHz and stored as stereo MP3 so the
agent/borrower channel switch still works, at about a tenth of the WAV size. Live mode is
switched off: it needs the repo, a running server and API keys.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import lameenc
import numpy as np

from ..common import config
from ..common.audio import float_to_pcm16, read_wav, resample
from ..extras import audit_log
from . import server

SITE = config.ROOT / "site"
APP = SITE / "app"  # the product; the landing page is the site root
MP3_RATE = 16000


def _json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _mp3(channels: list[np.ndarray], sr: int, kbps: int) -> bytes:
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(MP3_RATE)
    enc.set_channels(len(channels))
    enc.set_quality(2)
    pcm = np.stack([float_to_pcm16(resample(c, sr, MP3_RATE)) for c in channels], axis=1)
    return enc.encode(pcm.astype("<i2").tobytes()) + enc.flush()


def export() -> dict:
    SITE.mkdir(exist_ok=True)
    for child in SITE.iterdir():  # start clean, but keep the gh-pages checkout's .git
        if child.name != ".git":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    stats = {"runs": 0, "audio_bytes": 0, "audio_files": 0}

    calls = json.loads(server.calls().body)
    calls["live"]["gnani_key"] = False  # no live streaming from a static page
    for c in calls["calls"]:  # only the model the dashboard monitors with
        c["replays"] = {v: [r for r in runs if r["stt"] == config.STT_MODEL] for v, runs in c["replays"].items()}
    _json(APP / "data" / "calls.json", calls)
    _json(APP / "data" / "matrix.json", json.loads(server.matrix().body))
    _json(APP / "data" / "results.json", json.loads(server.results().body))
    # A snapshot of the integration layer (API keys, webhook events, cases, policies) from a local run.
    # It carries no secrets: keys and endpoints appear only by prefix, as on the dashboard.
    from .. import gateway
    _json(APP / "data" / "platform.json", gateway.c_state())

    for c in calls["calls"]:
        cid = c["call_id"]
        for variant, runs in c["replays"].items():
            for judge in sorted({r["judge"] for r in runs}):
                events = server.replay_events(cid, variant, judge)
                if events is None:
                    continue
                _json(APP / "data" / "run" / variant / f"{cid}-{judge}.json", {"events": events})
                log = server._pick(cid, variant, judge).with_name(f"{cid}.audit.jsonl")
                if log.exists():
                    ok, n, msg = audit_log.verify(log)
                    _json(APP / "data" / "audit" / variant / f"{cid}-{judge}.json", {"ok": ok, "records": n, "message": msg})
                stats["runs"] += 1
        for variant in c["variants"]:
            chans, sr = read_wav(config.CALLS_DIR / variant / f"{cid}.wav")
            out = APP / "audio" / variant / f"{cid}.mp3"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_mp3(chans, sr, 40))
            stats["audio_bytes"] += out.stat().st_size
            stats["audio_files"] += 1

    for wav in sorted(config.NUDGE_DIR.glob("*.wav")):
        chans, sr = read_wav(wav)
        out = APP / "nudges" / f"{wav.stem}.mp3"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_mp3(chans[:1], sr, 32))

    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    meta = ('<meta name="description" content="Maryada audits every loan-recovery call against the RBI\'s conduct rules, live, on noisy '
            'phone audio in nine Indian languages. Built on Gnani Prisma v3.0 and Timbre v3.0.">\n'
            '<script>window.MARYADA_STATIC = true;</script>\n')
    html = html.replace("<title>", meta + "<title>", 1)
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "index.html").write_text(html, encoding="utf-8")
    landing = (Path(__file__).parent / "landing" / "index.html").read_text(encoding="utf-8")
    (SITE / "index.html").write_text(landing.replace("<title>", '<script>window.MARYADA_STATIC = true;</script>\n<title>', 1), encoding="utf-8")
    for dest in (SITE / "images", APP / "images"):  # both pages use relative image paths
        shutil.copytree(Path(__file__).parent / "static" / "images", dest, dirs_exist_ok=True)
    (SITE / ".nojekyll").write_text("")
    stats["site_mb"] = round(sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file() and ".git" not in p.parts) / 1e6, 1)
    return stats


if __name__ == "__main__":
    print(export())
