"""Mask personal details before any text reaches the LLM judge.

The exact rules and the evidence log see the words as Prisma heard them; only the copy sent to the
LLM endpoint is masked. Names come from the call record, so they are masked in any script; phone,
account and ID numbers are found by pattern. Rupee amounts are left alone: the judge needs them.

    from maryada.engine.redact import Redactor
    r = Redactor(meta); r("नमस्ते पूजा जी, account LN71087484") -> "नमस्ते [BORROWER] जी, account [ACCOUNT]"
"""
from __future__ import annotations

import re
from collections import Counter

from ..common.schema import CallMeta

PHONE = re.compile(r"(?<![\d₹])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
ACCOUNT = re.compile(r"\b[A-Z]{2,4}\d{6,}\b")
LONG_NUMBER = re.compile(r"(?<![\d₹,])\d{9,}(?![\d,])")  # IDs and card-like numbers; amounts are shorter


class Redactor:
    def __init__(self, meta: CallMeta):
        self.names = [(n, tag) for n, tag in ((meta.borrower_name, "[BORROWER]"), (meta.agent_name, "[AGENT]")) if n]
        self.ids = [(i, "[ACCOUNT]") for i in (meta.loan.account, meta.borrower_id) if i]
        self.counts: Counter[str] = Counter()
        self._seen: dict[str, str] = {}

    def __call__(self, text: str) -> str:
        """Masked copy of text. Each distinct line is counted once, however often it is re-sent."""
        if text in self._seen:
            return self._seen[text]
        original = text
        for value, tag in self.ids + self.names:
            n = text.count(value)
            if n:
                text = text.replace(value, tag)
                self.counts[tag.strip("[]").lower()] += n
        for pattern, tag in ((PHONE, "[PHONE]"), (ACCOUNT, "[ACCOUNT]"), (LONG_NUMBER, "[NUMBER]")):
            text, n = pattern.subn(tag, text)
            if n:
                self.counts[tag.strip("[]").lower()] += n
        self._seen[original] = text
        return text

    def summary(self) -> dict[str, int]:
        return dict(sorted(self.counts.items()))
