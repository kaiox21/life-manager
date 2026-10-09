import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef } from "react";
import type { TermSink } from "../lib/useJarvis";

// Controle de fluxo (guia do xterm.js): acima de 500 KB ainda não desenhados, pede ao cérebro
// para parar de ler a sessão; abaixo de 100 KB, retoma.
export const HIGH_WATER = 500_000;
export const LOW_WATER = 100_000;

type Send = (msg: Record<string, unknown>) => void;

/** Um terminal real: a tela do `claude` daquela sessão, com as teclas indo direto para ela. */
export function TerminalView({
  sid,
  label,
  attach,
  send,
}: {
  sid: string;
  label: string;
  attach: (sid: string, sink: TermSink) => () => void;
  send: Send;
}) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const term = new Terminal({
      scrollback: 5000,
      fontFamily: '"SF Mono", ui-monospace, Menlo, monospace',
      fontSize: 13,
      cursorBlink: true,
      theme: { background: "#0b1020", foreground: "#e6edf7", cursor: "#9be7ff", selectionBackground: "#2a4a7a" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);

    // ⌘C com seleção copia (sem isso o atalho não chega à área de transferência)
    term.attachCustomKeyEventHandler((e) => {
      if (e.type === "keydown" && e.metaKey && e.key === "c" && term.hasSelection()) {
        void navigator.clipboard?.writeText(term.getSelection());
        return false;
      }
      return true;
    });

    let pending = 0;
    let paused = false;
    const write = (data: Uint8Array) => {
      pending += data.length;
      if (!paused && pending > HIGH_WATER) {
        paused = true;
        send({ type: "term_pause", sid, on: true });
      }
      term.write(data, () => {
        pending -= data.length;
        if (paused && pending < LOW_WATER) {
          paused = false;
          send({ type: "term_pause", sid, on: false });
        }
      });
    };
    const detach = attach(sid, (kind, data) => {
      if (kind === "replay") term.reset();
      write(data);
    });
    const input = term.onData((data) => send({ type: "term_input", sid, data }));
    const resized = term.onResize(({ cols, rows }) => send({ type: "term_resize", sid, cols, rows }));
    const doFit = () => {
      try {
        fit.fit();
      } catch {
        // janela ainda sem tamanho (painel escondido)
      }
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(doFit);
    observer?.observe(el);
    doFit();
    send({ type: "term_resize", sid, cols: term.cols, rows: term.rows });
    term.focus();

    return () => {
      observer?.disconnect();
      input.dispose();
      resized.dispose();
      if (paused) send({ type: "term_pause", sid, on: false });
      detach();
      term.dispose();
    };
  }, [sid, attach, send]);

  return <div className="term-view" ref={box} role="region" aria-label={label} />;
}
