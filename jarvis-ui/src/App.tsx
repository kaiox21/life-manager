import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import { Orb, type OrbState } from "./components/Orb";
import { TurnView } from "./components/TurnView";
import { Waveform } from "./components/Waveform";
import { useJarvis } from "./lib/useJarvis";

const AUTO_HIDE_MS = 8000;

function useClock() {
  const fmt = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const [time, setTime] = useState(fmt);
  useEffect(() => {
    const t = setInterval(() => setTime(fmt()), 1000);
    return () => clearInterval(t);
  }, []);
  return time;
}

export default function App() {
  const j = useJarvis();
  const { turns, link, problem, status, speaking, listening, levels, thinking } = j;
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const feed = useRef<HTMLDivElement>(null);
  const visibleBefore = useRef(false);
  const time = useClock();

  // Segurou o atalho de voz sem falar: o HUD volta a como estava (fechado, se estava fechado).
  useEffect(() => {
    j.setOnNoSpeech(() => {
      if (!visibleBefore.current) void invoke("hide_hud");
    });
  }, [j]);

  useEffect(() => {
    const unlisten = Promise.all([
      listen("jarvis://shown", () => {
        input.current?.focus();
        if (link === "offline") void j.reconnect();
      }),
      listen<{ state: "down" | "up"; visible: boolean }>("jarvis://ptt", (e) => {
        if (e.payload.state === "down") {
          visibleBefore.current = e.payload.visible;
          void j.startVoice();
        } else {
          j.endVoice();
        }
      }),
    ]);
    return () => {
      void unlisten.then((fns) => fns.forEach((f) => f()));
    };
  }, [j, link]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") void invoke("hide_hud");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // Em voz, o HUD some sozinho um pouco depois de terminar de falar.
  const last = turns[turns.length - 1];
  const idleVoice = !!last && last.mode === "voz" && last.status !== "thinking" && !speaking && !listening && !status;
  useEffect(() => {
    if (!idleVoice) return;
    const t = setTimeout(() => void invoke("hide_hud"), AUTO_HIDE_MS);
    return () => clearTimeout(t);
  }, [idleVoice, last?.id]);

  const orb: OrbState =
    link === "offline" ? "offline" : listening ? "listening" : speaking ? "speaking" : thinking || status ? "thinking" : "idle";
  const label =
    link === "offline" ? "offline" : link === "connecting" ? "conectando" : listening ? "ouvindo" : status ? status.replace(/…$/, "") : speaking ? "falando" : thinking ? "pensando" : "online";

  return (
    <main className="hud">
      <header className="hud__bar">
        <span className="hud__brand">
          J.A.R.V.I.S <small>assistente pessoal</small>
        </span>
        <span className="hud__status">
          <time>{time}</time>
          <span className={`led led--${link}`} aria-hidden="true" />
          {label}
        </span>
      </header>
      <form
        className="prompt"
        onSubmit={(e) => {
          e.preventDefault();
          j.ask(draft);
          setDraft("");
        }}
      >
        <Orb state={orb} size={60} />
        {listening ? (
          <Waveform levels={levels} />
        ) : (
          <>
            <label className="visually-hidden" htmlFor="ask">
              Pergunte ao Jarvis
            </label>
            <input
              id="ask"
              ref={input}
              className="prompt__input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={link === "offline" ? "Jarvis desconectado" : "Pergunte, ou segure ⌘⇧Espaço e fale…"}
              autoComplete="off"
              spellCheck={false}
              autoFocus
            />
          </>
        )}
        <kbd className="prompt__hint">esc</kbd>
      </form>
      {link === "offline" && problem && (
        <p className="banner" role="status">
          {problem}{" "}
          <button type="button" className="btn btn--ghost" onClick={() => void j.reconnect()}>
            Tentar de novo
          </button>
        </p>
      )}
      <div className="feed" ref={feed}>
        {turns.map((t) => (
          <TurnView key={t.id} turn={t} onConfirm={j.answerConfirm} />
        ))}
      </div>
    </main>
  );
}
