# Voice AI — Real-Time Voice Pipeline

A full-duplex, low-latency voice assistant using **FastAPI WebSockets + Vanilla JS AudioWorklet**. No LiveKit, no Vapi — raw PCM 16-bit throughout.

```
Browser Mic (PCM 16-bit @ 16kHz)
  → WebSocket → Deepgram STT
  → GPT-4o (sentence-level streaming)
  → Deepgram Aura TTS
  → WebSocket → Browser AudioWorklet Player
```

---

## Project Structure

```
voice_pipeline/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket /ws/audio
│   ├── audio_queue.py       # asyncio.Queue for PCM piping
│   ├── deepgram_stt.py      # Deepgram live STT consumer
│   ├── llm_handler.py       # GPT-4o streaming + sentence chunker
│   ├── tts_handler.py       # Deepgram Aura TTS → PCM
│   ├── interruption.py      # InterruptionHandler
│   ├── config.py            # Env var loading
│   └── requirements.txt
├── frontend/
│   ├── index.html           # App shell
│   ├── index.css            # Dark glassmorphism UI
│   ├── app.js               # State machine + WebSocket client
│   ├── audio-processor.worklet.js  # AudioWorklet: mic → PCM chunks
│   └── audio-player.js      # PCM playback with stop() support
└── .env.example             # API key template
```

---

## Quick Start

### 1. Set up API keys

```bash
cp .env.example .env
# Edit .env and add your DEEPGRAM_API_KEY and OPENAI_API_KEY
```

### 2. Backend

```powershell
cd voice_pipeline/backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend (in a new terminal)

```powershell
cd voice_pipeline/frontend
python -m http.server 3000
```

Then open **http://localhost:3000** in Chrome or Edge (required for AudioWorklet).

---

## Architecture Highlights

| Feature | Implementation |
|---|---|
| Audio capture | `AudioWorklet` — Float32 → Int16 PCM, 20ms chunks |
| Transport | WebSocket binary (PCM) + JSON control messages |
| STT | Deepgram Nova-2 live stream via `websockets` |
| LLM | OpenAI GPT-4o streaming, sentence-level chunker |
| TTS | Deepgram Aura `linear16` REST API, per-sentence |
| Interruption | `InterruptionHandler` — cancel tasks + `{"type":"stop"}` → `audioPlayer.stop()` |
| Audio playback | Gapless scheduling via `AudioBufferSourceNode` chain |

---

## Interruption Flow

```
1. User speaks while AI is speaking
2. Deepgram detects speech (SpeechStarted / interim results)
3. InterruptionHandler.trigger():
   a. Sets cancel_event → LLM/TTS tasks abort
   b. Clears audio_queue
   c. Sends {"type":"stop"} over WebSocket
4. Frontend: audioPlayer.stop() → silence
5. Pipeline resets for new user turn
```

---

## WebSocket Message Protocol

| Direction | Message | Format |
|---|---|---|
| Browser → Server | Raw PCM bytes | binary |
| Server → Browser | `{"type":"state","value":"listening\|thinking\|speaking\|idle"}` | JSON |
| Server → Browser | `{"type":"transcript","text":"..."}` | JSON |
| Server → Browser | `{"type":"llm_chunk","text":"..."}` | JSON |
| Server → Browser | TTS audio | binary |
| Server → Browser | `{"type":"stop"}` | JSON |

---

## Requirements

- Python 3.11+
- Modern browser with AudioWorklet support (Chrome/Edge recommended)
- Deepgram API key (STT + TTS)
- OpenAI API key (GPT-4o)
