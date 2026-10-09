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
  | { kind: "texto"; title: string; text: string; options?: string[] };

export type ServerEvent =
  | { type: "step"; id: string; text: string }
  | { type: "token"; id: string; text: string }
  | { type: "card"; id: string; card: Card }
  | { type: "confirm"; id: string; confirm_id: string; text: string; data?: Record<string, unknown> }
  | { type: "heard"; id: string; text: string }
  | { type: "no_speech"; id: string }
  | { type: "status"; id: string; text: string }
  | { type: "speaking"; id: string; data: { on: boolean } }
  | { type: "done"; id: string; text: string }
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
