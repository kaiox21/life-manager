import type { Turn } from "../lib/types";
import { CardView } from "./Cards";

interface Props {
  turn: Turn;
  onConfirm: (turnId: string, confirmId: string, accepted: boolean) => void;
}

const clock = (ms: number) =>
  new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function TurnView({ turn, onConfirm }: Props) {
  return (
    <article className={`turn turn--${turn.status}`}>
      <p className="turn__question">{turn.question}</p>
      {turn.steps.length > 0 && (
        <ol className="steps" aria-live="polite">
          {turn.steps.map((s, i) => {
            const now = turn.status === "thinking" && i === turn.steps.length - 1;
            return (
              <li key={i} className={now ? "steps__item steps__item--now" : "steps__item"}>
                <time className="steps__time">{clock(s.at)}</time>
                {s.text}
              </li>
            );
          })}
        </ol>
      )}
      {turn.cards.map((c, i) => (
        <CardView key={i} card={c} />
      ))}
      {turn.confirm && (
        <div className="confirm" role="group" aria-label="Confirmação">
          <p>{turn.confirm.text}</p>
          <div className="confirm__actions">
            <button type="button" className="btn btn--ghost" onClick={() => onConfirm(turn.id, turn.confirm!.confirmId, false)}>
              Cancelar
            </button>
            <button type="button" className="btn btn--primary" autoFocus onClick={() => onConfirm(turn.id, turn.confirm!.confirmId, true)}>
              Confirmar
            </button>
          </div>
        </div>
      )}
      {turn.answer && <p className={`turn__answer${turn.status === "error" ? " turn__answer--error" : ""}`}>{turn.answer}</p>}
    </article>
  );
}
