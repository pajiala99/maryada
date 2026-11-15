"""Deterministic checks. Anything that can be decided without a model is decided here.

  OUTSIDE_HOURS            from the dialer's call time and any consent on file
  NO_RECORDING_DISCLOSURE  agent never tells the borrower the call is recorded
  WRONG_DUES               a rupee figure the agent states is on no line of the loan record

plus a keyword baseline for the three judgement calls (threat, third party,
sensitive occasion). The baseline exists so the system still works with no LLM,
and so the benchmark can show what the LLM adds.
"""
from __future__ import annotations

import re
from datetime import datetime

from ..common.schema import AGENT, BORROWER, Alert, CallMeta, Segment

# ------------------------------------------------------------------ hours
OPEN, CLOSE = "08:00", "19:00"


def check_hours(meta: CallMeta, open_: str = OPEN, close: str = CLOSE) -> Alert | None:
    """open_/close default to the RBI window; a lender policy can only narrow it in practice."""
    clock = datetime.fromisoformat(meta.call_time).strftime("%H:%M")  # the offset in call_time is IST
    if open_ <= clock < close:
        return None
    w = meta.preferred_window
    if w and w[0] <= clock < w[1]:
        return None  # borrower expressly asked to be called in this window
    return Alert("OUTSIDE_HOURS", 0, f"Call placed at {clock} IST; permitted window is {open_}-{close}"
                 + (f", borrower's requested window is {w[0]}-{w[1]}" if w else ", no borrower request on file"),
                 "rule")


# ------------------------------------------------------------- disclosure
_RECORD = re.compile(r"record|रिकॉर्ड|रिकार्ड|रेकॉर्ड|रिकोर्ड|रेकार्ड|ਰਿਕਾਰਡ|ਰਿਕੌਰਡ|ਰੀਕਾਰਡ|ਰਿਕਾਡ|ரெக்கார்ட்|ரெக்கார்டு|ரிக்கார்ட்|రికార్డ్|రికార్డు|ರೆಕಾರ್ಡ್|রেকর্ড|રેકોર્ડ|റെക്കോർഡ്|റെക്കോഡ്", re.I)


def mentions_recording(text: str) -> bool:
    return bool(_RECORD.search(text))


class DisclosureTracker:
    """Fires once if the agent is well into the call and has not disclosed recording."""

    def __init__(self, deadline_ms: int = 20_000, min_agent_segments: int = 2):
        self.deadline_ms, self.min_segments = deadline_ms, min_agent_segments
        self.disclosed = False
        self.fired = False
        self.agent_segments = 0
        self.agent_text: list[str] = []

    def on_segment(self, seg: Segment) -> bool:
        """Returns True when the deadline has passed without a disclosure (caller confirms, then alerts)."""
        if seg.channel != AGENT or self.disclosed or self.fired:
            return False
        self.agent_segments += 1
        self.agent_text.append(seg.text)
        if mentions_recording(seg.text):
            self.disclosed = True
            return False
        return seg.end_ms >= self.deadline_ms and self.agent_segments >= self.min_segments

    def pending_at_end(self) -> bool:
        return not self.disclosed and not self.fired and self.agent_segments > 0

    def alert(self, at_ms: int) -> Alert:
        self.fired = True
        said = " / ".join(self.agent_text)[:140]
        return Alert("NO_RECORDING_DISCLOSURE", at_ms,
                     f"No recording notice in the agent's first {self.agent_segments} utterances: \"{said}\"", "rule")


# ------------------------------------------------------------------- dues
_NUM = r"\d{1,3}(?:,\d{2,3})+|\d+"
_SCALE = {"लाख": 100_000, "lakh": 100_000, "lac": 100_000, "ਲੱਖ": 100_000,
          "हज़ार": 1000, "हजार": 1000, "thousand": 1000, "ਹਜ਼ਾਰ": 1000, "ਹਜਾਰ": 1000}
_SCALED = re.compile(rf"({_NUM})\s*({'|'.join(_SCALE)})(?:\s*({_NUM}))?", re.I)  # "12 हज़ार 500"
_PLAIN = re.compile(rf"({_NUM})")
_DUES_CONTEXT = re.compile(
    r"outstanding|overdue|due|total|amount|emi|payment|pending|charges|penalty|pay|"
    r"बकाया|भर|जमा|रुपय|रुपए|₹|ਬਕਾਇਆ|ਜਮ੍ਹਾਂ|ਭਰ|ਰੁਪ|"
    # the same English words as an ASR may spell them in Devanagari or Gurmukhi
    r"आउटस्टैंडिंग|ओवरड्यू|टोटल|अमाउंट|ई ?एम ?आई|इ एम आई|पेमेंट|पेंडिंग|चार्ज|पेनल्टी|"
    r"ਆਊਟਸਟੈਂਡਿੰਗ|ਟੋਟਲ|ਅਮਾਊਂਟ|ਈ ?ਐਮ ?ਆਈ|ਪੇਮੈਂਟ|ਪੈਂਡਿੰਗ|ਚਾਰਜ|"
    r"நிலுவை|மொத்த|ரூபாய்|బాకీ|మొత్తం|రూపాయ|ಬಾಕಿ|ಒಟ್ಟು|ರೂಪಾಯಿ|বকেয়া|মোট|টাকা|थकबाकी|एकूण|रक्कम|બાકી|કુલ|રકમ|കുടിശ്ശിക|ആകെ|തുക", re.I)
MIN_AMOUNT = 500  # smaller numbers are dates, counts, clock times


def extract_amounts(text: str) -> list[int]:
    """Rupee figures in a transcript line: '₹12,500', '12500', '12 हज़ार 500', '2 lakh'."""
    values = []

    def scaled(m: re.Match) -> str:
        scale = _SCALE[m.group(2).lower()]
        rest = int(m.group(3).replace(",", "")) if m.group(3) else 0
        values.append(int(m.group(1).replace(",", "")) * scale + (rest if rest < scale else 0))
        return " "

    rest_of_text = _SCALED.sub(scaled, text)
    values += [int(m.group(1).replace(",", "")) for m in _PLAIN.finditer(rest_of_text)]
    return [v for v in values if MIN_AMOUNT <= v <= 50_000_000]


class DuesChecker:
    def __init__(self, meta: CallMeta):
        self.loan = meta.loan
        self.valid = set(meta.loan.valid_amounts())
        self.borrower_amounts: set[int] = set()
        self.flagged: set[int] = set()
        self.prev_agent_text = ""

    def on_segment(self, seg: Segment) -> tuple[list[int], Alert | None]:
        """Returns (amounts heard, alert or None)."""
        amounts = extract_amounts(seg.text)
        if seg.channel == BORROWER:
            self.borrower_amounts.update(amounts)  # a part payment the borrower proposes is not a "claim"
            return amounts, None
        allowed = self.valid | self.borrower_amounts | {self.loan.total_due - a for a in self.borrower_amounts}
        bad = [a for a in amounts if a not in allowed and a not in self.flagged]
        # A long sentence can be cut in two by the segment-length cap, so "total बकाया" may sit in
        # the previous agent segment and the figure in this one.
        context, self.prev_agent_text = self.prev_agent_text + " " + seg.text, seg.text
        if not bad or not _DUES_CONTEXT.search(context):
            return amounts, None
        self.flagged.update(bad)
        l = self.loan
        return amounts, Alert(
            "WRONG_DUES", seg.end_ms,
            f"Agent stated ₹{bad[0]:,}; loan record shows EMI ₹{l.emi:,} × {l.overdue_emis} + late fee ₹{l.late_fee:,} = ₹{l.total_due:,}",
            "rule", 0.9, seg.index)


# ---------------------------------------------------------- preferred time
_HOUR_WORDS = {"छह": 6, "छः": 6, "छे": 6, "सात": 7, "आठ": 8, "नौ": 9, "पाँच": 5, "पांच": 5,
               "ਛੇ": 6, "ਸੱਤ": 7, "ਅੱਠ": 8, "ਨੌਂ": 9, "ਪੰਜ": 5, "six": 6, "seven": 7, "eight": 8}
_EVENING = re.compile(r"शाम|रात|ਸ਼ਾਮ|ਰਾਤ|evening|night|pm", re.I)
_OCLOCK = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(?:बजे|ਵਜੇ|pm|o'?clock)|(" + "|".join(_HOUR_WORDS) + r")\s*(?:बजे|ਵਜੇ)", re.I)
_AFTER = re.compile(r"के बाद|ਤੋਂ ਬਾਅਦ|after|बाद ही|ਬਾਅਦ ਹੀ", re.I)


def preferred_time(text: str) -> str | None:
    """'शाम 6 बजे के बाद call कीजिए' -> '18:00'. Only fires on an explicit 'after <time>' request."""
    if not _AFTER.search(text):
        return None
    m = _OCLOCK.search(text)
    if not m:
        return None
    hour = int(m.group(1)) if m.group(1) else _HOUR_WORDS[m.group(3)]
    minute = int(m.group(2) or 0)
    if hour < 12 and _EVENING.search(text):
        hour += 12
    return f"{hour:02d}:{minute:02d}" if 0 <= hour < 24 else None


# ------------------------------------------------------- keyword baseline
_THREAT = re.compile(
    r"पुलिस|police|जेल|jail|अंदर करवा|उठा ले|सामान उठा|घर आकर|हाथ-?\s?पैर|बेशर्म|चोर|होशियारी|औकात|"
    r"ਪੁਲਿਸ|ਜੇਲ|ਅੰਦਰ ਕਰਵਾ|ਚੁੱਕ ਕੇ ਲੈ|ਸਮਾਨ ਚੁੱਕ|ਘਰ ਆ ਕੇ|ਬੇਸ਼ਰਮ|ਚਲਾਕੀ|ਪੁਲੀਸ|"
    r"ஆட்கள் வீட்டுக்கு|మనుషులు ఇంటికి|ಹುಡುಗರು ಮನೆಗೆ|ছেলেরা বাড়িতে|माणसं घरी|पोलीस|போலீஸ்|పోలీస్|ಪೊಲೀಸ್|পুলিশ", re.I)
# English words appear twice: as written in Latin, and as an ASR may spell them in Devanagari/Gurmukhi
_THIRD = re.compile(
    r"manager|office|boss|employer|पिताजी|पिता|भाई|पड़ोस|मोहल्ले|रिश्तेदार|whatsapp|facebook|social media|defaulter|"
    r"मैनेजर|ऑफिस|आफिस|बॉस|व्हाट्सऐप|व्हाट्सएप|वॉट्सऐप|फेसबुक|फ़ेसबुक|सोशल मीडिया|डिफॉल्टर|डिफ़ॉल्टर|"
    r"ਪਿਤਾ|ਭਰਾ|ਗੁਆਂਢ|ਪਿੰਡ|ਰਿਸ਼ਤੇਦਾਰ|ਮੈਨੇਜਰ|ਆਫਿਸ|ਦਫ਼ਤਰ|ਦਫਤਰ", re.I)
_SENSITIVE = re.compile(
    r"देहांत|गुज़र ग|गुजर ग|तेरहवीं|मौत|hospital|अस्पताल|icu|accident|operation|शादी|बारात|"
    r"हॉस्पिटल|हस्पताल|आईसीयू|आई सी यू|एक्सीडेंट|ऑपरेशन|आपरेशन|"
    r"ਪੂਰੇ ਹੋ|ਦੇਹਾਂਤ|ਭੋਗ|ਮੌਤ|ਹਸਪਤਾਲ|ਵਿਆਹ|ਹਾਸਪੀਟਲ|ਐਕਸੀਡੈਂਟ|ਆਈਸੀਯੂ|"
    r"இறந்துவிட்டார்|இறந்து|காரியம்|చనిపోయారు|ತೀರಿಕೊಂಡ|মারা গেছেন|শ্রাদ্ধ|वडील गेले|दिवसकार्य", re.I)
_PRESSURE = re.compile(
    r"आज ही|अभी के अभी|आज शाम|बहाने|payment कर दीजिए|pay नहीं|जमा होनी|पेमेंट कर दीजिए|पे नहीं|"
    r"ਅੱਜ ਹੀ|ਹੁਣੇ ਦੀ ਹੁਣੇ|ਅੱਜ ਸ਼ਾਮ|ਬਹਾਨੇ|ਜਮ੍ਹਾਂ ਹੋਣੀ|இன்றே|ఈ రోజే|ಇವತ್ತೇ|আজকেই|आजच|આજે જ|ഇന്ന് തന്നെ", re.I)
_BACKOFF = re.compile(r"दुख|माफ़|माफ|sorry|बाद में|कुछ दिन बाद|अगले हफ़्ते|ਦੁੱਖ|ਮਾਫ਼|ਮਾਫ|ਬਾਅਦ|ਅਗਲੇ ਹਫ਼ਤੇ", re.I)


class LexiconJudge:
    """Keyword matching on the agent channel. Deliberately simple: this is the baseline."""

    def __init__(self) -> None:
        self.sensitive = False
        self.borrower_named_relative = False

    def on_segment(self, seg: Segment) -> list[Alert]:
        if seg.channel == BORROWER:
            self.sensitive = self.sensitive or bool(_SENSITIVE.search(seg.text))
            return []
        alerts = []
        if m := _THREAT.search(seg.text):
            alerts.append(Alert("THREAT_OR_ABUSE", seg.end_ms, f"keyword \"{m.group(0)}\" in: {seg.text[:120]}", "lexicon", 0.6, seg.index))
        if m := _THIRD.search(seg.text):
            alerts.append(Alert("THIRD_PARTY", seg.end_ms, f"keyword \"{m.group(0)}\" in: {seg.text[:120]}", "lexicon", 0.6, seg.index))
        if self.sensitive and _PRESSURE.search(seg.text) and not _BACKOFF.search(seg.text):
            alerts.append(Alert("IGNORED_SENSITIVE_SITUATION", seg.end_ms, f"pressure after a sensitive disclosure: {seg.text[:120]}", "lexicon", 0.6, seg.index))
        return alerts
