## Context

O núcleo roda em Docker no Mac (o deploy no VPS está pausado) e expõe `/mcp` com token. O Jarvis é a segunda porta do `SPEC.md`: precisa de design caprichado e precisa nascer pronto para voz, onde a latência manda.

## Goals / Non-Goals

**Goals:**
- Chamar com ⌥Espaço de qualquer app e ver resposta com passos e cartões.
- Reaproveitar o núcleo pelo MCP, sem regra de negócio no Jarvis.
- Um protocolo de eventos que a voz possa usar sem mudar a interface.

**Non-Goals:**
- Voz, palavra de ativação, roteador de modelos, sessões do Claude Code.

## Decisions

1. **Tauri 2 + React/Vite/TS para a interface.**
   - Ícone na barra (tray), atalho global (plugin `global-shortcut`), janela sem borda, transparente, sempre no topo, com vibrancy do macOS.
   - Alternativa considerada: `pywebview` + `rumps`, mais simples, mas com vidro e janela flutuante piores. O design é o requisito central.
2. **Cérebro em Python, separado da interface** (`python -m jarvis`).
   - Reaproveita `app/agent/llm.py` (gateway, custo) e o padrão de validação.
   - WebSocket em `127.0.0.1`, com token gerado a cada execução e passado à interface.
   - A interface não tem chave de API nem regra.
3. **Cliente MCP do núcleo** (`http://localhost:8000/mcp/`, `MCP_TOKEN`).
   - O agente chama `contexto` no início da conversa e oferece ao modelo as ferramentas do núcleo mais as locais.
   - Depois do VPS, troca para o host do Tailscale.
4. **Cartões tipados no Python** (`agenda`, `gastos`, `fatura`, `grafico`, `texto`): a interface só desenha. O texto do modelo é curto; números vêm das ferramentas.
5. **Ferramentas locais com comandos fixos** (`subprocess` com lista de argumentos, sem shell):
   - `rodar_atalho` só com lista permitida;
   - ler a área de transferência pede confirmação na interface.
6. **Estilo visual "holográfico azul"** (referência do Kaio em `jarvis-ui/referencias-visuais/`, fora do git, 08/10/2026), que substitui o "Jarvis sóbrio" inicial:
   - fundo azul-marinho profundo sobre o vidro nativo, grade sutil e cantoneiras de HUD;
   - linhas e textos em ciano/azul elétrico com brilho;
   - orbe de partículas com anéis concêntricos marcados e girando;
   - rótulos em fonte monoespaçada maiúscula, cabeçalho com relógio e estado, passos como log com horário, números grandes com brilho nos cartões.
   - **Sempre escuro**: o visual não tem versão clara.
   - O painel de tela cheia ("central de comando") é um change futuro, `jarvis-painel`.
   - Movimento reduzido respeitado (anéis e partículas param).
7. **Registro**: cada conversa do Jarvis grava no próprio núcleo, via MCP (`agent_runs`, `channel='desktop'`), e num log local do Jarvis para as ferramentas locais.

Fatos conferidos em 08/10/2026:
- SDK `mcp` 2.3.0: cliente `streamable_http_client` com `httpx2.AsyncClient` (headers de autorização).
- OpenJarvis (Stanford, Apache 2.0) é um framework de agentes com modelos locais.
- Rust não está instalado no Mac (precisa de `rustup`).

## Risks / Trade-offs

- **[Latência do gpt-5-nano, 20–40 s]** → Aceitável em texto com os passos visíveis. Bloqueia a voz: decidir modelo rápido antes da próxima mudança.
- **[Permissões do macOS]** → Explicar na primeira execução; atalho configurável.
- **[Duas linguagens (Rust na casca, TS na interface)]** → A casca Rust fica mínima (tray, atalho, janela); a lógica fica em TS e Python.

## Open Questions

Respondidas em 08/10/2026:
- Rust: **instalado** (rustup 1.99, perfil mínimo; `~/.cargo/env` no `~/.zprofile`).
- Atalho: **⌥Espaço**, configurável. "Só Espaço" foi descartado porque sequestraria a barra de espaço em todos os apps.
- Atalhos da Apple permitidos: **nenhum** no início (lista vazia em configuração).
- Música: **Spotify** (AppleScript do app Spotify).
