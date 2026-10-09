import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import { Orb, type OrbState } from "./components/Orb";
import { TurnView } from "./components/TurnView";
import { Waveform } from "./components/Waveform";
import { chime } from "./lib/audio";
import { alertActive, isLoud } from "./lib/terminals";
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
  // O HUD está na tela por causa da voz (sem foco)? Só então ele some sozinho depois.
  const [voiceShown, setVoiceShown] = useState(false);
  const time = useClock();
  // HUD aberto por causa de um aviso de terminal (some sozinho quando o aviso acaba)
  const [alertOpened, setAlertOpened] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    j.setOnAlert((a) => {
      if (!isLoud(a)) return;
      void invoke<string>("show_alert").then((how) => {
        if (how === "painel") return; // o painel aberto mostra o aviso
        chime("start");
        if (how === "mostrado") setAlertOpened(true);
      });
    });
  }, [j]);

  const showAlert = alertActive(j.alert, j.terminals, now);
  useEffect(() => {
    if (!j.alert) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [j.alert]);
  useEffect(() => {
    if (showAlert || !alertOpened) return;
    const t = setTimeout(() => {
      setAlertOpened(false);
      void invoke("hide_hud");
    }, 3000);
    return () => clearTimeout(t);
  }, [showAlert, alertOpened]);

  // Segurou o atalho de voz sem falar: o HUD volta a como estava (fechado, se estava fechado).
  useEffect(() => {
    j.setOnNoSpeech(() => {
      if (!visibleBefore.current) void invoke("hide_hud");
    });
  }, [j]);

  useEffect(() => {
    const unlisten = Promise.all([
      listen("jarvis://esc", () => j.stop()), // Esc com o HUD sem foco: cala e fecha
      listen("jarvis://shown", () => {
        setVoiceShown(false); // aberto com ⌥Espaço para digitar: não fecha sozinho
        setAlertOpened(false);
        input.current?.focus();
        if (link === "offline") void j.reconnect();
      }),
      listen<{ state: "down" | "up"; target: "hud" | "painel"; visible: boolean }>("jarvis://ptt", (e) => {
        if (e.payload.target !== "hud") return; // o painel aberto cuida da fala
        if (e.payload.state === "down") {
          visibleBefore.current = e.payload.visible;
          setVoiceShown(true);
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
      if (e.key !== "Escape") return;
      invoke("hide_hud").catch((err) => void invoke("ui_log", { message: `HUD: hide_hud recusado: ${String(err)}` }));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // Em voz, o HUD some sozinho um pouco depois de terminar de falar.
  const last = turns[turns.length - 1];
  const idleVoice =
    voiceShown && !!last && last.mode === "voz" && last.status !== "thinking" && !speaking && !listening && !status;
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
      {showAlert && j.alert && (
        <p className="term-alert" role="alert">
          {j.alert.texto}
        </p>
      )}
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
