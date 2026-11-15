"""Tamper-evident evidence log.

Every record carries the SHA-256 of the previous record, so editing or deleting
any line breaks every hash after it. The RBI directions require recovery calls
to be logged and recordings kept for six months; this is the log a lender could
hand to an auditor alongside the audio.

    python -m maryada.extras.audit_log out/events/llm/snr10/C30.audit.jsonl   # verify
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

GENESIS = "0" * 64


def _digest(prev: str, record: dict) -> str:
    body = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode()).hexdigest()


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("")
        self.prev, self.seq = GENESIS, 0

    def append(self, record: dict) -> str:
        self.seq += 1
        h = _digest(self.prev, record)
        with self.path.open("a") as f:
            f.write(json.dumps({"seq": self.seq, "prev": self.prev, "hash": h, "record": record}, ensure_ascii=False) + "\n")
        self.prev = h
        return h


def verify(path: Path) -> tuple[bool, int, str]:
    """Returns (ok, records checked, message)."""
    prev, n = GENESIS, 0
    for n, line in enumerate(Path(path).read_text().splitlines(), start=1):
        row = json.loads(line)
        if row["prev"] != prev or row["seq"] != n:
            return False, n, f"chain broken at record {n}: previous-hash mismatch"
        if _digest(prev, row["record"]) != row["hash"]:
            return False, n, f"record {n} was modified after it was written"
        prev = row["hash"]
    return True, n, f"{n} records, chain intact, head {prev[:16]}"


if __name__ == "__main__":
    ok, _, msg = verify(Path(sys.argv[1]))
    print(("OK  " if ok else "FAIL  ") + msg)
    sys.exit(0 if ok else 1)
