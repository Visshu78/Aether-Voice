"""
main.py — FastAPI application entry point.

Exposes:
  GET  /          → health check
  WS   /ws/audio  → full-duplex voice pipeline

Per-connection lifecycle:
  1. Client connects via WebSocket
  2. Receive loop: binary PCM → audio_queue
  3. STT task: audio_queue → Deepgram → transcript_queue
  4. Pipeline loop: transcript_queue → LLM → TTS → WebSocket
  5. InterruptionHandler: speech-during-playback → cancel + stop signal
  6. On disconnect: cancel all tasks gracefully
"""
print("DEBUG: main.py loading...")
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from audio_queue import AudioQueue
from config import DEEPGRAM_API_KEY, LLM_MODEL  # validates key at import
from deepgram_stt import run_stt
from interruption import InterruptionHandler
from llm_handler import stream_llm_sentences
from tts_handler import synthesize_sentence

# Simplified logging: Stream only to avoid file issues on Windows
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*50)
    print("🚀  DEBUGGER AGENT: VOICE PIPELINE STARTING  🚀")
    print("="*50 + "\n")
    logger.info("🚀 Voice Pipeline started — keys OK")
    yield
    print("\n" + "="*50)
    print("🛑  DEBUGGER AGENT: VOICE PIPELINE SHUTDOWN  🛑")
    print("="*50 + "\n")
    logger.info("🛑 Voice Pipeline shutdown")


app = FastAPI(title="Voice Pipeline", version="1.0.0", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "voice-pipeline", "model": LLM_MODEL}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)





# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _safe_send_text(ws: WebSocket, data: dict) -> None:
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            # print(f"DEBUGGER AGENT: 📤 Sending JSON: {data.get('type')}")
            await ws.send_text(json.dumps(data))
        else:
            print(f"DEBUGGER AGENT: ⚠️  Cannot send JSON, ws state is {ws.client_state}")
    except Exception as e:
        print(f"DEBUGGER AGENT: ❌ Error sending JSON: {e}")
        pass


async def _safe_send_bytes(ws: WebSocket, data: bytes) -> None:
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_bytes(data)
        else:
             print(f"DEBUGGER AGENT: ⚠️  Cannot send bytes, ws state is {ws.client_state}")
    except Exception as e:
        print(f"DEBUGGER AGENT: ❌ Error sending bytes: {e}")
        pass


# ---------------------------------------------------------------------------
# Pipeline runner — STT → LLM sentences → TTS
# ---------------------------------------------------------------------------

async def _run_pipeline(
    transcript: str,
    ws: WebSocket,
    interrupt: InterruptionHandler,
):
    """
    For a single final transcript, run LLM → TTS pipeline.
    Yields each TTS sentence back to the client.
    """
    # Notify frontend: transcript received
    await _safe_send_text(ws, {"type": "transcript", "text": transcript})
    await _safe_send_text(ws, {"type": "state", "value": "thinking"})

    # Stream LLM sentences → TTS
    await _safe_send_text(ws, {"type": "state", "value": "speaking"})

    async for sentence in stream_llm_sentences(
        transcript,
        interrupt.cancel_event,
        on_state=lambda s: _safe_send_text(ws, {"type": "state", "value": s}),
    ):
        if interrupt.cancel_event.is_set():
            logger.info("Pipeline interrupted — stopping TTS")
            break

        # Send LLM chunk to UI for display
        await _safe_send_text(ws, {"type": "llm_chunk", "text": sentence})

        # Synthesize and stream sentence audio
        success = await synthesize_sentence(
            sentence,
            interrupt.cancel_event,
            ws_send_bytes=lambda b: _safe_send_bytes(ws, b),
            ws_send_json=lambda d: _safe_send_text(ws, d),
        )
        if not success:
            logger.warning("TTS failed for sentence")

    print(f"DEBUG: Pipeline FINISHED for: '{transcript}'")
    if not interrupt.cancel_event.is_set():
        await _safe_send_text(ws, {"type": "state", "value": "listening"})


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket):
    await websocket.accept()
    print("DEBUGGER AGENT: ✅ WebSocket accepted")
    logger.info("🔌 WebSocket connected")

    audio_queue = AudioQueue(maxsize=200)
    transcript_queue: asyncio.Queue[str] = asyncio.Queue()
    interrupt = InterruptionHandler(websocket, audio_queue)

    # --- Interruption callback called by STT when speech is detected ---
    async def on_speech_started():
        # Only interrupt if we are currently in "speaking" state
        # (i.e., TTS is playing). The cancel_event being clear means
        # we are in a fresh turn — don't interrupt ourselves.
        if interrupt.cancel_event.is_set():
            return  # already interrupted
        # Check if there are active pipeline tasks (speaking)
        if interrupt._active_tasks:
            await interrupt.trigger()

    # --- STT task ---
    stt_task = asyncio.create_task(
        run_stt(
            audio_queue,
            transcript_queue,
            interrupt.cancel_event,
            on_speech_started=on_speech_started,
        )
    )

    # --- Transcript consumer loop ---
    async def _transcript_consumer():
        while True:
            try:
                transcript = await asyncio.wait_for(
                    transcript_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # Reset interruption state for this new turn
            interrupt.reset()

            # Run pipeline for this transcript
            print(f"DEBUG: Starting pipeline for: '{transcript}'")
            pipeline_task = asyncio.create_task(
                _run_pipeline(transcript, websocket, interrupt)
            )
            interrupt.register_task(pipeline_task)
            try:
                print(f"DEBUG: Awaiting pipeline task for: '{transcript}'")
                await pipeline_task
                print(f"DEBUG: Pipeline task COMPLETED for: '{transcript}'")
            except asyncio.CancelledError:
                print(f"DEBUG: Pipeline task CANCELLED for: '{transcript}'")
                pass
            except Exception as e:
                logger.error(f"Pipeline crashed for transcript: {e}", exc_info=True)

    consumer_task = asyncio.create_task(_transcript_consumer())

    # --- Receive loop: WebSocket → audio_queue ---
    await _safe_send_text(websocket, {"type": "state", "value": "listening"})
    
    # Debug tracking
    format_verified = False
    chunk_count = 0

    try:
        while True:
            try:
                message = await websocket.receive()
                # Debugger Agent: Log every message type
                m_type = message.get("type")
                if m_type != "websocket.receive": # excessive for binary
                     pass # handled below
            except RuntimeError:
                # Socket already disconnected
                print("DEBUGGER AGENT: ❌ WebSocket runtime error")
                break

            # Debugger Agent: Log every single message structure
            if "bytes" in message:
                # Chunk logs (every 50)
                if not format_verified:
                    print(f"DEBUGGER AGENT: 📥 RECEIVED INITIAL BINARY CHUNK ({len(message['bytes'])} bytes)")
                    format_verified = True
                
                chunk_count += 1
                if chunk_count % 50 == 0:
                    print(f"DEBUGGER AGENT: 📥 Audio Chunks received: {chunk_count}")
                await audio_queue.put(message["bytes"])

            elif "text" in message:
                print(f"DEBUGGER AGENT: 📥 RECEIVED TEXT: {message['text'][:100]}")
                try:
                    ctrl = json.loads(message["text"])
                    if ctrl.get("type") == "interrupt":
                        await interrupt.trigger()
                except json.JSONDecodeError:
                    pass
            else:
                print(f"DEBUGGER AGENT: 📥 RECEIVED UNKNOWN MSG TYPE: {message.get('type')} Keys: {list(message.keys())}")

    except WebSocketDisconnect:
        logger.info("🔌 Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Cancel all tasks
        interrupt.cancel_event.set()
        for t in [stt_task, consumer_task]:
            if not t.done():
                t.cancel()
        await asyncio.gather(stt_task, consumer_task, return_exceptions=True)
        logger.info("🧹 Session cleaned up")
