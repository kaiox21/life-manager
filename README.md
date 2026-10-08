# Gerenciador de Vida

Assistente pessoal de agenda e gastos: bot de WhatsApp (núcleo num VPS) e, depois, um Jarvis por voz no Mac, ambos usando as mesmas ferramentas.

## Onde está cada coisa

| Arquivo | Para quê |
| --- | --- |
| `SPEC.md` | Visão, decisões, riscos e questões em aberto |
| `openspec/specs/` | Requisitos e cenários de cada capacidade (fonte de verdade do comportamento) |
| `openspec/changes/` | Mudanças em andamento (`openspec list`) |
| `CLAUDE.md` | Regras que o Claude Code segue em toda sessão |
| `tests/eval/casos.yaml` | A prova: 56 mensagens com a chamada de ferramenta esperada |
| `docs/fases/` | Histórico das fases 1 a 7 (antes do OpenSpec) |
| `docs/mcp.md` | Como conectar clientes MCP |
| `deploy/` | Deploy, backup e restauração |
| `.env.example` | Variáveis de ambiente; copie para `.env` |
