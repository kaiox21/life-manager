import type { ServerEvent, Turn } from "./types";

export const MAX_TURNS = 4;

/** Aplica um evento do cérebro à conversa (função pura, testada). */
export function applyEvent(turns: Turn[], ev: ServerEvent, now: number = Date.now()): Turn[] {
  return turns.map((t) => {
    if (t.id !== ev.id) return t;
    switch (ev.type) {
      case "step":
        return { ...t, steps: [...t.steps, { text: ev.text, at: now }] };
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
    }
  });
}

export function startTurn(turns: Turn[], id: string, question: string): Turn[] {
  const next: Turn = { id, question, steps: [], cards: [], answer: "", status: "thinking" };
  return [...turns, next].slice(-MAX_TURNS);
}

export function clearConfirm(turns: Turn[], confirmId: string): Turn[] {
  return turns.map((t) => (t.confirm?.confirmId === confirmId ? { ...t, confirm: undefined } : t));
}
