## Decisions

- **SDK oficial `anthropic`**, não o endpoint compatível com OpenAI.
- O adaptador traduz o formato que o agente já usa:
  - `system` → parâmetro `system`;
  - `assistant.tool_calls` → blocos `tool_use`;
  - mensagens `tool` consecutivas → um único `user` com blocos `tool_result`;
  - `image_url` em data URI → bloco `image` base64;
  - `tool_choice` de função forçada → `{"type": "tool", "name": ...}`.
  - A resposta volta como `Completion` (texto, `ToolCall` com o JSON dos argumentos, tokens, custo, latência).
- `REASONING_EFFORT` vira `output_config.effort` quando definido; vazio = padrão do modelo.
- O custo usa `MODEL_PRICES` (US$ por milhão de tokens, entrada e saída) do `.env`; modelo sem preço registra custo 0.

Fatos conferidos em 08/10/2026 (API da Anthropic, chave do Kaio):
- Modelos disponíveis: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-sonnet-5`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`.
- `claude-haiku-5-5`: 1M de contexto, 128K de saída, criado em 07/10/2026, aceita `effort`. Preço no catálogo do gateway: US$ 0,10 / US$ 0,50.
- Teste de agenda ("marca dentista amanhã às 15h"): 1,2–1,5 s, argumentos corretos; `tool_choice` forçado aceito.

## Risks / Trade-offs

- [Modelo lançado ontem, sem histórico] → a prova (≥ 90%) decide; o gateway continua disponível pela configuração.
- [Chave colada na conversa] → recomendar rotacionar no console da Anthropic depois.
