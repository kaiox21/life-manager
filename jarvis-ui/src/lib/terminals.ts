import type { TerminalAlert, TerminalInfo } from "./types";

export const ALERT_MS = 20_000;

export const RESOLVED_MS = 2_500;

export interface ShownAlert extends TerminalAlert {
  at: number; // ms
  /** Pedido de uma aba já resolvido: "permitido", "negado", "respondido na aba"… */
  resolvido?: string;
  resolvidoAt?: number;
  /** Clique enviado, esperando a confirmação do cérebro. */
  enviado?: "permitir" | "negar";
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

/** O aviso continua enquanto o terminal segue naquele estado, por no máximo 20 s. O de uma
 * aba (com `pedido`) fica até o pedido ser resolvido e mostra o resultado por 2,5 s. */
export function alertActive(alert: ShownAlert | null, terminals: TerminalInfo[], now: number): boolean {
  if (!alert) return false;
  if (alert.pedido) {
    return !alert.resolvido || now - (alert.resolvidoAt ?? 0) < RESOLVED_MS;
  }
  if (now - alert.at > ALERT_MS) return false;
  const t = terminals.find((x) => x.numero === alert.numero);
  return !!t && t.estado === STATE_FOR[alert.tipo];
}

/** Marca o pedido como resolvido no aviso mostrado (se for o mesmo). */
export function resolveAlert(alert: ShownAlert | null, pedido: string, resultado: string, now: number) {
  if (!alert || alert.pedido !== pedido) return alert;
  return { ...alert, resolvido: resultado, resolvidoAt: now };
}

/** Estado de uma aba, pela lista de terminais (a sessão aberta pelo Jarvis tem `aba` = sid). */
export function tabState(sid: string, terminals: TerminalInfo[]): TerminalInfo["estado"] | undefined {
  return terminals.find((t) => t.aba === sid)?.estado;
}

export function isBusy(estado: TerminalInfo["estado"] | undefined): boolean {
  return estado === "trabalhando" || estado === "pedindo permissão";
}

export function sinceLabel(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
