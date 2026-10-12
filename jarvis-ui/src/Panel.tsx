import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import { Gauge, HudCard, Ring } from "./components/Hud";
import type { OrbState } from "./components/Orb";
import { PanelOrb } from "./components/PanelOrb";
import { TurnView } from "./components/TurnView";
import { Waveform } from "./components/Waveform";
import { chime } from "./lib/audio";
import { alertActive, isLoud } from "./lib/terminals";
import { TerminalList } from "./components/Cards";
import { AlertBar } from "./components/AlertBar";
import { CENTRAL, TerminalTabs } from "./components/TerminalTabs";
import { TerminalView } from "./components/TerminalView";
import { PANEL_REFRESH_MS, barShare, dayShort, hhmm, isPast, nextEvent, resetsIn, whenShort, type PanelState } from "./lib/panel";
import type { PanelData, Turn } from "./lib/types";
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

/** Painel "central de comando" no estilo HUD (change jarvis-painel-hud; maquete aprovada em
 * 10/10/2026): orbe com modos no centro, cartões de anéis e medidores nas laterais. */
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
  // "central" ou o id da aba de terminal em primeiro plano
  // "central" ou a sessão do tmux da aba em primeiro plano (lembrada neste Mac)
  const [view, setViewState] = useState<string>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) || CENTRAL;
    } catch {
      return CENTRAL;
    }
  });
  const setView = (v: string) => {
    setViewState(v);
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      // sem armazenamento: só não lembra a aba
    }
  };
  const tab = j.terminals.find((t) => t.tmux && t.aba && t.tmux === view);
  const known = j.terminals.length > 0;
  useEffect(() => {
    if (view !== CENTRAL && known && !tab) setViewState(CENTRAL); // a aba sumiu (fechada)
  }, [view, tab, known]);

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

  // Fechado, o painel ignora o pulso da voz (nada redesenha à toa).
  useEffect(() => {
    api.current.setVisible(open);
  }, [open]);

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

  // Aviso de terminal com o painel aberto: aparece aqui (o HUD não abre por cima).
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    j.setOnAlert((a) => {
      if (openRef.current && isLoud(a)) chime("start");
    });
  }, [j]);
  useEffect(() => {
    if (!j.alert || !open) return;
    const t = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [j.alert, open]);
  const showAlert = open && alertActive(j.alert, j.terminals, Math.max(tick, j.alert?.at ?? 0));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Esc numa aba de terminal é do Claude Code (interromper); o painel fecha com ⌥⇧Espaço
      if (e.key === "Escape" && !inTerminal(e.target)) void invoke("hide_panel");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const orb: OrbState =
    link === "offline" ? "offline" : listening ? "listening" : speaking ? "speaking" : thinking || status ? "thinking" : "idle";
  const label =
    link === "offline" ? "offline" : listening ? "ouvindo" : status ? status.replace(/…$/, "") : speaking ? "falando" : thinking ? "pensando" : "online";
  const last = turns[turns.length - 1];
  const alertBar = showAlert && j.alert && (
    <AlertBar alert={j.alert} onAnswer={j.answerPermission} onDismiss={j.dismissAlert} className="painel__alert" />
  );
  const tabsBar = (
    <TerminalTabs
      terminals={j.terminals}
      active={tab ? view : CENTRAL}
      onSelect={setView}
      onOpen={j.openTerminal}
      onCloseTab={(sessao) => j.setTab(sessao, false)}
    />
  );

  if (tab) {
    // aba de terminal em primeiro plano: o terminal ocupa o lugar das colunas
    const pendingTurn = last && (last.confirm || last.status === "thinking" || last.status === "listening");
    return (
      <main className="painel painel--term">
        <Header now={now} link={link} label={label} />
        {tabsBar}
        <section className="painel__termarea" aria-label={`Terminal ${tab.numero}`}>
          {alertBar}
          {open && tab.tmux && (
            <TerminalView
              key={tab.tmux}
              sessao={tab.tmux}
              label={`Terminal ${tab.numero} · ${tab.pasta}`}
              attach={j.attachTerminal}
              send={j.termSend}
            />
          )}
          {pendingTurn && (
            <div className="painel__mini" aria-live="polite">
              <TurnView turn={last} onConfirm={j.answerConfirm} />
            </div>
          )}
        </section>
      </main>
    );
  }

  const firstTab = j.terminals.find((t) => t.tmux && t.aba);
  const openProject = async (caminho: string) => {
    const r = await j.openTerminal({ pasta: caminho, claude: false });
    if ("status" in r) setView(r.sessao);
  };

  return (
    <main className="painel painel--hud">
      <Header now={now} link={link} label={label} musica={panel.local?.musica} />
      {tabsBar}

      <div className="painel__side painel__side--left">
        <ClockCard now={now} panel={panel} />
        <MacCard panel={panel} />
        <HudCard title="Terminais" className="painel__terms">
          <TerminalList
            items={j.terminals}
            contexts={panel.local?.claude?.sessoes}
            onOpenTab={(sessao) => {
              j.setTab(sessao, true);
              setView(sessao);
            }}
          />
        </HudCard>
        <Month panel={panel} />
      </div>

      <section className="painel__center" aria-label="Centro">
        {alertBar}
        <div className="painel__stage">
          <PanelOrb state={orb} level={levels[levels.length - 1] ?? 0} active={open} pulse={j.pulse} size={380} />
          <nav className="painel__modes" aria-label="Modos">
            <button type="button" className="hud-mode hud-mode--a" onClick={j.briefing} disabled={link !== "online"}>
              Resumo
            </button>
            <button type="button" className="hud-mode hud-mode--b" onClick={j.toggleMusic} disabled={link !== "online"}>
              Música
            </button>
            <button
              type="button"
              className="hud-mode hud-mode--c"
              onClick={() => firstTab?.tmux && setView(firstTab.tmux)}
              disabled={!firstTab}
              title={firstTab ? undefined : "Nenhum terminal aberto numa aba"}
            >
              Terminais
            </button>
          </nav>
          <p className="painel__state" aria-live="polite">
            {label === "online" ? 'em espera · diga "Jarvis"' : label}
          </p>
        </div>
        <Conversation panel={panel} turn={last} onConfirm={j.answerConfirm} />
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
                placeholder={link === "offline" ? "Jarvis desconectado" : "Peça ao Jarvis…  (segure ⌘⇧Espaço para falar)"}
                autoComplete="off"
                spellCheck={false}
              />
            </>
          )}
          <kbd className="prompt__hint">esc</kbd>
        </form>
        <MusicStrip panel={panel} />
      </section>

      <div className="painel__side painel__side--right">
        <Agenda panel={panel} now={now} />
        <ClaudeCard panel={panel} now={now} />
        <Projects panel={panel} onOpen={(c) => void openProject(c)} />
        <Weather panel={panel} />
      </div>
    </main>
  );
}

const VIEW_KEY = "jarvis.aba";

export function inTerminal(target: EventTarget | null): boolean {
  return target instanceof Element && !!target.closest(".term-view");
}

function Header({
  now,
  link,
  label,
  musica,
}: {
  now: Date;
  link: string;
  label: string;
  musica?: PanelData["musica"];
}) {
  return (
    <header className="painel__top">
      <div className="painel__brand">J.A.R.V.I.S.</div>
      <div className="painel__chips">
        <span className="painel__chip">
          <span className={`led led--${link}`} aria-hidden="true" /> {label}
        </span>
        {musica && (
          <span className="painel__chip">
            <span className={`led ${musica.tocando ? "led--online" : "led--connecting"}`} aria-hidden="true" /> Spotify
          </span>
        )}
        <time className="visually-hidden">{now.toLocaleTimeString("pt-BR")}</time>
      </div>
    </header>
  );
}

/** Cartão com dados do núcleo: avisa quando caiu e esmaece os dados antigos. */
function CoreCard({
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
    <HudCard title={title} className={className} busy={panel.loading}>
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
    </HudCard>
  );
}

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

export function ClockCard({ now, panel }: { now: Date; panel: PanelState }) {
  const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const next = panel.data ? nextEvent(panel.data.agenda.hoje, now) : null;
  return (
    <HudCard title="Hoje" className="painel__clock">
      <div className="hud-row">
        <Ring value={now.getDate() / days} size={132} ticks={60} label={`${now.getDate()} de ${MONTHS[now.getMonth()]}`}>
          <text x="66" y="58" textAnchor="middle" className="hud-ring__cap">
            {MONTHS[now.getMonth()].toUpperCase()}
          </text>
          <text x="66" y="92" textAnchor="middle" className="hud-ring__num">
            {now.getDate()}
          </text>
        </Ring>
        <div className="hud-stack">
          <time className="painel__time">{now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</time>
          <span className="hud-label">{now.toLocaleDateString("pt-BR", { weekday: "long" })}</span>
          <span className="painel__next">
            {next ? (
              <>
                Próximo: <strong>{next.titulo}</strong> · {next.hora}
              </>
            ) : panel.data ? (
              "Nada mais hoje."
            ) : (
              ""
            )}
          </span>
        </div>
      </div>
    </HudCard>
  );
}

export function MacCard({ panel }: { panel: PanelState }) {
  const mac = panel.local?.mac;
  const items = [
    {
      label: "Memória livre",
      short: "MEMÓRIA",
      value: mac?.memoria_livre != null ? mac.memoria_livre / 100 : null,
      text: mac?.memoria_livre != null ? `${mac.memoria_livre}%` : "—",
      color: mac?.memoria_livre != null && mac.memoria_livre < 20 ? "var(--danger)" : "var(--accent)",
    },
    {
      label: "Swap usado",
      short: "SWAP",
      value: mac?.swap_gb != null ? Math.min(1, mac.swap_gb / 8) : null,
      text: mac?.swap_gb != null ? `${mac.swap_gb.toLocaleString("pt-BR")}G` : "—",
      color: "var(--accent-2)",
    },
    {
      label: "Bateria",
      short: mac?.bateria?.carregando ? "CARREGANDO" : "BATERIA",
      value: mac?.bateria ? mac.bateria.pct / 100 : null,
      text: mac?.bateria ? `${mac.bateria.pct}%` : "—",
      color: "var(--accent)",
    },
  ];
  return (
    <HudCard title="Sistema" className="painel__mac">
      {panel.local && !mac ? (
        <p className="painel__empty">Dados do Mac indisponíveis.</p>
      ) : (
        <ul className="hud-gauges">
          {items.map((g) => (
            <li key={g.short}>
              <Ring value={g.value ?? 0} size={74} stroke={6} color={g.color} label={`${g.label}: ${g.text}`}>
                <text x="37" y="42" textAnchor="middle" className="hud-ring__small">
                  {g.text}
                </text>
              </Ring>
              <span className="hud-label hud-label--small">{g.short}</span>
            </li>
          ))}
        </ul>
      )}
    </HudCard>
  );
}

export function Month({ panel }: { panel: PanelState }) {
  return (
    <CoreCard title="Mês" panel={panel} className="painel__month">
      {(d) => {
        const [first, ...others] = d.faturas;
        const max = Math.max(0, ...d.mes.grupos.map((g) => g.total_centavos));
        const top = d.mes.grupos.slice(0, 4);
        const rest = d.mes.grupos.slice(4);
        return (
          <>
            {first ? (
              <div className="hud-row">
                <Ring
                  value={first.fracao_ciclo ?? 0}
                  size={112}
                  stroke={9}
                  color="var(--accent-2)"
                  label={`Fatura ${first.cartao}: ${first.total}`}
                >
                  <text x="56" y="56" textAnchor="middle" className="hud-ring__num hud-ring__num--mid">
                    {first.dias_para_fechar ?? "–"}
                  </text>
                  <text x="56" y="74" textAnchor="middle" className="hud-ring__cap">
                    {first.dias_para_fechar === 1 ? "DIA P/ FECHAR" : "DIAS P/ FECHAR"}
                  </text>
                </Ring>
                <div className="hud-stack">
                  <span className="hud-label">Fatura · {first.cartao}</span>
                  <span className="painel__money">{first.total}</span>
                  <span className="painel__muted">
                    fecha {first.fechamento.slice(0, 5)} · vence {first.vencimento.slice(0, 5)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="painel__empty">Nenhum cartão de crédito.</p>
            )}
            {others.length > 0 && (
              <ul className="painel__list painel__cards">
                {others.map((f) => (
                  <li key={f.cartao}>
                    <span>
                      {f.cartao}
                      <small> fecha {f.fechamento.slice(0, 5)}</small>
                    </span>
                    <span className="painel__value">{f.total}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="painel__total">
              Mês <strong>{d.mes.total}</strong>
            </p>
            {d.mes.grupos.length === 0 ? (
              <p className="painel__empty">Nenhum gasto ainda.</p>
            ) : (
              <ul className="painel__bars">
                {top.map((g) => (
                  <li key={g.grupo}>
                    <span>{g.grupo}</span>
                    <span className="painel__value">{g.total}</span>
                    <span className="painel__bar" style={{ inlineSize: `${barShare(g.total_centavos, max)}%` }} />
                  </li>
                ))}
                {rest.length > 0 && (
                  <li className="painel__muted">
                    <span>outras {rest.length}</span>
                  </li>
                )}
              </ul>
            )}
          </>
        );
      }}
    </CoreCard>
  );
}

export function Conversation({
  panel,
  turn,
  onConfirm,
}: {
  panel: PanelState;
  turn?: Turn;
  onConfirm: (turnId: string, confirmId: string, accepted: boolean) => void;
}) {
  const [tab, setTab] = useState<"conversa" | "registro">("conversa");
  return (
    <section className="hud-card painel__talk" aria-label="Conversa e registro">
      <div className="painel__tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "conversa"} onClick={() => setTab("conversa")}>
          Conversa
        </button>
        <button type="button" role="tab" aria-selected={tab === "registro"} onClick={() => setTab("registro")}>
          Registro
        </button>
      </div>
      {tab === "conversa" ? (
        <div className="painel__turn" aria-live="polite">
          {turn ? <TurnView turn={turn} onConfirm={onConfirm} /> : <p className="painel__hint">Pergunte, ou diga "Jarvis".</p>}
        </div>
      ) : (
        <Log panel={panel} />
      )}
    </section>
  );
}

export function Log({ panel }: { panel: PanelState }) {
  const d = panel.data;
  if (!d) return <p className="painel__empty">{panel.error || "carregando…"}</p>;
  return (
    <div className={`painel__log${panel.error ? " painel__stale" : ""}`}>
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
      {d.perguntas.length > 0 && (
        <ul className="painel__list painel__questions" aria-label="Perguntas desta sessão">
          {d.perguntas.map((q, i) => (
            <li key={i}>
              <span className="painel__when">›</span>
              <span>{q}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Agenda({ panel, now = new Date() }: { panel: PanelState; now?: Date }) {
  return (
    <CoreCard title="Agenda" panel={panel} className="painel__agenda">
      {(d) => {
        const next = nextEvent(d.agenda.hoje, now);
        return (
          <>
            {d.agenda.hoje.length === 0 ? (
              <p className="painel__empty">Dia livre.</p>
            ) : (
              <ol className="hud-timeline">
                {d.agenda.hoje.map((e) => {
                  const state = e === next ? "next" : isPast(e, now) ? "past" : "later";
                  return (
                    <li key={e.id + e.hora} className={`hud-timeline__item hud-timeline__item--${state}`}>
                      <span className="painel__when">{e.hora}</span>
                      <span>
                        {e.titulo}
                        {e.local && <small> · {e.local}</small>}
                      </span>
                    </li>
                  );
                })}
              </ol>
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
        );
      }}
    </CoreCard>
  );
}

export function Projects({ panel, onOpen }: { panel: PanelState; onOpen: (caminho: string) => void }) {
  const items = panel.local?.projetos ?? [];
  return (
    <HudCard title="Projetos" className="painel__projects">
      {items.length === 0 ? (
        <p className="painel__empty">{panel.local ? "Nenhuma pasta de projeto." : "carregando…"}</p>
      ) : (
        <ul className="hud-launcher">
          {items.map((p) => (
            <li key={p.caminho}>
              <button type="button" className="hud-launcher__item" onClick={() => onOpen(p.caminho)} title={`Abrir um terminal em ${p.caminho}`}>
                <span className="hud-launcher__dot" aria-hidden="true" />
                <span className="hud-launcher__line" aria-hidden="true" />
                {p.nome}
              </button>
            </li>
          ))}
        </ul>
      )}
    </HudCard>
  );
}

export function Weather({ panel }: { panel: PanelState }) {
  const c = panel.local?.clima;
  return (
    <HudCard title={`Clima${c ? ` · ${c.cidade}` : ""}`} note="open-meteo" className="painel__weather">
      {!c ? (
        <p className="painel__empty">{panel.local ? "Clima indisponível." : "carregando…"}</p>
      ) : (
        <div className="hud-row">
          <Gauge value={c.agora} min={0} max={40} size={150} label={`${Math.round(c.agora)} graus agora`}>
            <text x="77" y="90" textAnchor="middle" className="hud-ring__num hud-ring__num--big">
              {Math.round(c.agora)}°
            </text>
          </Gauge>
          <div className="hud-stack">
            <span className="painel__muted">
              máx {Math.round(c.max)}° · mín {Math.round(c.min)}°
            </span>
            <span className="painel__muted">chuva {c.chuva}%</span>
          </div>
        </div>
      )}
    </HudCard>
  );
}

function MusicStrip({ panel }: { panel: PanelState }) {
  const m = panel.local?.musica;
  if (!m) return null;
  return (
    <p className="painel__music">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <path d="M9 18V5l12-2v13" />
        <circle cx="6" cy="18" r="3" />
        <circle cx="18" cy="16" r="3" />
      </svg>
      <span className="painel__music-track">{m.faixa}</span>
      <span className="painel__muted">· {m.artista}</span>
      {!m.tocando && <span className="painel__muted">(pausado)</span>}
    </p>
  );
}

/** Limites do Claude Code (janela de 5 h e semana), lidos da barra de status. */
export function ClaudeCard({ panel, now = new Date() }: { panel: PanelState; now?: Date }) {
  const c = panel.local?.claude;
  const windows = [
    { key: "5 horas", w: c?.cinco_horas },
    { key: "Semana", w: c?.semana },
  ];
  const color = (pct: number) => (pct >= 80 ? "var(--danger)" : pct >= 60 ? "oklch(0.85 0.14 85)" : "var(--accent)");
  return (
    <HudCard
      title="Claude Code"
      note={c?.atualizado ? `lido ${hhmm(c.atualizado * 1000)}` : undefined}
      className="painel__claude"
    >
      {!c ? (
        <p className="painel__empty">{panel.local ? "Sem dados: abra uma sessão do Claude Code." : "carregando…"}</p>
      ) : (
        <ul className="hud-gauges hud-gauges--two">
          {windows.map(({ key, w }) => (
            <li key={key}>
              <Ring
                value={w ? w.pct / 100 : 0}
                size={84}
                stroke={7}
                color={w ? color(w.pct) : "var(--track)"}
                label={`Limite de ${key.toLowerCase()}: ${w ? `${Math.round(w.pct)}% usado` : "sem dado"}`}
              >
                <text x="42" y="47" textAnchor="middle" className="hud-ring__small">
                  {w ? `${Math.round(w.pct)}%` : "—"}
                </text>
              </Ring>
              <span className="hud-label hud-label--small">{key.toUpperCase()}</span>
              <span className="painel__muted painel__reset">{w ? resetsIn(w.resets_at, now.getTime()) : "zerou"}</span>
            </li>
          ))}
        </ul>
      )}
    </HudCard>
  );
}
