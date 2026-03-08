"""
deepgram_stt.py — Deepgram Live STT consumer.

Pulls PCM chunks from AudioQueue, streams to Deepgram,
publishes final transcripts to transcript_queue.
Detects mid-playback speech → triggers interruption.
"""
import asyncio
import json
import logging

import websockets

from audio_queue import AudioQueue
from config import DEEPGRAM_API_KEY, SAMPLE_RATE, ENCODING, CHANNELS

logger = logging.getLogger(__name__)

DEEPGRAM_URL = (
    f"wss://api.deepgram.com/v1/listen"
    f"?model=nova-2"
    f"&encoding={ENCODING}"
    f"&sample_rate={SAMPLE_RATE}"
    f"&channels={CHANNELS}"
    f"&interim_results=true"
    f"&endpointing=100"
    f"&utterance_end_ms=600"
)


async def run_stt(
    audio_queue: AudioQueue,
    transcript_queue: asyncio.Queue,
    cancel_event: asyncio.Event,
    on_speech_started,          # async callable — fired on interim speech
):
    """
    Connect to Deepgram live STT and bridge AudioQueue → transcript_queue.

    Args:
        audio_queue: Source of raw PCM bytes from the browser.
        transcript_queue: Destination for final transcript strings.
        cancel_event: Set this to stop. Checked between frames.
        on_speech_started: Async callback invoked when Deepgram detects
                           user speech (used to trigger interruption).
    """
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    try:
        async with websockets.connect(DEEPGRAM_URL, extra_headers=headers) as dg_ws:
            logger.info("🎙️  Connected to Deepgram STT")

            async def _sender():
                """Pull PCM from queue and push to Deepgram."""
                while not cancel_event.is_set():
                    try:
                        chunk = await asyncio.wait_for(
                            audio_queue.get(), timeout=0.5
                        )
                        await dg_ws.send(chunk)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break
                # Send close frame so Deepgram flushes remaining results
                try:
                    await dg_ws.send(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass

            async def _receiver():
                """Receive Deepgram events and emit transcripts."""
                async for raw in dg_ws:
                    if cancel_event.is_set():
                        break
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("type", "")

                    # Speech detected from interim results — use to interrupt
                    if msg_type == "Results":
                        is_final = msg.get("is_final", False)
                        speech_final = msg.get("speech_final", False)
                        try:
                            transcript = (
                                msg["channel"]["alternatives"][0]["transcript"]
                            )
                        except (KeyError, IndexError):
                            continue

                        if transcript.strip():
                            if not is_final:
                                # Interim: user is speaking — may need to interrupt TTS
                                logger.debug(f"   Interim: {transcript}")
                                asyncio.ensure_future(on_speech_started())
                            elif is_final:
                                print(f"DEBUG: Final transcript received: {transcript}")
                                logger.info(f"📝 Final transcript: {transcript}")
                                await transcript_queue.put(transcript.strip())

                    elif msg_type == "UtteranceEnd":
                        logger.debug("Utterance ended")

            sender_task = asyncio.create_task(_sender())
            receiver_task = asyncio.create_task(_receiver())
            await asyncio.gather(sender_task, receiver_task)

    except asyncio.CancelledError:
        logger.info("STT task cancelled")
    except Exception as e:
        logger.error(f"Deepgram STT error: {e}", exc_info=True)
