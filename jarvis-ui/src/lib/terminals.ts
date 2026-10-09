import type { TerminalAlert, TerminalInfo } from "./types";

export const ALERT_MS = 20_000;

export interface ShownAlert extends TerminalAlert {
  at: number; // ms
}

const STATE_FOR: Record<TerminalAlert["tipo"], TerminalInfo["estado"]> = {
  permissao: "pedindo permissão",
  espera: "esperando você",
  terminou: "terminou",
};

/** Avisos que chamam o Kaio (aparecem por cima); "terminou" só muda a lista. */
export function isLoud(alert: TerminalAlert): boolean {
  return alert.tipo !== "terminou";
}

/** O aviso continua enquanto o terminal segue naquele estado, por no máximo 20 s. */
export function alertActive(alert: ShownAlert | null, terminals: TerminalInfo[], now: number): boolean {
  if (!alert || now - alert.at > ALERT_MS) return false;
  const t = terminals.find((x) => x.numero === alert.numero);
  return !!t && t.estado === STATE_FOR[alert.tipo];
}

export function sinceLabel(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
