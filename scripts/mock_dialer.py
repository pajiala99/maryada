"""A stand-in for a lender's dialer: submit a call to Maryada's API, wait for the verdict, show the webhooks.

    export MARYADA_API_KEY=mk_test_...          # create one on the dashboard's Developers page
    python scripts/mock_dialer.py                 # replays C30 at 10 dB through the API pipeline (no API cost)
    python scripts/mock_dialer.py --call C16 --line clean --receiver   # also registers the demo webhook receiver
    python scripts/mock_dialer.py --source stream # streams the recording to Prisma v3.0 now (needs a Gnani key on the server)

Uses only the public /v1 API, the same calls a real integration would make.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("MARYADA_BASE", "http://127.0.0.1:8770"))
    ap.add_argument("--call", default="C30")
    ap.add_argument("--line", default="snr10", choices=["clean", "snr20", "snr10", "snr5", "snr0"])
    ap.add_argument("--judge", default="llm", choices=["llm", "lexicon"])
    ap.add_argument("--source", default="replay", choices=["replay", "stream"])
    ap.add_argument("--receiver", action="store_true", help="register the demo webhook receiver first")
    a = ap.parse_args()
    key = os.environ.get("MARYADA_API_KEY")
    if not key:
        print("Set MARYADA_API_KEY (create a key on the dashboard's Developers page).")
        return 2
    c = httpx.Client(base_url=a.base, headers={"Authorization": f"Bearer {key}"}, timeout=30)

    def call(method: str, path: str, **kw) -> dict:
        r = c.request(method, path, **kw)
        body = r.json()
        print(f"{method} {path} -> {r.status_code}  (Request-Id {r.headers.get('Request-Id')})")
        if r.status_code >= 400:
            print("  " + body["error"]["message"])
            sys.exit(1)
        return body

    if a.receiver:
        ep = call("POST", "/v1/webhook_endpoints", json={"url": f"{a.base}/demo/receiver/new", "events": ["*"], "description": "mock dialer demo"})
        print(f"  endpoint {ep['id']} -> {ep['url']}\n  signing secret (shown once): {ep['secret']}")

    job = call("POST", "/v1/calls", json={"source": a.source, "call_id": a.call, "line": a.line, "judge": a.judge, "metadata": {"dialer": "mock"}})
    print(f"  {job['id']}: {job['status']}")
    while True:
        time.sleep(1)
        job = c.get(f"/v1/calls/{job['id']}").json()
        if job["status"] in ("completed", "failed"):
            break
        print(f"  {job['status']}, {len(job['findings'])} finding(s) so far")
    print(f"\n{job['id']}  {job['status']}")
    if job["status"] == "failed":
        print("  " + job.get("error", ""))
        return 1
    for f in job["findings"]:
        print(f"  {f['at_ms'] / 1000:5.1f}s  {f['title']:<40}  {f['clause']:<38}  found by {f['found_by']}")
    v, e = job["verdict"], job["evidence"]
    print(f"  verdict: {'compliant' if v['compliant'] else 'rules broken: ' + ', '.join(v['violations'])}")
    print(f"  evidence: {'verified, ' + str(e['records']) + ' records, head ' + str(e['head']) if e and e['verified'] else e}")
    if job.get("case"):
        print(f"  case opened: {job['case']}")
    time.sleep(1.5)
    events = call("GET", "/v1/events", params={"limit": 8})["data"]
    print()
    for ev in events[::-1]:
        d = ev["deliveries"][-1] if ev["deliveries"] else None
        state = "no endpoint" if not d else f"delivered {d['status']} in {d['ms']} ms" if d["ok"] else f"failed ({d['status'] or d['error']}), attempt {d['attempt']}"
        print(f"  {ev['id']}  {ev['type']:<15}  {state}")
    print(json.dumps(events[0], ensure_ascii=False, indent=2)[:900] if events else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
