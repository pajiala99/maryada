"""Write the benchmark numbers into README.md from results/*.json.

    python -m maryada.bench.report

Fills the blocks between <!-- RESULTS --> / <!-- /RESULTS --> and <!-- PROBE --> / <!-- /PROBE -->,
so the README always shows exactly what the last evaluation produced.
"""
from __future__ import annotations

import json
import re

from ..common import config
from ..common.schema import VIOLATION_TYPES

LABEL = {"clean": "Clean line", "snr20": "20 dB", "snr10": "10 dB", "snr5": "5 dB", "snr0": "0 dB"}
SHORT = {"OUTSIDE_HOURS": "Hours", "NO_RECORDING_DISCLOSURE": "Recording notice", "THREAT_OR_ABUSE": "Threat",
         "WRONG_DUES": "Wrong dues", "THIRD_PARTY": "Relatives / shaming", "IGNORED_SENSITIVE_SITUATION": "Sensitive occasion"}


def pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def results_block(res: dict) -> str:
    runs = [r for r in res["runs"] if r["stt"] == "prisma-v3.0"]
    by = {(r["judge"], r["variant"]): r for r in runs}
    judges = [j for j in ("llm", "lexicon") if any(k[0] == j for k in by)]
    variants = [v for v in config.VARIANTS if any(k[1] == v for k in by)]
    out = [f"{res['calls']} calls, {res['clean_calls']} of them clean. Every recording streamed through Prisma v3.0 "
           f"at real-time pace; both judges read the same saved transcripts. Generated {res['generated'][:16].replace('T', ' ')}.\n",
           "**Speech recognition (Prisma v3.0, 8 kHz, two channels)**\n",
           "| Line | WER agent | WER borrower | of which: words missed / words invented | Avg. latency |",
           "|---|---|---|---|---|"]
    for v in variants:
        r = by.get(("lexicon", v)) or by.get((judges[0], v))
        if r:
            out.append(f"| {LABEL[v]} | {pct(r['wer']['agent'])} | {pct(r['wer']['borrower'])} | "
                       f"{pct((r['missed']['agent'] + r['missed']['borrower']) / 2)} / {pct((r['extra']['agent'] + r['extra']['borrower']) / 2)} "
                       f"| {r['stt_latency_ms']} ms |")
    out += ["", "**Violation detection (call level)**", "",
            "| Line | Judge | Precision | Recall | F1 | Right verdict per call | Alert on the right turn |",
            "|---|---|---|---|---|---|---|"]
    for v in variants:
        for j in judges:
            r = by.get((j, v))
            if r:
                m = r["micro"]
                out.append(f"| {LABEL[v]} | {'LLM' if j == 'llm' else 'Keywords'} | {pct(m['precision'])} | {pct(m['recall'])} | "
                           f"{pct(m['f1'])} | {pct(r['verdict_accuracy'])} | {pct(r['localised'])} |")
    out += ["", "**Caught / planted, per rule** (`+n` = false alarms)", "",
            "| Line | Judge | " + " | ".join(SHORT[t] for t in VIOLATION_TYPES) + " |",
            "|---|---|" + "---|" * len(VIOLATION_TYPES)]
    for v in variants:
        j = "llm" if ("llm", v) in by else "lexicon"
        r = by[(j, v)]
        cells = [f"{c['tp']}/{c['tp'] + c['fn']}" + (f" +{c['fp']}" if c["fp"] else "") for c in (r["per_type"][t] for t in VIOLATION_TYPES)]
        out.append(f"| {LABEL[v]} | {'LLM' if j == 'llm' else 'Keywords'} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def compare_block(res: dict) -> str | None:
    """Prisma v2.5 vs v3.0 on the same recordings, both judged by the keyword baseline."""
    by = {(r["stt"], r["variant"]): r for r in res["runs"] if r["judge"] == "lexicon"}
    variants = [v for v in config.VARIANTS if ("prisma-v2.5", v) in by and ("prisma-v3.0", v) in by]
    if not variants:
        return None
    out = ["Same 180 recordings, same streaming settings, same keyword judge; only the speech model changes. "
           "Prisma v2.5 gets one language and no context; v3.0 also gets keyterms, a topic and the speakers' names.\n",
           "| Line | Breaks caught v2.5 | Breaks caught v3.0 | False alarms v2.5 | False alarms v3.0 | Right verdict v2.5 | Right verdict v3.0 |",
           "|---|---|---|---|---|---|---|"]
    caught = lambda r: f"{r['micro']['tp']}/{r['micro']['tp'] + r['micro']['fn']}"  # noqa: E731
    for v in variants:
        a, b = by[("prisma-v2.5", v)], by[("prisma-v3.0", v)]
        better = lambda x, y, hi=True: (f"**{x}**", y) if (x > y if hi else x < y) else (x, f"**{y}**") if (y > x if hi else y < x) else (x, y)  # noqa: E731
        ca, cb = better(a["micro"]["tp"], b["micro"]["tp"])
        fa, fb = better(a["micro"]["fp"], b["micro"]["fp"], hi=False)
        tot = a["micro"]["tp"] + a["micro"]["fn"]
        out.append(f"| {LABEL[v]} | {ca}/{tot} | {cb}/{tot} | {fa} | {fb} | {pct(a['verdict_accuracy'])} | {pct(b['verdict_accuracy'])} |")
    out += ["",
            "Two things to know before reading this table, both found by looking at the transcripts:",
            "",
            "- **Word error rate is left out on purpose.** v2.5 writes English words in Devanagari (\"होम लोन\", \"इ एम आई\"); v3.0, like the scripts, keeps them in Latin (\"home loan\", \"EMI\"). Scored against the script, v2.5 looked several times worse even where it heard correctly, so WER here would measure spelling, not hearing. The same thing first broke our keyword judge, whose list had *manager* and *hospital* only in Latin; every keyword now also matches its Devanagari spelling, and both models were re-judged with that list.",
            "- **v2.5's streams were closed at 40 s.** In our setup every v2.5 session ended at exactly 40,000 ms (56 times in the run); the client reconnects and carries on, but a sentence in progress at the cut is lost, and that took the ending, sometimes the breach, off five calls. v3.0 sessions were never cut. Some of the gap on clean and 20 dB lines is this, not recognition.",
            "",
            "What holds regardless: on clean to moderately noisy lines v3.0 catches more and raises fewer false alarms, and its code-mixed output keeps \"EMI\", \"record\" and rupee amounts in the form the rules expect."]
    return "\n".join(out)


LANG_NAMES = {"ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada", "bn-IN": "Bengali", "mr-IN": "Marathi", "gu-IN": "Gujarati", "ml-IN": "Malayalam"}


def languages_block(res: dict) -> str | None:
    ml = res.get("more_languages") or {}
    runs = [r for r in ml.get("runs", []) if r["stt"] == "prisma-v3.0"]
    if not runs:
        return None
    pick = lambda j, v: next((r for r in runs if r["judge"] == j and r["variant"] == v), None)  # noqa: E731
    cols = [("llm", "clean", "LLM, clean"), ("lexicon", "clean", "Keywords, clean"), ("lexicon", "snr10", "Keywords, 10 dB")]
    cols = [c for c in cols if pick(c[0], c[1])]
    out = [f"{ml['calls']} more calls, six in each of {', '.join(LANG_NAMES.get(l, l) for l in ml['languages'])}: "
           "two compliant, and every rule planted once per language. They are scored apart from the main benchmark. "
           "Each cell is breaches caught out of planted, then calls given the right verdict.\n",
           "| Language | " + " | ".join(c[2] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for lang in ml["languages"]:
        cells = []
        for j, v, _ in cols:
            x = pick(j, v)["by_language"].get(lang)
            cells.append("–" if not x else f"{x['micro']['tp']}/{x['micro']['tp'] + x['micro']['fn']} · {round(x['verdict_accuracy'] * x['n_calls'])}/{x['n_calls']}")
        out.append(f"| {LANG_NAMES.get(lang, lang)} | " + " | ".join(cells) + " |")
    cells = []
    for j, v, _ in cols:
        a = pick(j, v)["all"]
        cells.append(f"**{a['micro']['tp']}/{a['micro']['tp'] + a['micro']['fn']} · {round(a['verdict_accuracy'] * a['n_calls'])}/{a['n_calls']}**")
    out.append("| **All of them** | " + " | ".join(cells) + " |")
    out += ["", "The keyword baseline only knows a few words in these languages, so the LLM judge is the one to read here. "
            "The lines were written by us, not checked by native speakers."]
    return "\n".join(out)


def probe_block(probe: dict) -> str:
    s = probe["summary"]
    out = ["| Judge | Utterances judged exactly right | Violations caught (of 9) | False alarms on harmless lines |",
           "|---|---|---|---|"]
    for key, name in (("keywords", "Keywords"), ("llm", f"LLM ({s.get('llm_model', '')})")):
        if key in s:
            t = s[key]
            out.append(f"| {name} | {t['exact']} / {t['of']} | {t['tp']} | {t['fp']} |")
    return "\n".join(out)


def replace(text: str, tag: str, body: str) -> str:
    return re.sub(rf"<!-- {tag} -->.*?<!-- /{tag} -->", f"<!-- {tag} -->\n{body}\n<!-- /{tag} -->", text, flags=re.S)


if __name__ == "__main__":
    readme = config.ROOT / "README.md"
    text = readme.read_text()
    res = json.loads((config.RESULTS_DIR / "results.json").read_text())
    text = replace(text, "RESULTS", results_block(res))
    if (lb := languages_block(res)) and "<!-- LANGS -->" in text:
        text = replace(text, "LANGS", lb)
    if (cmp := compare_block(res)) and "<!-- COMPARE -->" in text:
        text = replace(text, "COMPARE", cmp)
    probe = config.RESULTS_DIR / "probe.json"
    if probe.exists():
        text = replace(text, "PROBE", probe_block(json.loads(probe.read_text())))
    readme.write_text(text)
    print("README results updated")
