## MODIFIED Requirements

### Requirement: Modelos por configuração
O sistema SHALL escolher o provedor por `LLM_PROVIDER`: `anthropic` (SDK oficial `anthropic`, chave `ANTHROPIC_API_KEY`) ou `gateway` (cliente `openai` com `base_url` do Vercel AI Gateway, `ALLOWED_PROVIDERS` como `providerOptions.gateway.only`). Os nomes SHALL vir só de `MODEL_CLASSIFIER`, `MODEL_PRIMARY` e `MODEL_ESCALATION`; `REASONING_EFFORT` (opcional) é repassado; `MODEL_PRICES` dá o preço por modelo para o custo em `agent_runs`. Nenhum nome de modelo fica fixo no código.

#### Scenario: Troca de modelo
- **WHEN** `MODEL_PRIMARY` muda no `.env`
- **THEN** o app passa a usar o novo modelo após reiniciar, sem mudança de código

#### Scenario: Troca de provedor
- **WHEN** `LLM_PROVIDER` muda de `gateway` para `anthropic`
- **THEN** agente, classificador, Jarvis e prova usam o SDK da Anthropic sem nenhuma outra mudança
