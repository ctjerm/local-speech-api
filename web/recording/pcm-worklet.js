// Capture mono PCM on the audio thread. Output stays silent: no microphone feedback.
class PcmCapture extends AudioWorkletProcessor {
  constructor({ processorOptions }) {
    super();
    this.limit = processorOptions.maxFrames;
    this.frames = 0;
    this.buffer = new ArrayBuffer(8192);
    this.view = new DataView(this.buffer);
    this.used = 0;
    this.done = false;
    this.port.onmessage = ({ data }) => { if (data === "finish") this.finish(); };
  }

  flush() {
    if (!this.used) return;
    const bytes = this.buffer.slice(0, this.used * 2);
    this.port.postMessage({ type: "pcm", bytes, frames: this.frames }, [bytes]);
    this.used = 0;
  }

  finish() {
    if (this.done) return;
    this.done = true;
    this.flush();
    this.port.postMessage({ type: "done" });
  }

  process(inputs) {
    if (this.done) return true;
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const value of input) {
      const sample = Math.max(-1, Math.min(1, value));
      this.view.setInt16(this.used * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
      this.used++;
      this.frames++;
      if (this.used === 4096) this.flush();
      if (this.frames >= this.limit) { this.finish(); break; }
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
