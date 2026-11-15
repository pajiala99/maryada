"""Offline tests for the integration layer: keys, signatures, policies and masking before the LLM."""
import time

import pytest
from fastapi.testclient import TestClient

from maryada import gateway
from maryada.common import config
from maryada.common.schema import CallMeta
from maryada.engine.redact import Redactor


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DIR", tmp_path)
    from maryada.ui import server
    return TestClient(server.app)


def test_signature_round_trip_and_tampering():
    body = b'{"type":"alert.created"}'
    header = gateway.sign("whsec_test", body)
    assert gateway.verify_signature("whsec_test", body, header) == (True, "signature verified")
    assert not gateway.verify_signature("whsec_test", body + b" ", header)[0]          # body changed
    assert not gateway.verify_signature("whsec_other", body, header)[0]                # wrong secret
    stale = gateway.sign("whsec_test", body, t=int(time.time()) - 3600)
    assert gateway.verify_signature("whsec_test", body, stale)[1] == "timestamp outside the 5-minute tolerance"


def test_keys_are_shown_once_and_checked_by_hash(client):
    assert client.get("/v1/rules").status_code == 401
    key = client.post("/api/platform/keys", json={"name": "test"}).json()
    assert key["secret"].startswith("mk_test_") and "hash" not in key
    r = client.get("/v1/rules", headers={"Authorization": f"Bearer {key['secret']}"})
    assert r.status_code == 200 and r.headers["Request-Id"].startswith("req_")
    assert {x["id"] for x in r.json()["data"]} >= {"OUTSIDE_HOURS", "WRONG_DUES"}
    client.delete(f"/api/platform/keys/{key['id']}")
    r = client.get("/v1/rules", headers={"Authorization": f"Bearer {key['secret']}"})
    assert r.status_code == 401 and "revoked" in r.json()["error"]["message"]


def test_policy_stays_inside_the_rbi_window_and_is_versioned(client):
    bad = client.put("/api/platform/policies/Udaan%20Capital", json={"calling_window": ["07:00", "20:00"], "recording_grace_s": 20})
    assert bad.status_code == 422 and bad.json()["request_id"]
    ok = client.put("/api/platform/policies/Udaan%20Capital", json={"calling_window": ["09:00", "18:00"], "recording_grace_s": 15}).json()
    assert ok["version"] == 1 and ok["changes"] == ["Calling window: 08:00-19:00 to 09:00-18:00", "Recording notice within: 20 s to 15 s"]


def test_masking_before_the_llm_keeps_amounts():
    meta = CallMeta.load(config.CALLS_DIR / "C30.meta.json")
    r = Redactor(meta)
    out = r(f"AGENT: {meta.borrower_name} जी, account {meta.loan.account} पर ₹4,400 बकाया है, 98765 43210 पर call करें, मैं {meta.agent_name}")
    assert meta.borrower_name not in out and meta.agent_name not in out and meta.loan.account not in out and "98765" not in out
    assert "₹4,400" in out
    assert r.summary() == {"account": 1, "agent": 1, "borrower": 1, "phone": 1}
    r(f"AGENT: {meta.borrower_name}")
    r(f"AGENT: {meta.borrower_name}")  # the same line re-sent with later context is counted once
    assert r.summary()["borrower"] == 2


def test_hours_rule_takes_a_narrower_policy_window():
    from maryada.engine import rules
    meta = CallMeta.load(config.CALLS_DIR / "C10.meta.json")  # placed at 14:00
    assert rules.check_hours(meta) is None
    assert rules.check_hours(meta, "15:00", "18:00") is not None


def test_complaints_are_seeded_and_kept(client):
    s = client.get("/api/platform/state").json()
    ids = [c["id"] for c in s["complaints"]]
    assert ids == ["CMP-0001", "CMP-0002", "CMP-0003", "CMP-0004", "CMP-0005", "CMP-0006"]
    c = s["complaints"][0]
    assert c["status"] == "received" and c["borrower_id"] == "B1030" and c["lender"] == "Udaan Capital"
    changed = {**c, "status": "in_review", "allegation": "rewritten by the client", "attached": [{"call_id": "C30", "variant": "clean", "judge": "llm"}]}
    r = client.put("/api/platform/complaints/CMP-0001", json=changed).json()
    assert r["status"] == "in_review" and r["attached"][0]["call_id"] == "C30"
    assert r["allegation"] == c["allegation"]  # the facts of the complaint are not the client's to change
    assert client.put("/api/platform/complaints/CMP-0001", json={**c, "status": "lost"}).status_code == 422


def test_actions_packs_and_reset(client):
    a = client.post("/api/platform/actions", json={"type": "retraining", "agent": "Ankit", "lender": "Udaan Capital", "complaint": "CMP-0001", "note": "Threat at 0:23"}).json()
    assert a["id"].startswith("ACT-") and a["type"] == "retraining"
    assert client.post("/api/platform/actions", json={"type": "fine", "agent": "Ankit"}).status_code == 422
    pk = client.post("/api/platform/packs", json={"complaint": "CMP-0001", "calls": ["C30"]}).json()
    assert pk["id"] == "PK-0001"
    s = client.get("/api/platform/state").json()
    assert len(s["actions"]) == 1 and len(s["packs"]) == 1
    client.post("/api/platform/reset_demo")
    s = client.get("/api/platform/state").json()
    assert s["actions"] == [] and s["packs"] == [] and s["complaints"][0]["status"] == "received"
