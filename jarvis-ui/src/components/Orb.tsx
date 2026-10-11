import { useEffect, useMemo, useRef, type MutableRefObject } from "react";
import { pulseOut, pulsing, smooth, tokenBoost, voiceTarget, type Pulse } from "../lib/pulse";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "offline";

interface Props {
  state: OrbState;
  size?: number;
  /** Voz tocando e texto chegando: o orbe pulsa com a resposta (change jarvis-painel-hud). */
  pulse?: MutableRefObject<Pulse>;
}

function reducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Laço de quadros só enquanto há voz ou texto chegando; escreve variáveis CSS (sem re-render). */
function useVoicePulse(el: React.RefObject<HTMLDivElement | null>, state: OrbState, pulse?: MutableRefObject<Pulse>) {
  const speaking = state === "speaking";
  const tokenAt = pulse?.current.tokenAt ?? 0;
  useEffect(() => {
    const node = el.current;
    if (!node || !pulse || reducedMotion()) return;
    let voice = 0;
    let last = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const p = pulse.current;
      voice = smooth(voice, voiceTarget(p, speaking, now), now - last);
      last = now;
      const out = pulseOut(voice, tokenBoost(p, now));
      node.style.setProperty("--voice-scale", out.scale.toFixed(3));
      node.style.setProperty("--voice-glow", out.glow.toFixed(3));
      if (pulsing(p, speaking, now, voice)) frame = requestAnimationFrame(tick);
      else {
        node.style.removeProperty("--voice-scale");
        node.style.removeProperty("--voice-glow");
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [el, pulse, speaking, tokenAt]);
}

/** Pontos do núcleo: mais densos no centro, posições fixas (gerador com semente). */
function particles(count: number) {
  let seed = 7;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  return Array.from({ length: count }, () => {
    const r = Math.sqrt(rand()) * rand() * 46 + rand() * 4;
    const a = rand() * Math.PI * 2;
    return { x: 100 + Math.cos(a) * r, y: 100 + Math.sin(a) * r, s: 0.4 + rand() * 1.1, o: 0.35 + rand() * 0.65 };
  });
}

const ticks = Array.from({ length: 72 }, (_, i) => i * 5);
const markers = [0, 60, 120, 180, 240, 300];

/** Orbe holográfico: núcleo de partículas e anéis marcados girando em sentidos opostos. */
export function Orb({ state, size = 64, pulse }: Props) {
  const dots = useMemo(() => particles(140), []);
  const el = useRef<HTMLDivElement>(null);
  useVoicePulse(el, state, pulse);
  return (
    <div ref={el} className={`orb orb--${state}${pulse ? " orb--voice" : ""}`} style={{ inlineSize: size, blockSize: size }} role="img" aria-label={`Jarvis ${labels[state]}`}>
      <svg viewBox="0 0 200 200" aria-hidden="true">
        <defs>
          <radialGradient id="orb-glow">
            <stop offset="0" stopColor="var(--glow-core)" stopOpacity="0.95" />
            <stop offset="0.35" stopColor="var(--accent)" stopOpacity="0.45" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx="100" cy="100" r="56" fill="url(#orb-glow)" className="orb__glow" />
        <g className="orb__core">
          {dots.map((d, i) => (
            <circle key={i} cx={d.x} cy={d.y} r={d.s} opacity={d.o} />
          ))}
        </g>
        <g className="orb__ring orb__ring--ticks">
          {ticks.map((deg) => (
            <line key={deg} x1="100" y1="12" x2="100" y2={deg % 30 === 0 ? 22 : 17} transform={`rotate(${deg} 100 100)`} />
          ))}
        </g>
        <g className="orb__ring orb__ring--markers">
          <circle cx="100" cy="100" r="74" fill="none" strokeDasharray="2 6" />
          {markers.map((deg) => (
            <path key={deg} d="M100 22 l4 -7 h-8 z" transform={`rotate(${deg} 100 100)`} />
          ))}
        </g>
        <circle cx="100" cy="100" r="64" fill="none" className="orb__inner" />
      </svg>
    </div>
  );
}

const labels = {
  idle: "pronto",
  listening: "ouvindo",
  thinking: "pensando",
  speaking: "falando",
  offline: "desconectado",
} as const;
