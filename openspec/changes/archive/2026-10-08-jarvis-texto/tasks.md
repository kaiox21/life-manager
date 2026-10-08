## 1. Base

- [x] 1.1 Instalar Rust (`rustup`) e criar `jarvis-ui/` com Tauri 2 + React/Vite/TS
- [x] 1.2 Criar o pacote `jarvis/` (Python) com o servidor WebSocket local e o protocolo de eventos (`step`, `token`, `card`, `done`, `error`)
- [x] 1.3 Cliente MCP do núcleo (`MCP_TOKEN`), com teste de integração contra o Docker

## 2. Agente e ferramentas

- [x] 2.1 Ferramentas locais com comandos fixos, validação e lista permitida; testes com `subprocess` falso
- [x] 2.2 Agente: `contexto` no início, ferramentas MCP + locais, validação, escalada, streaming de passos; testes com LLM falso
- [x] 2.3 Conversão de resultados em cartões tipados; testes com resultados reais das ferramentas

## 3. Interface

- [x] 3.1 Tray, atalho global ⌥Espaço, janela HUD (transparente, sem borda, sempre no topo, vibrancy), Esc fecha
- [x] 3.2 Estados (oculto, digitando, pensando, respondendo), orbe animado, lista de passos
- [x] 3.3 Cartões (agenda, gastos, fatura, gráfico, texto) e tema claro/escuro; testes de componente (Vitest)
- [x] 3.4 Confirmações na interface (pendências do núcleo e leitura da área de transferência)

## 4. Fechamento

- [x] 4.1 LaunchAgent para abrir com o login
- [x] 4.2 `uv run pytest`, `ruff`, testes da UI
- [x] 4.3 Aceite real: ⌥Espaço → "abre o Safari e me diz meus compromissos de amanhã"
- [x] 4.4 Atualizar specs (archive) e relatório
