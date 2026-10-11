import { useMemo, type ReactNode } from "react";

// Peças do painel HUD (change jarvis-painel-hud): anéis e medidores em SVG, parados. O valor muda
// por stroke-dasharray com uma transição curta, só quando o dado muda (nada anima sozinho).

/** Marcações radiais: um único path, gerado uma vez por combinação de medidas. */
export function tickPath(cx: number, r1: number, r2: number, n: number, from = 0, to = 360): string {
  let d = "";
  for (let i = 0; i < n; i++) {
    const a = ((from + ((to - from) * i) / n - 90) * Math.PI) / 180;
    const c = Math.cos(a);
    const s = Math.sin(a);
    d += `M${(cx + r1 * c).toFixed(1)} ${(cx + r1 * s).toFixed(1)}L${(cx + r2 * c).toFixed(1)} ${(cx + r2 * s).toFixed(1)}`;
  }
  return d;
}

const clamp = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

/** Arco proporcional (0–1) num círculo de `span` (1 = volta inteira), com dasharray. */
export function arcDash(r: number, value: number, span = 1): string {
  const circ = 2 * Math.PI * r;
  return `${(circ * span * clamp(value)).toFixed(1)} ${circ.toFixed(1)}`;
}

interface RingProps {
  value: number; // 0–1
  size: number;
  stroke?: number;
  color?: string;
  ticks?: number;
  label: string; // leitor de tela
  children?: ReactNode; // texto no centro (SVG <text>)
}

/** Anel de volta inteira: dia do mês, ciclo da fatura, medidores do Mac. */
export function Ring({ value, size, stroke = 8, color = "var(--accent)", ticks = 0, label, children }: RingProps) {
  const c = size / 2;
  const r = c - stroke / 2 - 2;
  const marks = useMemo(() => (ticks ? tickPath(c, r - stroke - 6, r - stroke - 2, ticks) : ""), [c, r, stroke, ticks]);
  return (
    <svg className="hud-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
      <circle cx={c} cy={c} r={r} fill="none" stroke="var(--track)" strokeWidth={stroke} />
      <circle
        className="hud-ring__value"
        cx={c}
        cy={c}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeDasharray={arcDash(r, value)}
        transform={`rotate(-90 ${c} ${c})`}
      />
      {marks && <path d={marks} stroke="var(--line-strong)" strokeWidth={1.5} />}
      {children}
    </svg>
  );
}

/** Medidor de 270° (clima): a escala vai de `min` a `max`. */
export function Gauge({
  value,
  min,
  max,
  size,
  label,
  children,
}: {
  value: number;
  min: number;
  max: number;
  size: number;
  label: string;
  children?: ReactNode;
}) {
  const c = size / 2;
  const r = c - 8;
  const marks = useMemo(() => tickPath(c, r - 18, r - 13, 30, -135, 135), [c, r]);
  const frac = (value - min) / (max - min);
  return (
    <svg className="hud-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
      <circle
        cx={c}
        cy={c}
        r={r}
        fill="none"
        stroke="var(--track)"
        strokeWidth={10}
        strokeDasharray={arcDash(r, 1, 0.75)}
        transform={`rotate(135 ${c} ${c})`}
      />
      <circle
        className="hud-ring__value"
        cx={c}
        cy={c}
        r={r}
        fill="none"
        stroke="var(--accent)"
        strokeWidth={10}
        strokeDasharray={arcDash(r, frac, 0.75)}
        transform={`rotate(135 ${c} ${c})`}
      />
      <path d={marks} stroke="var(--line-strong)" strokeWidth={1.5} />
      {children}
    </svg>
  );
}

/** Cartão de cantos chanfrados do HUD. `note` fica à direita do título (fonte, hora…). */
export function HudCard({
  title,
  note,
  className = "",
  busy,
  children,
}: {
  title: string;
  note?: ReactNode;
  className?: string;
  busy?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`hud-card ${className}`} aria-label={title} aria-busy={busy}>
      <header className="hud-card__head">
        <h2 className="hud-card__title">{title}</h2>
        {note && <span className="hud-card__note">{note}</span>}
      </header>
      {children}
    </section>
  );
}
