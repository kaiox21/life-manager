# Fase 2 — Gastos por texto

Status: **código implementado; escolha do modelo pendente** (08/10/2026). Plano aprovado em 07/10/2026.

Objetivo (do `SPEC.md`): tabelas, seeds de categorias e cartões, ferramentas de gasto, classificador, laço do agente, `agent_runs` e o executor da prova.

Critérios de aceite:

1. "gastei 47 no almoço no Nubank" grava.
2. "total da fatura do Nubank" bate com a soma feita à mão.
3. Os testes da regra de fatura cobrem fechamento, virada de ano e parcelas.
4. O modelo escolhido acerta ao menos 90% da prova.

## Meios de pagamento reais (informados em 07/10/2026; ficam só no banco local)

Os dados reais (nomes, fechamento e vencimento) **não** vão para o repositório público. Ficam em `data/meios_pagamento.yaml`. A forma: dois cartões de crédito (um fecha no último dia do mês) e um débito no mesmo banco de um deles.

Sem Pix, sem dinheiro e sem apelidos. **Os dados reais não vão para o GitHub**: ficam em `data/meios_pagamento.yaml` (a pasta `data/` já está no `.gitignore`), carregado por `uv run python -m app.db.seed`. O repositório só traz `seeds/meios_pagamento.exemplo.yaml` com cartões fictícios.

**Crédito ou débito no mesmo banco: perguntar sempre.** "gastei 30 no <banco>" (havendo crédito e débito nele) não diz qual dos dois, então o bot pergunta. "no débito" (só existe um débito) e "no crédito do <banco>" resolvem direto. Um banco que só tem crédito não é ambíguo. Isso segue a regra do `SPEC.md` ("ambíguo ou inexistente, pergunta"). Em `total_fatura` só entram meios de crédito, então "fatura do <banco>" resolve direto para o crédito desse banco.

## Regra da fatura (`app/domain/billing.py`)

A regra do `SPEC.md` ("dia da compra menor que `closing_day` → fatura que vence no próximo `due_day`; senão, a seguinte") fica implementada assim, sem mudar o comportamento:

1. **Fechamento efetivo** no mês da compra = `min(closing_day, último dia do mês)`. "Fecha no último dia" é gravado como `closing_day = 31`, e a função ajusta para 30, 29 ou 28. **Proposta de acréscimo ao `SPEC.md`**: uma frase sobre esse ajuste.
2. Compra **antes** do fechamento efetivo → fatura que fecha neste mês. No dia do fechamento ou depois → fatura que fecha no mês seguinte.
3. Mês de vencimento: se `due_day > closing_day`, vence no mesmo mês do fechamento (ex.: fecha 10, vence 17). Senão, no mês seguinte (Nubank: fecha 31, vence 8).
4. `statement_month` = dia 1 do mês de vencimento.
5. **Parcelas:** N linhas com o mesmo `purchase_group` e `statement_month` avançando um mês cada. O valor é dividido em centavos inteiros e a sobra vai para a 1ª parcela (R$ 100,00 em 3x = 33,34 + 33,33 + 33,33). A soma sempre fecha exatamente com o total.

Exemplos que viram teste:

| Compra | Cartão | Fatura (vencimento) |
| --- | --- | --- |
| 15/10/2026 | Nubank | 08/11/2026 |
| 31/10/2026 (dia do fechamento) | Nubank | 08/12/2026 |
| 30/11/2026 (último dia de novembro) | Nubank | 08/01/2027 (virada de ano) |
| 27/02/2027 / 28/02/2027 | Nubank | 08/03/2027 / 08/04/2027 (fevereiro) |
| 09/10/2026 / 10/10/2026 | fecha 10, vence 17 | 17/10/2026 / 17/11/2026 |
| 20/12/2026 | fecha 10, vence 17 | 17/01/2027 (virada de ano) |
| 600,00 em 3x em 15/10/2026 | fecha 10, vence 17 | 17/11, 17/12/2026, 17/01/2027 (200,00 cada) |

## Mudanças em `tests/eval/casos.yaml` (continua com cartões fictícios)

A prova é pública, então os cartões continuam de exemplo. Eles passam a ter a **mesma forma** do seu uso real, para a prova medir o que importa: dois cartões de crédito (um fechando no último dia do mês) e um débito no mesmo banco de um deles.

- `fixtures.meios_pagamento`: Nubank (crédito, fecha 31, vence 8), Itaú Crédito (fecha 25, vence 5), Itaú Débito, Pix, Dinheiro. Pix e Dinheiro ficam nos exemplos para não reescrever 7 casos que só testam a extração.
- **Itaú → "itaú crédito"** nas frases de g03, g06, g13 e g16; `payment_method: Itaú Crédito`.
- **g18** "gastei 9,50 num café, débito": como existe um único débito, passa a esperar `lancar_gasto` com `payment_method: Itaú Débito` e `category: Alimentação`.
- **Casos novos**: g22 "padaria 12 no itaú" → `pergunta` (crédito ou débito?), proibido `lancar_gasto`; g23 "farmácia 45,90 no débito do itaú" → `lancar_gasto` com `Itaú Débito`.
- **Faturas recalculadas** com o Nubank fechando no último dia: c01 e c03 continuam `2026-11`. c02 e c04 (Itaú, fecha 25, vence 5) continuam `2026-10` e `2026-11`, agora com `payment_method: Itaú Crédito`.
- **Convenção nova no cabeçalho**: `payment_method` é comparado **depois da resolução** pelos mesmos `name`/`aliases` da ferramenta. Assim, "Itaú" em `total_fatura` (só crédito) bate com `Itaú Crédito`.
- Frases (`msg`) continuam as atuais (você não quis reescrever agora). Total passa a 56 casos, 40 fora de agenda.

## Arquivos

```text
app/
  clock.py                  # Clock injetável (now() com fuso America/Sao_Paulo)
  domain/billing.py         # regra da fatura e parcelas (100% testada)
  db/models.py              # + PaymentMethod, Category, Expense, PendingAction, AgentRun
  db/migrations/versions/0002_gastos.py
  db/seed.py                # categorias + meios de data/meios_pagamento.yaml; idempotente
seeds/meios_pagamento.exemplo.yaml   # formato do arquivo, com cartões fictícios
  agent/
    llm.py                  # cliente openai -> Vercel AI Gateway; custo por chamada
    intent.py               # classificador (6 intenções)
    prompt.py               # prompt de sistema + tabela de hoje e dos próximos 7 dias
    loop.py                 # laço de tool calling, validação, escalada, agent_runs
    tools/
      __init__.py           # registro: nome -> (schema Pydantic, função, grupo)
      gastos.py             # lancar_gasto, desfazer_ultimo, gerenciar_meio_pagamento
      consultas.py          # buscar_gastos, total_fatura, resumo_gastos
      confirmacao.py        # confirmar_pendente + criação de pendências
      resolve.py            # casa "nubank"/"roxinho" com meio; categoria por nome (sem acento/caixa)
  handler.py                # troca o eco pelo agente; "sim"/"não" com pendência vai direto, sem LLM
tests/
  unit/test_billing.py      # tabela acima + propriedades (soma das parcelas = total)
  unit/test_tools_gastos.py # ferramentas contra o Postgres de teste, clock fixo
  unit/test_loop.py         # laço com LLM falso: validação, 1 retry, escalada, desistência, agent_runs
  unit/test_intent.py       # parsing da resposta do classificador (LLM falso)
  unit/test_confirmacao.py  # pendência > R$ 500, sim/não, expiração em 30 min
  eval/test_eval.py         # a prova (marcador eval)
  eval/conftest.py
```

`people`, `events` e as ferramentas de agenda e pessoa **não** entram (fase 3).

## Decisões

1. **Ferramentas** com nomes e argumentos exatamente como no `SPEC.md`. Cada uma recebe `(session, clock, args)` e devolve um dict curto. Os valores voltam em centavos e também formatados ("R$ 47,90"), para o modelo só copiar.
2. **Valores acima de R$ 500** (`amount_cents > 50000`, o total da compra) criam `pending_actions` em vez de gravar. "sim"/"não" com pendência aberta é resolvido no handler sem LLM (passo 4 do `SPEC.md`). `confirmar_pendente` existe para o caminho via classificador. Pendências expiram em 30 min.
3. **`desfazer_ultimo`**: exclusão lógica da compra mais recente ainda não excluída, com todas as parcelas do mesmo `purchase_group`. Nesta fase vale só para gastos.
4. **Resolução de nomes** sem acento e sem diferenciar maiúsculas, por `name` e `aliases`. Inexistente ou ambíguo devolve erro com a lista de opções, e o modelo pergunta.
5. **Classificador**: uma chamada curta pedindo uma palavra das seis. Resposta fora da lista vale `fora_do_escopo`.
6. **Histórico**: últimas 10 mensagens de `messages`. No modo provisório, as respostas guardadas sem a marca `🤖 `.
7. **Escalada** exatamente como o `SPEC.md`: argumento inválido volta ao modelo uma vez; dois fracassos (ou resposta sem ferramenta quando a intenção exigia uma) passam para `MODEL_ESCALATION`; se a escalada também falhar, pede para reformular. Até 6 iterações.
8. **Custo em `agent_runs`**: tokens da resposta × preço do modelo no catálogo do gateway (`GET /v1/models`, consultado uma vez e guardado em cache). Se o gateway devolver o custo na própria resposta, uso esse valor.
9. **Filtro de fornecedores** (`ALLOWED_PROVIDERS`) mandado no corpo da requisição ao gateway. Confiro o nome exato do campo na documentação antes de codar e registro aqui.
10. **Prova nesta fase:** o classificador é avaliado nos 54 casos. O agente, nos casos que não são de agenda (gasto, consulta, confirmação e fora do escopo), porque as ferramentas de agenda são da fase 3. O critério de 90% vale sobre esses 40 (38 + g22 e g23). Na fase 3 a prova roda inteira de novo.
11. **Sem LLM nos testes unitários**: o laço recebe um cliente falso com respostas roteirizadas.

## Modelos candidatos (catálogo do gateway, 07/10/2026; US$ por milhão de tokens entrada/saída)

Todos usam ferramentas. Prefiro os que também aceitam imagem, por causa do recibo da fase 4.

| Papel | Candidatos |
| --- | --- |
| Principal | `openai/gpt-5-nano` (0,05/0,40), `google/gemini-2.5-flash-lite` (0,10/0,40), `anthropic/claude-haiku-5.5` (0,10/0,50), `alibaba/qwen3.8-flash` (0,15/0,47), `zai/glm-5.3-flash` (0,15/0,50), `deepseek/deepseek-v4-flash` (0,13/0,26; sem imagem) |
| Escalada (chinês mais forte) | `deepseek/deepseek-v4-pro` (0,66/1,98), `alibaba/qwen3.7-plus` (0,40/1,60), `moonshotai/kimi-k2.5` (0,60/3,00) |
| Classificador | os três mais baratos da linha "Principal" |

Estimativa: cerca de 3,5 mil tokens de entrada por caso, ou seja, uns US$ 0,02–0,15 por rodada completa de um modelo. Todas as rodadas acima ficam **abaixo de US$ 1** dos seus US$ 5. O placar de cada modelo é registrado aqui, e a escolha sai dele (maior acerto, custo como desempate).

## Testes

- `uv run pytest`: billing, ferramentas contra o Postgres de teste com clock fixo em 07/10/2026, laço e classificador com LLM falso, confirmação. Sem rede.
- `uv run pytest -m eval`: a prova contra os modelos reais, no banco de teste. Imprime o placar por grupo e o custo total.
- Aceite real pelo WhatsApp: "gastei 47 no almoço no Nubank" e depois "total da fatura do Nubank", conferido à mão contra o banco.

## Respostas (07/10/2026)

1. Meios: dois créditos e um débito (detalhes só no banco local). Sem Pix, dinheiro ou apelidos.
2. Crédito ou débito ambíguo: perguntar sempre.
3. Frases da prova: seguem as atuais.
4. Dados reais só no banco local; a prova pública usa cartões fictícios com a mesma forma.

Proposta ao `SPEC.md` antes de codar: acrescentar à "Regra da fatura" a frase sobre `closing_day` maior que o último dia do mês (ajusta para o último dia), e ao "Resolução de referências" que crédito e débito do mesmo banco sem especificar contam como ambíguos.

---

# Andamento (08/10/2026)

## Feito

- `app/domain/billing.py` com fechamento no último dia do mês, virada de ano, fevereiro, bissexto e parcelas (sobra na 1ª).
- Migração `0002`: `payment_methods`, `categories`, `expenses`, `pending_actions`, `agent_runs` e a extensão `unaccent`. Em `expenses.created_at`, `clock_timestamp()` dá ordem real dentro da mesma transação; o `desfazer_ultimo` depende disso.
- Seed: categorias fixas + `data/meios_pagamento.yaml` (real, fora do git); exemplo em `seeds/`.
- Ferramentas: `lancar_gasto`, `desfazer_ultimo`, `gerenciar_meio_pagamento`, `buscar_gastos`, `total_fatura`, `resumo_gastos`, `confirmar_pendente`.
- Classificador por **chamada de ferramenta forçada** (`classificar`, intenções num `enum`). No primeiro teste real, o `gpt-5-nano` respondeu "lançar" em texto livre.
- Laço com validação, uma nova tentativa, escalada, desistência e `agent_runs`. Cada tentativa roda num savepoint: se escala, o que o modelo principal gravou é desfeito.
- "sim"/"não" com pendência aberta resolve sem LLM.
- Prompt com tabela de datas (ontem, últimos 7 dias, próximos 7, este mês, mês passado, semanas) e **faturas abertas por cartão**, para o modelo copiar `mes_vencimento` em vez de calcular.
- Prova: `casos.yaml` atualizado (56 casos; 40 avaliados no agente), `tests/eval/test_eval.py` e `tests/eval/run_matrix.sh`.
- 161 testes unitários, sem rede.

## Bloqueio

Os US$ 5 do AI Gateway são do **plano gratuito**: `claude-haiku-5.5`, `qwen3.8-flash`, `glm-5.3-flash` e `deepseek-v4-flash` devolvem 403 ("Free tier users do not have access to this model"). O BYOK da Anthropic também exige créditos comprados. Só `gpt-5-nano` e `gemini-2.5-flash-lite` rodam.

## Pendente

- Escolher os modelos pelo placar e preencher `MODEL_*` no `.env`.
- Reconstruir o app, rodar a seed real e fazer o aceite pelo WhatsApp.
- Relatório final desta fase.
