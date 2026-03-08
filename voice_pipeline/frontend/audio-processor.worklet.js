/**
 * audio-processor.worklet.js
 *
 * AudioWorklet processor: captures Float32 samples from the microphone,
 * converts them to Int16 PCM (16-bit little-endian), and posts them back
 * to the main thread for transmission over WebSocket.
 *
 * Target: 16kHz mono. The AudioContext must be created at 16000 Hz,
 * or the app.js resampler will handle the conversion.
 *
 * Chunk size: 320 samples = 20ms at 16kHz (optimal for Deepgram).
 */

const CHUNK_SAMPLES = 320;

class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(CHUNK_SAMPLES);
    this._bufferIndex = 0;
    this._active = true;

    this.port.onmessage = (e) => {
      if (e.data && e.data.type === "stop") {
        this._active = false;
      }
    };
  }

  process(inputs) {
    if (!this._active) return false;

    const input = inputs[0];
    if (!input || !input[0]) return true;

    const samples = input[0]; // mono channel

    for (let i = 0; i < samples.length; i++) {
      this._buffer[this._bufferIndex++] = samples[i];

      if (this._bufferIndex >= CHUNK_SAMPLES) {
        // Convert Float32 → Int16 PCM
        const pcm = new Int16Array(CHUNK_SAMPLES);
        for (let j = 0; j < CHUNK_SAMPLES; j++) {
          const s = Math.max(-1, Math.min(1, this._buffer[j]));
          pcm[j] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        // Transfer ownership for zero-copy performance
        this.port.postMessage({ type: "pcm", buffer: pcm.buffer }, [pcm.buffer]);
        this._bufferIndex = 0;
      }
    }

    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
