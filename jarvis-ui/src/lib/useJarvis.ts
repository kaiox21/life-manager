import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { applyEvent, clearConfirm, startTurn } from "./conversation";
import type { ServerEvent, Turn } from "./types";

type Link = "connecting" | "online" | "offline";

interface Session {
  port: number;
  token: string;
}

/** Conexão com o cérebro local (WebSocket em 127.0.0.1, token do arquivo de sessão). */
export function useJarvis() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [link, setLink] = useState<Link>("connecting");
  const [problem, setProblem] = useState<string>("");
  const ws = useRef<WebSocket | null>(null);

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
      setTurns((prev) => startTurn(prev, id, question));
      ws.current.send(JSON.stringify({ type: "ask", id, text: question }));
    },
    [connect],
  );

  const answerConfirm = useCallback((turnId: string, confirmId: string, accepted: boolean) => {
    ws.current?.send(JSON.stringify({ type: "confirm", id: turnId, confirm_id: confirmId, accepted }));
    setTurns((prev) => clearConfirm(prev, confirmId));
  }, []);

  const thinking = turns.some((t) => t.status === "thinking");
  return { turns, link, problem, thinking, ask, answerConfirm, reconnect: connect };
}
