"""Small audio toolbox: WAV I/O, G.711 mu-law, telephone band-pass, levels.

numpy/scipy only (the stdlib `audioop` module is gone in Python 3.13).
All signals are float32 in [-1, 1] unless a function says PCM16.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy import signal

_MU = 255.0


def pcm16_to_float(pcm: np.ndarray) -> np.ndarray:
    return pcm.astype(np.float32) / 32768.0


def float_to_pcm16(x: np.ndarray) -> np.ndarray:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")


def mulaw_decode(data: bytes) -> np.ndarray:
    """Raw G.711 mu-law bytes -> float32. This is what Timbre returns for container=mulaw."""
    u = np.frombuffer(data, dtype=np.uint8).astype(np.int16)
    u = ~u & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample = sample - 0x84
    pcm = np.where(sign != 0, -sample, sample).astype(np.int16)
    return pcm16_to_float(pcm)


def g711_roundtrip(x: np.ndarray) -> np.ndarray:
    """Compand to 8 bits and back, as a phone line does to whatever reaches it (noise included)."""
    y = np.sign(x) * np.log1p(_MU * np.abs(np.clip(x, -1, 1))) / np.log1p(_MU)
    q = np.round((y + 1) / 2 * 255) / 255 * 2 - 1
    return (np.sign(q) * ((1 + _MU) ** np.abs(q) - 1) / _MU).astype(np.float32)


def telephone_band(x: np.ndarray, sr: int = 8000) -> np.ndarray:
    """300-3400 Hz, the PSTN voice band."""
    sos = signal.butter(4, [300, 3400], btype="bandpass", fs=sr, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x
    g = np.gcd(sr_from, sr_to)
    return signal.resample_poly(x, sr_to // g, sr_from // g).astype(np.float32)


def active_rms(x: np.ndarray, sr: int = 8000, frame_ms: int = 20) -> float:
    """RMS over frames that actually contain speech, so silence does not dilute the level."""
    n = max(1, sr * frame_ms // 1000)
    if len(x) < n:
        return float(np.sqrt(np.mean(x**2) + 1e-12))
    frames = x[: len(x) // n * n].reshape(-1, n)
    e = np.sqrt(np.mean(frames**2, axis=1))
    thresh = max(e.max() * 0.05, 1e-4)
    act = e[e > thresh]
    return float(np.sqrt(np.mean(act**2))) if len(act) else float(e.mean() + 1e-9)


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float, sr: int = 8000) -> np.ndarray:
    """Add `noise` so that active-speech power over noise power equals snr_db."""
    if len(noise) < len(speech):
        noise = np.tile(noise, int(np.ceil(len(speech) / len(noise))))
    noise = noise[: len(speech)]
    s = active_rms(speech, sr)
    n = float(np.sqrt(np.mean(noise**2) + 1e-12))
    gain = s / (n * 10 ** (snr_db / 20))
    return (speech + gain * noise).astype(np.float32)


def write_wav(path: Path, channels: list[np.ndarray], sr: int = 8000) -> None:
    n = max(len(c) for c in channels)
    data = np.zeros((n, len(channels)), dtype="<i2")
    for i, c in enumerate(channels):
        data[: len(c), i] = float_to_pcm16(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(channels))
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def read_wav(path: Path) -> tuple[list[np.ndarray], int]:
    """Returns ([channel0, channel1, ...] as float32, sample_rate)."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM")
        sr, nch = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, nch)
    return [pcm16_to_float(data[:, i]) for i in range(nch)], sr


def duration_ms(x: np.ndarray, sr: int = 8000) -> int:
    return int(len(x) * 1000 / sr)
