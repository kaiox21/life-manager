# jarvis-ui

Interface do Jarvis (Tauri 2 + React/Vite/TS): ícone na barra de menus, atalho ⌥Espaço e HUD holográfico com passos e cartões. Só desenha: o cérebro é o `jarvis/` (Python), que conversa com esta interface por WebSocket em 127.0.0.1.

```bash
npm install
npm run tauri dev                      # desenvolvimento (com: uv run python -m jarvis)
npm test                               # testes de componente (Vitest)
npm run tauri build -- --bundles app   # Jarvis.app; instalar com ../jarvis/install_mac.sh
```

Referências visuais ficam em `referencias-visuais/` (fora do git).
