"""Timbre v3.0 client (REST inference), used by the bench to voice calls and by
the engine to whisper nudges to the agent.

We ask for container=mulaw: Timbre then returns raw G.711 mu-law at 8 kHz, i.e.
audio that has already been through a telephone codec. Results are cached on
disk by content hash so re-running the bench costs no credits.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
import numpy as np

from . import config
from .audio import mulaw_decode

URL = f"{config.GNANI_BASE_URL}/api/v1/tts/inference"

# Timbre v3.0 catalogue (every voice speaks all ten languages).
FEMALE = ["Shivani", "Lakshmi", "Kalpana", "Chetana", "Vasudha", "Riyaa", "Tarika"]
MALE = ["Avinash", "Shubham", "Prakash", "Devansh", "Yashraj", "Harshad"]
AUDIO_TAGS = ["laugh", "giggle", "sigh", "exhales", "sniffles", "yawns", "coughs", "clears throat",
              "whispers", "shouting", "excited", "slow", "pauses"]


class TimbreError(RuntimeError):
    pass


def _cache_path(payload: dict, cache_dir: Path) -> Path:
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    return cache_dir / f"{key}.ulaw"


def synthesize(text: str, voice: str, language: str, *, speed: float = 1.0,
               cache_dir: Path | None = None, client: httpx.Client | None = None) -> np.ndarray:
    """Text -> float32 mono at 8 kHz. Retries on 429 (accounts may allow one active request)."""
    payload = {
        "text": text, "voice": voice, "model": config.TTS_MODEL, "language": language, "speed": speed,
        "audio_config": {"container": "mulaw", "sample_rate": 8000, "num_channels": 1, "sample_width": 2},
    }
    if os.environ.get("MARYADA_MOCK") == "1":
        # Offline development: a hum as long as the line would take to say. Never cached, never a result.
        n = int(8000 * max(0.6, len(text) / 16))
        return (0.2 * np.sin(2 * np.pi * 180 * np.arange(n) / 8000) * np.hanning(n)).astype(np.float32)
    cache_dir = cache_dir or config.TTS_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(payload, cache_dir)
    if path.exists():
        return mulaw_decode(path.read_bytes())

    headers = {"X-API-Key-ID": config.require_gnani(), "Content-Type": "application/json"}
    own = client is None
    client = client or httpx.Client(timeout=120)
    try:
        delay = 1.0
        for attempt in range(10):
            try:
                r = client.post(URL, headers=headers, json=payload)
            except httpx.HTTPError:  # flaky TLS / dropped connection: same request is safe to resend
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            if r.status_code == 200 and r.content:
                path.write_bytes(r.content)
                return mulaw_decode(r.content)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            raise TimbreError(f"Timbre {r.status_code}: {r.text[:300]}")
        raise TimbreError("Timbre still failing after retries")
    finally:
        if own:
            client.close()
