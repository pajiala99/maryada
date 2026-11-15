"""Shared data contracts. Everything that crosses a module boundary is defined here.

Two files describe a call, and the split is deliberate:

  calls/<id>.meta.json   what the lender's dialer/CRM knows before the call.
                         The engine reads ONLY this (plus the audio).
  calls/<id>.truth.json  the script and the planted violations.
                         Only the bench (generator + evaluator) reads this.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Violation taxonomy. Clause labels follow the RBI recovery-conduct amendment
# directions of 6 Aug 2026 (NBFC paragraph numbering, in force 1 Jan 2027).
VIOLATIONS: dict[str, dict[str, str]] = {
    "OUTSIDE_HOURS": {
        "title": "Call outside 08:00-19:00",
        "clause": "Contact hours (para 100W(4))",
        "rule": "Borrowers may be contacted only between 08:00 and 19:00 unless they expressly asked for another time.",
    },
    "NO_RECORDING_DISCLOSURE": {
        "title": "Recording not disclosed",
        "clause": "Call recording (para 100N)",
        "rule": "Recovery calls must be recorded and the borrower told that the conversation is being recorded.",
    },
    "THREAT_OR_ABUSE": {
        "title": "Threat or abusive language",
        "clause": "Harsh practices (para 100X(1),(5),(7))",
        "rule": "No minatory or abusive language, threatening calls, or threat of violence to person, family, assets or reputation.",
    },
    "WRONG_DUES": {
        "title": "Dues misstated",
        "clause": "Harsh practices (para 100X(8))",
        "rule": "No false or misleading representation about the amount of the debt.",
    },
    "THIRD_PARTY": {
        "title": "Relatives / employer / public shaming",
        "clause": "Harsh practices (para 100X(2),(6)); para 100W(1)",
        "rule": "Dues are discussed only with the borrower. No harassing relatives, referees, friends or co-workers, no public humiliation.",
    },
    "IGNORED_SENSITIVE_SITUATION": {
        "title": "Pressed during bereavement / calamity / wedding",
        "clause": "Inappropriate occasions (para 100W(6))",
        "rule": "Avoid inappropriate occasions such as bereavement, other calamitous occasions or marriage functions.",
    },
}
VIOLATION_TYPES = list(VIOLATIONS)

AGENT, BORROWER = "agent", "borrower"
CHANNELS = (AGENT, BORROWER)  # stereo order: L = agent, R = borrower


@dataclass
class Loan:
    account: str
    product: str
    emi: int
    overdue_emis: int
    late_fee: int
    total_due: int  # emi * overdue_emis + late_fee: the figure the agent may quote
    days_past_due: int

    def valid_amounts(self) -> set[int]:
        """Every rupee figure an agent can truthfully state for this loan."""
        overdue = self.emi * self.overdue_emis
        return {self.emi, self.late_fee, overdue, self.total_due}


@dataclass
class CallMeta:
    call_id: str
    call_time: str  # ISO-8601 with offset, e.g. 2026-11-14T20:15:00+05:30
    borrower_id: str
    borrower_name: str
    agent_name: str
    lender: str
    language: str  # "hi-en" (Hinglish) or "pa-IN" (Punjabi)
    loan: Loan
    preferred_window: list[str] | None = None  # ["19:00", "21:00"], an express borrower request on file

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: Path) -> "CallMeta":
        d = json.loads(Path(path).read_text())
        d["loan"] = Loan(**d["loan"])
        return cls(**d)


@dataclass
class Turn:
    speaker: str  # AGENT | BORROWER
    text: str  # what Timbre is asked to speak (may carry <audio tags>, ₹ amounts as digits)
    ref: str  # tag-free reference transcript used for WER
    slot: str = ""  # which line-bank slot produced it (for error analysis)
    start_ms: int = 0  # filled by the mixer
    end_ms: int = 0


@dataclass
class CallTruth:
    call_id: str
    scenario: str
    turns: list[Turn]
    violations: list[dict]  # [{"type": <VIOLATION_TYPES>, "turn_index": int}]
    stated_preferred_window: list[str] | None = None  # spoken by the borrower in this call
    voices: dict[str, str] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: Path) -> "CallTruth":
        d = json.loads(Path(path).read_text())
        d["turns"] = [Turn(**t) for t in d["turns"]]
        return cls(**d)

    def violation_types(self) -> set[str]:
        return {v["type"] for v in self.violations}


@dataclass
class Segment:
    """One committed Prisma utterance, placed on the call's clock."""
    channel: str
    text: str
    start_ms: int
    end_ms: int
    lang: str | None = None
    latency_ms: int | None = None
    index: int = 0


@dataclass
class Alert:
    type: str
    at_ms: int
    evidence: str
    source: str  # "rule" | "llm" | "lexicon"
    confidence: float = 1.0
    segment_index: int | None = None

    def to_event(self) -> dict:
        info = VIOLATIONS[self.type]
        return {"t": "alert", **asdict(self), "title": info["title"], "clause": info["clause"]}
