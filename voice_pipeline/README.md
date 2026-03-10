# 🎙️ Aether Voice — Real-Time AI Voice Pipeline

A low-latency, full-duplex voice AI pipeline. Speak into your browser — your speech is transcribed, sent to a local LLM, and the response is spoken back to you in real time.

**Stack:** Deepgram STT → Local LLM (OpenAI-compatible) → Deepgram Aura TTS · Raw PCM 16-bit · No LiveKit

---

## Architecture

```
Browser Mic (PCM 16-bit)
        │
        ▼ WebSocket (ws://localhost:8002/ws/audio)
┌───────────────────────────────────────────┐
│              FastAPI Backend              │
│                                           │
│  Audio Queue → Deepgram STT (WebSocket)   │
│                     │ final transcript    │
│                     ▼                     │
│          Local LLM (SSE streaming)        │
│          http://192.168.56.1:2424/v1      │
│                     │ sentence chunks     │
│                     ▼                     │
│        Deepgram Aura TTS (REST)           │
│                     │ raw PCM audio       │
│                     ▼                     │
│        WebSocket → Browser AudioPlayer    │
└───────────────────────────────────────────┘
```

---

## Project Structure

```
voice_pipeline/
├── backend/
│   ├── main.py            # FastAPI app, WebSocket endpoint, pipeline orchestration
│   ├── audio_queue.py     # Thread-safe async queue for PCM audio chunks
│   ├── deepgram_stt.py    # Deepgram live STT WebSocket bridge
│   ├── llm_handler.py     # Local LLM SSE streaming + sentence chunker
│   ├── tts_handler.py     # Deepgram Aura TTS (WAV → raw PCM streaming)
│   ├── interruption.py    # Barge-in handler — cancels pipeline on user speech
│   ├── config.py          # .env loader and validation
│   ├── requirements.txt
│   └── .env               # API keys and model config (see below)
└── frontend/
    ├── index.html
    ├── index.css
    ├── app.js             # WebSocket client, mic capture, AudioWorklet, state machine
    ├── audio-player.js    # PCM playback via Web Audio API
    └── audio-processor.worklet.js  # AudioWorklet: Float32 → Int16 PCM converter
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.10+ (tested on 3.14) |
| **Deepgram API Key** | Free tier at [deepgram.com](https://deepgram.com) |
| **Local LLM Server** | Any OpenAI-compatible server (LM Studio, Ollama, etc.) |
| **Browser** | Chrome / Edge (AudioWorklet support required) |

---

## Setup

### 1. Clone & create virtual environment

```bash
git clone https://github.com/Visshu78/Aether-Voice.git
cd Aether-Voice/voice_pipeline/backend

python -m venv ../../env
# Windows
../../env/Scripts/activate
# macOS/Linux
source ../../env/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
pip install pip-system-certs   # Windows only — fixes SSL cert issues
```

### 3. Configure `.env`

Copy and edit the environment file:

```bash
cp .env.example .env   # or edit .env directly
```

```ini
# .env
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# Local LLM server — must include /v1
LOCAL_LLM_BASE_URL=http://192.168.56.1:2424/v1
LOCAL_LLM_API_KEY=local

# Model ID — must match a model loaded in your LLM server
LLM_MODEL=qwen3-4b-instruct-2507

# Audio / TTS
SAMPLE_RATE=16000
TTS_MODEL=aura-asteria-en
```

> **Important:** `LOCAL_LLM_BASE_URL` must end with `/v1`. The backend appends `/chat/completions` to build the full endpoint URL.

### 4. Start your local LLM

Open LM Studio (or any OpenAI-compatible server) and:
- Load your model (e.g. `qwen3-4b-instruct-2507`)
- Start the server on the port matching `LOCAL_LLM_BASE_URL`
- Verify via: `http://<your-ip>:2424/v1/models`

---

## Running

Open **two terminals**:

**Terminal 1 — Backend**
```bash
cd voice_pipeline/backend
python -m uvicorn main:app --reload --port 8002
```

**Terminal 2 — Frontend**
```bash
cd voice_pipeline/frontend
python -m http.server 3000
```

Open your browser at **[http://localhost:3000](http://localhost:3000)**

---

## Usage

1. Click **▶ Start** — browser requests microphone permission
2. Speak clearly — the status dot shows **Listening → Thinking → Speaking**
3. The AI's response appears as text and is spoken back via TTS
4. Click **⚡ Interrupt** at any time to stop the AI mid-sentence
5. Click **■ Stop** to end the session

---

## Pipeline Flow (Per Turn)

```
1. Browser mic captures PCM @ 16kHz (AudioWorklet)
2. PCM chunks → WebSocket binary frames → FastAPI backend
3. Backend forwards PCM → Deepgram STT (live WebSocket)
4. Deepgram returns final transcript (speech_final=True)
5. Transcript → Local LLM (streaming SSE POST /v1/chat/completions)
6. LLM tokens accumulated into sentences (punctuation / word-count chunking)
7. Each sentence → Deepgram Aura TTS (WAV response, 44-byte header stripped)
8. Raw PCM bytes streamed back over WebSocket → browser AudioPlayer
9. If user speaks during playback → InterruptionHandler cancels pipeline
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DEEPGRAM_API_KEY` | *(required)* | Deepgram API key for STT + TTS |
| `LOCAL_LLM_BASE_URL` | *(required)* | LLM server base URL including `/v1` |
| `LOCAL_LLM_API_KEY` | `local` | Passed as Bearer token (can be any string for local servers) |
| `LLM_MODEL` | `gemini-2.5-flash` | Must match an available model ID on your server |
| `SAMPLE_RATE` | `16000` | Audio sample rate in Hz |
| `TTS_MODEL` | `aura-asteria-en` | Deepgram Aura voice model |

### Available Deepgram TTS voices
`aura-asteria-en` · `aura-luna-en` · `aura-stella-en` · `aura-athena-en` · `aura-hera-en` · `aura-orion-en` · `aura-arcas-en` · `aura-perseus-en`

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Status stays on **Listening** forever | LLM URL wrong / model not found | Check `LOCAL_LLM_BASE_URL` includes `/v1`, verify `LLM_MODEL` matches `GET /v1/models` |
| `WebSocket connection failed` | Backend not running | Start uvicorn on port 8002 |
| No microphone input | Browser blocked mic | Allow microphone in browser site settings |
| AI responds but no audio | TTS error / Deepgram key issue | Check `DEEPGRAM_API_KEY` is valid and has credits |
| Interruption fires during AI thinking | (Fixed in this version) | `is_speaking` guard ensures interrupt only fires during TTS playback |

---

## Key Design Decisions

- **No LiveKit / WebRTC** — pure WebSocket + Web Audio API for simplicity
- **Raw PCM 16-bit** — minimal encoding overhead, directly accepted by Deepgram
- **Sentence-level TTS chunking** — LLM tokens are buffered into complete sentences before TTS, keeping latency low while avoiding unnatural cutoffs
- **Barge-in at TTS level** — interruption only fires when TTS audio is actively playing (`is_speaking` flag), not while the LLM is thinking
- **`<think>` block handling** — reasoning models (DeepSeek R1, Qwen3) output reasoning inside `<think>` tags which are silently discarded; if no content remains, think content is used as fallback
