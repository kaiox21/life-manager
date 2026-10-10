import type { Mode, ServerEvent, Turn } from "./types";

export const MAX_TURNS = 4;

/** Aplica um evento do cérebro à conversa (função pura, testada). */
export function applyEvent(turns: Turn[], ev: ServerEvent, now: number = Date.now()): Turn[] {
  if (ev.type === "no_speech") return turns.filter((t) => t.id !== ev.id);
  return turns.map((t) => {
    if (t.id !== ev.id) return t;
    switch (ev.type) {
      case "heard":
        return { ...t, question: ev.text, status: "thinking" };
      case "step":
        return { ...t, steps: [...t.steps, { text: ev.text, at: now }], status: "thinking" };
      case "token":
        return { ...t, answer: t.answer + ev.text };
      case "card":
        return { ...t, cards: [...t.cards, ev.card] };
      case "confirm":
        return { ...t, confirm: { confirmId: ev.confirm_id, text: ev.text } };
      case "done":
        return { ...t, answer: ev.text, status: "done", confirm: undefined };
      case "error":
        return { ...t, answer: ev.text, status: "error", confirm: undefined };
      default:
        return t;
    }
  });
}

/** "Jarvis" detectado: começa um turno de voz com o id do cérebro (o pedido chega em `heard`). */
export function startWakeTurn(turns: Turn[], id: string): Turn[] {
  return turns.some((t) => t.id === id) ? turns : startTurn(turns, id, "", "voz");
}

export function startTurn(turns: Turn[], id: string, question: string, mode: Mode = "texto"): Turn[] {
  const next: Turn = {
    id,
    mode,
    question,
    steps: [],
    cards: [],
    answer: "",
    status: mode === "voz" ? "listening" : "thinking",
  };
  return [...turns, next].slice(-MAX_TURNS);
}

export function clearConfirm(turns: Turn[], confirmId: string): Turn[] {
  return turns.map((t) => (t.confirm?.confirmId === confirmId ? { ...t, confirm: undefined } : t));
}
