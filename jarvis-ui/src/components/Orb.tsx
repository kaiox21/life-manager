import { useMemo } from "react";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "offline";

interface Props {
  state: OrbState;
  size?: number;
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
export function Orb({ state, size = 64 }: Props) {
  const dots = useMemo(() => particles(140), []);
  return (
    <div className={`orb orb--${state}`} style={{ inlineSize: size, blockSize: size }} role="img" aria-label={`Jarvis ${labels[state]}`}>
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
