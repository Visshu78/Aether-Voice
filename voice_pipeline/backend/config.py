"""
config.py — Load and validate environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Please copy .env.example to .env and fill in your API keys."
        )
    return val

DEEPGRAM_API_KEY: str = _require("DEEPGRAM_API_KEY")

# Gemini API
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")

SAMPLE_RATE: int   = int(os.getenv("SAMPLE_RATE", "16000"))
LLM_MODEL: str     = os.getenv("LLM_MODEL", "gemini-2.5-flash")
TTS_MODEL: str     = os.getenv("TTS_MODEL", "aura-asteria-en")

# Audio encoding for Deepgram STT
ENCODING: str      = "linear16"
CHANNELS: int      = 1
