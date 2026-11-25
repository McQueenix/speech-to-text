// AudioWorklet: converts the mic's float audio (usually 44.1/48 kHz) into
// 16 kHz, 16-bit little-endian mono PCM — the format the Gemini Live API expects —
// and posts ~100 ms chunks to the main thread.
class PcmDownsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // `sampleRate` is a worklet global
    this.chunkSize = 1600; // 100 ms at 16 kHz
    this.buffer = new Int16Array(this.chunkSize);
    this.offset = 0;
    this.pos = 0; // fractional read position into the incoming stream
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    // Simple averaging downsampler (box filter) — good enough for speech.
    while (this.pos < channel.length) {
      const start = Math.floor(this.pos);
      const end = Math.min(Math.floor(this.pos + this.ratio), channel.length);
      let sum = 0;
      let n = 0;
      for (let i = start; i < Math.max(end, start + 1); i++) {
        sum += channel[i];
        n++;
      }
      const s = Math.max(-1, Math.min(1, sum / n));
      this.buffer[this.offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.offset === this.chunkSize) {
        this.port.postMessage(this.buffer.buffer.slice(0));
        this.offset = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= channel.length;
    return true;
  }
}

registerProcessor("pcm-downsampler", PcmDownsampler);
