## Why

O `gpt-5-nano` (via Vercel AI Gateway, plano gratuito) leva 10–40 s por resposta, o que deixa o bot e o Jarvis lentos demais, e a voz inviável. O Kaio tem crédito na API da Anthropic e pediu o modelo mais barato que dê conta (08/10/2026).

## What Changes

- Novo adaptador `AnthropicLLM` (SDK oficial `anthropic`), ao lado do `GatewayLLM`, que implementa o mesmo protocolo `LLM`. O agente, o classificador, o Jarvis e a prova não mudam.
- `LLM_PROVIDER=anthropic|gateway` no `.env` escolhe o adaptador. Os nomes de modelo continuam só no `.env`.
- Modelos: `claude-haiku-5-5` (lançado em 07/10/2026; US$ 0,10/0,50 por milhão de tokens; 1–1,5 s numa chamada de agenda nos testes) para classificador e principal; `claude-sonnet-5-5` para a escalada.
- Custo em `agent_runs`: preços por modelo em `MODEL_PRICES` (JSON no `.env`).
- Decisões do `SPEC.md` tocadas: "Modelo de IA" (os modelos não passam mais só pelo gateway) e a regra 6 do `CLAUDE.md` ("cliente openai com base_url do gateway").

## Non-goals

- Remover o gateway (continua como opção, `LLM_PROVIDER=gateway`).
- Prompt caching e voz (mudanças futuras).

## Capabilities

### Modified Capabilities
- `agente`: o requisito "Modelos por configuração" passa a aceitar dois provedores.

## Impact

- `app/agent/llm.py`, `app/config.py`, os pontos que constroem o LLM (`app/main.py`, `jarvis/__main__.py`, `tests/eval`), `.env.example`, `SPEC.md`, `CLAUDE.md`.
- Nova dependência: `anthropic` (1.x, usa `httpx2`, já presente pelo `mcp`).
