// AudioWorklet: junta o áudio do microfone em blocos de 64 ms (1024 amostras a 16 kHz),
// converte para Int16 e manda para a página com o nível (RMS) para a forma de onda.
class Pcm16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(1024);
    this.n = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.buf[this.n++] = ch[i];
      if (this.n === this.buf.length) this.flush();
    }
    return true;
  }
  flush() {
    const out = new Int16Array(this.n);
    let sum = 0;
    for (let i = 0; i < this.n; i++) {
      const s = Math.max(-1, Math.min(1, this.buf[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      sum += s * s;
    }
    const rms = Math.sqrt(sum / this.n);
    this.port.postMessage({ pcm: out.buffer, rms }, [out.buffer]);
    this.n = 0;
  }
}
registerProcessor("pcm16", Pcm16Processor);
