"""Turn the scenario table into labelled call scripts.

    python -m maryada.bench.script_gen            # writes calls/C01.meta.json, calls/C01.truth.json, ...

Deterministic (seeded), so the benchmark is reproducible: the same seed always
yields the same 36 calls, the same loan records and the same planted violations.
"""
from __future__ import annotations

import argparse
import random
import re

from ..common import config
from ..common.schema import AGENT, BORROWER, CallMeta, CallTruth, Loan, Turn
from ..common.timbre import FEMALE, MALE
from . import lines as L

AGENT_VOICES = ["Avinash", "Prakash", "Yashraj", "Harshad"]  # Timbre's collections / BFSI voices
_TAG = re.compile(r"<[^>]+>\s*")
_GENDER = re.compile(r"\[([^|\]]*)\|([^\]]*)\]")


def rupees(n: int) -> str:
    """12500 -> '₹12,500', 240000 -> '₹2,40,000' (Indian grouping; Timbre reads it as words)."""
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return "₹" + s


def _resolve_gender(text: str, gender: str) -> str:
    return _GENDER.sub(lambda m: m.group(1) if gender == "m" else m.group(2), text)


def make_loan(rng: random.Random, idx: int) -> Loan:
    emi = rng.choice([2450, 3200, 4750, 5600, 6850, 8300, 9900, 12400])
    overdue = rng.choice([1, 2, 2, 3])
    late_fee = rng.choice([350, 500, 650, 800])
    return Loan(
        account=f"LN{rng.randint(10**7, 10**8 - 1)}",
        product=rng.choice(L.PRODUCTS),
        emi=emi, overdue_emis=overdue, late_fee=late_fee,
        total_due=emi * overdue + late_fee,
        days_past_due=overdue * 30 - rng.randint(0, 12),
    )


def build_call(idx: int, scenario: tuple, rng: random.Random) -> tuple[CallMeta, CallTruth]:
    name, lang, clock, pref_on_file, slots = scenario
    call_id = f"C{idx:02d}"
    borrower, gender = rng.choice(L.BORROWERS[lang])
    agent = rng.choice(L.AGENTS[lang])
    loan = make_loan(rng, idx)

    # An inflated figure that is on no line of the loan record, and a part payment likewise.
    wrong = int(round(loan.total_due * rng.uniform(1.3, 1.7), -2)) + 300
    part = rng.choice([1500, 2000, 3000, 4000])
    while part in loan.valid_amounts() or wrong in loan.valid_amounts():
        part += 500
        wrong += 100
    pt_start, pt_hi, pt_pa = rng.choice(L.PREF_TIMES)

    fill = {
        "name": borrower, "agent": agent, "lender": rng.choice(L.LENDERS), "product": loan.product,
        "n": L.N_WORDS[lang][loan.overdue_emis], "due": rupees(loan.total_due), "emi": rupees(loan.emi),
        "wrong": rupees(wrong), "part": rupees(part), "pt": pt_hi if lang == L.HI else pt_pa,
    }

    turns: list[Turn] = []
    violations: list[dict] = []
    stated_pref = None
    for slot in slots:
        text = _resolve_gender(rng.choice(L.LINES[slot][lang]), gender).format(**fill)
        speaker = AGENT if slot.startswith("A_") else BORROWER
        turns.append(Turn(speaker=speaker, text=text, ref=_TAG.sub("", text).strip(), slot=slot))
        if slot in L.SLOT_VIOLATION:
            violations.append({"type": L.SLOT_VIOLATION[slot], "turn_index": len(turns) - 1})
        if slot == "B_PREF_TIME":
            stated_pref = [pt_start, "21:00"]

    hh, mm = map(int, clock.split(":"))
    in_window = 8 * 60 <= hh * 60 + mm < 19 * 60
    consented = pref_on_file and pref_on_file[0] <= clock < pref_on_file[1]
    if not in_window and not consented:
        violations.append({"type": "OUTSIDE_HOURS", "turn_index": 0})

    meta = CallMeta(
        call_id=call_id, call_time=f"2026-11-{10 + idx % 5:02d}T{clock}:00+05:30",
        borrower_id=f"B{1000 + idx}", borrower_name=borrower, agent_name=agent,
        lender=fill["lender"], language=lang, loan=loan, preferred_window=pref_on_file,
    )
    truth = CallTruth(
        call_id=call_id, scenario=name, turns=turns, violations=violations,
        stated_preferred_window=stated_pref,
        voices={AGENT: rng.choice(AGENT_VOICES), BORROWER: rng.choice(MALE[1:] if gender == "m" else FEMALE)},
    )
    if truth.voices[BORROWER] == truth.voices[AGENT]:
        truth.voices[BORROWER] = "Devansh" if truth.voices[AGENT] != "Devansh" else "Shubham"
    return meta, truth


def generate(seed: int = 7, limit: int | None = None, overwrite: bool = False) -> list[str]:
    config.CALLS_DIR.mkdir(parents=True, exist_ok=True)
    ids = []
    for i, scenario in enumerate(L.SCENARIOS[:limit], start=1):
        if (config.CALLS_DIR / f"C{i:02d}.truth.json").exists() and not overwrite:
            # never rewrite an existing call: its truth file holds the turn timings the mixer measured
            ids.append(f"C{i:02d}")
            continue
        meta, truth = build_call(i, scenario, random.Random(seed * 1000 + i))
        meta.save(config.CALLS_DIR / f"{meta.call_id}.meta.json")
        truth.save(config.CALLS_DIR / f"{meta.call_id}.truth.json")
        ids.append(meta.call_id)
    return ids


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    ids = generate(a.seed, a.limit)
    print(f"wrote {len(ids)} call scripts to {config.CALLS_DIR}")
