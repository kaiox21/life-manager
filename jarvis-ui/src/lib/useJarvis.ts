import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { MicCapture, chime } from "./audio";
import { applyEvent, clearConfirm, startTurn } from "./conversation";
import { EMPTY_PANEL, applyPanel, panelFailed, panelLoading, type PanelState } from "./panel";
import type { ServerEvent, Turn } from "./types";

type Link = "connecting" | "online" | "offline";

interface Session {
  port: number;
  token: string;
}

const LEVELS = 40;

/** Conexão com o cérebro local (WebSocket em 127.0.0.1, token do arquivo de sessão). */
export function useJarvis() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [link, setLink] = useState<Link>("connecting");
  const [problem, setProblem] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [levels, setLevels] = useState<number[]>([]);
  const ws = useRef<WebSocket | null>(null);
  const mic = useRef<MicCapture | null>(null);
  const voice = useRef<{ id: string; started: boolean } | null>(null);
  const onNoSpeech = useRef<() => void>(() => {});
  const onWrite = useRef<() => void>(() => {});
  const [panel, setPanel] = useState<PanelState>(EMPTY_PANEL);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(msg));
  }, []);

  const connect = useCallback(async () => {
    setLink("connecting");
    let session: Session;
    try {
      session = await invoke<Session>("jarvis_session");
    } catch (err) {
      setLink("offline");
      setProblem(String(err));
      return;
    }
    const socket = new WebSocket(`ws://127.0.0.1:${session.port}/?token=${encodeURIComponent(session.token)}`);
    socket.binaryType = "arraybuffer";
    socket.onopen = () => {
      setLink("online");
      setProblem("");
    };
    socket.onclose = () => {
      setLink("offline");
      setProblem("Sem conexão com o cérebro do Jarvis.");
    };
    socket.onmessage = (msg) => {
      const ev = JSON.parse(msg.data as string) as ServerEvent;
      switch (ev.type) {
        case "status":
          setStatus(ev.text);
          return;
        case "speaking":
          setSpeaking(ev.data.on);
          return;
        case "no_speech":
          setStatus("");
          setTurns((prev) => applyEvent(prev, ev));
          onNoSpeech.current();
          return;
        case "panel":
          setPanel((prev) => applyPanel(prev, ev.data, Date.now()));
          return;
        case "done":
          setStatus("");
          if (ev.data?.wrote) onWrite.current();
          break;
        case "heard":
        case "error":
          setStatus("");
          break;
      }
      setTurns((prev) => applyEvent(prev, ev));
    };
    ws.current = socket;
  }, []);

  useEffect(() => {
    void connect();
    return () => ws.current?.close();
  }, [connect]);

  const ask = useCallback(
    (text: string) => {
      const question = text.trim();
      if (!question) return;
      if (ws.current?.readyState !== WebSocket.OPEN) {
        void connect();
        return;
      }
      const id = crypto.randomUUID();
      setTurns((prev) => startTurn(prev, id, question, "texto"));
      send({ type: "ask", id, text: question, mode: "texto" });
    },
    [connect, send],
  );

  /** ⌘⇧Espaço apertado: interrompe o que estiver falando e começa a capturar. */
  const startVoice = useCallback(async () => {
    if (mic.current) return;
    if (ws.current?.readyState !== WebSocket.OPEN) {
      void connect();
      return;
    }
    send({ type: "interrupt" });
    chime("start");
    const id = crypto.randomUUID();
    const state = { id, started: false };
    voice.current = state;
    setListening(true);
    setLevels([]);
    setTurns((prev) => startTurn(prev, id, "", "voz"));
    const capture = new MicCapture(
      (pcm) => {
        if (state.started && ws.current?.readyState === WebSocket.OPEN) ws.current.send(pcm);
      },
      (rms) => setLevels((prev) => [...prev.slice(-(LEVELS - 1)), rms]),
    );
    mic.current = capture;
    try {
      await capture.start();
    } catch (err) {
      mic.current = null;
      setListening(false);
      setTurns((prev) => prev.filter((t) => t.id !== id));
      setProblem(`Sem acesso ao microfone: ${String(err)}`);
      return;
    }
    if (voice.current !== state) {
      capture.stop(); // soltou antes de o microfone abrir (ex.: caixa de permissão)
      return;
    }
    send({ type: "voice_start", id, sampleRate: capture.sampleRate });
    state.started = true;
  }, [connect, send]);

  /** ⌘⇧Espaço solto: fecha a captura; o cérebro decide se houve fala. */
  const endVoice = useCallback(() => {
    const state = voice.current;
    voice.current = null;
    mic.current?.stop();
    mic.current = null;
    setListening(false);
    if (!state) return;
    chime("end");
    if (!state.started) {
      setTurns((prev) => prev.filter((t) => t.id !== state.id));
      onNoSpeech.current();
      return;
    }
    setStatus("transcrevendo…");
    send({ type: "voice_end", id: state.id });
  }, [send]);

  const answerConfirm = useCallback(
    (turnId: string, confirmId: string, accepted: boolean) => {
      send({ type: "confirm", id: turnId, confirm_id: confirmId, accepted });
      setTurns((prev) => clearConfirm(prev, confirmId));
    },
    [send],
  );

  /** Dados do painel, direto do núcleo (o cérebro não chama o modelo). */
  const requestPanel = useCallback(() => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setPanel((prev) => panelFailed(prev, "cérebro indisponível"));
      void connect();
      return;
    }
    setPanel(panelLoading);
    send({ type: "panel", id: crypto.randomUUID() });
  }, [connect, send]);

  const thinking = turns.some((t) => t.status === "thinking");
  return {
    turns, link, problem, status, speaking, listening, levels, thinking,
    panel, requestPanel,
    ask, startVoice, endVoice, answerConfirm, reconnect: connect,
    setOnNoSpeech: (fn: () => void) => { onNoSpeech.current = fn; },
    setOnWrite: (fn: () => void) => { onWrite.current = fn; },
  };
}
