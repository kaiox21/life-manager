import { useEffect, useRef } from "react";
import type { OrbState } from "./Orb";

interface Props {
  state: OrbState;
  /** Nível do microfone (0–1) para "ouvindo". */
  level?: number;
  /** Só anima com o painel aberto. */
  active: boolean;
  size?: number;
}

const COUNT = 800;
const FPS = 60;

/** Pontos numa esfera (espiral de Fibonacci): distribuição uniforme e estável. */
function sphere(count: number) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  return Array.from({ length: count }, (_, i) => {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const t = golden * i;
    return { x: Math.cos(t) * r, y, z: Math.sin(t) * r, s: 0.6 + ((i * 7919) % 100) / 120 };
  });
}

const SPEED: Record<OrbState, number> = { idle: 0.12, listening: 0.25, thinking: 0.7, speaking: 0.3, offline: 0 };

/** Cor do tema se o canvas souber ler (oklch), senão a reserva. */
function canvasColor(ctx: CanvasRenderingContext2D, css: string, fallback: string): string {
  ctx.fillStyle = fallback;
  ctx.fillStyle = css.trim() || fallback;
  return ctx.fillStyle;
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Orbe do painel: esfera de partículas girando, com anéis marcados (Canvas 2D). */
export function PanelOrb({ state, level = 0, active, size = 420 }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef({ state, level });
  live.current = { state, level };

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    el.width = size * dpr;
    el.height = size * dpr;
    ctx.scale(dpr, dpr);
    const points = sphere(COUNT);
    const accent = canvasColor(ctx, getComputedStyle(el).getPropertyValue("--accent"), "#6fd3f5");
    const core = canvasColor(ctx, getComputedStyle(el).getPropertyValue("--glow-core"), "#eafcff");
    let angle = 0;
    let ring = 0;
    let last = performance.now();
    let frame = 0;

    const draw = (now: number) => {
      const { state: st, level: lv } = live.current;
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      angle += SPEED[st] * dt;
      ring += (SPEED[st] * 0.5 + 0.05) * dt;
      const c = size / 2;
      const pulse =
        st === "listening" ? 1 + Math.min(lv * 4, 0.25) : st === "speaking" ? 1 + Math.sin(now / 160) * 0.04 : 1;
      const radius = size * 0.27 * pulse;
      ctx.clearRect(0, 0, size, size);

      // brilho do núcleo
      const glow = ctx.createRadialGradient(c, c, 0, c, c, radius * 1.3);
      glow.addColorStop(0, core);
      glow.addColorStop(0.25, accent);
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.globalAlpha = st === "offline" ? 0.25 : st === "thinking" ? 0.75 : 0.55;
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, size, size);

      // partículas: gira em Y, inclina um pouco em X, mais claras na frente
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      ctx.fillStyle = accent;
      for (const p of points) {
        const x = p.x * cos - p.z * sin;
        const z = p.x * sin + p.z * cos;
        const y = p.y * 0.96 - z * 0.28;
        const depth = (z + 1) / 2;
        ctx.globalAlpha = (0.15 + depth * 0.85) * (st === "offline" ? 0.3 : 1);
        const r = p.s * (0.5 + depth * 0.9);
        ctx.fillRect(c + x * radius - r / 2, c + y * radius - r / 2, r, r);
      }

      // anéis: marcações girando em sentidos opostos
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.arc(c, c, size * 0.4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 0.85;
      for (let i = 0; i < 72; i++) {
        const a = (i / 72) * Math.PI * 2 + ring;
        const inner = size * (i % 6 === 0 ? 0.43 : 0.445);
        ctx.beginPath();
        ctx.moveTo(c + Math.cos(a) * inner, c + Math.sin(a) * inner);
        ctx.lineTo(c + Math.cos(a) * size * 0.46, c + Math.sin(a) * size * 0.46);
        ctx.stroke();
      }
      ctx.setLineDash([2, 7]);
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.arc(c, c, size * 0.36, -ring * 1.6, Math.PI * 2 - ring * 1.6);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    };

    if (!active || reducedMotion()) {
      draw(performance.now()); // um quadro estático
      return;
    }
    let previous = 0;
    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (now - previous < 1000 / FPS - 2) return;
      previous = now;
      draw(now);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [active, size]);

  return (
    <canvas
      ref={canvas}
      className="panel-orb"
      style={{ inlineSize: size, blockSize: size }}
      role="img"
      aria-label={`Jarvis ${state === "idle" ? "pronto" : state}`}
    />
  );
}
