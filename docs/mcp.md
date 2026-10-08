# MCP: usar agenda e gastos no Claude (fase 7)

O núcleo expõe as mesmas ferramentas do bot do WhatsApp em `http://<host>:8000/mcp/`, protegidas por token (`MCP_TOKEN` no `.env`).

- **Ferramentas**: `contexto` (chame primeiro), `lancar_gasto`, `desfazer_ultimo`, `gerenciar_meio_pagamento`, `buscar_gastos`, `total_fatura`, `resumo_gastos`, `criar_evento`, `buscar_eventos`, `atualizar_evento`, `remover_evento`, `gerenciar_pessoa`, `confirmar_pendente`.
- **Confirmações valem como no WhatsApp**: remoção, valor acima de R$ 500 etc. devolvem `aguardando_confirmacao`.
- **Registro**: cada chamada vira uma linha em `agent_runs` com `channel='desktop'`.

Hoje o núcleo roda no Mac, então o host é `localhost`. Depois da fase 6, troca para o nome do VPS no Tailscale (ex.: `http://jarvis:8000/mcp/`), e esse nome entra em `MCP_ALLOWED_HOSTS`.

## Token

```bash
grep ^MCP_TOKEN ~/Downloads/life-manager/.env | cut -d= -f2
```

Não versione nem cole o token em lugar público: ele dá acesso total a agenda e gastos.

## Claude Code

```bash
claude mcp add --scope user --transport http life-manager http://localhost:8000/mcp/ \
  --header "Authorization: Bearer $(grep ^MCP_TOKEN ~/Downloads/life-manager/.env | cut -d= -f2)"
claude mcp list
```

## Claude Desktop

O Claude Desktop fala com servidores remotos por uma ponte local (`mcp-remote`, via `npx`). Edite `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "life-manager": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp/", "--header", "Authorization:${LM_AUTH}"],
      "env": { "LM_AUTH": "Bearer <MCP_TOKEN>" }
    }
  }
}
```

O `${LM_AUTH}` sem espaço no argumento é proposital: o `mcp-remote` substitui a variável e evita problemas com espaços no Claude Desktop.

Reinicie o Claude Desktop. As ferramentas aparecem no ícone de ferramentas da conversa.

## Teste rápido

No Claude: "lança 25 reais de café no débito do inter". No WhatsApp: "quanto gastei hoje?". O café deve aparecer.
