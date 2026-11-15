"""The integration layer a lender's systems talk to: API, webhooks, cases and policies.

    /v1/...              the API a dialer calls (test-mode keys, request IDs, OpenAPI docs at /docs)
    webhooks             signed alert.created, call.completed and case.updated events, with a delivery log
    cases                each flagged call becomes a case: status, assignee, notes, decisions, activity
    policies             per-lender calling window and recording-notice grace, with version history
    /api/platform/...    the dashboard's console for the same objects
    /demo/receiver/...   a webhook receiver inside this server that verifies signatures, for the demo

Everything is stored as JSON under out/platform/. There is no real login or multi-tenancy: this is a
test-mode layer over synthetic calls, and the dashboard says so. Webhook signatures are HMAC-SHA256 over
"<timestamp>.<raw body>" with the endpoint's secret, sent as  Maryada-Signature: t=<unix>,v1=<hex>.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .common import config
from .common.schema import VIOLATIONS, CallMeta
from .engine import rules
from .engine.redact import Redactor
from .extras import audit_log

DIR = config.OUT_DIR / "platform"
IST = timezone(timedelta(hours=5, minutes=30))
EVENT_TYPES = ["alert.created", "call.completed", "case.updated"]
CASE_STATUSES = ["open", "in_review", "confirmed", "dismissed"]
DEFAULT_POLICY = {"calling_window": [rules.OPEN, rules.CLOSE], "recording_grace_s": 20}
_lock = threading.Lock()


def now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


# ------------------------------------------------------------------ storage
# Six synthetic complaints, tied to real calls in the dataset: four whose call broke the rule alleged, one whose
# call is clean, and one with no call on record. The dashboard works the complaint; the server keeps it.
SEED_COMPLAINTS = [
    {"id": "CMP-0001", "borrower": "पूजा", "borrower_id": "B1030", "account": "LN71087484", "lender": "Udaan Capital", "received": "2026-11-11",
     "window": ["2026-11-09", "2026-11-11"], "channel": "Phone", "severity": "High", "rules": ["OUTSIDE_HOURS", "THREAT_OR_ABUSE", "WRONG_DUES"],
     "allegation": "The agent called after nine at night, quoted an amount she says she does not owe, and threatened her when she asked for time."},
    {"id": "CMP-0002", "borrower": "सुनीता", "borrower_id": "B1016", "account": "LN52050752", "lender": "Navjeevan Housing Finance", "received": "2026-11-12",
     "window": ["2026-11-10", "2026-11-12"], "channel": "Email", "severity": "Medium", "rules": ["WRONG_DUES"],
     "allegation": "She was told she owes far more than her statement shows, and that the full amount had to be paid that day."},
    {"id": "CMP-0003", "borrower": "नेहा", "borrower_id": "B1018", "account": "LN94976654", "lender": "Navjeevan Housing Finance", "received": "2026-11-14",
     "window": ["2026-11-12", "2026-11-14"], "channel": "Regulator referral", "severity": "High", "rules": ["THIRD_PARTY"],
     "allegation": "She says the agent threatened to post her photo as a defaulter on her WhatsApp groups and Facebook."},
    {"id": "CMP-0004", "borrower": "सुनीता", "borrower_id": "B1019", "account": "LN70125368", "lender": "Suvidha Finance", "received": "2026-11-15",
     "window": ["2026-11-13", "2026-11-15"], "channel": "Branch", "severity": "High", "rules": ["IGNORED_SENSITIVE_SITUATION"],
     "allegation": "Her mother had died the week before. She told the agent, and he kept pressing for payment and said he would not hang up until she paid."},
    {"id": "CMP-0005", "borrower": "विकास", "borrower_id": "B1008", "account": "LN26254693", "lender": "Navjeevan Housing Finance", "received": "2026-11-14",
     "window": ["2026-11-12", "2026-11-14"], "channel": "Phone", "severity": "Low", "rules": ["OUTSIDE_HOURS"],
     "allegation": "An agent called him after seven in the evening."},
    {"id": "CMP-0006", "borrower": "हरजीत", "borrower_id": "B2041", "account": "LN40311977", "lender": "Suvidha Finance", "received": "2026-11-15",
     "window": ["2026-11-13", "2026-11-15"], "channel": "Email", "severity": "Medium", "rules": ["THIRD_PARTY"],
     "allegation": "An agent called his brother about his loan."},
]


def seeded_complaints() -> dict:
    out = {}
    for c in SEED_COMPLAINTS:
        out[c["id"]] = {**c, "object": "complaint", "status": "received", "assignee": None, "attached": [], "decisions": {}, "notes": [],
                        "pack": None, "actions": [], "activity": [{"at": f"{c['received']}T10:00:00+05:30", "actor": c["channel"], "text": "Complaint received"}]}
    return out


def _blank() -> dict:
    return {"keys": {}, "endpoints": {}, "events": [], "calls": {}, "cases": {}, "policies": {}, "regressions": [],
            "complaints": seeded_complaints(), "actions": [], "packs": {}}


def load() -> dict:
    p = DIR / "state.json"
    if not p.exists():
        return _blank()
    s = json.loads(p.read_text())
    for k, v in _blank().items():
        s.setdefault(k, v)
    return s


def save(s: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = DIR / "state.json.tmp"
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1))
    tmp.replace(DIR / "state.json")


def mutate(fn):
    """Run fn(state) under the lock and save; returns fn's result."""
    with _lock:
        s = load()
        out = fn(s)
        save(s)
        return out


def log_request(rec: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    with (DIR / "requests.jsonl").open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def recent_requests(n: int = 50) -> list[dict]:
    p = DIR / "requests.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()[-n:]][::-1] if p.exists() else []


def error(status: int, kind: str, message: str) -> HTTPException:
    return HTTPException(status, {"type": kind, "message": message})


# ------------------------------------------------------------------ keys
def create_key(name: str) -> dict:
    secret = "mk_test_" + secrets.token_urlsafe(24)
    rec = {"id": new_id("key"), "object": "api_key", "name": name or "Untitled key", "prefix": secret[:12],
           "hash": hashlib.sha256(secret.encode()).hexdigest(), "mode": "test", "created": now(), "revoked": None, "last_used": None}
    mutate(lambda s: s["keys"].__setitem__(rec["id"], rec))
    return {**public_key(rec), "secret": secret}


def public_key(k: dict) -> dict:
    return {x: k[x] for x in ("id", "object", "name", "prefix", "mode", "created", "revoked", "last_used")}


def revoke_key(key_id: str) -> dict:
    def f(s):
        k = s["keys"].get(key_id)
        if not k:
            raise error(404, "invalid_request_error", f"No API key {key_id}.")
        k["revoked"] = k["revoked"] or now()
        return public_key(k)
    return mutate(f)


def require_key(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise error(401, "authentication_error", "Send your API key as  Authorization: Bearer mk_test_...")
    digest = hashlib.sha256(token.encode()).hexdigest()

    def f(s):
        k = next((k for k in s["keys"].values() if hmac.compare_digest(k["hash"], digest)), None)
        if not k:
            raise error(401, "authentication_error", "This API key is not valid.")
        if k["revoked"]:
            raise error(401, "authentication_error", f"This API key was revoked on {k['revoked'][:10]}.")
        k["last_used"] = now()
        return public_key(k)
    key = mutate(f)
    request.state.key_prefix = key["prefix"]
    return key


# ------------------------------------------------------------------ policies
def policy_for(s: dict, lender: str) -> dict:
    hist = s["policies"].get(lender) or []
    return hist[-1]["settings"] if hist else dict(DEFAULT_POLICY)


def set_policy(lender: str, settings: dict, actor: str) -> dict:
    w = settings.get("calling_window") or DEFAULT_POLICY["calling_window"]
    try:
        grace = int(settings.get("recording_grace_s", 20))
    except (TypeError, ValueError):
        raise error(422, "invalid_request_error", "recording_grace_s must be a whole number of seconds.")
    if not (isinstance(w, list) and len(w) == 2 and rules.OPEN <= w[0] < w[1] <= rules.CLOSE):
        raise error(422, "invalid_request_error", "The calling window must sit inside 08:00-19:00, the RBI's own window.")
    if not 5 <= grace <= 60:
        raise error(422, "invalid_request_error", "The recording-notice grace period must be between 5 and 60 seconds.")
    clean = {"calling_window": [w[0], w[1]], "recording_grace_s": grace}

    def f(s):
        hist = s["policies"].setdefault(lender, [])
        before = hist[-1]["settings"] if hist else dict(DEFAULT_POLICY)
        show = {"calling_window": lambda v: f"{v[0]}-{v[1]}", "recording_grace_s": lambda v: f"{v} s"}
        name = {"calling_window": "Calling window", "recording_grace_s": "Recording notice within"}
        changes = [f"{name[k]}: {show[k](before[k])} to {show[k](clean[k])}" for k in clean if before.get(k) != clean[k]]
        if not changes:
            return {"lender": lender, "version": len(hist), "settings": clean, "unchanged": True}
        hist.append({"version": len(hist) + 1, "settings": clean, "changed_by": actor, "changed_at": now(), "changes": changes})
        return {"lender": lender, **hist[-1]}
    return mutate(f)


# ------------------------------------------------------------------ webhooks
def sign(secret: str, body: bytes, t: int | None = None) -> str:
    t = int(time.time()) if t is None else t
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify_signature(secret: str, body: bytes, header: str, tolerance_s: int = 300) -> tuple[bool, str]:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t = int(parts["t"])
    except (ValueError, KeyError):
        return False, "malformed signature header"
    if abs(time.time() - t) > tolerance_s:
        return False, "timestamp outside the 5-minute tolerance"
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return (True, "signature verified") if hmac.compare_digest(expected, parts.get("v1", "")) else (False, "signature does not match")


def add_endpoint(url: str, events: list[str], description: str = "") -> dict:
    if not url.startswith(("http://", "https://")):
        raise error(422, "invalid_request_error", "The endpoint URL must start with http:// or https://.")
    bad = [e for e in events if e != "*" and e not in EVENT_TYPES]
    if bad:
        raise error(422, "invalid_request_error", f"Unknown event types: {', '.join(bad)}. Use {', '.join(EVENT_TYPES)} or *.")
    rec = {"id": new_id("we"), "object": "webhook_endpoint", "url": url, "events": events or ["*"], "description": description,
           "secret": "whsec_" + secrets.token_hex(24), "created": now(), "disabled": False}
    if url.rstrip("/").endswith("/demo/receiver/new"):  # the receiver inside this server, addressed by the endpoint's own id
        rec["url"] = url.rstrip("/").removesuffix("new") + rec["id"]
        rec["description"] = description or "Demo receiver inside this server"
    mutate(lambda s: s["endpoints"].__setitem__(rec["id"], rec))
    return rec


def public_endpoint(e: dict) -> dict:
    return {**{k: v for k, v in e.items() if k != "secret"}, "secret_prefix": e["secret"][:10]}


def remove_endpoint(eid: str) -> dict:
    def f(s):
        e = s["endpoints"].pop(eid, None)
        if not e:
            raise error(404, "invalid_request_error", f"No webhook endpoint {eid}.")
        return public_endpoint(e)
    return mutate(f)


def emit_event(kind: str, data: dict) -> dict:
    """Record an event and deliver it to every subscribed endpoint in the background."""
    ev = {"id": new_id("evt"), "object": "event", "type": kind, "created": now(), "mode": "test", "data": data, "deliveries": []}

    def f(s):
        s["events"].append(ev)
        s["events"] = s["events"][-500:]
        return [e for e in s["endpoints"].values() if not e["disabled"] and ("*" in e["events"] or kind in e["events"])]
    targets = mutate(f)
    for t in targets:
        _spawn(deliver(ev["id"], t["id"]))
    return ev


_tasks: set[asyncio.Task] = set()  # the loop keeps only weak references; hold them until they finish


_main_loop: asyncio.AbstractEventLoop | None = None  # the server's loop, captured by the request middleware


def _spawn(coro) -> None:
    """Run coro in the background on the server's loop, from the loop itself or from a worker thread."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        if _main_loop and _main_loop.is_running():  # a sync endpoint runs in a worker thread
            asyncio.run_coroutine_threadsafe(coro, _main_loop)
        else:  # scripts and tests without a server
            asyncio.run(coro)
        return
    task = loop.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def deliver(event_id: str, endpoint_id: str, attempts: int = 3) -> None:
    for n in range(1, attempts + 1):
        s = load()
        ev = next((e for e in s["events"] if e["id"] == event_id), None)
        ep = s["endpoints"].get(endpoint_id)
        if not ev or not ep:
            return
        body = json.dumps({k: v for k, v in ev.items() if k != "deliveries"}, ensure_ascii=False, separators=(",", ":")).encode()
        t0, status, err = time.perf_counter(), None, None
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(ep["url"], content=body, headers={"Content-Type": "application/json", "User-Agent": "Maryada-Webhooks/1.0",
                                                                   "Maryada-Signature": sign(ep["secret"], body), "Maryada-Event-Id": ev["id"]})
            status = r.status_code
        except httpx.HTTPError as e:
            err = type(e).__name__
        ok = status is not None and 200 <= status < 300
        rec = {"endpoint": endpoint_id, "url": ep["url"], "attempt": n, "at": now(), "status": status, "ms": round(1000 * (time.perf_counter() - t0)),
               "error": err, "ok": ok}

        def f(s, rec=rec):
            e = next((e for e in s["events"] if e["id"] == event_id), None)
            if e:
                e["deliveries"].append(rec)
        mutate(f)
        if ok:
            return
        if n < attempts:
            await asyncio.sleep(2 * 3 ** (n - 1))  # 2 s, then 6 s


def resend(event_id: str) -> dict:
    s = load()
    ev = next((e for e in s["events"] if e["id"] == event_id), None)
    if not ev:
        raise error(404, "invalid_request_error", f"No event {event_id}.")
    targets = [e for e in s["endpoints"].values() if not e["disabled"] and ("*" in e["events"] or ev["type"] in e["events"])]
    if not targets:
        raise error(409, "invalid_request_error", "No webhook endpoint is subscribed to this event type.")
    for t in targets:
        _spawn(deliver(event_id, t["id"], attempts=1))
    return {"id": event_id, "resent_to": [t["id"] for t in targets]}


# ------------------------------------------------------------------ cases
def _activity(case: dict, actor: str, text: str) -> None:
    case["activity"].append({"at": now(), "actor": actor, "text": text})
    case["updated"] = now()


def finding_key(a: dict) -> str:
    seg = a.get("segment_index")
    return f"{a['type']}:{'call' if seg is None else seg}"


def open_case(s: dict, call_id: str, variant: str, judge: str, findings: list[dict], source: str, api_call: str | None = None) -> dict:
    key = f"{call_id}:{variant}:{judge}"
    case = next((c for c in s["cases"].values() if c["key"] == key), None)
    if case:
        return case
    meta = _meta(call_id)
    case = {"id": new_id("case"), "object": "case", "key": key, "call_id": call_id, "variant": variant, "judge": judge,
            "lender": meta.lender if meta else None, "borrower": meta.borrower_name if meta else None,
            "status": "open", "assignee": None,
            "findings": [{"key": finding_key(a), "type": a["type"], "ms": a.get("ms"), "evidence": a.get("evidence"), "source": a.get("source"), "decision": None}
                         for a in findings],
            "notes": [], "activity": [], "created": now(), "updated": now(), "api_call": api_call}
    _activity(case, source, f"Case opened with {len(findings)} finding{'s' if len(findings) != 1 else ''}")
    s["cases"][case["id"]] = case
    return case


def update_case(case_id: str, changes: dict, actor: str) -> dict:
    def f(s):
        c = s["cases"].get(case_id)
        if not c:
            raise error(404, "invalid_request_error", f"No case {case_id}.")
        if "status" in changes and changes["status"] != c["status"]:
            if changes["status"] not in CASE_STATUSES:
                raise error(422, "invalid_request_error", f"Status must be one of {', '.join(CASE_STATUSES)}.")
            _activity(c, actor, f"Status changed from {c['status'].replace('_', ' ')} to {changes['status'].replace('_', ' ')}")
            c["status"] = changes["status"]
        if "assignee" in changes and (changes["assignee"] or None) != c["assignee"]:
            _activity(c, actor, f"Assigned to {changes['assignee'] or 'nobody'}")
            c["assignee"] = changes["assignee"] or None
        if note := (changes.get("note") or "").strip():
            c["notes"].append({"at": now(), "actor": actor, "text": note[:2000], "finding": changes.get("finding")})
            _activity(c, actor, "Added a note")
        if "decision" in changes and changes.get("finding"):
            fd = next((x for x in c["findings"] if x["key"] == changes["finding"]), None)
            if not fd:
                raise error(404, "invalid_request_error", f"No finding {changes['finding']} on this case.")
            d = changes["decision"]
            if d not in ("confirmed", "dismissed", None):
                raise error(422, "invalid_request_error", "A decision is confirmed, dismissed or null.")
            if d != fd["decision"]:
                fd["decision"] = d
                _activity(c, actor, f"{'Cleared the decision on' if d is None else d.capitalize()}: {VIOLATIONS[fd['type']]['title']}")
                if d == "dismissed":  # a dismissed alert becomes a regression case for the judge
                    s["regressions"].append({"id": new_id("reg"), "case": c["id"], "call_id": c["call_id"], "variant": c["variant"], "judge": c["judge"],
                                             "type": fd["type"], "evidence": fd["evidence"], "expected": "no alert", "added": now()})
            decided = [x["decision"] for x in c["findings"]]
            if decided and all(decided):
                new = "confirmed" if "confirmed" in decided else "dismissed"
                if c["status"] != new:
                    _activity(c, "system", f"Status changed from {c['status'].replace('_', ' ')} to {new}: every finding decided")
                    c["status"] = new
            elif c["status"] == "open" and any(decided):
                _activity(c, "system", "Status changed from open to in review")
                c["status"] = "in_review"
        return c
    case = mutate(f)
    emit_event("case.updated", {"case": {k: case[k] for k in ("id", "call_id", "status", "assignee", "updated")}})
    return case


def cases_csv(s: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["case_id", "call_id", "lender", "borrower", "line", "judge", "status", "assignee", "findings", "confirmed", "dismissed", "notes", "created", "updated"])
    for c in sorted(s["cases"].values(), key=lambda c: c["created"]):
        d = [f["decision"] for f in c["findings"]]
        w.writerow([c["id"], c["call_id"], c["lender"], c["borrower"], c["variant"], c["judge"], c["status"], c["assignee"] or "",
                    "; ".join(VIOLATIONS[f["type"]]["title"] for f in c["findings"]), d.count("confirmed"), d.count("dismissed"),
                    " | ".join(n["text"] for n in c["notes"]), c["created"], c["updated"]])
    return buf.getvalue()


# ------------------------------------------------------------------ calls
def _meta(call_id: str) -> CallMeta | None:
    p = config.CALLS_DIR / f"{call_id}.meta.json"
    return CallMeta.load(p) if p.exists() else None


def _seal(call_id: str, variant: str, judge: str, run_dir=None) -> dict:
    from .ui import server
    if run_dir:
        log = run_dir / f"{call_id}.audit.jsonl"
    else:
        path = server._pick(call_id, variant, judge)
        log = path.with_name(f"{call_id}.audit.jsonl") if path else None
    if not log or not log.exists():
        return {"verified": None, "records": 0, "head": None}
    ok, n, msg = audit_log.verify(log)
    return {"verified": ok, "records": n, "head": msg.split("head ")[-1] if ok else None, "message": msg}


def public_call(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def _alert_payload(api_id: str, call_id: str, a: dict) -> dict:
    v = VIOLATIONS[a["type"]]
    return {"call": api_id, "call_id": call_id, "alert": {"type": a["type"], "title": a.get("title") or v["title"], "clause": a.get("clause") or v["clause"],
                                                          "at_ms": a.get("ms"), "evidence": a.get("evidence"), "found_by": a.get("source")}}


def _finish_call(api_id: str, events: list[dict]) -> None:
    alerts = [e for e in events if e["t"] == "alert"]
    summary = next((e for e in events if e["t"] == "summary"), {})

    def f(s):
        c = s["calls"][api_id]
        c["status"] = "completed"
        c["completed"] = now()
        c["verdict"] = {"compliant": summary.get("compliant", not alerts), "violations": summary.get("violations", sorted({a["type"] for a in alerts}))}
        c["evidence"] = _seal(c["call_id"], c["variant"], c["judge"], DIR / "runs" / api_id if c["source"] == "stream" else None)
        if summary.get("redacted") is not None:
            c["redacted_before_llm"] = summary["redacted"]
        if alerts:
            c["case"] = open_case(s, c["call_id"], c["variant"], c["judge"], alerts, "api", api_call=api_id)["id"]
        return c
    c = mutate(f)
    emit_event("call.completed", {"call": public_call(c)})


def _add_finding(api_id: str, call_id: str, a: dict) -> None:
    payload = _alert_payload(api_id, call_id, a)
    mutate(lambda s: s["calls"][api_id]["findings"].append(payload["alert"]))
    emit_event("alert.created", payload)


async def _process_replay(api_id: str) -> None:
    """Play a saved run back through the event pipeline: no Prisma or LLM call, the same result every time."""
    from .ui import server
    c = load()["calls"][api_id]
    mutate(lambda s: s["calls"][api_id].__setitem__("status", "processing"))
    events = server.replay_events(c["call_id"], c["variant"], c["judge"]) or []
    for a in [e for e in events if e["t"] == "alert"]:
        await asyncio.sleep(0.25)
        _add_finding(api_id, c["call_id"], a)
    _finish_call(api_id, events)


async def _process_stream(api_id: str) -> None:
    """Stream the recording to Prisma v3.0 now, with the lender's policy, raising webhooks as alerts fire."""
    from .engine.monitor import run_call
    c = load()["calls"][api_id]
    mutate(lambda s: s["calls"][api_id].__setitem__("status", "processing"))
    seen: list[dict] = []

    def on_event(e: dict) -> None:
        seen.append(e)
        if e["t"] == "alert":
            _add_finding(api_id, c["call_id"], e)
    try:
        await run_call(c["call_id"], c["variant"], judge=c["judge"], on_event=on_event, policy=c["policy"], out_dir=DIR / "runs" / api_id)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        def f(s, e=e):
            s["calls"][api_id]["status"] = "failed"
            s["calls"][api_id]["error"] = f"{type(e).__name__}: {e}"[:300]
        mutate(f)
        return
    _finish_call(api_id, seen)


def submit_call(*, source: str, call_id: str, variant: str, judge: str, metadata: dict, request_id: str | None) -> dict:
    from .ui import server
    meta = _meta(call_id)
    if not meta:
        raise error(404, "invalid_request_error", f"Unknown call {call_id}.")
    if variant not in config.VARIANTS:
        raise error(422, "invalid_request_error", f"line must be one of {', '.join(config.VARIANTS)}.")
    if source == "replay":
        if judge not in ("llm", "lexicon"):
            raise error(422, "invalid_request_error", "judge must be llm or lexicon.")
        if not server._pick(call_id, variant, judge):
            raise error(404, "invalid_request_error", f"No saved {judge} run for {call_id} at {variant}. Choose another line or judge.")
    elif source == "stream":
        if not config.GNANI_API_KEY:
            raise error(400, "invalid_request_error", "Streaming needs a Gnani API key on the server. Use source=replay instead.")
        judge = "llm" if config.LLM_ENABLED else "lexicon"
    else:
        raise error(422, "invalid_request_error", "source must be replay or stream.")
    rec = {"id": new_id("call"), "object": "call", "mode": "test", "source": source, "call_id": call_id, "line": variant, "variant": variant, "judge": judge,
           "lender": meta.lender, "status": "queued", "created": now(), "completed": None, "findings": [], "verdict": None, "evidence": None,
           "policy": policy_for(load(), meta.lender), "metadata": metadata or {}, "request_id": request_id}
    if source == "replay":
        rec["policy_note"] = "A replay returns the saved verdict; the lender policy applies to streamed calls."
    mutate(lambda s: s["calls"].__setitem__(rec["id"], rec))
    _spawn(_process_replay(rec["id"]) if source == "replay" else _process_stream(rec["id"]))
    return public_call(rec)


def save_upload(audio: bytes, meta: dict) -> str:
    """A new stereo recording from a dialer: agent on the left channel, borrower on the right."""
    from .common.audio import read_wav
    cid = "API" + secrets.token_hex(4).upper()
    wav = config.CALLS_DIR / "clean" / f"{cid}.wav"
    mp = config.CALLS_DIR / f"{cid}.meta.json"

    def reject(msg: str) -> HTTPException:
        wav.unlink(missing_ok=True)
        mp.unlink(missing_ok=True)
        return error(422, "invalid_request_error", msg)
    need = {"borrower_name", "agent_name", "lender", "language", "call_time", "loan"}
    if missing := sorted(need - set(meta)):
        raise reject(f"metadata is missing: {', '.join(missing)}.")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(audio)
    try:
        chans, _ = read_wav(wav)
    except Exception:  # noqa: BLE001
        raise reject("audio must be a WAV file.")
    if len(chans) != 2:
        raise reject("audio must be stereo: agent on the left channel, borrower on the right.")
    mp.write_text(json.dumps({**meta, "call_id": cid, "borrower_id": meta.get("borrower_id", "")}, ensure_ascii=False, indent=2))
    try:
        CallMeta.load(mp)
    except Exception as e:  # noqa: BLE001
        raise reject(f"metadata could not be read: {e}")
    return cid


def rules_doc() -> dict:
    how = {"OUTSIDE_HOURS": "exact rule", "NO_RECORDING_DISCLOSURE": "exact rule; the LLM judge can confirm a notice", "WRONG_DUES": "exact rule",
           "THREAT_OR_ABUSE": "LLM judge (keyword list when the LLM is off)", "THIRD_PARTY": "LLM judge (keyword list when the LLM is off)",
           "IGNORED_SENSITIVE_SITUATION": "LLM judge (keyword list when the LLM is off)"}
    setting = {"OUTSIDE_HOURS": {"calling_window": DEFAULT_POLICY["calling_window"], "per_lender": True},
               "NO_RECORDING_DISCLOSURE": {"grace_s": DEFAULT_POLICY["recording_grace_s"], "min_agent_lines": 2, "per_lender": True},
               "WRONG_DUES": {"allowed": ["emi", "late_fee", "overdue_emis_total", "total_due", "amounts the borrower proposed"]}}
    sample, ex = _meta("C30"), None
    if sample:
        r = Redactor(sample)
        line = f"AGENT: {sample.borrower_name} जी, account {sample.loan.account} पर ₹{sample.loan.total_due:,} बकाया है, मुझे 98765 43210 पर call करें"
        ex = {"before": line, "after": r(line), "masked": r.summary()}
    return {"object": "list", "data": [{"id": t, "title": v["title"], "clause": v["clause"], "rule": v["rule"], "checked_by": how[t], "settings": setting.get(t, {})}
                                       for t, v in VIOLATIONS.items()],
            "redaction": {"enabled_for_live_and_api_calls": config.LLM_REDACT, "masks": ["borrower and agent names", "account and borrower IDs", "phone numbers", "numbers of 9 or more digits"],
                          "keeps": ["rupee amounts"], "example": ex}}


# ------------------------------------------------------------------ the public API
api = APIRouter(prefix="/v1", tags=["Maryada API v1"])


@api.get("/rules", summary="The six rules, their settings, and how text is masked before the LLM")
def v1_rules(key: dict = Depends(require_key)) -> dict:
    return rules_doc()


@api.post("/calls", status_code=202, summary="Submit a call: a stereo recording, or a test-bench call to replay or stream")
async def v1_create_call(request: Request, key: dict = Depends(require_key)) -> dict:
    """JSON  {"source": "replay"|"stream", "call_id": "C30", "line": "snr10", "judge": "llm"}, or multipart with
    an `audio` stereo WAV (agent left, borrower right) and a `metadata` JSON field, which is always streamed."""
    rid = getattr(request.state, "request_id", None)
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        up = form.get("audio")
        if up is None or not hasattr(up, "read"):
            raise error(422, "invalid_request_error", "Send the recording as the multipart field  audio.")
        try:
            meta = json.loads(form.get("metadata") or "{}")
        except json.JSONDecodeError:
            raise error(422, "invalid_request_error", "metadata must be JSON.")
        if not config.GNANI_API_KEY:
            raise error(400, "invalid_request_error", "Uploaded recordings are streamed to Prisma, which needs a Gnani API key on the server.")
        cid = save_upload(await up.read(), meta)
        return submit_call(source="stream", call_id=cid, variant="clean", judge="llm", metadata={"uploaded": True}, request_id=rid)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise error(422, "invalid_request_error", "Send JSON, or multipart with an audio file.")
    return submit_call(source=body.get("source", "replay"), call_id=str(body.get("call_id", "")), variant=body.get("line", "clean"),
                       judge=body.get("judge", "llm"), metadata=body.get("metadata") or {}, request_id=rid)


@api.get("/calls", summary="Calls submitted through the API, newest first")
def v1_calls(limit: int = 20, key: dict = Depends(require_key)) -> dict:
    rows = sorted(load()["calls"].values(), key=lambda c: c["created"], reverse=True)[:max(1, min(limit, 100))]
    return {"object": "list", "data": [public_call(c) for c in rows]}


@api.get("/calls/{call}", summary="One call: status, findings, verdict and the evidence seal")
def v1_call(call: str, key: dict = Depends(require_key)) -> dict:
    c = load()["calls"].get(call)
    if not c:
        raise error(404, "invalid_request_error", f"No call {call}.")
    return public_call(c)


@api.post("/streams", status_code=201, summary="Open a live monitoring session for a test-bench call")
def v1_stream(request: Request, body: dict, key: dict = Depends(require_key)) -> dict:
    cid, line = str(body.get("call_id", "")), body.get("line", "clean")
    if not _meta(cid):
        raise error(404, "invalid_request_error", f"Unknown call {cid}.")
    if not config.GNANI_API_KEY:
        raise error(400, "invalid_request_error", "Live sessions need a Gnani API key on the server.")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return {"id": new_id("str"), "object": "stream", "call_id": cid, "line": line, "websocket_url": f"{scheme}://{request.url.netloc}/ws/monitor?call={cid}&variant={line}",
            "events": ["call_start", "segment", "alert", "nudge", "summary"], "expires_at": (datetime.now(IST) + timedelta(minutes=10)).isoformat(timespec="seconds")}


@api.get("/events", summary="Webhook events, newest first, with their delivery attempts")
def v1_events(limit: int = 20, key: dict = Depends(require_key)) -> dict:
    return {"object": "list", "data": load()["events"][::-1][:max(1, min(limit, 100))]}


@api.post("/events/{event}/resend", summary="Deliver an event again to every subscribed endpoint")
def v1_resend(event: str, key: dict = Depends(require_key)) -> dict:
    return resend(event)


@api.get("/webhook_endpoints", summary="Registered webhook endpoints")
def v1_endpoints(key: dict = Depends(require_key)) -> dict:
    return {"object": "list", "data": [public_endpoint(e) for e in load()["endpoints"].values()]}


@api.post("/webhook_endpoints", status_code=201, summary="Register an endpoint; the signing secret is returned once")
def v1_add_endpoint(body: dict, key: dict = Depends(require_key)) -> dict:
    return add_endpoint(str(body.get("url", "")), list(body.get("events") or ["*"]), str(body.get("description", "")))


@api.get("/cases", summary="Cases opened for flagged calls")
def v1_cases(key: dict = Depends(require_key)) -> dict:
    return {"object": "list", "data": sorted(load()["cases"].values(), key=lambda c: c["updated"], reverse=True)}


@api.patch("/cases/{case}", summary="Change a case's status or assignee, add a note, or decide a finding")
def v1_case(case: str, body: dict, key: dict = Depends(require_key)) -> dict:
    return update_case(case, body, f"api key {key['prefix']}")


@api.get("/regressions", summary="Dismissed alerts, kept as regression cases for the judge")
def v1_regressions(key: dict = Depends(require_key)) -> dict:
    return {"object": "list", "data": load()["regressions"]}


@api.get("/policies/{lender}", summary="A lender's current settings and version history")
def v1_policy(lender: str, key: dict = Depends(require_key)) -> dict:
    s = load()
    return {"lender": lender, "settings": policy_for(s, lender), "history": s["policies"].get(lender, [])}


@api.put("/policies/{lender}", summary="Change a lender's calling window or recording-notice grace period")
def v1_set_policy(lender: str, body: dict, key: dict = Depends(require_key)) -> dict:
    return set_policy(lender, body, f"api key {key['prefix']}")


# ------------------------------------------------------------------ the dashboard console (local, no login)
console = APIRouter(prefix="/api/platform", include_in_schema=False)
ACTOR = "dashboard (no login in this demo)"


@console.get("/state")
def c_state() -> dict:
    s = load()
    lenders = sorted({CallMeta.load(p).lender for p in config.CALLS_DIR.glob("C*.meta.json")})
    rp = DIR / "received.jsonl"
    received = [json.loads(l) for l in rp.read_text().splitlines()[-30:]][::-1] if rp.exists() else []
    return {"keys": [public_key(k) for k in s["keys"].values()], "endpoints": [public_endpoint(e) for e in s["endpoints"].values()],
            "events": s["events"][::-1][:60], "requests": recent_requests(60), "received": received,
            "calls": sorted(s["calls"].values(), key=lambda c: c["created"], reverse=True)[:30],
            "cases": sorted(s["cases"].values(), key=lambda c: c["updated"], reverse=True), "regressions": s["regressions"][::-1],
            "policies": {l: {"settings": policy_for(s, l), "history": s["policies"].get(l, [])} for l in lenders},
            "rules": rules_doc(), "event_types": EVENT_TYPES, "gnani_key": bool(config.GNANI_API_KEY), "generated": now(),
            "complaints": sorted(s["complaints"].values(), key=lambda c: c["id"]), "actions": s["actions"][::-1],
            "packs": sorted(s["packs"].values(), key=lambda p: p["id"])}


# ------------------------------------------------------------------ complaints, agent actions and evidence packs
# The dashboard runs the workflow (matching, steps, activity) so the online demo can run it too; the server keeps it.
COMPLAINT_STATUSES = ["received", "calls_matched", "in_review", "evidence_packed", "action_taken", "closed"]
ACTION_TYPES = ["coaching_note", "retraining", "escalation"]


@console.put("/complaints/{cid}")
def c_put_complaint(cid: str, body: dict) -> dict:
    if body.get("status") not in COMPLAINT_STATUSES:
        raise error(422, "invalid_request_error", f"status must be one of {', '.join(COMPLAINT_STATUSES)}.")

    def f(s):
        if cid not in s["complaints"]:
            raise error(404, "invalid_request_error", f"No complaint {cid}.")
        keep = {k: s["complaints"][cid][k] for k in ("id", "object", "borrower", "borrower_id", "account", "lender", "received", "window", "channel", "severity", "rules", "allegation")}
        s["complaints"][cid] = {**body, **keep}
        return s["complaints"][cid]
    return mutate(f)


@console.post("/actions")
def c_add_action(body: dict) -> dict:
    if body.get("type") not in ACTION_TYPES:
        raise error(422, "invalid_request_error", f"type must be one of {', '.join(ACTION_TYPES)}.")
    if not body.get("agent"):
        raise error(422, "invalid_request_error", "An action needs the agent it is about.")
    rec = {"id": "ACT-" + secrets.token_hex(3).upper(), "object": "agent_action", "created": now(), "created_by": ACTOR,
           **{k: body.get(k) for k in ("type", "agent", "agent_key", "lender", "note", "complaint", "call_id", "finding")}}
    mutate(lambda s: s["actions"].append(rec))
    return rec


@console.post("/packs")
def c_add_pack(body: dict) -> dict:
    def f(s):
        pid = f"PK-{len(s['packs']) + 1:04d}"
        rec = {**body, "id": pid, "object": "evidence_pack", "generated": now()}
        s["packs"][pid] = rec
        return rec
    return mutate(f)


@console.post("/reset_demo")
def c_reset_demo() -> dict:
    def f(s):
        s["complaints"], s["actions"], s["packs"] = seeded_complaints(), [], {}
        return {"reset": True, "complaints": len(s["complaints"])}
    return mutate(f)


@console.post("/keys")
def c_create_key(body: dict) -> dict:
    return create_key(str(body.get("name", "")))


@console.delete("/keys/{key_id}")
def c_revoke(key_id: str) -> dict:
    return revoke_key(key_id)


@console.post("/webhook_endpoints")
def c_add_endpoint(request: Request, body: dict) -> dict:
    url = str(body.get("url") or f"{request.url.scheme}://{request.url.netloc}/demo/receiver/new")
    return add_endpoint(url, list(body.get("events") or ["*"]), str(body.get("description", "")))


@console.delete("/webhook_endpoints/{eid}")
def c_remove_endpoint(eid: str) -> dict:
    return remove_endpoint(eid)


@console.post("/events/{event}/resend")
def c_resend(event: str) -> dict:
    return resend(event)


@console.post("/test_call")
def c_test_call(request: Request, body: dict) -> dict:
    """What the mock dialer does, started from the dashboard: replay a saved run through the API pipeline."""
    rid = getattr(request.state, "request_id", new_id("req"))
    rec = submit_call(source=body.get("source", "replay"), call_id=str(body.get("call_id", "C30")), variant=body.get("line", "snr10"),
                      judge=body.get("judge", "llm"), metadata={"submitted_from": "dashboard"}, request_id=rid)
    log_request({"id": rid, "at": now(), "method": "POST", "path": "/v1/calls", "status": 202, "ms": 0, "key": "dashboard", "origin": "dashboard"})
    return rec


@console.post("/cases/open")
def c_open_case(body: dict) -> dict:
    from .ui import server
    cid, variant, judge = str(body.get("call_id")), body.get("variant", "clean"), body.get("judge", "llm")
    events = server.replay_events(cid, variant, judge)
    if events is None:
        raise error(404, "invalid_request_error", f"No saved {judge} run for {cid} at {variant}.")
    return mutate(lambda s: open_case(s, cid, variant, judge, [e for e in events if e["t"] == "alert"], ACTOR))


@console.patch("/cases/{case}")
def c_case(case: str, body: dict) -> dict:
    return update_case(case, body, str(body.get("actor") or ACTOR))


@console.get("/cases.csv")
def c_cases_csv() -> PlainTextResponse:
    return PlainTextResponse(cases_csv(load()), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=maryada-cases.csv"})


@console.put("/policies/{lender}")
def c_policy(lender: str, body: dict) -> dict:
    return set_policy(lender, body, ACTOR)


# ------------------------------------------------------------------ the demo receiver
receiver = APIRouter(prefix="/demo/receiver", include_in_schema=False)


@receiver.post("/{endpoint_id}")
async def r_receive(endpoint_id: str, request: Request) -> JSONResponse:
    """Stands in for the lender's server: verifies the signature exactly as a real receiver would."""
    body = await request.body()
    ep = load()["endpoints"].get(endpoint_id)
    ok, why = (False, "unknown endpoint") if not ep else verify_signature(ep["secret"], body, request.headers.get("maryada-signature", ""))
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}
    DIR.mkdir(parents=True, exist_ok=True)
    with (DIR / "received.jsonl").open("a") as f:
        f.write(json.dumps({"at": now(), "endpoint": endpoint_id, "event": payload.get("id"), "type": payload.get("type"), "verified": ok, "detail": why}) + "\n")
    return JSONResponse({"received": True, "verified": ok, "detail": why}, status_code=200 if ok else 400)


# ------------------------------------------------------------------ request IDs and error bodies
async def request_ids(request: Request, call_next):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    rid = new_id("req")
    request.state.request_id = rid
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        response = JSONResponse({"error": {"type": "api_error", "message": "Something went wrong on our side."}, "request_id": rid}, status_code=500)
    response.headers["Request-Id"] = rid
    if request.url.path.startswith("/v1/"):
        log_request({"id": rid, "at": now(), "method": request.method, "path": request.url.path, "status": response.status_code,
                     "ms": round(1000 * (time.perf_counter() - t0)), "key": getattr(request.state, "key_prefix", None), "origin": "api"})
    return response


async def error_body(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"type": "invalid_request_error", "message": str(exc.detail)}
    return JSONResponse({"error": detail, "request_id": getattr(request.state, "request_id", None)}, status_code=exc.status_code)
