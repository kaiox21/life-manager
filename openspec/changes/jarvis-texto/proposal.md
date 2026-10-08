## Why

O núcleo (WhatsApp, gastos, agenda, lembretes, MCP) está pronto, mas no Mac o único jeito de usá-lo é pelo celular ou pelo Claude Desktop. O Kaio quer um **Jarvis com design próprio**, rápido de chamar e pensado desde já para voz. A ponte MCP (concluída em 08/10/2026) é a base que permite isso sem duplicar regras.

## What Changes

- App **Jarvis** no Mac.
  - **Casca**: Tauri 2 com ícone na barra de menus, atalho global (⌥Espaço) e um HUD flutuante de vidro, com orbe animado, passos visíveis ("consultando a agenda…") e respostas em **cartões** (agenda, gastos, fatura, gráfico, texto).
  - **Cérebro**: processo Python local, com um agente que usa as ferramentas do núcleo **pelo MCP** e **6 ferramentas locais** do macOS (abrir app, buscar arquivo, rodar Atalho permitido, música, timer, área de transferência).
- Interface e cérebro conversam por WebSocket em `127.0.0.1`, com streaming de eventos (`step`, `token`, `card`, `done`, `error`): o mesmo protocolo que a voz vai usar.
- Nesta mudança só **texto**. Voz (push-to-talk, `mlx-whisper`, resposta falada) é a próxima mudança.
- Decisões do `SPEC.md` tocadas:
  - "Jarvis" passa de `rumps` + painel para **Tauri + React** (design).
  - A questão em aberto "cinco primeiras ações do Jarvis" é fechada com as 6 ferramentas locais do `SPEC.md`.
  - O **OpenJarvis** foi avaliado e não substitui (é um framework de modelos locais, sem interface nem voz prontas).

## Non-goals

- Voz e palavra de ativação (próximas mudanças).
- Roteador de modelos por dificuldade e acompanhamento das sessões do Claude Code (mudanças futuras do Jarvis).
- Modelo rápido: o Jarvis usa o `gpt-5-nano` atual (20–40 s por resposta). A escolha de um modelo rápido é pré-requisito da voz, não desta mudança.
- Qualquer acesso direto ao banco pelo Jarvis, shell livre, apagar arquivos ou mandar mensagens.

## Capabilities

### New Capabilities
- `jarvis-interface`: app de barra de menus, atalho global, HUD com estados, cartões e streaming.
- `jarvis-agente`: agente do Mac que usa o núcleo pelo MCP e as ferramentas locais, com validação e escalada.
- `ferramentas-locais`: ações seguras no macOS com comandos fixos e argumentos validados.

### Modified Capabilities
<!-- nenhuma: o núcleo não muda de comportamento -->

## Impact

- Novas pastas `jarvis/` (Python) e `jarvis-ui/` (Tauri + React/Vite/TS) no mesmo repositório.
- Dependências: Rust (`rustup`) e Tauri CLI no Mac; pacotes Node do `jarvis-ui`; o cliente `mcp` no Python (já instalado).
- Permissões do macOS: Acessibilidade (atalho global) e Automação (Música, Safari).
- O núcleo não muda: o Jarvis é só mais um cliente do `/mcp`.
