import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import type { OrbState } from "./components/Orb";
import { PanelOrb } from "./components/PanelOrb";
import { TurnView } from "./components/TurnView";
import { Waveform } from "./components/Waveform";
import { PANEL_REFRESH_MS, barShare, dayShort, hhmm, whenShort, type PanelState } from "./lib/panel";
import type { PanelData } from "./lib/types";
import { useJarvis } from "./lib/useJarvis";

function useNow(active: boolean) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!active) return;
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

/** Painel "central de comando": orbe e conversa no centro, agenda, gastos e registro em volta. */
export function Panel() {
  const j = useJarvis();
  const { turns, link, status, speaking, listening, levels, thinking, panel } = j;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const now = useNow(open);
  const api = useRef(j);
  api.current = j;
  const openRef = useRef(open);
  openRef.current = open;

  // Abrir/fechar vem do Rust (atalho, menu, Esc); a fala só chega aqui com o painel aberto.
  useEffect(() => {
    const unlisten = Promise.all([
      listen<boolean>("jarvis://panel", (e) => {
        setOpen(e.payload);
        if (e.payload) {
          api.current.requestPanel();
          input.current?.focus();
        }
      }),
      listen("jarvis://shown", () => input.current?.focus()),
      listen<{ state: "down" | "up"; target: string }>("jarvis://ptt", (e) => {
        if (e.payload.target !== "painel") return;
        if (e.payload.state === "down") void api.current.startVoice();
        else api.current.endVoice();
      }),
    ]);
    return () => void unlisten.then((fns) => fns.forEach((f) => f()));
  }, []);

  // A cada 60 s enquanto aberto e logo depois de um turno que gravou algo.
  useEffect(() => {
    j.setOnWrite(() => {
      if (openRef.current) api.current.requestPanel();
    });
  }, [j]);
  useEffect(() => {
    if (!open) return;
    const t = setInterval(() => api.current.requestPanel(), PANEL_REFRESH_MS);
    return () => clearInterval(t);
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") void invoke("hide_panel");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const orb: OrbState =
    link === "offline" ? "offline" : listening ? "listening" : speaking ? "speaking" : thinking || status ? "thinking" : "idle";
  const label =
    link === "offline" ? "offline" : listening ? "ouvindo" : status ? status.replace(/…$/, "") : speaking ? "falando" : thinking ? "pensando" : "online";
  const last = turns[turns.length - 1];

  return (
    <main className="painel">
      <header className="painel__top">
        <div className="painel__brand">
          J.A.R.V.I.S <small>central de comando</small>
        </div>
        <div className="painel__clock">
          <time className="painel__time">{now.toLocaleTimeString("pt-BR")}</time>
          <span className="painel__date">
            {now.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </span>
          <span className="painel__link">
            <span className={`led led--${link}`} aria-hidden="true" /> {label}
          </span>
        </div>
      </header>

      <Agenda panel={panel} />

      <section className="painel__center" aria-label="Conversa">
        <PanelOrb state={orb} level={levels[levels.length - 1] ?? 0} active={open} />
        <div className="painel__turn" aria-live="polite">
          {last ? <TurnView turn={last} onConfirm={j.answerConfirm} /> : <p className="painel__hint">Pergunte, ou segure ⌘⇧Espaço e fale.</p>}
        </div>
        <form
          className="prompt painel__prompt"
          onSubmit={(e) => {
            e.preventDefault();
            j.ask(draft);
            setDraft("");
          }}
        >
          {listening ? (
            <Waveform levels={levels} />
          ) : (
            <>
              <label className="visually-hidden" htmlFor="painel-ask">
                Pergunte ao Jarvis
              </label>
              <input
                id="painel-ask"
                ref={input}
                className="prompt__input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={link === "offline" ? "Jarvis desconectado" : "Pergunte ao Jarvis…"}
                autoComplete="off"
                spellCheck={false}
              />
            </>
          )}
          <kbd className="prompt__hint">esc</kbd>
        </form>
      </section>

      <Money panel={panel} />
      <Log panel={panel} />
    </main>
  );
}

function Column({
  title,
  panel,
  className,
  children,
}: {
  title: string;
  panel: PanelState;
  className: string;
  children: (data: PanelData) => React.ReactNode;
}) {
  const stale = !!panel.error;
  return (
    <section className={`painel__col ${className}`} aria-label={title} aria-busy={panel.loading}>
      <h2 className="painel__title">{title}</h2>
      {stale && (
        <p className="painel__warn" role="status">
          {panel.error}
          {panel.updatedAt ? ` · dados de ${hhmm(panel.updatedAt)}` : ""}
        </p>
      )}
      {panel.data ? (
        <div className={stale ? "painel__stale" : undefined}>{children(panel.data)}</div>
      ) : (
        !stale && <p className="painel__empty">carregando…</p>
      )}
    </section>
  );
}

export function Agenda({ panel }: { panel: PanelState }) {
  return (
    <Column title="Agenda" panel={panel} className="painel__agenda">
      {(d) => (
        <>
          <h3 className="painel__sub">Hoje</h3>
          {d.agenda.hoje.length === 0 ? (
            <p className="painel__empty">Dia livre.</p>
          ) : (
            <ul className="painel__list">
              {d.agenda.hoje.map((e) => (
                <li key={e.id + e.hora}>
                  <span className="painel__when">{e.hora}</span>
                  <span>
                    {e.titulo}
                    {e.local && <small> · {e.local}</small>}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <h3 className="painel__sub">Próximos 7 dias</h3>
          {d.agenda.proximos.length === 0 ? (
            <p className="painel__empty">Nada marcado.</p>
          ) : (
            <ul className="painel__list">
              {d.agenda.proximos.map((e) => (
                <li key={e.id + e.data}>
                  <span className="painel__when">
                    {dayShort(e.data)}
                    <small>{e.hora}</small>
                  </span>
                  <span>{e.titulo}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Column>
  );
}

export function Money({ panel }: { panel: PanelState }) {
  return (
    <Column title="Gastos do mês" panel={panel} className="painel__money">
      {(d) => {
        const max = Math.max(0, ...d.mes.grupos.map((g) => g.total_centavos));
        return (
          <>
            <p className="painel__big">
              {d.mes.total}
              <small>{d.mes.periodo}</small>
            </p>
            {d.mes.grupos.length === 0 ? (
              <p className="painel__empty">Nenhum gasto ainda.</p>
            ) : (
              <ul className="painel__bars">
                {d.mes.grupos.map((g) => (
                  <li key={g.grupo}>
                    <span>{g.grupo}</span>
                    <span className="painel__value">{g.total}</span>
                    <span className="painel__bar" style={{ inlineSize: `${barShare(g.total_centavos, max)}%` }} />
                  </li>
                ))}
              </ul>
            )}
            <h3 className="painel__sub">Faturas abertas</h3>
            {d.faturas.length === 0 ? (
              <p className="painel__empty">Nenhum cartão de crédito.</p>
            ) : (
              <ul className="painel__list painel__cards">
                {d.faturas.map((f) => (
                  <li key={f.cartao}>
                    <span>
                      {f.cartao}
                      <small>
                        fecha {f.fechamento.slice(0, 5)} · vence {f.vencimento.slice(0, 5)}
                      </small>
                    </span>
                    <span className="painel__value">{f.total}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        );
      }}
    </Column>
  );
}

export function Log({ panel }: { panel: PanelState }) {
  return (
    <Column title="Registro" panel={panel} className="painel__log">
      {(d) => (
        <div className="painel__logcols">
          <ul className="painel__list">
            {d.registro.length === 0 && <li className="painel__empty">Nada lançado ainda.</li>}
            {d.registro.map((r) => (
              <li key={r.quando + r.texto}>
                <span className="painel__when">{whenShort(r.quando)}</span>
                <span>
                  {r.texto}
                  {r.origem && <small className="painel__origin"> {r.origem === "whatsapp" ? "WhatsApp" : "Mac"}</small>}
                </span>
              </li>
            ))}
          </ul>
          <ul className="painel__list painel__questions" aria-label="Perguntas desta sessão">
            {d.perguntas.map((q, i) => (
              <li key={i}>
                <span className="painel__when">›</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Column>
  );
}
