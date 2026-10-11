// Pulso do orbe ligado à resposta (change jarvis-painel-hud): a voz que toca (nível ~15/s vindo
// do cérebro) e o texto chegando (impulso por pedaço). Funções puras; o orbe chama a cada quadro.

export interface Pulse {
  level: number; // 0–1, último nível da voz recebido
  levelAt: number; // performance.now() do último nível
  tokenAt: number; // performance.now() do último pedaço de texto
}

export interface PulseOut {
  scale: number; // raio do orbe (1 = normal)
  glow: number; // brilho do núcleo (0–1)
  speed: number; // multiplicador da rotação
}

const ATTACK_MS = 60;
const RELEASE_MS = 180;
const TOKEN_MS = 400;
const LEVEL_STALE_MS = 300; // sem nível recente falando: voz local (`say`), pulso sintético
const SYNTH_HZ = 3;

/** Nível suavizado (ataque rápido, soltura mais lenta). */
export function smooth(prev: number, target: number, dtMs: number): number {
  const tau = target > prev ? ATTACK_MS : RELEASE_MS;
  return prev + (target - prev) * (1 - Math.exp(-dtMs / tau));
}

/** Alvo da voz agora: o nível real, ou um pulso sintético se a voz local não manda nível. */
export function voiceTarget(p: Pulse, speaking: boolean, now: number): number {
  if (!speaking) return 0;
  if (now - p.levelAt < LEVEL_STALE_MS) return p.level;
  return 0.35 + 0.3 * Math.sin((now / 1000) * Math.PI * 2 * SYNTH_HZ);
}

/** Quanto do impulso do texto ainda resta (1 logo depois de um pedaço, 0 após 400 ms). */
export function tokenBoost(p: Pulse, now: number): number {
  return Math.max(0, 1 - (now - p.tokenAt) / TOKEN_MS);
}

export function pulseOut(voice: number, boost: number): PulseOut {
  return {
    scale: 1 + voice * 0.12 + boost * 0.04,
    glow: Math.min(1, 0.55 + voice * 0.4 + boost * 0.2),
    speed: 1 + voice * 1.5 + boost * 2,
  };
}

/** Ainda há o que animar (para o laço de quadros parar quando acaba). */
export function pulsing(p: Pulse, speaking: boolean, now: number, voice: number): boolean {
  return speaking || voice > 0.01 || tokenBoost(p, now) > 0;
}
