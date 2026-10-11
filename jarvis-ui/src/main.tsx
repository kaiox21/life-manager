import { getCurrentWindow } from "@tauri-apps/api/window";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Panel } from "./Panel";
// fontes do painel HUD empacotadas no app (OFL; nenhuma requisição ao Google Fonts)
import "@fontsource/orbitron/500.css";
import "@fontsource/orbitron/700.css";
import "@fontsource/rajdhani/500.css";
import "@fontsource/rajdhani/600.css";
import "@fontsource/rajdhani/700.css";
import "@fontsource/share-tech-mono/400.css";
import "./theme.css";
import "./panel.css";

// Duas janelas, um bundle: o rótulo da janela escolhe a tela.
const isPanel = getCurrentWindow().label === "painel";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>{isPanel ? <Panel /> : <App />}</React.StrictMode>,
);
