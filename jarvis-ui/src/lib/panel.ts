import type { PanelData, PanelEvent } from "./types";

export interface PanelState {
  /** Últimos dados bons (ficam visíveis, esmaecidos, quando o núcleo cai). */
  data: PanelData | null;
  /** Vazio quando os dados são atuais. */
  error: string;
  /** Momento (ms) da última atualização bem-sucedida. */
  updatedAt: number | null;
  loading: boolean;
  /** Dados locais do cérebro (clima, Mac, música, projetos): chegam mesmo com o núcleo fora. */
  local?: LocalData;
}

export type LocalData = Pick<PanelData, "clima" | "mac" | "musica" | "projetos" | "claude">;

export const EMPTY_PANEL: PanelState = { data: null, error: "", updatedAt: null, loading: false };

function localOf(payload: Partial<PanelData>): LocalData | undefined {
  const keys = ["clima", "mac", "musica", "projetos", "claude"];
  if (!keys.some((k) => k in payload)) return undefined;
  return { clima: payload.clima, mac: payload.mac, musica: payload.musica, projetos: payload.projetos, claude: payload.claude };
}
export const PANEL_REFRESH_MS = 60_000;

export function panelLoading(state: PanelState): PanelState {
  return { ...state, loading: true };
}

/** Resposta do cérebro: dados novos ou erro (mantendo os antigos marcados como antigos). */
export function applyPanel(
  state: PanelState,
  payload: PanelData | ({ erro: string } & Partial<PanelData>),
  now: number,
): PanelState {
  const local = localOf(payload) ?? state.local;
  if ("erro" in payload) return { ...state, error: payload.erro, loading: false, local };
  return { data: payload, error: "", updatedAt: now, loading: false, local };
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

/** Compromisso de hoje já passou? ("dia inteiro" nunca passa.) */
export function isPast(e: PanelEvent, now: Date): boolean {
  if (!/^\d\d:\d\d$/.test(e.hora)) return false;
  return e.hora < now.toTimeString().slice(0, 5);
}

/** O próximo compromisso de hoje (o primeiro que não passou, inclusive o de dia inteiro). */
export function nextEvent(hoje: PanelEvent[], now: Date): PanelEvent | null {
  return hoje.find((e) => !isPast(e, now)) ?? null;
}

/** "zera em 2h10" / "zera em 3 dias" a partir do epoch (s) de reinício da janela. */
export function resetsIn(epoch: number | null, now: number = Date.now()): string {
  if (!epoch) return "";
  const min = Math.max(0, Math.round((epoch * 1000 - now) / 60000));
  if (min < 60) return `zera em ${min} min`;
  if (min < 48 * 60) return `zera em ${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`;
  return `zera em ${Math.round(min / 1440)} dias`;
}
