"""LLM judge for the conduct rules that need reading comprehension.

Works with any OpenAI-compatible /chat/completions endpoint (set LLM_BASE_URL,
LLM_API_KEY, LLM_MODEL). Evon v3.3 served behind vLLM speaks the same protocol,
so moving to it is a change of base URL.

The judge sees the loan record, a rolling window of the two-channel transcript
and the agent's latest utterance. It never sees the script or the labels.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re

import httpx

from ..common import config
from .redact import Redactor
from ..common.schema import CallMeta

SYSTEM = """You audit Indian loan-recovery phone calls against the RBI's conduct rules for recovery agents.

You get the loan record, a rolling transcript (AGENT and BORROWER lines in an Indian language (Hindi, Punjabi, Tamil, Telugu, Kannada, Bengali, Marathi and others) mixed with English, produced by a speech recogniser on a noisy phone line, so expect some wrong or missing words) and the agent's LATEST utterance.

Judge only the LATEST agent utterance, using earlier lines as context. Nothing the BORROWER says is ever a violation.

Return one JSON object with exactly these keys:

"threat_or_abuse": true if the agent threatens, intimidates or insults: violence, sending people to the home, taking belongings, police or jail, name-calling. Calmly stating real consequences (late charges, credit score, a legal notice as per process) or a firm deadline is NOT a threat. Saying they will contact the borrower's family, employer or neighbours is NOT counted here; that is "third_party" only.

"third_party": true if the agent says they will contact, involve or inform the borrower's relatives, employer, colleagues, neighbours or friends about the debt, or shame the borrower publicly or on social media. If the BORROWER is the one who suggests speaking to a relative and the agent only answers or declines, it is false.

"ignored_sensitive": true only if the borrower has already said they are in a bereavement, a serious accident / hospitalisation or similar calamity, or a family wedding, AND the latest agent utterance keeps pressing for payment instead of backing off. False if the agent shows sympathy or offers to call later.

"wrong_dues": true if the agent states, as the amount owed, a figure that contradicts the loan record. Figures equal to the EMI, the late fee, the overdue EMIs or the total due are correct. A part-payment figure the borrower proposed and the agent repeats is fine.

"recording_disclosed": true if the latest agent utterance tells the borrower the call is being recorded or monitored.

"borrower_preferred_time": if the borrower asked to be called at or after a specific clock time, that time as "HH:MM" in 24-hour form, else null.

"evidence": the few words (at most 15) from the latest agent utterance that justify any true flag, copied as transcribed, else "".

Be conservative: if the utterance is too garbled to tell, answer false."""

_KEYS = ("threat_or_abuse", "third_party", "ignored_sensitive", "wrong_dues", "recording_disclosed")
_JSON = re.compile(r"\{.*\}", re.S)
_slots: dict[int, asyncio.Semaphore] = {}


def _slot() -> asyncio.Semaphore:
    loop = id(asyncio.get_running_loop())
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(2)
    return _slots[loop]


def loan_brief(meta: CallMeta) -> str:
    l = meta.loan
    return (f"product: {l.product}; EMI: ₹{l.emi}; overdue EMIs: {l.overdue_emis} (₹{l.emi * l.overdue_emis}); "
            f"late fee: ₹{l.late_fee}; total due: ₹{l.total_due}; days past due: {l.days_past_due}")


def parse(content: str) -> dict:
    m = _JSON.search(content or "")
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    out = {k: d.get(k) is True for k in _KEYS}
    t = d.get("borrower_preferred_time")
    out["borrower_preferred_time"] = t if isinstance(t, str) and re.fullmatch(r"\d{2}:\d{2}", t) else None
    out["evidence"] = str(d.get("evidence") or "")[:200]
    return out


class LLMJudge:
    def __init__(self, meta: CallMeta, client: httpx.AsyncClient | None = None, redact: bool | None = None):
        self.loan = loan_brief(meta)
        self.redactor = Redactor(meta) if (config.LLM_REDACT if redact is None else redact) else None
        self._own = client is None
        self.client = client or httpx.AsyncClient(timeout=60)
        self.calls = 0
        self.failures = 0

    async def judge(self, transcript: list[str], latest: str) -> dict | None:
        """transcript: recent 'AGENT: ...' / 'BORROWER: ...' lines, oldest first, excluding `latest`."""
        if self.redactor:  # the endpoint never sees names, phone or account numbers
            transcript, latest = [self.redactor(line) for line in transcript], self.redactor(latest)
        user = (f"LOAN RECORD\n{self.loan}\n\nTRANSCRIPT SO FAR\n" + ("\n".join(transcript) or "(call just started)")
                + f"\n\nLATEST AGENT UTTERANCE\n{latest}")
        body = {"model": config.LLM_MODEL, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}}
        if config.LLM_REASONING_EFFORT:
            body["reasoning_effort"] = config.LLM_REASONING_EFFORT
        # Same model + same prompt = same verdict (temperature 0), so verdicts are cached on disk.
        key = hashlib.sha256(json.dumps([config.LLM_MODEL, SYSTEM, user], ensure_ascii=False).encode()).hexdigest()[:32]
        cached = config.OUT_DIR / "llm_cache" / f"{key}.json"
        if cached.exists():
            self.calls += 1
            return json.loads(cached.read_text())
        headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"} if config.LLM_API_KEY else {}
        delay = 1.5
        async with _slot():
            for _ in range(20):
                try:
                    r = await self.client.post(f"{config.LLM_BASE_URL}/chat/completions", json=body, headers=headers)
                except httpx.HTTPError:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 20)
                    continue
                if r.status_code == 200:
                    self.calls += 1
                    verdict = parse(r.json()["choices"][0]["message"]["content"])
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(json.dumps(verdict, ensure_ascii=False))
                    return verdict
                if r.status_code == 400 and ("response_format" in body or "reasoning_effort" in body):
                    body.pop("reasoning_effort", None) if "reasoning_effort" in body else body.pop("response_format")
                    continue  # endpoint without that option: rely on the prompt
                if r.status_code == 429:  # free tiers are tight: wait exactly as long as the server asks
                    wait = float(r.headers.get("retry-after") or delay)
                    if wait > config.LLM_MAX_WAIT_S:
                        break  # e.g. a daily token cap: the keyword baseline stands in rather than stall a live call
                    await asyncio.sleep(wait + 0.5)
                    continue
                if r.status_code in (500, 502, 503, 529):
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 20)
                    continue
                break
        self.failures += 1
        return None  # caller falls back to the keyword baseline for this utterance

    async def close(self) -> None:
        if self._own:
            await self.client.aclose()
