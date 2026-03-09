/**
 * app.js — Main application logic
 *
 * Responsibilities:
 *  - WebSocket connection lifecycle
 *  - Microphone capture via getUserMedia + AudioWorklet
 *  - State machine: idle → listening → thinking → speaking → listening
 *  - Dispatches binary PCM from Worklet → WebSocket
 *  - Receives binary TTS PCM → AudioPlayer
 *  - Receives JSON control messages (transcript, state, stop, llm_chunk)
 *  - Canvas waveform animation via AnalyserNode
 *  - Interrupt button (manual) + auto-interrupt on {"type":"stop"}
 */

import { AudioPlayer } from "./audio-player.js";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const WS_URL = "ws://localhost:8002/ws/audio";
const SAMPLE_RATE = 16000;

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------

const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const transcriptEl = document.getElementById("transcript-text");
const responseEl = document.getElementById("response-text");
const waveCanvas = document.getElementById("waveform");
const ctx2d = waveCanvas.getContext("2d");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let ws = null;
let audioContext = null;
let workletNode = null;
let analyserNode = null;
let stream = null;
let audioPlayer = null;
let animFrameId = null;
let currentState = "idle";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

const STATE_CONFIG = {
    idle: { label: "Idle", dotClass: "dot-idle" },
    listening: { label: "Listening", dotClass: "dot-listening" },
    thinking: { label: "Thinking", dotClass: "dot-thinking" },
    speaking: { label: "Speaking", dotClass: "dot-speaking" },
    error: { label: "Error", dotClass: "dot-error" },
};

function setState(state) {
    currentState = state;
    const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle;

    statusLabel.textContent = cfg.label;
    statusDot.className = "status-dot " + cfg.dotClass;

    // Button availability
    const isIdle = state === "idle";
    startBtn.disabled = !isIdle;
    stopBtn.disabled = isIdle;
    const interruptBtn = document.getElementById("interrupt-btn");
    if (interruptBtn) interruptBtn.disabled = isIdle;
}

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------

function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
        console.info("WS connected");
    };

    ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
            // Binary: raw PCM from TTS
            if (audioPlayer) audioPlayer.enqueue(event.data);
        } else {
            // Text: JSON control message
            try {
                const msg = JSON.parse(event.data);
                handleServerMessage(msg);
            } catch (e) {
                console.warn("Malformed WS message", event.data);
            }
        }
    };

    ws.onerror = (err) => {
        console.error("WS error", err);
        setState("error");
    };

    ws.onclose = () => {
        console.info("WS closed");
        if (currentState !== "idle") setState("idle");
    };
}

function handleServerMessage(msg) {
    switch (msg.type) {
        case "state":
            setState(msg.value);
            if (msg.value === "speaking" && audioPlayer) {
                audioPlayer.start();
            }
            break;

        case "transcript":
            transcriptEl.textContent = msg.text;
            transcriptEl.parentElement.style.display = "block";
            break;

        case "llm_chunk":
            responseEl.textContent += (responseEl.textContent ? " " : "") + msg.text;
            responseEl.parentElement.style.display = "block";
            break;

        case "tts_start":
            // nothing extra needed — audioPlayer.start() called on "state:speaking"
            break;

        case "tts_end":
            // nothing — playback drains naturally
            break;

        case "stop":
            // Interrupt: stop audio immediately
            if (audioPlayer) {
                audioPlayer.stop();
                audioPlayer.resume();
            }
            setState("listening");
            break;

        default:
            break;
    }
}

// ---------------------------------------------------------------------------
// Microphone + AudioWorklet
// ---------------------------------------------------------------------------

async function startMic() {
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });

    stream = await navigator.mediaDevices.getUserMedia({
        audio: {
            channelCount: 1,
            sampleRate: SAMPLE_RATE,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
        },
        video: false,
    });

    const micSource = audioContext.createMediaStreamSource(stream);

    // Load AudioWorklet
    await audioContext.audioWorklet.addModule("./audio-processor.worklet.js");
    workletNode = new AudioWorkletNode(audioContext, "audio-capture-processor");

    // Forward PCM chunks from Worklet → WebSocket
    workletNode.port.onmessage = (e) => {
        if (e.data.type === "pcm" && ws && ws.readyState === WebSocket.OPEN) {
            if (!window._pcm_verified) {
                console.info("DEBUGGER AGENT: Sending Raw PCM (Int16) buffer to backend. Size:", e.data.buffer.byteLength);
                window._pcm_verified = true;
            }
            ws.send(e.data.buffer);
        }
    };

    // Analyser for waveform visualization
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.8;

    micSource.connect(analyserNode);
    micSource.connect(workletNode);
    workletNode.connect(audioContext.destination); // silent (no audio out yet)

    // AudioPlayer shares the same AudioContext
    audioPlayer = new AudioPlayer(audioContext);
}

async function stopMic() {
    if (workletNode) {
        workletNode.port.postMessage({ type: "stop" });
        workletNode.disconnect();
        workletNode = null;
    }
    if (stream) {
        stream.getTracks().forEach((t) => t.stop());
        stream = null;
    }
    if (audioPlayer) {
        audioPlayer.stop();
        audioPlayer = null;
    }
    if (audioContext) {
        await audioContext.close();
        audioContext = null;
    }
    analyserNode = null;
}

// ---------------------------------------------------------------------------
// Waveform animation
// ---------------------------------------------------------------------------

function drawWaveform() {
    animFrameId = requestAnimationFrame(drawWaveform);

    const W = waveCanvas.width;
    const H = waveCanvas.height;
    ctx2d.clearRect(0, 0, W, H);

    if (!analyserNode || currentState === "idle") {
        // Draw a flat line when idle
        ctx2d.strokeStyle = "rgba(124,58,237,0.25)";
        ctx2d.lineWidth = 2;
        ctx2d.beginPath();
        ctx2d.moveTo(0, H / 2);
        ctx2d.lineTo(W, H / 2);
        ctx2d.stroke();
        return;
    }

    const bufLen = analyserNode.frequencyBinCount;
    const dataArr = new Uint8Array(bufLen);
    analyserNode.getByteTimeDomainData(dataArr);

    const gradient = ctx2d.createLinearGradient(0, 0, W, 0);
    gradient.addColorStop(0, "rgba(124,58,237,0.8)");
    gradient.addColorStop(0.5, "rgba(192,38,211,0.9)");
    gradient.addColorStop(1, "rgba(124,58,237,0.8)");

    ctx2d.strokeStyle = gradient;
    ctx2d.lineWidth = 2.5;
    ctx2d.beginPath();

    const sliceW = W / bufLen;
    let x = 0;
    for (let i = 0; i < bufLen; i++) {
        const v = dataArr[i] / 128.0;
        const y = (v * H) / 2;
        i === 0 ? ctx2d.moveTo(x, y) : ctx2d.lineTo(x, y);
        x += sliceW;
    }
    ctx2d.lineTo(W, H / 2);
    ctx2d.stroke();
}

// ---------------------------------------------------------------------------
// Button handlers
// ---------------------------------------------------------------------------

startBtn.addEventListener("click", async () => {
    try {
        setState("listening");
        // Clear previous turn content
        transcriptEl.textContent = "";
        responseEl.textContent = "";
        transcriptEl.parentElement.style.display = "none";
        responseEl.parentElement.style.display = "none";

        connectWebSocket();
        await startMic();
        drawWaveform();
    } catch (err) {
        console.error("Start error:", err);
        setState("error");
        statusLabel.textContent = err.message || "Microphone error";
    }
});

stopBtn.addEventListener("click", async () => {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;

    if (ws) {
        ws.close();
        ws = null;
    }
    await stopMic();
    setState("idle");
});

// Manual interrupt button (optional — clicking while speaking)
document.getElementById("interrupt-btn")?.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "interrupt" }));
    }
    if (audioPlayer) {
        audioPlayer.stop();
        audioPlayer.resume();
    }
    setState("listening");
});

// ---------------------------------------------------------------------------
// Resize canvas to container
// ---------------------------------------------------------------------------

function resizeCanvas() {
    const container = waveCanvas.parentElement;
    waveCanvas.width = container.clientWidth;
    waveCanvas.height = container.clientHeight;
}

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
