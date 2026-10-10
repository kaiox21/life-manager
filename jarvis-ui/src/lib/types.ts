// Protocolo com o cérebro (jarvis/events.py).

export type CardItem = Record<string, string | number | boolean | undefined>;

export type Card =
  | { kind: "agenda"; title: string; items: CardItem[]; omitted: number }
  | { kind: "gastos"; title: string; total: string; count: number; items: CardItem[]; omitted: number }
  | {
      kind: "fatura";
      title: string;
      total: string;
      due: string;
      closing: string;
      status: string;
      count: number;
      items: CardItem[];
    }
  | {
      kind: "grafico";
      title: string;
      total: string;
      groupBy?: string;
      series: { label: string; value: number; display: string; count: number }[];
    }
  | { kind: "arquivos"; title: string; items: string[]; total: number }
  | { kind: "texto"; title: string; text: string; options?: string[] }
  | { kind: "terminais"; title: string; items: TerminalInfo[] };

export type ServerEvent =
  | { type: "step"; id: string; text: string }
  | { type: "token"; id: string; text: string }
  | { type: "card"; id: string; card: Card }
  | { type: "confirm"; id: string; confirm_id: string; text: string; data?: Record<string, unknown> }
  | { type: "heard"; id: string; text: string }
  | { type: "no_speech"; id: string }
  | { type: "status"; id: string; text: string }
  | { type: "speaking"; id: string; data: { on: boolean } }
  | { type: "done"; id: string; text: string; data?: { wrote?: boolean } }
  | { type: "panel"; id: string; data: PanelData | { erro: string } }
  | { type: "terminals"; id: string; data: { terminais: TerminalInfo[] } }
  | { type: "terminal_alert"; id: string; data: TerminalAlert }
  | { type: "terminal_opened"; id: string; data: TerminalOpened }
  | { type: "terminal_resolved"; id: string; data: { pedido: string; resultado: string } }
  | { type: "wake"; id: string }
  | { type: "error"; id: string; text: string };

export type Mode = "texto" | "voz";

export interface Turn {
  id: string;
  mode: Mode;
  question: string;
  steps: { text: string; at: number }[];
  cards: Card[];
  answer: string;
  confirm?: { confirmId: string; text: string };
  status: "listening" | "thinking" | "done" | "error";
}

// Painel (ferramenta `painel` do núcleo + perguntas da sessão). Tudo vem pronto: a interface
// só desenha; valores e datas já chegam formatados ao lado dos centavos.
export interface PanelEvent {
  id: string;
  titulo: string;
  tipo: string;
  data: string;
  hora: string;
  pessoa?: string;
  local?: string;
  recorrencia?: string;
}

export interface PanelData {
  agora: string;
  agenda: { hoje: PanelEvent[]; proximos: PanelEvent[] };
  mes: {
    periodo: string;
    total: string;
    total_centavos: number;
    grupos: { grupo: string; total: string; total_centavos: number; lancamentos: number }[];
  };
  faturas: {
    cartao: string;
    mes_vencimento: string;
    vencimento: string;
    fechamento: string;
    situacao: string;
    total: string;
    total_centavos: number;
    lancamentos: number;
  }[];
  registro: { tipo: "gasto" | "evento"; quando: string; texto: string; origem: "whatsapp" | "mac" | null }[];
  perguntas: string[];
}

// Terminais (jarvis/terminals.py): sessões do Claude Code e terminais compartilhados (tmux).
export type TerminalState =
  | "trabalhando"
  | "pedindo permissão"
  | "esperando você"
  | "terminou"
  | "livre" // shell no prompt
  | "rodando"; // shell com um programa em primeiro plano

export interface TerminalInfo {
  numero: number;
  pasta: string;
  desde: number; // segundos (epoch)
  estado: TerminalState;
  sessao: string;
  pid: number | null;
  ferramenta: string;
  resumo: string;
  chave?: string;
  tipo?: "claude" | "shell";
  tmux?: string; // session_id do tmux do Jarvis (vazio = sessão de fora, sem aba)
  painel?: string;
  origem?: "terminal" | "jarvis" | "";
  aba?: boolean; // aberto numa aba do painel
  janela?: boolean; // aberto numa janela do Terminal.app
  comando?: string;
  ocupado?: boolean;
  pedido?: string; // pedido de permissão aberto (terminais compartilhados)
}

export interface TerminalAlert {
  tipo: "permissao" | "espera" | "terminou";
  numero: number;
  pasta: string;
  ferramenta: string;
  resumo: string;
  texto: string;
  pedido?: string; // terminal compartilhado: o aviso tem Permitir/Negar
  chave?: string;
}

export type TerminalOpened =
  | { status: "aberto"; numero: number; pasta: string; sessao: string; tipo: "claude" | "shell" }
  | { erro: string; opcoes?: never }
  | { opcoes: string[]; erro?: never };
