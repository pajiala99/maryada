"""Lay voiced turns onto a two-channel call recording and degrade it.

    python -m maryada.bench.mixer [--ids C01] [--variants clean snr10]

Output: calls/<variant>/<id>.wav, stereo 8 kHz PCM16, L = agent, R = borrower,
which is how dialers record ("dual-channel"). The turn start/end times are
written back into calls/<id>.truth.json.

Noise is added *before* the telephone band-pass and G.711 companding, because
that is the order on a real line: the room is noisy, then the codec squeezes it.
The same noise realisation is reused at every SNR for a call, so only the level
changes between variants.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import signal

from ..common import config
from ..common.audio import (active_rms, g711_roundtrip, mix_at_snr, telephone_band, write_wav)
from ..common.schema import AGENT, CallTruth
from .voice import call_ids, voice_call

SR = config.SAMPLE_RATE
TARGET_RMS = 0.08  # about -22 dBFS on active speech
LOUD_SLOTS = {"A_THREAT", "B_ANGRY"}


def _ms(n_ms: float) -> int:
    return int(SR * n_ms / 1000)


def assemble(call_id: str, clips: list[np.ndarray], rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, CallTruth]:
    """Sequential turns with natural gaps; an angry turn cuts in early."""
    truth = CallTruth.load(config.CALLS_DIR / f"{call_id}.truth.json")
    cursor = _ms(600)
    placed = []
    for turn, clip in zip(truth.turns, clips):
        level = TARGET_RMS * (1.6 if turn.slot in LOUD_SLOTS else 1.0)
        clip = clip * (level / max(active_rms(clip, SR), 1e-6))
        gap = _ms(rng.uniform(60, 150) if turn.slot in LOUD_SLOTS else rng.uniform(280, 750))
        start = cursor + gap
        placed.append((turn, clip, start))
        cursor = start + len(clip)
        turn.start_ms = int(start * 1000 / SR)
        turn.end_ms = int(cursor * 1000 / SR)
    total = cursor + _ms(1500)
    agent, borrower = np.zeros(total, np.float32), np.zeros(total, np.float32)
    for turn, clip, start in placed:
        (agent if turn.speaker == AGENT else borrower)[start:start + len(clip)] += clip
    truth.save(config.CALLS_DIR / f"{call_id}.truth.json")
    return agent, borrower, truth


# --------------------------------------------------------------------- noise
def far_field(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Speech from across a room: the highs are gone and reverberation smears the syllables.

    The first version of this bench mixed in other calls at full clarity. Prisma then did exactly
    what it should with a clearly audible second speaker: it transcribed them. A headset on a
    call-centre floor picks up neighbours as a murmur, which is what this models.
    """
    sos = signal.butter(2, 2200, btype="lowpass", fs=SR, output="sos")
    n_ir = int(0.4 * SR)
    ir = rng.standard_normal(n_ir) * np.exp(-np.arange(n_ir) / (0.1 * SR))
    ir[0] = 0.3  # weak direct path, mostly reflections
    return signal.fftconvolve(signal.sosfilt(sos, x), ir)[: len(x)].astype(np.float32)


def babble(pool: list[np.ndarray], n: int, rng: np.random.Generator, voices: int = 8) -> np.ndarray:
    """Call-centre floor: several other synthetic speakers talking at once, heard from a distance."""
    out = np.zeros(n, np.float32)
    for _ in range(voices):
        stream, filled = np.zeros(n, np.float32), int(rng.integers(0, SR))
        while filled < n:
            clip = pool[int(rng.integers(len(pool)))]
            m = min(len(clip), n - filled)
            stream[filled:filled + m] = clip[:m] * rng.uniform(0.5, 1.0)
            filled += m + int(rng.integers(0, SR // 2))
        out += stream
    out = far_field(out, rng)
    return out / (np.sqrt(np.mean(out**2)) + 1e-9)


def hiss(n: int, rng: np.random.Generator) -> np.ndarray:
    """Broadband room noise (air-conditioning, fans, tyres on a road): pink spectrum."""
    spec = np.fft.rfft(rng.standard_normal(n))
    spec /= np.sqrt(np.maximum(np.arange(len(spec)), 1))
    x = np.fft.irfft(spec, n).astype(np.float32)
    return x / (np.sqrt(np.mean(x**2)) + 1e-9)


def street(n: int, rng: np.random.Generator) -> np.ndarray:
    """Roadside: engine rumble, broadband hiss and the odd horn."""
    white = rng.standard_normal(n).astype(np.float32)
    brown = np.cumsum(white)
    brown -= np.convolve(brown, np.ones(400) / 400, mode="same")  # remove drift
    brown /= np.abs(brown).max() + 1e-9
    t = np.arange(n) / SR
    rumble = brown * (0.6 + 0.4 * np.sin(2 * np.pi * 0.23 * t + rng.uniform(0, 6)))
    out = rumble + 0.12 * white
    for _ in range(max(1, n // (SR * 6))):
        start, dur = int(rng.integers(0, max(1, n - SR))), int(rng.uniform(0.25, 0.8) * SR)
        tt = np.arange(min(dur, n - start)) / SR
        f = rng.choice([390, 440, 520])
        horn = sum(np.sin(2 * np.pi * f * k * tt) / k for k in (1, 2, 3)) * np.hanning(len(tt))
        out[start:start + len(tt)] += 0.9 * horn.astype(np.float32)
    return (out / (np.sqrt(np.mean(out**2)) + 1e-9)).astype(np.float32)


def line(x: np.ndarray) -> np.ndarray:
    """What the telephone network does to a signal."""
    return g711_roundtrip(np.clip(telephone_band(x, SR), -1, 1))


def render(call_ids_: list[str], variants: list[str]) -> None:
    all_ids = call_ids()
    clips = {cid: voice_call(cid) for cid in all_ids}  # cached after bench.voice
    for cid in call_ids_:
        seed = int(cid[1:])
        agent, borrower, truth = assemble(cid, clips[cid], np.random.default_rng(seed))
        pool = [c for other, cs in clips.items() if other != cid for c in cs]
        nrng = np.random.default_rng(1000 + seed)
        n = len(agent)
        # agent sits on a call-centre floor: distant chatter plus air-conditioning
        floor = babble(pool, n, nrng) + 0.7 * hiss(n, nrng)
        # borrowers answer from the roadside (even ids) or a busy home or shop (odd ids)
        road = street(n, nrng) + 0.7 * hiss(n, nrng)
        borrower_noise = road if seed % 2 == 0 else babble(pool, n, nrng, voices=5) + 0.5 * road
        # Levels are set inside the telephone band, so "10 dB" is the ratio the line actually
        # carries: rumble below 300 Hz does not get to make the number look worse than it is.
        floor, borrower_noise = telephone_band(floor, SR), telephone_band(borrower_noise, SR)
        agent_band, borrower_band = telephone_band(agent, SR), telephone_band(borrower, SR)
        for v in variants:
            snr = config.VARIANTS[v]
            if snr is None:
                a, b = agent, borrower
            else:
                a = g711_roundtrip(np.clip(mix_at_snr(agent_band, floor, snr, SR), -1, 1))
                b = g711_roundtrip(np.clip(mix_at_snr(borrower_band, borrower_noise, snr, SR), -1, 1))
            write_wav(config.CALLS_DIR / v / f"{cid}.wav", [a, b], SR)
        print(f"{cid}: {len(agent) / SR:.1f}s, {len(truth.turns)} turns, variants {variants}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--variants", nargs="*", default=list(config.VARIANTS))
    a = ap.parse_args()
    render(a.ids or call_ids(), a.variants)
