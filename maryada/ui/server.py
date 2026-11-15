"""Dashboard backend.

    .venv/bin/uvicorn maryada.ui.server:app --port 8770

  GET  /                          the dashboard
  GET  /api/calls                 calls, metadata, answer key (with where each breach was planted), saved runs
  GET  /api/run/{variant}/{id}    a saved run, ready to replay in step with the audio (?judge=llm|lexicon|auto)
  GET  /api/matrix                every call x noise level x judge: planted vs detected (the results grid)
  GET  /api/audit/{variant}/{id}  verify the hash-chained evidence log of a saved run
  GET  /api/results               the benchmark (results/results.json)
  GET  /audio/{variant}/{id}      the dual-channel recording
  GET  /nudges/{name}             a rendered whisper
  WS   /ws/monitor                ?call=C30&variant=snr10&judge=auto: streams the call to Prisma live and
                                  pushes events as they happen
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .. import gateway
from ..common import config
from ..common.schema import VIOLATIONS, CallMeta, CallTruth
from ..engine.monitor import run_call, stt_label
from ..extras import audit_log

app = FastAPI(
    title="Maryada API",
    version="1.0.0-test",
    description="Audit loan-recovery calls against the RBI's recovery-conduct directions. Test mode: every call is synthetic. "
                "Authenticate with  Authorization: Bearer mk_test_...  (create a key on the dashboard's Developers page). "
                "Webhooks are signed: Maryada-Signature: t=<unix>,v1=HMAC-SHA256(secret, '<t>.<raw body>').",
)
app.include_router(gateway.api)
app.include_router(gateway.console)
app.include_router(gateway.receiver)
app.middleware("http")(gateway.request_ids)


@app.exception_handler(HTTPException)
async def _errors(request, exc):  # the platform routes answer {"error": {...}, "request_id": ...}; /api keeps FastAPI's shape
    if request.url.path.startswith(("/v1/", "/api/platform/")):
        return await gateway.error_body(request, exc)
    return await http_exception_handler(request, exc)
STATIC = Path(__file__).parent / "static"
_live_lock = asyncio.Lock()
CALL_LEVEL = {"OUTSIDE_HOURS", "NO_RECORDING_DISCLOSURE"}
LIVE_DIR = config.OUT_DIR / "live"  # live sessions from the dashboard; never the benchmark's files  # breaches of the whole call, not one turn


def _replays(call_id: str) -> dict[str, list[dict]]:
    """variant -> saved runs, real speech models first, LLM judge first."""
    out: dict[str, list[dict]] = {}
    for p in (config.OUT_DIR / "events").glob(f"*/*/*/{call_id}.events.jsonl"):
        stt, judge, variant = p.parts[-4], p.parts[-3], p.parts[-2]
        out.setdefault(variant, []).append({"stt": stt, "judge": judge})
    for runs in out.values():  # the configured speech model first, then other real models, mock last
        runs.sort(key=lambda r: (r["stt"] == "mock", r["stt"] != config.STT_MODEL, r["judge"] != "llm"))
    return out


def _pick(call_id: str, variant: str, judge: str) -> Path | None:
    runs = _replays(call_id).get(variant, [])
    pick = next((r for r in runs if judge in ("auto", r["judge"])), None)
    if not pick:
        return None
    return config.OUT_DIR / "events" / pick["stt"] / pick["judge"] / variant / f"{call_id}.events.jsonl"


def _valid(call_id: str, variant: str) -> None:
    if variant not in config.VARIANTS or not (config.CALLS_DIR / f"{call_id}.meta.json").exists():
        raise HTTPException(404, "Unknown call or noise level")


LANDING = Path(__file__).parent / "landing"
IMAGES = STATIC / "images"


@app.get("/", include_in_schema=False)
def landing() -> FileResponse:
    return FileResponse(LANDING / "index.html")


@app.get("/app", include_in_schema=False)
def app_noslash() -> RedirectResponse:
    return RedirectResponse("/app/")


@app.get("/app/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/images/{name}", include_in_schema=False)
@app.get("/app/images/{name}", include_in_schema=False)
def image(name: str) -> FileResponse:
    p = IMAGES / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/api/calls")
def calls() -> JSONResponse:
    rows = []
    for p in sorted(config.CALLS_DIR.glob("C*.meta.json")):
        meta = CallMeta.load(p)
        truth = CallTruth.load(p.with_name(f"{meta.call_id}.truth.json"))
        spans = []
        for v in truth.violations:
            t = truth.turns[v["turn_index"]]
            spans.append({"type": v["type"], "start_ms": 0 if v["type"] in CALL_LEVEL else t.start_ms,
                          "end_ms": 0 if v["type"] in CALL_LEVEL else t.end_ms})
        rows.append({
            **asdict(meta), "scenario": truth.scenario, "planted": sorted(truth.violation_types()), "planted_spans": spans,
            "duration_ms": truth.turns[-1].end_ms + 1500 if truth.turns else 0,
            "variants": [v for v in config.VARIANTS if (config.CALLS_DIR / v / f"{meta.call_id}.wav").exists()],
            "replays": _replays(meta.call_id),
        })
    return JSONResponse({"calls": rows, "violations": VIOLATIONS, "variants": config.VARIANTS,
                         "live": {"stt": stt_label(), "gnani_key": bool(config.GNANI_API_KEY),
                                  "judge": "llm" if config.LLM_ENABLED else "lexicon", "llm_model": config.LLM_MODEL}})


def replay_events(call_id: str, variant: str, judge: str = "auto") -> list[dict] | None:
    """A saved run, re-timed for playback against the audio."""
    path = _pick(call_id, variant, judge)
    if not path:
        return None
    events = [json.loads(line) for line in path.read_text().splitlines()]
    end = max((e["clock_ms"] for e in events if e["t"] == "segment"), default=0)
    seg_clock = {(e["channel"], e["index"]): e["clock_ms"] for e in events if e["t"] == "segment"}
    for e in events:
        if e["t"] == "alert":  # runs judged offline may carry queueing time: show the alert when it was heard
            e["clock_ms"] = min(e["clock_ms"], e["ms"] + 2500)
            if e.get("segment_index") is not None:  # never before the line it points at has appeared
                e["clock_ms"] = max(e["clock_ms"], seg_clock.get(("agent", e["segment_index"]), 0) + 300)
        elif e["t"] == "summary":
            e["clock_ms"] = end + 1200
    if not any(e["t"] == "nudge" for e in events):
        # Bench runs were not live, so they recorded no whispers. Show the one the live system sends
        # for each alert, from the cached Timbre audio (replay never calls the API).
        from ..extras import nudge
        meta = CallMeta.load(config.CALLS_DIR / f"{call_id}.meta.json")
        lang = nudge.nudge_lang(meta)
        for a in [e for e in events if e["t"] == "alert"]:
            amount = meta.loan.total_due if a["type"] == "WRONG_DUES" else 0
            wav = config.NUDGE_DIR / f"{a['type']}_{lang}_{amount}.wav"
            if wav.exists():
                events.append({"t": "nudge", "type": a["type"], "audio": wav.name, "clock_ms": a["clock_ms"] + 900,
                               "text": nudge.nudge_text(a["type"], meta).replace("<whispers> ", "")})
    events.sort(key=lambda e: e["clock_ms"])
    return events


@app.get("/api/run/{variant}/{call_id}")
def run(variant: str, call_id: str, judge: str = "auto") -> JSONResponse:
    _valid(call_id, variant)
    events = replay_events(call_id, variant, judge)
    if events is None:
        raise HTTPException(404, "No saved run for this call, noise level and judge. Run it live first.")
    return JSONResponse({"events": events, "path": str(_pick(call_id, variant, judge).relative_to(config.ROOT))})


@app.get("/api/audit/{variant}/{call_id}")
def audit(variant: str, call_id: str, judge: str = "auto", live: int = 0) -> JSONResponse:
    _valid(call_id, variant)
    if live:  # the dashboard's own live session, kept apart from the benchmark runs
        log = LIVE_DIR / variant / f"{call_id}.audit.jsonl"
    else:
        path = _pick(call_id, variant, judge)
        log = path.with_name(f"{call_id}.audit.jsonl") if path else None
    if not log or not log.exists():
        return JSONResponse({"ok": None, "message": "no audit log for this run"})
    ok, n, msg = audit_log.verify(log)
    return JSONResponse({"ok": ok, "records": n, "message": msg})


@app.get("/api/matrix")
def matrix() -> JSONResponse:
    """For the results grid: what each judge flagged on each call at each noise level."""
    out: dict[str, dict[str, dict[str, list[str]]]] = {}
    root = config.OUT_DIR / "events"
    for stt_dir in [root / config.STT_MODEL]:  # the grid shows the model the dashboard monitors with
        for judge_dir in sorted(p for p in stt_dir.glob("*") if p.is_dir()):
            for variant in config.VARIANTS:
                for f in sorted((judge_dir / variant).glob("C*.events.jsonl")):
                    found = sorted({json.loads(l)["type"] for l in f.read_text().splitlines() if '"t": "alert"' in l})
                    out.setdefault(judge_dir.name, {}).setdefault(variant, {})[f.name.split(".")[0]] = found
    return JSONResponse(out)


@app.get("/api/results")
def results() -> JSONResponse:
    p = config.RESULTS_DIR / "results.json"
    return JSONResponse(json.loads(p.read_text()) if p.exists() else {"runs": []})


@app.get("/audio/{variant}/{call_id}")
def audio(variant: str, call_id: str) -> FileResponse:
    p = config.CALLS_DIR / variant / f"{call_id.removesuffix('.wav')}.wav"
    if variant not in config.VARIANTS or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/wav")


@app.get("/nudges/{name}")
def nudge_audio(name: str) -> FileResponse:
    p = config.NUDGE_DIR / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/wav")


async def _live(ws: WebSocket, call_id: str, variant: str, judge: str) -> None:
    if _live_lock.locked():
        await ws.send_json({"t": "error", "message": "Another live call is being monitored. Wait for it to finish."})
        return
    async with _live_lock:
        q: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(run_call(call_id, variant, judge=judge, on_event=q.put_nowait, out_dir=LIVE_DIR / variant,
                                            nudges=bool(config.GNANI_API_KEY) and stt_label() != "mock"))
        try:
            while True:
                getter = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    await ws.send_json(getter.result())
                    continue
                getter.cancel()
                while not q.empty():
                    await ws.send_json(q.get_nowait())
                task.result()  # re-raise a failure such as a rejected API key
                break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@app.websocket("/ws/mic")
async def mic(ws: WebSocket, call: str) -> None:
    """Speak as the agent: the browser streams 16 kHz PCM16 mono from the microphone, we forward it to
    Prisma v3.0 in 1,024-byte frames and run the same monitor on what comes back. The selected call
    supplies the borrower's name and loan record; the call time is now."""
    await ws.accept()
    if not config.GNANI_API_KEY or not (config.CALLS_DIR / f"{call}.meta.json").exists():
        await ws.send_json({"t": "error", "message": "Mic mode needs a Gnani API key and a known call."})
        await ws.close()
        return
    if _live_lock.locked():
        await ws.send_json({"t": "error", "message": "Another live session is running. Wait for it to finish."})
        await ws.close()
        return
    from websockets.asyncio.client import connect as ws_connect

    from ..common.schema import AGENT, Segment
    from ..engine import stt_stream
    from ..engine.monitor import Monitor

    meta = CallMeta.load(config.CALLS_DIR / f"{call}.meta.json")
    meta.call_time = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
    headers = stt_stream.headers_for(meta, AGENT)
    headers["x-sample-rate"] = "16000"
    headers["x-max-speech-s"] = "12"
    loop = asyncio.get_running_loop()
    out: asyncio.Queue = asyncio.Queue()
    t0 = loop.time()
    clock = lambda: int((loop.time() - t0) * 1000)  # noqa: E731

    async def sender() -> None:
        while (e := await out.get()) is not None:
            await ws.send_json(e)

    async with _live_lock:
        send_task = asyncio.create_task(sender())
        mon = Monitor(meta, judge="auto", emit=out.put_nowait, nudges=True)
        try:
            async with ws_connect(config.STT_WS_URL, additional_headers=headers, open_timeout=20, max_size=None) as prisma:
                mon.start()
                await ws.send_json({"t": "mic_ready", "call_time": meta.call_time})

                async def from_browser() -> None:
                    buf = b""
                    while True:
                        msg = await ws.receive()
                        if msg["type"] == "websocket.disconnect" or msg.get("text") == "stop":
                            break
                        if msg.get("bytes"):
                            buf += msg["bytes"]
                            while len(buf) >= stt_stream.FRAME_BYTES:
                                await prisma.send(buf[:stt_stream.FRAME_BYTES])
                                buf = buf[stt_stream.FRAME_BYTES:]
                    for _ in range(50):  # 1.6 s of silence so the last sentence closes
                        await prisma.send(bytes(stt_stream.FRAME_BYTES))
                    await prisma.send(json.dumps({"type": "commit"}))

                async def from_prisma() -> None:
                    index = 0
                    async for raw in prisma:
                        if isinstance(raw, bytes):
                            continue
                        m = json.loads(raw)
                        if m.get("type") == "transcript" and (text := (m.get("text") or "").strip()):
                            index += 1
                            end = max(0, clock() - int(m.get("latency") or 0) - stt_stream.MIN_SILENCE_MS)
                            dur = int(float(m.get("audio_duration_ms") or 0))
                            await mon.on_segment(Segment(AGENT, text, max(0, end - dur), end, m.get("detected_language_code"),
                                                         m.get("latency"), index), clock())
                        elif m.get("type") == "error":
                            out.put_nowait({"t": "error", "message": f"Prisma: {m.get('message')}"[:200], "clock_ms": clock()})

                reader = asyncio.create_task(from_prisma())
                await from_browser()
                try:
                    await asyncio.wait_for(asyncio.shield(reader), timeout=4)
                except asyncio.TimeoutError:
                    pass
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
            await mon.finish()
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            out.put_nowait({"t": "error", "message": f"{type(e).__name__}: {e}"[:200], "clock_ms": clock()})
        finally:
            out.put_nowait(None)
            await asyncio.gather(send_task, return_exceptions=True)
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass


@app.websocket("/ws/monitor")
async def monitor(ws: WebSocket, call: str, variant: str = "clean", judge: str = "auto") -> None:
    await ws.accept()
    try:
        if variant not in config.VARIANTS or not (config.CALLS_DIR / f"{call}.meta.json").exists():
            await ws.send_json({"t": "error", "message": "Unknown call or noise level."})
        else:
            await _live(ws, call, variant, judge)
    except WebSocketDisconnect:
        return
    except (Exception, SystemExit) as e:
        await ws.send_json({"t": "error", "message": f"{type(e).__name__}: {e}"[:300]})
    await ws.close()
