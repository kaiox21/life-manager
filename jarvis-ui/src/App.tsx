import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import { Orb } from "./components/Orb";
import { TurnView } from "./components/TurnView";
import { useJarvis } from "./lib/useJarvis";

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
  const { turns, link, problem, thinking, ask, answerConfirm, reconnect } = useJarvis();
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const feed = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unlisten = listen("jarvis://shown", () => {
      input.current?.focus();
      if (link === "offline") void reconnect();
    });
    return () => {
      void unlisten.then((f) => f());
    };
  }, [link, reconnect]);

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

  const orb = link === "offline" ? "offline" : thinking ? "thinking" : "idle";
  const time = useClock();

  return (
    <main className="hud">
      <header className="hud__bar">
        <span className="hud__brand">
          J.A.R.V.I.S <small>assistente pessoal</small>
        </span>
        <span className="hud__status">
          <time>{time}</time>
          <span className={`led led--${link}`} aria-hidden="true" />
          {link === "online" ? "online" : link === "connecting" ? "conectando" : "offline"}
        </span>
      </header>
      <form
        className="prompt"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
          setDraft("");
        }}
      >
        <Orb state={orb} size={60} />
        <label className="visually-hidden" htmlFor="ask">
          Pergunte ao Jarvis
        </label>
        <input
          id="ask"
          ref={input}
          className="prompt__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={link === "offline" ? "Jarvis desconectado" : "Pergunte ou peça algo…"}
          autoComplete="off"
          spellCheck={false}
          autoFocus
        />
        <kbd className="prompt__hint">esc</kbd>
      </form>
      {link === "offline" && problem && (
        <p className="banner" role="status">
          {problem}{" "}
          <button type="button" className="btn btn--ghost" onClick={() => void reconnect()}>
            Tentar de novo
          </button>
        </p>
      )}
      <div className="feed" ref={feed}>
        {turns.map((t) => (
          <TurnView key={t.id} turn={t} onConfirm={answerConfirm} />
        ))}
      </div>
    </main>
  );
}
