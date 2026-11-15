"""Paraphrase probe: does the judge understand, or just match words?

    python -m maryada.bench.probe

On the main bench the keyword baseline looks as good as the LLM, because the same people
wrote the call lines and the keyword list. These 16 utterances are written the other way
round: the violations avoid every keyword, and the harmless lines contain them. That makes
the probe adversarial to keywords by construction. It is text only (no audio), so it tests
the judge and nothing else.
"""
from __future__ import annotations

import asyncio
import json

from ..common import config
from ..common.schema import AGENT, BORROWER, CallMeta, Loan, Segment
from ..engine import rules
from ..engine.classifier import LLMJudge

LOAN = Loan("LN-PROBE", "personal loan", emi=4750, overdue_emis=2, late_fee=500, total_due=10000, days_past_due=52)
META = CallMeta("P00", "2026-11-14T11:00:00+05:30", "B0", "राजेश", "रोहित", "Suvidha Finance", "hi-en", LOAN)
T, P, S, W = "THREAT_OR_ABUSE", "THIRD_PARTY", "IGNORED_SENSITIVE_SITUATION", "WRONG_DUES"

# (id, earlier lines, agent's latest utterance, violations it contains)
ITEMS: list[tuple[str, list[str], str, set[str]]] = [
    # ---- violations, phrased without any keyword
    ("threat_vague", [], "कल सुबह तक इंतज़ाम कर लो, नहीं तो ऐसा हाल करेंगे कि ज़िंदगी भर याद रखोगे।", {T}),
    ("threat_vehicle", [], "तेरी गाड़ी आज रात ही गायब हो जाएगी, समझा? और तू कुछ नहीं कर पाएगा।", {T}),
    ("threat_punjabi", [], "ਜੇ ਸੋਮਵਾਰ ਤੱਕ ਰਕਮ ਨਾ ਆਈ ਤਾਂ ਤੇਰੀ ਖ਼ੈਰ ਨਹੀਂ, ਇਹ ਗੱਲ ਯਾਦ ਰੱਖੀਂ।", {T}),
    ("inlaws", [], "आपकी सास और ससुर को भी आज खबर कर देते हैं कि बहू ने किस्त नहीं चुकाई।", {P}),
    ("hr_mail", [], "आपके HR department को mail डाल रहा हूँ, वही आपकी salary से कटवाएँगे।", {P}),
    ("spouse_school", [], "ਤੇਰੀ ਘਰਵਾਲੀ ਦੇ ਸਕੂਲ ਜਾ ਕੇ ਸਾਰੇ staff ਸਾਹਮਣੇ ਦੱਸਾਂਗੇ ਕਿ ਤੂੰ ਕਰਜ਼ਾ ਨਹੀਂ ਮੋੜਦਾ।", {P}),
    ("cremation", ["BORROWER: मेरे दादाजी आज सुबह चल बसे, हम श्मशान से लौटे ही हैं।"],
     "ठीक है, पर किस्त का क्या? दो घंटे में transfer कर दीजिए, मैं line पर हूँ।", {S}),
    ("flood", ["BORROWER: बाढ़ में हमारा पूरा घर डूब गया है, हम राहत camp में हैं।"],
     "वो सब ठीक है, लेकिन EMI तो भरनी पड़ेगी, रात तक कर दीजिए।", {S}),
    ("dues_in_words", [], "आपका कुल बकाया साढ़े सत्रह हज़ार रुपये है, यही भरना होगा।", {W}),
    # ---- harmless, but containing keywords
    ("police_form", [], "मैं police verification वाले form की बात नहीं कर रहा, बस आपकी EMI की date confirm करनी थी।", set()),
    ("brother_pays", ["BORROWER: मेरे भाई ही payment करेंगे इस बार।"],
     "ठीक है, तो आप अपने भाई से पूछकर मुझे date बता दीजिएगा।", set()),
    ("receipt_whatsapp", [], "Receipt मैं आपके WhatsApp पर भेज देता हूँ, आप office से लौटकर देख लीजिएगा।", set()),
    ("father_unwell", ["BORROWER: मेरे पिताजी hospital में हैं।"],
     "आपके पिताजी जल्दी ठीक हों। Payment की चिंता अभी मत कीजिए, आज ही नहीं, जब सुविधा हो तब बात करेंगे।", set()),
    ("no_police_punjabi", [], "ਪੁਲਿਸ ਵਾਲੀ ਕੋਈ ਗੱਲ ਨਹੀਂ ਜੀ, ਘਬਰਾਓ ਨਾ। ਮੈਂ ਸਿਰਫ਼ ਤਰੀਕ ਪੁੱਛਣ ਲਈ call ਕੀਤੀ ਹੈ।", set()),
    ("dues_right_in_words", [], "आपकी EMI चार हज़ार सात सौ पचास रुपये की है, दो EMI बाकी हैं, late fee मिलाकर कुल दस हज़ार रुपये बनते हैं।", set()),
    ("lawful_notice", [], "अगर इस महीने भी payment नहीं आई तो account NPA में चला जाएगा और company legal notice भेजेगी, यह मैं आपको पहले से बता रहा हूँ।", set()),
]


def keyword_labels(context: list[str], latest: str) -> set[str]:
    judge, dues = rules.LexiconJudge(), rules.DuesChecker(META)
    for line in context:
        seg = Segment(BORROWER, line.split(": ", 1)[1], 0, 1000)
        judge.on_segment(seg)
        dues.on_segment(seg)
    seg = Segment(AGENT, latest, 2000, 6000, index=1)
    found = {a.type for a in judge.on_segment(seg)}
    if dues.on_segment(seg)[1]:
        found.add(W)
    return found


async def llm_labels(context: list[str], latest: str, judge: LLMJudge) -> set[str]:
    v = await judge.judge(context, latest) or {}
    keys = {"threat_or_abuse": T, "third_party": P, "ignored_sensitive": S, "wrong_dues": W}
    return {label for key, label in keys.items() if v.get(key)}


def tally(rows: list[dict], who: str) -> dict:
    tp = sum(len(set(r[who]) & set(r["expected"])) for r in rows)
    fp = sum(len(set(r[who]) - set(r["expected"])) for r in rows)
    fn = sum(len(set(r["expected"]) - set(r[who])) for r in rows)
    return {"exact": sum(set(r[who]) == set(r["expected"]) for r in rows), "of": len(rows), "tp": tp, "fp": fp, "fn": fn}


async def main() -> None:
    judge = LLMJudge(META) if config.LLM_ENABLED else None
    rows = []
    for item_id, context, latest, expected in ITEMS:
        row = {"id": item_id, "utterance": latest, "expected": sorted(expected), "keywords": sorted(keyword_labels(context, latest))}
        if judge:
            row["llm"] = sorted(await llm_labels(context, latest, judge))
        rows.append(row)
        print(f"{item_id:20s} expected {row['expected'] or '-'}  keywords {row['keywords'] or '-'}  llm {row.get('llm', 'n/a') or '-'}", flush=True)
    if judge:
        await judge.close()
    summary = {"keywords": tally(rows, "keywords"), **({"llm": tally(rows, "llm"), "llm_model": config.LLM_MODEL} if judge else {})}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "probe.json").write_text(json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    asyncio.run(main())
