/** Captura do microfone no próprio app: PCM Int16 em blocos, mais o nível para a forma de onda. */
export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;

  constructor(
    private onChunk: (pcm: ArrayBuffer) => void,
    private onLevel: (rms: number) => void,
  ) {}

  /** Taxa real do contexto (o WebView pode não aceitar 16 kHz; o cérebro reamostra). */
  sampleRate = 16000;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    try {
      this.ctx = new AudioContext({ sampleRate: 16000 });
    } catch {
      this.ctx = new AudioContext();
    }
    this.sampleRate = this.ctx.sampleRate;
    await this.ctx.audioWorklet.addModule("/pcm-worklet.js");
    this.node = new AudioWorkletNode(this.ctx, "pcm16", { numberOfInputs: 1, numberOfOutputs: 0 });
    this.node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; rms: number }>) => {
      this.onLevel(e.data.rms);
      this.onChunk(e.data.pcm);
    };
    this.ctx.createMediaStreamSource(this.stream).connect(this.node);
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  stop(): void {
    this.node?.disconnect();
    this.node = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    void this.ctx?.close();
    this.ctx = null;
  }
}

let chimeCtx: AudioContext | null = null;

/** Toque curto e discreto: sobe ao começar a ouvir, desce ao terminar. */
export function chime(kind: "start" | "end"): void {
  try {
    chimeCtx ??= new AudioContext();
    const ctx = chimeCtx;
    const [from, to] = kind === "start" ? [880, 1320] : [1175, 784];
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(from, t);
    osc.frequency.exponentialRampToValueAtTime(to, t + 0.09);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.07, t + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.18);
  } catch {
    // sem áudio de saída: segue sem o toque
  }
}
