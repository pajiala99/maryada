"""Score the monitor against the planted ground truth.

    python -m maryada.bench.evaluate

For every (speech model, judge, noise level) found under out/events/ it reports:
  * WER and CER per channel, against the script the audio was generated from
  * precision / recall / F1 per violation type, at call level
  * how often an alert landed on the turn that actually contained the breach
  * whether each call's overall verdict (clean / not clean) was right
Writes results/results.json and results/RESULTS.md.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..common import config
from ..common.schema import AGENT, BORROWER, VIOLATION_TYPES, CallTruth

try:
    from rapidfuzz.distance import Levenshtein

    def edit_distance(a: list, b: list) -> int:
        return Levenshtein.distance(a, b)

    def insertions(ref: list, hyp: list) -> int:
        return sum(op.tag == "insert" for op in Levenshtein.editops(ref, hyp))
except ImportError:  # pure-Python fallback
    def insertions(ref: list, hyp: list) -> int:
        return max(0, len(hyp) - len(ref))

    def edit_distance(a: list, b: list) -> int:
        prev = list(range(len(b) + 1))
        for i, x in enumerate(a, 1):
            cur = [i]
            for j, y in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
            prev = cur
        return prev[-1]

# ------------------------------------------------------------ normalisation
_KEEP = re.compile(r"[^0-9a-zऀ-ॿ਀-੿ ]+")
_CURRENCY = re.compile(r"₹|\brs\.?\b|\binr\b|रुपये|रुपए|रुपया|रूपये|ਰੁਪਏ|ਰੁਪਿਆ|ਰੁਪਈਏ|rupees?")
_SMALL = {"एक": "1", "दो": "2", "तीन": "3", "ਇੱਕ": "1", "ਦੋ": "2", "ਤਿੰਨ": "3"}
_FOLD = str.maketrans({"़": None, "਼": None,  # nukta: ज़ -> ज
                       "ँ": "ं", "ਁ": "ਂ", "ੰ": "ਂ",  # chandrabindu / tippi -> bindu
                       "।": " ", "॥": " "})  # danda


def normalize(text: str) -> list[str]:
    """Fold away differences that are not recognition errors: punctuation, case, nukta, ₹ signs, digit grouping."""
    t = unicodedata.normalize("NFC", text).lower()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = _CURRENCY.sub(" ", t)
    t = unicodedata.normalize("NFD", t).translate(_FOLD)
    t = unicodedata.normalize("NFC", _KEEP.sub(" ", t.replace("-", " ")))
    return [_SMALL.get(w, w) for w in t.split()]


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if (p is not None and r is not None) else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def score_run(event_dir: Path, ids: set[str] | None = None) -> dict | None:
    files = [f for f in sorted(event_dir.glob("*.events.jsonl")) if ids is None or f.name.split(".")[0] in ids]
    if not files:
        return None
    counts = {t: [0, 0, 0] for t in VIOLATION_TYPES}  # tp, fp, fn
    err = {AGENT: [0, 0], BORROWER: [0, 0]}  # word errors, ref words
    cerr = {AGENT: [0, 0], BORROWER: [0, 0]}
    extra = {AGENT: 0, BORROWER: 0}  # words in the transcript that nobody on that channel said
    verdict_ok = localised = localisable = pref_n = pref_ok = llm_fallbacks = 0
    latencies, misses, false_alarms = [], [], []

    for f in files:
        cid = f.name.split(".")[0]
        truth = CallTruth.load(config.CALLS_DIR / f"{cid}.truth.json")
        events = [json.loads(line) for line in f.read_text().splitlines()]
        alerts = [e for e in events if e["t"] == "alert"]
        segs = sorted((e for e in events if e["t"] == "segment"), key=lambda e: e["start_ms"])
        summary = next(e for e in events if e["t"] == "summary")

        for ch in (AGENT, BORROWER):
            ref = normalize(" ".join(t.ref for t in truth.turns if t.speaker == ch))
            hyp = normalize(" ".join(s["text"] for s in segs if s["channel"] == ch))
            err[ch][0] += edit_distance(ref, hyp)
            err[ch][1] += len(ref)
            extra[ch] += insertions(ref, hyp)
            rc, hc = list("".join(ref)), list("".join(hyp))
            cerr[ch][0] += edit_distance(rc, hc)
            cerr[ch][1] += len(rc)
        latencies += [s["latency_ms"] for s in segs if s.get("latency_ms")]
        llm_fallbacks += summary.get("llm_failures", 0)

        want, got = truth.violation_types(), {a["type"] for a in alerts}
        for t in VIOLATION_TYPES:
            counts[t][0] += t in want and t in got
            counts[t][1] += t not in want and t in got
            counts[t][2] += t in want and t not in got
        misses += [f"{cid}:{t}" for t in sorted(want - got)]
        false_alarms += [f"{cid}:{t}" for t in sorted(got - want)]
        verdict_ok += (not want) == summary["compliant"]

        for v in truth.violations:
            if v["type"] in ("OUTSIDE_HOURS", "NO_RECORDING_DISCLOSURE"):
                continue  # these belong to the call, not to one turn
            turn = truth.turns[v["turn_index"]]
            localisable += 1
            localised += any(a["type"] == v["type"] and turn.start_ms - 1500 <= a["ms"] <= turn.end_ms + 4000 for a in alerts)

        if truth.stated_preferred_window:
            pref_n += 1
            pref_ok += summary.get("preferred_time") == truth.stated_preferred_window[0]

    tot = [sum(c[i] for c in counts.values()) for i in range(3)]
    w = lambda d, ch: d[ch][0] / d[ch][1] if d[ch][1] else None  # noqa: E731
    allw = lambda d: (d[AGENT][0] + d[BORROWER][0]) / max(1, d[AGENT][1] + d[BORROWER][1])  # noqa: E731
    return {
        "n_calls": len(files),
        "wer": {"agent": w(err, AGENT), "borrower": w(err, BORROWER), "all": allw(err)},
        "cer": {"agent": w(cerr, AGENT), "borrower": w(cerr, BORROWER), "all": allw(cerr)},
        # WER split in two: words that were said but lost or changed, and words that were never said
        "missed": {ch: (err[ch][0] - extra[ch]) / err[ch][1] for ch in (AGENT, BORROWER)},
        "extra": {ch: extra[ch] / err[ch][1] for ch in (AGENT, BORROWER)},
        "per_type": {t: _prf(*c) for t, c in counts.items()},
        "micro": _prf(*tot),
        "verdict_accuracy": verdict_ok / len(files),
        "localised": localised / localisable if localisable else None,
        "preferred_time": {"n": pref_n, "correct": pref_ok},
        "stt_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "llm_fallbacks": llm_fallbacks,  # utterances judged by keywords because the LLM was unavailable
        "misses": misses, "false_alarms": false_alarms,
    }


CORE_LANGUAGES = {"hi-en", "pa-IN"}  # the main benchmark: 36 Hinglish and Punjabi calls


def evaluate() -> dict:
    metas = {p.name.split(".")[0]: json.loads(p.read_text())["language"] for p in sorted(config.CALLS_DIR.glob("C*.meta.json"))}
    core = {cid for cid, lang in metas.items() if lang in CORE_LANGUAGES}
    by_lang: dict[str, set[str]] = defaultdict(set)
    for cid, lang in metas.items():
        if lang not in CORE_LANGUAGES:
            by_lang[lang].add(cid)
    truths = [CallTruth.load(p) for p in sorted(config.CALLS_DIR.glob("C*.truth.json")) if p.name.split(".")[0] in core]
    positives = defaultdict(int)
    for t in truths:
        for v in t.violation_types():
            positives[v] += 1
    runs, more_languages = [], []
    root = config.OUT_DIR / "events"
    for stt_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        for judge_dir in sorted(p for p in stt_dir.glob("*") if p.is_dir()):
            for variant, snr in config.VARIANTS.items():
                if r := score_run(judge_dir / variant, core):
                    runs.append({"stt": stt_dir.name, "judge": judge_dir.name, "variant": variant, "snr_db": snr, **r})
                more = set().union(*by_lang.values()) if by_lang else set()
                if more and (r := score_run(judge_dir / variant, more)):
                    entry = {"stt": stt_dir.name, "judge": judge_dir.name, "variant": variant, "snr_db": snr,
                             "all": {k: r[k] for k in ("n_calls", "micro", "verdict_accuracy", "per_type", "wer", "stt_latency_ms")}, "by_language": {}}
                    for lang, ids in sorted(by_lang.items()):
                        if x := score_run(judge_dir / variant, ids):
                            entry["by_language"][lang] = {k: x[k] for k in ("n_calls", "micro", "verdict_accuracy", "wer")}
                    more_languages.append(entry)
    return {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "calls": len(truths), "clean_calls": sum(not t.violations for t in truths),
        "positives": {t: positives[t] for t in VIOLATION_TYPES}, "runs": runs,
        "more_languages": {"calls": sum(len(v) for v in by_lang.values()), "languages": sorted(by_lang), "runs": more_languages},
    }


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def to_markdown(res: dict) -> str:
    out = [f"# Maryada benchmark results\n\nGenerated {res['generated']}. {res['calls']} synthetic calls "
           f"({res['clean_calls']} with no violation). Planted violations: "
           + ", ".join(f"{t} ×{n}" for t, n in res["positives"].items()) + ".\n"]
    groups = defaultdict(list)
    for r in res["runs"]:
        groups[(r["stt"], r["judge"])].append(r)
    for (stt, judge), rs in groups.items():
        note = "  **(mock transcripts: pipeline test only, not a result)**" if stt == "mock" else ""
        out.append(f"\n## {stt} + {judge} judge{note}\n")
        out.append("| Noise | Calls | WER agent | WER borrower | CER | Precision | Recall | F1 | Verdict acc. | Alert on right turn |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rs:
            m = r["micro"]
            label = "clean line" if r["snr_db"] is None else f"{r['snr_db']:.0f} dB SNR"
            out.append(f"| {label} | {r['n_calls']} | {_pct(r['wer']['agent'])} | {_pct(r['wer']['borrower'])} | {_pct(r['cer']['all'])} "
                       f"| {_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['f1'])} | {_pct(r['verdict_accuracy'])} | {_pct(r['localised'])} |")
        out.append("\nRecall by violation type (detected / planted):\n")
        out.append("| Noise | " + " | ".join(VIOLATION_TYPES) + " |")
        out.append("|---|" + "---|" * len(VIOLATION_TYPES))
        for r in rs:
            label = "clean" if r["snr_db"] is None else f"{r['snr_db']:.0f} dB"
            cells = [f"{c['tp']}/{c['tp'] + c['fn']}" + (f" (+{c['fp']} false)" if c["fp"] else "") for c in r["per_type"].values()]
            out.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    res = evaluate()
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    md = to_markdown(res)
    (config.RESULTS_DIR / "RESULTS.md").write_text(md)
    print(md)
