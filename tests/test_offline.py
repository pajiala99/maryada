"""Checks that need no network: rules, text normalisation, audio maths, audit chain.

    .venv/bin/python -m pytest tests -q
"""
import numpy as np

from maryada.bench.evaluate import edit_distance, normalize
from maryada.bench.script_gen import rupees
from maryada.common import audio
from maryada.common.schema import AGENT, BORROWER, CallMeta, Loan, Segment
from maryada.engine import rules
from maryada.engine.classifier import parse
from maryada.extras import audit_log

LOAN = Loan("LN1", "personal loan", emi=4750, overdue_emis=2, late_fee=500, total_due=10000, days_past_due=50)


def meta(clock="11:00", window=None):
    return CallMeta("C00", f"2026-11-14T{clock}:00+05:30", "B1", "राजेश", "रोहित", "Suvidha Finance", "hi-en", LOAN, window)


def seg(channel, text, end=30_000, index=1):
    return Segment(channel, text, end - 3000, end, "hi-IN", 300, index)


def test_hours_window_and_consent():
    assert rules.check_hours(meta("11:00")) is None
    assert rules.check_hours(meta("07:59")).type == "OUTSIDE_HOURS"
    assert rules.check_hours(meta("19:00")).type == "OUTSIDE_HOURS"  # 19:00 itself is outside
    assert rules.check_hours(meta("19:40", ["19:00", "21:00"])) is None  # borrower asked for evenings
    assert rules.check_hours(meta("21:30", ["19:00", "21:00"])).type == "OUTSIDE_HOURS"


def test_amount_extraction():
    assert rules.extract_amounts("total बकाया ₹12,500 है") == [12500]
    assert rules.extract_amounts("12 हज़ार 500 रुपये") == [12500]
    assert rules.extract_amounts("2 lakh 40,000 outstanding") == [240000]
    assert rules.extract_amounts("2 EMI pending हैं, 15 तारीख तक") == []  # counts and dates are not amounts
    assert rupees(240000) == "₹2,40,000" and rupees(950) == "₹950"


def test_dues_checker():
    d = rules.DuesChecker(meta())
    assert d.on_segment(seg(AGENT, "आपकी 4750 की EMI bounce हुई है, total outstanding 10,000 है"))[1] is None
    assert d.on_segment(seg(AGENT, "total बकाया ₹16,300 है"))[1].type == "WRONG_DUES"
    # a part payment the borrower proposes may be repeated by the agent
    d = rules.DuesChecker(meta())
    d.on_segment(seg(BORROWER, "मैं फ़िलहाल 3,000 दे सकता हूँ"))
    assert d.on_segment(seg(AGENT, "ठीक है, 3,000 का part payment आज कर दीजिए"))[1] is None


def test_disclosure_tracker():
    t = rules.DisclosureTracker()
    assert not t.on_segment(seg(AGENT, "यह call record की जा रही है", end=9000))
    assert t.disclosed and not t.pending_at_end()
    t = rules.DisclosureTracker()
    assert not t.on_segment(seg(AGENT, "नमस्ते, मैं रोहित बोल रहा हूँ", end=8000))
    assert t.on_segment(seg(AGENT, "आपकी EMI pending है", end=24_000))  # deadline passed, nothing said
    assert rules.mentions_recording("ਇਹ call record ਹੋ ਰਹੀ ਹੈ") and rules.mentions_recording("कॉल रिकॉर्ड हो रही है")


def test_preferred_time():
    assert rules.preferred_time("आप please शाम छह बजे के बाद call कीजिए") == "18:00"
    assert rules.preferred_time("ਮੈਨੂੰ ਰਾਤ 8 ਵਜੇ ਤੋਂ ਬਾਅਦ ਹੀ phone ਕਰਿਆ ਕਰੋ") == "20:00"
    assert rules.preferred_time("शाम तक payment कर दूँगा") is None


def test_lexicon_ignores_borrower_and_tracks_sensitivity():
    j = rules.LexiconJudge()
    assert j.on_segment(seg(BORROWER, "चोर company है तुम्हारी, police में जाऊँगा")) == []
    assert [a.type for a in j.on_segment(seg(AGENT, "पुलिस भेजकर अंदर करवा दूँगा"))] == ["THREAT_OR_ABUSE"]
    j.on_segment(seg(BORROWER, "मेरे पिताजी का देहांत हो गया है"))
    assert "IGNORED_SENSITIVE_SITUATION" in [a.type for a in j.on_segment(seg(AGENT, "Payment आज ही चाहिए"))]
    j2 = rules.LexiconJudge()
    j2.on_segment(seg(BORROWER, "मेरे पिताजी का देहांत हो गया है"))
    assert j2.on_segment(seg(AGENT, "बहुत दुख हुआ, हम कुछ दिन बाद बात करेंगे")) == []


def test_normalize_folds_format_not_words():
    assert normalize("Total बकाया ₹12,500 है।") == normalize("total बकाया 12500 रुपये है")
    assert normalize("<sigh> हज़ार") == normalize("हजार")
    assert normalize("दो EMI") == ["2", "emi"]
    assert edit_distance(normalize("यह call record हो रही है"), normalize("यह call हो रही है")) == 1


def test_mulaw_and_snr():
    x = (0.5 * np.sin(2 * np.pi * 440 * np.arange(8000) / 8000)).astype(np.float32)
    y = audio.g711_roundtrip(x)
    assert np.max(np.abs(x - y)) < 0.03  # 8-bit companding error stays small
    # the decoder agrees with the textbook encoder
    pcm = audio.float_to_pcm16(x).astype(np.int32)
    sign = pcm < 0
    mag = np.minimum(np.abs(pcm), 32635) + 0x84
    exp = np.floor(np.log2(mag)).astype(int) - 7
    ulaw = ~((sign << 7) | (exp << 4) | ((mag >> (exp + 3)) & 0x0F)) & 0xFF
    dec = audio.mulaw_decode(ulaw.astype(np.uint8).tobytes())
    assert np.max(np.abs(dec - x)) < 0.03
    noise = np.random.default_rng(0).standard_normal(8000).astype(np.float32)
    mixed = audio.mix_at_snr(x, noise, 10.0)
    got = 20 * np.log10(audio.active_rms(x) / np.sqrt(np.mean((mixed - x) ** 2)))
    assert abs(got - 10.0) < 0.2


def test_llm_output_parsing_is_strict():
    v = parse('Sure! {"threat_or_abuse": true, "third_party": "yes", "borrower_preferred_time": "18:00", "evidence": "पुलिस"}')
    assert v["threat_or_abuse"] is True and v["third_party"] is False  # only a JSON true counts
    assert v["borrower_preferred_time"] == "18:00" and v["evidence"] == "पुलिस"
    assert parse("not json")["wrong_dues"] is False


def test_audit_chain_detects_tampering(tmp_path):
    p = tmp_path / "a.jsonl"
    log = audit_log.AuditLog(p)
    for i in range(4):
        log.append({"t": "segment", "text": f"line {i}"})
    assert audit_log.verify(p)[0]
    lines = p.read_text().splitlines()
    lines[1] = lines[1].replace("line 1", "line X")
    p.write_text("\n".join(lines) + "\n")
    ok, n, _ = audit_log.verify(p)
    assert not ok and n == 2
