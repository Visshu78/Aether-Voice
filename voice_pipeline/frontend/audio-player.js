/**
 * audio-player.js
 *
 * Streams raw PCM chunks (Int16, 16kHz, mono) to an AudioContext
 * for real-time playback with minimal buffering latency.
 *
 * Supports:
 *  - stop()    — immediately halts playback (on interrupt/stop signal)
 *  - resume()  — readies player for next turn
 */

export class AudioPlayer {
    constructor(audioContext) {
        /** @type {AudioContext} */
        this.ctx = audioContext;
        this._scheduledUntil = 0;      // wall-clock time next buffer should start
        this._sources = [];            // active AudioBufferSourceNodes
        this._sampleRate = audioContext.sampleRate;
        this._active = false;
    }

    /** Prepare player for a new TTS turn. */
    start() {
        this._active = true;
        this._scheduledUntil = this.ctx.currentTime; // start immediately on first chunk
    }

    /**
     * Enqueue a raw PCM chunk for immediate playback.
     * @param {ArrayBuffer} arrayBuffer  — raw Int16 LE bytes from server
     */
    enqueue(arrayBuffer) {
        if (!this._active) return;

        const int16 = new Int16Array(arrayBuffer);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768.0;
        }

        const audioBuffer = this.ctx.createBuffer(
            1,                      // mono
            float32.length,
            this._sampleRate
        );
        audioBuffer.copyToChannel(float32, 0);

        const source = this.ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.ctx.destination);

        // Schedule gaplessly after previous chunk
        const startAt = Math.max(this._scheduledUntil, this.ctx.currentTime);
        source.start(startAt);
        this._scheduledUntil = startAt + audioBuffer.duration;

        this._sources.push(source);
        source.onended = () => {
            const idx = this._sources.indexOf(source);
            if (idx !== -1) this._sources.splice(idx, 1);
        };
    }

    /**
     * Stop all scheduled and playing audio immediately.
     * Called on {"type":"stop"} from server or user interrupt.
     */
    stop() {
        this._active = false;
        const now = this.ctx.currentTime;
        for (const src of this._sources) {
            try { src.stop(now); } catch (_) { }
        }
        this._sources = [];
        this._scheduledUntil = now;
    }

    /** Re-arm for next turn without recreating the AudioContext. */
    resume() {
        this._active = false;  // will be set true by start()
    }

    /** True if currently playing or has buffers scheduled. */
    get isPlaying() {
        return this._active && this._sources.length > 0;
    }
}
