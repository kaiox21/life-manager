import { sinceLabel } from "../lib/terminals";
import type { Card, CardItem, TerminalInfo } from "../lib/types";

const text = (v: CardItem[string]) => (v === undefined || v === null ? "" : String(v));

export function CardView({ card }: { card: Card }) {
  switch (card.kind) {
    case "agenda":
      return <AgendaCard card={card} />;
    case "gastos":
      return <GastosCard card={card} />;
    case "fatura":
      return <FaturaCard card={card} />;
    case "grafico":
      return <ChartCard card={card} />;
    case "arquivos":
      return <ArquivosCard card={card} />;
    case "texto":
      return <TextCard card={card} />;
    case "terminais":
      return (
        <Shell title={card.title} kind="terminais">
          <TerminalList items={card.items} />
        </Shell>
      );
  }
}

function Shell({ title, kind, children }: { title: string; kind: string; children: React.ReactNode }) {
  return (
    <section className={`card card--${kind}`} aria-label={title}>
      <h3 className="card__title">{title}</h3>
      {children}
    </section>
  );
}

function AgendaCard({ card }: { card: Extract<Card, { kind: "agenda" }> }) {
  if (card.items.length === 0) {
    return (
      <Shell title={card.title} kind="agenda">
        <p className="card__empty">Nada na agenda.</p>
      </Shell>
    );
  }
  return (
    <Shell title={card.title} kind="agenda">
      <ul className="agenda">
        {card.items.map((it, i) => (
          <li key={i} className="agenda__item">
            <span className="agenda__time">{text(it.hora)}</span>
            <span className="agenda__body">
              <strong>{text(it.titulo)}</strong>
              <small>
                {[it.data, it.pessoa, it.local, it.recorrencia].filter(Boolean).map(text).join(" · ")}
              </small>
            </span>
          </li>
        ))}
      </ul>
      {card.omitted > 0 && <p className="card__more">+{card.omitted} eventos</p>}
    </Shell>
  );
}

function GastosCard({ card }: { card: Extract<Card, { kind: "gastos" }> }) {
  return (
    <Shell title={card.title} kind="gastos">
      <p className="card__total">
        {card.total} <small>{card.count === 1 ? "1 lançamento" : `${card.count} lançamentos`}</small>
      </p>
      <ul className="rows">
        {card.items.map((it, i) => (
          <li key={i} className="rows__item">
            <span>
              {text(it.descricao)}
              <small>{[it.data, it.meio, it.categoria].filter(Boolean).map(text).join(" · ")}</small>
            </span>
            <span className="rows__value">{text(it.valor)}</span>
          </li>
        ))}
      </ul>
      {card.omitted > 0 && <p className="card__more">+{card.omitted} lançamentos</p>}
    </Shell>
  );
}

function FaturaCard({ card }: { card: Extract<Card, { kind: "fatura" }> }) {
  return (
    <Shell title={card.title} kind="fatura">
      <p className="card__total">
        {card.total} <span className={`chip chip--${card.status}`}>{card.status}</span>
      </p>
      <p className="card__meta">
        Fecha {card.closing} · vence {card.due} · {card.count} lançamentos
      </p>
      {card.items.length > 0 && (
        <ul className="rows">
          {card.items.map((it, i) => (
            <li key={i} className="rows__item">
              <span>{text(it.descricao)}</span>
              <span className="rows__value">{text(it.valor)}</span>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

function ChartCard({ card }: { card: Extract<Card, { kind: "grafico" }> }) {
  const max = Math.max(1, ...card.series.map((s) => s.value));
  return (
    <Shell title={card.title} kind="grafico">
      <p className="card__total">{card.total}</p>
      <ul className="bars">
        {card.series.map((s) => (
          <li key={s.label} className="bars__row">
            <span className="bars__label">{s.label}</span>
            <span className="bars__track" aria-hidden="true">
              <span className="bars__fill" style={{ inlineSize: `${(s.value / max) * 100}%` }} />
            </span>
            <span className="bars__value">{s.display}</span>
          </li>
        ))}
      </ul>
    </Shell>
  );
}

function ArquivosCard({ card }: { card: Extract<Card, { kind: "arquivos" }> }) {
  return (
    <Shell title={card.title} kind="arquivos">
      <ul className="files">
        {card.items.map((p) => (
          <li key={p} className="files__item" title={p}>
            {p}
          </li>
        ))}
      </ul>
      {card.total > card.items.length && <p className="card__more">+{card.total - card.items.length} arquivos</p>}
    </Shell>
  );
}

function TextCard({ card }: { card: Extract<Card, { kind: "texto" }> }) {
  return (
    <Shell title={card.title} kind="texto">
      <p>{card.text}</p>
      {card.options && card.options.length > 0 && (
        <ul className="chips">
          {card.options.map((o) => (
            <li key={o} className="chip">
              {o}
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

/** Lista de terminais (cartão e painel). Terminais compartilhados sem aba ganham "abrir aba". */
export function TerminalList({ items, onOpenTab }: { items: TerminalInfo[]; onOpenTab?: (sessao: string) => void }) {
  if (items.length === 0) return <p className="card__empty">Nenhum terminal aberto.</p>;
  return (
    <ul className="terms">
      {items.map((t) => (
        <li key={t.numero} className={`terms__item terms__item--${t.estado === "pedindo permissão" ? "ask" : t.estado === "esperando você" ? "wait" : "ok"}`}>
          <span className="terms__num">T{t.numero}</span>
          <span className="terms__where">
            {t.pasta}
            <small> · desde {sinceLabel(t.desde)}</small>
          </span>
          <span className="terms__state">
            {t.tmux ? (t.tipo === "claude" ? "Claude Code · " : "terminal · ") : ""}
            {t.estado}
          </span>
          {onOpenTab && t.tmux && !t.aba && (
            <button type="button" className="terms__open btn btn--ghost" onClick={() => onOpenTab(t.tmux!)}>
              abrir aba
            </button>
          )}
          {t.resumo && <code className="terms__ask">{t.resumo}</code>}
        </li>
      ))}
    </ul>
  );
}
