"""Live agent nudge: when a check fails mid-call, whisper a correction into the
agent's headset in their own language, using Timbre v3.0's <whispers> tag.

    python -m maryada.extras.nudge      # pre-render the fixed nudges (cached)
"""
from __future__ import annotations

from pathlib import Path

from ..common import config, timbre
from ..common.audio import write_wav
from ..common.schema import CallMeta

VOICE = "Shivani"

NUDGES = {
    "hi-en": {
        "OUTSIDE_HOURS": "<whispers> यह call permitted hours के बाहर है। कृपया विनम्रता से call समाप्त कीजिए।",
        "NO_RECORDING_DISCLOSURE": "<whispers> Recording disclosure अभी बाकी है। Borrower को बताइए कि call record हो रही है।",
        "THREAT_OR_ABUSE": "<whispers> Tone संभालिए। धमकी या अपशब्द की अनुमति नहीं है।",
        "WRONG_DUES": "<whispers> बताया गया amount record से match नहीं करता। सही बकाया {due} है।",
        "THIRD_PARTY": "<whispers> परिवार, office या social media का ज़िक्र मत कीजिए। बात सिर्फ़ borrower से कीजिए।",
        "IGNORED_SENSITIVE_SITUATION": "<whispers> Borrower मुश्किल समय में है। सहानुभूति जताइए और बाद में call करने का offer दीजिए।",
    },
    "en-IN": {  # used for languages without their own set of whispers
        "OUTSIDE_HOURS": "<whispers> This call is outside permitted hours. Please end it politely.",
        "NO_RECORDING_DISCLOSURE": "<whispers> Please tell the borrower that this call is being recorded.",
        "THREAT_OR_ABUSE": "<whispers> Watch your tone. Threats and abuse are not allowed.",
        "WRONG_DUES": "<whispers> That amount does not match the record. The correct dues are {due}.",
        "THIRD_PARTY": "<whispers> Do not mention family, office or social media. Speak only with the borrower.",
        "IGNORED_SENSITIVE_SITUATION": "<whispers> The borrower is going through a difficult time. Show sympathy and offer to call later.",
    },
    "pa-IN": {
        "OUTSIDE_HOURS": "<whispers> ਇਹ call permitted hours ਤੋਂ ਬਾਹਰ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਨਿਮਰਤਾ ਨਾਲ call ਖ਼ਤਮ ਕਰੋ।",
        "NO_RECORDING_DISCLOSURE": "<whispers> Recording disclosure ਅਜੇ ਬਾਕੀ ਹੈ। Borrower ਨੂੰ ਦੱਸੋ ਕਿ call record ਹੋ ਰਹੀ ਹੈ।",
        "THREAT_OR_ABUSE": "<whispers> Tone ਸੰਭਾਲੋ। ਧਮਕੀ ਜਾਂ ਗਾਲ੍ਹ ਦੀ ਇਜਾਜ਼ਤ ਨਹੀਂ ਹੈ।",
        "WRONG_DUES": "<whispers> ਦੱਸਿਆ ਗਿਆ amount record ਨਾਲ match ਨਹੀਂ ਕਰਦਾ। ਸਹੀ ਬਕਾਇਆ {due} ਹੈ।",
        "THIRD_PARTY": "<whispers> ਪਰਿਵਾਰ, office ਜਾਂ social media ਦਾ ਜ਼ਿਕਰ ਨਾ ਕਰੋ। ਗੱਲ ਸਿਰਫ਼ borrower ਨਾਲ ਕਰੋ।",
        "IGNORED_SENSITIVE_SITUATION": "<whispers> Borrower ਔਖੇ ਵੇਲੇ ਵਿੱਚ ਹੈ। ਹਮਦਰਦੀ ਜਤਾਓ ਤੇ ਬਾਅਦ ਵਿੱਚ call ਕਰਨ ਦਾ offer ਦਿਓ।",
    },
}


def nudge_lang(meta: CallMeta) -> str:
    return meta.language if meta.language in NUDGES else "en-IN"


def nudge_text(violation: str, meta: CallMeta) -> str:
    lang = nudge_lang(meta)
    return NUDGES[lang][violation].format(due=f"₹{meta.loan.total_due:,}")


def render(violation: str, meta: CallMeta) -> tuple[str, Path]:
    """Returns (text shown to the supervisor, wav path). Blocking; call from a worker thread."""
    text = nudge_text(violation, meta)
    lang = nudge_lang(meta)
    path = config.NUDGE_DIR / f"{violation}_{lang}_{meta.loan.total_due if violation == 'WRONG_DUES' else 0}.wav"
    if not path.exists():
        audio = timbre.synthesize(text, VOICE, lang, cache_dir=config.NUDGE_DIR / ".cache")
        write_wav(path, [audio], config.SAMPLE_RATE)
    return text.replace("<whispers> ", ""), path


if __name__ == "__main__":
    from ..bench.voice import call_ids

    seen = set()
    for cid in call_ids():
        meta = CallMeta.load(config.CALLS_DIR / f"{cid}.meta.json")
        lang = nudge_lang(meta)
        for v in NUDGES[lang]:
            if v == "WRONG_DUES" or (v, lang) not in seen:
                seen.add((v, lang))
                print(render(v, meta)[1].name, flush=True)
