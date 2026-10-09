import type { PanelData } from "./types";

export interface PanelState {
  /** Últimos dados bons (ficam visíveis, esmaecidos, quando o núcleo cai). */
  data: PanelData | null;
  /** Vazio quando os dados são atuais. */
  error: string;
  /** Momento (ms) da última atualização bem-sucedida. */
  updatedAt: number | null;
  loading: boolean;
}

export const EMPTY_PANEL: PanelState = { data: null, error: "", updatedAt: null, loading: false };
export const PANEL_REFRESH_MS = 60_000;

export function panelLoading(state: PanelState): PanelState {
  return { ...state, loading: true };
}

/** Resposta do cérebro: dados novos ou erro (mantendo os antigos marcados como antigos). */
export function applyPanel(state: PanelState, payload: PanelData | { erro: string }, now: number): PanelState {
  if ("erro" in payload) return { ...state, error: payload.erro, loading: false };
  return { data: payload, error: "", updatedAt: now, loading: false };
}

export function panelFailed(state: PanelState, error: string): PanelState {
  return { ...state, error, loading: false };
}

/** Largura da barra de uma categoria: proporção visual, o número exibido vem do núcleo. */
export function barShare(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0;
  return Math.max(2, Math.round((value / max) * 100));
}

export function hhmm(ms: number | string): string {
  return new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Hora se for hoje; senão dia/mês (o registro mistura dias). */
export function whenShort(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (d.toDateString() === now.toDateString()) return hhmm(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** "sábado 10/10/2026" (do núcleo) → "sáb 10/10". */
export function dayShort(data: string): string {
  const [weekday, date = ""] = data.split(" ");
  return `${weekday.slice(0, 3)} ${date.replace(/\/\d{4}$/, "")}`.trim();
}
