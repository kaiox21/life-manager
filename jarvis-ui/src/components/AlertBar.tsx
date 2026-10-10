import type { ShownAlert } from "../lib/terminals";

const RESULT: Record<string, string> = {
  // o Jarvis não vê se o Kaio já tinha respondido no Terminal.app: diz só o que mandou
  permitido: "Permitir enviado ao terminal.",
  negado: "Negar enviado ao terminal.",
  "respondido na aba": "Respondido no terminal.",
  "sem resposta": "O pedido expirou: responda no terminal.",
  "já respondido": "Esse pedido já tinha sido respondido.",
};

/** Aviso de terminal. Numa sessão aberta pelo Jarvis (com `pedido`), tem Permitir e Negar:
 * a resposta só sai deste clique (sem atalho de teclado, sem foco automático). */
export function AlertBar({
  alert,
  onAnswer,
  onDismiss,
  className = "",
}: {
  alert: ShownAlert;
  onAnswer: (pedido: string, decisao: "permitir" | "negar") => void;
  onDismiss?: () => void;
  className?: string;
}) {
  const pedido = alert.pedido;
  return (
    <div className={`term-alert ${className}`} role="alert">
      <p className="term-alert__text">{alert.texto}</p>
      {onDismiss && (
        <button type="button" className="term-alert__close" aria-label="Fechar o aviso" onClick={onDismiss}>
          ×
        </button>
      )}
      {pedido &&
        (alert.resolvido ? (
          <p className="term-alert__result" role="status">
            {RESULT[alert.resolvido] ?? alert.resolvido}
          </p>
        ) : (
          <div className="term-alert__actions">
            <button
              type="button"
              className="btn btn--deny"
              disabled={!!alert.enviado}
              onClick={() => onAnswer(pedido, "negar")}
            >
              Negar
            </button>
            <button
              type="button"
              className="btn btn--allow"
              disabled={!!alert.enviado}
              onClick={() => onAnswer(pedido, "permitir")}
            >
              Permitir
            </button>
          </div>
        ))}
    </div>
  );
}
