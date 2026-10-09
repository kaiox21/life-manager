import { useEffect, useState } from "react";
import { isBusy, tabState } from "../lib/terminals";
import type { TerminalInfo, TerminalOpened, TerminalTab } from "../lib/types";

export const CENTRAL = "central";
const CONFIRM_MS = 4000;

const DOT: Record<string, string> = {
  "pedindo permissão": "ask",
  "esperando você": "wait",
  trabalhando: "work",
  terminou: "ok",
};

/** Barra de abas do painel: "Central" + uma aba por sessão aberta pelo Jarvis + "+". */
export function TerminalTabs({
  tabs,
  terminals,
  active,
  onSelect,
  onOpen,
  onClose,
}: {
  tabs: TerminalTab[];
  terminals: TerminalInfo[];
  active: string;
  onSelect: (sid: string) => void;
  onOpen: (req: { pasta?: string; retomar?: string }) => Promise<TerminalOpened>;
  onClose: (sid: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [pasta, setPasta] = useState("");
  const [msg, setMsg] = useState<{ erro?: string; opcoes?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(null), CONFIRM_MS);
    return () => clearTimeout(t);
  }, [confirming]);

  const open = async (req: { pasta?: string; retomar?: string }) => {
    setBusy(true);
    const r = await onOpen(req);
    setBusy(false);
    if ("status" in r) {
      setAdding(false);
      setPasta("");
      setMsg(null);
      onSelect(r.sid);
    } else {
      setMsg(r.opcoes ? { opcoes: r.opcoes } : { erro: r.erro });
    }
  };

  const close = (tab: TerminalTab) => {
    // trabalhando ou pedindo permissão: o primeiro clique só pergunta
    if (tab.aberta && isBusy(tabState(tab.sid, terminals)) && confirming !== tab.sid) {
      setConfirming(tab.sid);
      return;
    }
    setConfirming(null);
    if (active === tab.sid) onSelect(CENTRAL);
    onClose(tab.sid);
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
        {tabs.map((tab) => {
          const estado = tab.aberta ? tabState(tab.sid, terminals) : undefined;
          return (
            <span key={tab.sid} className={`tabs__item${tab.aberta ? "" : " tabs__item--closed"}`}>
              <button
                type="button"
                role="tab"
                aria-selected={active === tab.sid}
                className="tabs__tab"
                onClick={() => onSelect(tab.sid)}
                title={estado ?? (tab.aberta ? "" : "encerrada")}
              >
                <span className={`tabs__dot tabs__dot--${tab.aberta ? (DOT[estado ?? ""] ?? "ok") : "off"}`} aria-hidden="true" />
                Terminal {tab.numero} · {tab.pasta}
                {!tab.aberta && (
                  <>
                    {" "}
                    <small>(encerrada)</small>
                  </>
                )}
              </button>
              {!tab.aberta && (
                <button type="button" className="tabs__action" disabled={busy} onClick={() => void open({ retomar: tab.sid })}>
                  Retomar
                </button>
              )}
              <button
                type="button"
                className="tabs__close"
                aria-label={confirming === tab.sid ? `Confirmar: fechar Terminal ${tab.numero}` : `Fechar Terminal ${tab.numero}`}
                onClick={() => close(tab)}
              >
                {confirming === tab.sid ? `fechar? (${estado})` : "×"}
              </button>
            </span>
          );
        })}
        <button
          type="button"
          className="tabs__add"
          aria-label="Abrir um Claude Code"
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
            if (pasta.trim()) void open({ pasta: pasta.trim() });
          }}
        >
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
                <button key={o} type="button" className="btn btn--ghost" onClick={() => void open({ pasta: o })}>
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
