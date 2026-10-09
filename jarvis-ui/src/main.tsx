import { getCurrentWindow } from "@tauri-apps/api/window";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Panel } from "./Panel";
import "./theme.css";
import "./panel.css";

// Duas janelas, um bundle: o rótulo da janela escolhe a tela.
const isPanel = getCurrentWindow().label === "painel";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>{isPanel ? <Panel /> : <App />}</React.StrictMode>,
);
