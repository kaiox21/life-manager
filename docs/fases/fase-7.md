# Fase 7 — Núcleo vira MCP

Status: **concluída em 08/10/2026** (sem a parte do Tailscale, que espera o VPS da fase 6). Plano aprovado em 08/10/2026. Padrões para as dúvidas sem resposta: OpenSpec reavaliado na fase 8; Claude Desktop e Claude Code documentados; Tailscale instalado junto com o VPS.

Contexto: a fase 6 está aberta, à espera da Oracle liberar a VM. O Kaio pediu para adiantar o Jarvis, e a fase 7 é a base dele. Ela pode ser desenvolvida e aceita no Mac agora; a parte do Tailscale e do VPS fecha quando a fase 6 terminar.

Objetivo (do `SPEC.md`): servidor MCP com as ferramentas do núcleo, Tailscale no Mac e no VPS.

Critério de aceite: um gasto lançado pelo **Claude Desktop** conectado ao MCP aparece numa consulta feita pelo **WhatsApp**.

## Fatos conferidos (08/10/2026)

- SDK Python `mcp` **2.3.0**: `FastMCP` virou `MCPServer` (`from mcp.server.mcpserver import MCPServer`). A documentação antiga não vale.
- `MCPServer.streamable_http_app()` devolve um app Starlette (transporte Streamable HTTP), que dá para montar dentro do FastAPI em `/mcp`.
- O `MCPServer` também aceita `token_verifier`. Para usuário único, um token fixo resolve (decisão 3).

## Arquivos

```text
app/
  mcp_server.py        # MCPServer com as ferramentas do núcleo + "contexto"; montado em /mcp
  agent/tools/base.py  # (sem mudança de regra) as mesmas Tool/Pydantic do agente do WhatsApp
  main.py              # monta /mcp com verificação de token; sync do Calendar depois de escrever
  config.py            # MCP_TOKEN
tests/unit/
  test_mcp_server.py   # lista de ferramentas, schema, token, chamada válida/inválida, agent_runs
docs/
  mcp.md               # como conectar Claude Code e Claude Desktop
```

## Decisões

1. **Mesmas ferramentas, mesmo código.** O MCP expõe as funções de `app/agent/tools/`, com os mesmos nomes (`lancar_gasto`, `total_fatura`...) e a mesma validação Pydantic.
   - Nada de regra de negócio duplicada: é o que o `SPEC.md` pede ("o Jarvis não toca o banco diretamente").
   - Confirmações continuam valendo: `remover_evento` só cria pendência, e o cliente precisa chamar `confirmar_pendente`.
2. **Ferramenta extra `contexto`** (somente leitura): data e hora atuais, tabela de datas, meios de pagamento com as faturas abertas, categorias, pessoas e a agenda dos próximos 7 dias.
   - É o mesmo material do prompt do WhatsApp. Sem isso, um cliente externo (Claude Desktop) não sabe que "hoje" é 08/10 nem qual fatura está aberta, e acabaria calculando datas, o que o `SPEC.md` proíbe.
3. **Acesso**:
   - Token fixo (`MCP_TOKEN` no `.env`, header `Authorization: Bearer`) **e** rede restrita.
   - No Mac, por enquanto, só `127.0.0.1`.
   - No VPS (depois da fase 6), só pela interface do **Tailscale**; nunca na internet.
4. **Montado no mesmo processo do FastAPI** (`/mcp`), não num contêiner à parte: o mesmo banco, o mesmo sync do Calendar e os mesmos logs. Menos peças.
5. **Registro**:
   - Cada chamada MCP gera uma linha em `agent_runs`, com `channel='desktop'`, o nome do cliente em `model` e a ferramenta em `tools_called`.
   - Mantém a regra "tudo que mexe no banco fica registrado".
   - `source='texto'` (digitado): valor acima de R$ 500 continua pedindo confirmação.
6. **Clientes**:
   - **Claude Code**: conecta direto por HTTP (`claude mcp add --transport http ...`).
   - **Claude Desktop**: usa a ponte `mcp-remote` (npx) no `claude_desktop_config.json`, porque o conector remoto do Claude.ai passa pela nuvem da Anthropic e não alcança `localhost` nem o Tailscale.
   - Passo a passo em `docs/mcp.md`.
7. **Tailscale**:
   - No Mac, instalar agora (grátis, uso pessoal).
   - No VPS, entra no `bootstrap.sh` quando a VM existir.
   - Até lá, o aceite é feito com o Claude Desktop falando com o núcleo no próprio Mac. É o mesmo banco que o WhatsApp usa hoje, então o critério se cumpre de verdade.

## Testes

- Unitários, com o cliente MCP do próprio SDK em memória, sem rede:
  - lista as 12 ferramentas mais `contexto`, com schemas;
  - chamada sem token → 401;
  - `lancar_gasto` válido grava e gera `agent_runs` com `channel='desktop'`;
  - argumento inválido → erro de validação legível;
  - `remover_evento` só cria pendência;
  - `contexto` traz a data e as faturas abertas.
- Aceite real:
  1. no Claude Desktop, "lança 25 reais de café no débito do inter" (via MCP);
  2. no WhatsApp, "quanto gastei hoje?" → aparece o café.

## Dúvidas para você

1. **OpenSpec no Jarvis**: eu tinha sugerido avaliar no começo da fase 7. Proposta: **não** agora. A fase 7 é pequena e cabe no fluxo atual (`SPEC.md` + `docs/fases`). Reavaliar na fase 8, quando o app do Mac (voz, ferramentas locais, roteador, sessões do Claude Code) começar e houver várias frentes em paralelo.
2. **Quais clientes você vai usar**: Claude Desktop, Claude Code ou os dois? Configuro e documento os dois por padrão.
3. **Tailscale**: posso instalar no Mac agora (`brew install --cask tailscale`, login com Google/GitHub)? Ou deixamos para quando o VPS existir?

---

# Relatório da fase 7

## O que foi feito

- `app/mcp_server.py`: `MCPServer` (SDK `mcp` 2.3) com as 12 ferramentas do agente mais `contexto` (só leitura).
  - O schema vem dos mesmos modelos Pydantic, por uma assinatura gerada; a chamada revalida com o modelo original (`extra=forbid` e validadores).
  - Erro de domínio (meio ambíguo etc.) volta como resultado. Erro de validação volta como erro legível, pelo `ToolError` do SDK (exceção genérica seria escondida).
  - Cada chamada grava `agent_runs` com `channel='desktop'` e dispara o sync do Google Calendar.
- `contexto`: o mesmo material do prompt do WhatsApp (data, tabela de datas, faturas abertas, cartões, categorias, pessoas, agenda da semana), sem persona nem regras (`data_only`).
- Montado no FastAPI em `/mcp`:
  - token `MCP_TOKEN` (sem token o MCP fica desligado);
  - proteção de host (`MCP_ALLOWED_HOSTS`);
  - o `session_manager` do SDK roda no lifespan.
- `docs/mcp.md` com a configuração do Claude Code e do Claude Desktop.
- 227 testes unitários, mais o teste de ponta a ponta por HTTP real com o cliente oficial (13 ferramentas, `contexto`, `total_fatura` com dados reais).

## Critério de aceite

| Critério | Resultado |
| --- | --- |
| Gasto lançado pelo Claude Desktop aparece numa consulta pelo WhatsApp | **ok** em 08/10. Às 16:53, o Claude Desktop (via `mcp-remote`) chamou `lancar_gasto`: café, R$ 25,00, no débito (`agent_runs.channel='desktop'`). Às 17:21, no WhatsApp, "quanto gastei?" → "hoje" → `buscar_gastos` listou o café de R$ 25,00 no total de R$ 72,00. |

## Decisões e desvios

- **Claude Code desconectado** a pedido do Kaio. Com escopo de usuário, o MCP aparecia em todas as sessões, inclusive as de trabalho. Fica configurado só no Claude Desktop, com o conector desligado por padrão nas conversas.
- **Conta Claude compartilhada com o trabalho**: o histórico de conversas é da conta. Conversas que usam o conector ficam visíveis para quem usa a mesma conta. Recomendação registrada: conta pessoal separada.
- **Celular**: o Claude do celular só usa conectores remotos (da conta inteira, pela nuvem da Anthropic, exigindo o núcleo exposto com HTTPS e OAuth). Isso contraria o `SPEC.md`, então não foi feito. O acesso pelo celular continua sendo o bot do WhatsApp.
- **Tailscale**: fica para quando houver VPS (fase 6 pausada).
