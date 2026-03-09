"""
tts_handler.py — Deepgram Aura TTS.

Synthesizes one sentence at a time via Deepgram REST TTS API,
returns raw PCM bytes (linear16, 16kHz, mono).
Sends them in chunks over the WebSocket so playback can begin
before the full sentence audio is ready.
"""
import asyncio
import logging
import struct
import traceback

import httpx

from config import DEEPGRAM_API_KEY, SAMPLE_RATE, TTS_MODEL

logger = logging.getLogger(__name__)

DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"

# Deepgram TTS returns WAV; we strip the 44-byte header to get raw PCM.
WAV_HEADER_SIZE = 44
CHUNK_SIZE = 4096  # bytes per send


async def synthesize_sentence(
    sentence: str,
    cancel_event: asyncio.Event,
    ws_send_bytes,   # async callable(bytes)
    ws_send_json,    # async callable(dict)
) -> bool:
    """
    Synthesize `sentence` via Deepgram TTS and stream PCM over WebSocket.

    Returns True if successful, False if cancelled or errored.
    """
    if cancel_event.is_set():
        return False

    params = {
        "model": TTS_MODEL,
        "encoding": "linear16",
        "sample_rate": SAMPLE_RATE,
        "container": "wav",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"text": sentence}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                DEEPGRAM_TTS_URL,
                json=body,
                headers=headers,
                params=params,
            ) as response:
                response.raise_for_status()

                # Signal frontend: TTS audio incoming
                await ws_send_json({"type": "tts_start", "text": sentence})

                first_chunk = True
                async for raw_chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                    if cancel_event.is_set():
                        logger.info("TTS cancelled mid-stream")
                        return False

                    # Strip WAV header from the first chunk
                    if first_chunk:
                        raw_chunk = raw_chunk[WAV_HEADER_SIZE:]
                        first_chunk = False

                    if raw_chunk:
                        await ws_send_bytes(raw_chunk)

                await ws_send_json({"type": "tts_end"})
                return True

    except asyncio.CancelledError:
        logger.info("TTS task cancelled")
        return False
    except httpx.HTTPStatusError as e:
        logger.error(f"TTS HTTP error {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        print(f"CRITICAL TTS ERROR: {e}")
        traceback.print_exc()
        logger.error(f"TTS error: {e}", exc_info=True)
        return False
