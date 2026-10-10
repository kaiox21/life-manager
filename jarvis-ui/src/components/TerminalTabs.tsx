import { useEffect, useState } from "react";
import { closingEnds, tabsOf } from "../lib/terminals";
import type { TerminalInfo, TerminalOpened } from "../lib/types";

export const CENTRAL = "central";
const CONFIRM_MS = 4000;

const DOT: Record<string, string> = {
  "pedindo permissão": "ask",
  "esperando você": "wait",
  trabalhando: "work",
  rodando: "work",
  terminou: "ok",
  livre: "ok",
};

/** Barra de abas do painel: "Central" + uma aba por terminal compartilhado aberto + "+". As abas
 * vêm do cérebro (marca na sessão do tmux): sobrevivem ao reinício do Jarvis. */
export function TerminalTabs({
  terminals,
  active,
  onSelect,
  onOpen,
  onCloseTab,
}: {
  terminals: TerminalInfo[];
  active: string;
  onSelect: (sessao: string) => void;
  onOpen: (req: { pasta: string; claude: boolean }) => Promise<TerminalOpened>;
  onCloseTab: (sessao: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [pasta, setPasta] = useState("");
  const [claude, setClaude] = useState(false);
  const [msg, setMsg] = useState<{ erro?: string; opcoes?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const tabs = tabsOf(terminals);

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(null), CONFIRM_MS);
    return () => clearTimeout(t);
  }, [confirming]);

  const open = async (where: string) => {
    setBusy(true);
    const r = await onOpen({ pasta: where, claude });
    setBusy(false);
    if ("status" in r) {
      setAdding(false);
      setPasta("");
      setMsg(null);
      onSelect(r.sessao);
    } else {
      setMsg(r.opcoes ? { opcoes: r.opcoes } : { erro: r.erro });
    }
  };

  const close = (t: TerminalInfo) => {
    const sessao = t.tmux ?? "";
    // a aba some e o terminal acaba junto, com algo rodando: o primeiro clique só pergunta
    if (closingEnds(t) && t.ocupado && confirming !== sessao) {
      setConfirming(sessao);
      return;
    }
    setConfirming(null);
    if (active === sessao) onSelect(CENTRAL);
    onCloseTab(sessao);
  };

  return (
    <nav className="tabs" aria-label="Abas do painel">
      <div className="tabs__list" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={active === CENTRAL}
          className="tabs__tab"
          onClick={() => onSelect(CENTRAL)}
        >
          Central
        </button>
        {tabs.map((t) => {
          const sessao = t.tmux ?? "";
          return (
            <span key={sessao} className="tabs__item">
              <button
                type="button"
                role="tab"
                aria-selected={active === sessao}
                className="tabs__tab"
                onClick={() => onSelect(sessao)}
                title={`${t.tipo === "claude" ? "Claude Code" : "terminal"} · ${t.estado}${t.janela ? " · também no Terminal.app" : ""}`}
              >
                <span className={`tabs__dot tabs__dot--${DOT[t.estado] ?? "ok"}`} aria-hidden="true" />
                Terminal {t.numero} · {t.pasta}
              </button>
              <button
                type="button"
                className="tabs__close"
                aria-label={confirming === sessao ? `Confirmar: encerrar Terminal ${t.numero}` : `Fechar a aba do Terminal ${t.numero}`}
                onClick={() => close(t)}
              >
                {confirming === sessao ? `encerrar? (${t.estado})` : "×"}
              </button>
            </span>
          );
        })}
        <button
          type="button"
          className="tabs__add"
          aria-label="Abrir um terminal"
          aria-expanded={adding}
          onClick={() => {
            setAdding((v) => !v);
            setMsg(null);
          }}
        >
          +
        </button>
      </div>
      {adding && (
        <form
          className="tabs__new"
          onSubmit={(e) => {
            e.preventDefault();
            if (pasta.trim()) void open(pasta.trim());
          }}
        >
          <fieldset className="tabs__kind">
            <legend className="visually-hidden">O que abrir</legend>
            <label>
              <input type="radio" name="tabs-kind" checked={!claude} onChange={() => setClaude(false)} /> Terminal
            </label>
            <label>
              <input type="radio" name="tabs-kind" checked={claude} onChange={() => setClaude(true)} /> Claude Code
            </label>
          </fieldset>
          <label htmlFor="tabs-pasta">Pasta do projeto</label>
          <input
            id="tabs-pasta"
            value={pasta}
            onChange={(e) => setPasta(e.target.value)}
            placeholder="ex.: life-manager"
            autoComplete="off"
            spellCheck={false}
            autoFocus
          />
          <button type="submit" className="btn" disabled={busy || !pasta.trim()}>
            {busy ? "Abrindo…" : "Abrir"}
          </button>
          {msg?.erro && (
            <p className="tabs__msg" role="alert">
              {msg.erro}
            </p>
          )}
          {msg?.opcoes && (
            <p className="tabs__msg">
              Qual delas?{" "}
              {msg.opcoes.map((o) => (
                <button key={o} type="button" className="btn btn--ghost" onClick={() => void open(o)}>
                  {o}
                </button>
              ))}
            </p>
          )}
        </form>
      )}
    </nav>
  );
}
