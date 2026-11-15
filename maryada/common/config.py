"""Settings, read once from the environment (.env at the repo root)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


GNANI_API_KEY = _get("GNANI_API_KEY")
GNANI_BASE_URL = _get("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/")
STT_WS_URL = GNANI_BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/stt/v3/stream"
STT_MODEL = _get("STT_MODEL", "prisma-v3.0")
TTS_MODEL = _get("TTS_MODEL", "timbre-v3.0")
MAX_STT_SESSIONS = int(_get("MAX_STT_SESSIONS", "4") or 4)

# Any OpenAI-compatible endpoint. Pointing LLM_BASE_URL at a vLLM server that
# hosts Evon v3.3 is the whole migration.
LLM_BASE_URL = _get("LLM_BASE_URL").rstrip("/")
LLM_API_KEY = _get("LLM_API_KEY")
LLM_MODEL = _get("LLM_MODEL")
LLM_REASONING_EFFORT = _get("LLM_REASONING_EFFORT")  # e.g. "low" for reasoning models; dropped if the endpoint refuses it
LLM_ENABLED = bool(LLM_BASE_URL and LLM_MODEL)
# Longest rate-limit wait worth taking. Live calls want a fast fallback; a batch re-judge can afford more.
LLM_MAX_WAIT_S = float(_get("LLM_MAX_WAIT_S", "8") or 8)
# Mask names, phone and account numbers before text goes to the LLM endpoint (engine/redact.py).
LLM_REDACT = _get("LLM_REDACT", "1") != "0"

SAMPLE_RATE = 8000  # narrowband telephony, end to end

CALLS_DIR = ROOT / "calls"
OUT_DIR = ROOT / "out"
RESULTS_DIR = ROOT / "results"
DATA_DIR = ROOT / "data"
TTS_CACHE = CALLS_DIR / ".tts_cache"
NUDGE_DIR = DATA_DIR / "nudges"

# Noise conditions the bench renders. "clean" is the codec-only baseline.
VARIANTS = {"clean": None, "snr20": 20.0, "snr10": 10.0, "snr5": 5.0, "snr0": 0.0}


def require_gnani() -> str:
    if not GNANI_API_KEY:
        raise SystemExit("GNANI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return GNANI_API_KEY
