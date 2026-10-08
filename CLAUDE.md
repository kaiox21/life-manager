# CLAUDE.md

Assistente pessoal de usuário único (Kaio): agenda + gastos, com bot de WhatsApp e um Jarvis no Mac. **Fonte de verdade: `openspec/specs/` (o quê) e `SPEC.md` (visão, decisões e porquê).** Leia os dois antes de qualquer tarefa e não contradiga sem perguntar.

## Como trabalhamos (OpenSpec, desde 08/10/2026)

- **Toda mudança é um change do OpenSpec** em `openspec/changes/<nome>/` (`proposal.md`, `design.md`, `tasks.md` e deltas em `specs/`). Use `/opsx:propose` para criar e `/opsx:apply` para implementar. Não implemente nada fora do change em andamento "já que está aqui".
- **Antes de codar:** proposta, design, tarefas e deltas escritos e `openspec validate <nome> --strict` passando; pare para aprovação do Kaio.
- **Durante:** marque as tarefas em `tasks.md` conforme forem feitas; fatos conferidos em documentação oficial vão para o `design.md` com data.
- **Ao terminar:** rode os testes (e a prova, se mexeu em prompt, ferramenta ou modelo), faça o aceite real e arquive com `/opsx:archive` (os deltas entram em `openspec/specs`).
- Mudou uma decisão de desenho ou um risco? Atualize o `SPEC.md` no mesmo change.
- Dúvida que muda o comportamento para o usuário: pergunte. Detalhe técnico com padrão óbvio: decida e registre no `design.md`.
- `docs/fases/` é o histórico das fases 1 a 7 (antes do OpenSpec); não crie fases novas lá.

## Comandos

```bash
openspec list                # changes abertos (e --specs para as capacidades)
openspec validate --all --strict
uv sync                      # dependências
uv run pytest                # testes unitários (rápidos, sem rede, sem LLM)
uv run pytest -m eval        # prova contra o modelo real (custa centavos; precisa da chave do LLM_PROVIDER)
uv run ruff check . && uv run ruff format .
docker compose up -d         # evolution-api, postgres, redis, app
docker compose logs -f app
uv run alembic upgrade head
```

`pytest` sem `-m eval` nunca deve chamar a rede nem gastar dinheiro.

## Regras de arquitetura (não negociáveis)

1. **Só `app/channel/` conhece a Evolution API.** O resto do código recebe e devolve tipos próprios (`IncomingMessage`, `OutgoingMessage`). Trocar Baileys pela API oficial não pode tocar no agente.
2. **O LLM só toca o banco pelas ferramentas** de `app/agent/tools/`. Sem SQL livre, sem acesso direto ao ORM pelo modelo.
3. **O LLM nunca faz contas.** Somas, totais, fatura e parcelas são SQL ou Python. A regra da fatura vive em `app/domain/billing.py`, com testes cobrindo fechamento, virada de ano e parcelas.
4. **Dinheiro em centavos (`int`).** Nunca `float` para valores.
5. **Datas com fuso.** Tudo `timezone-aware`, fuso `America/Sao_Paulo`. "Hoje" vem de uma função injetável (`clock`) para os testes poderem fixar a data.
6. **Modelo por configuração.** `LLM_PROVIDER` escolhe o adaptador em `app/agent/llm.py`: `anthropic` (SDK oficial `anthropic`, o padrão em uso) ou `gateway` (cliente `openai` com `base_url` do Vercel AI Gateway). Nomes de modelo só via `.env` (`MODEL_CLASSIFIER`, `MODEL_PRIMARY`, `MODEL_ESCALATION`) e preços em `MODEL_PRICES`. Nunca nome de modelo fixo no código.
7. **Roteamento por intenção:** o agente recebe só as ferramentas do grupo da intenção (`openspec/specs/agente`, "Ferramentas por grupo").
8. **Validação e escalada:** argumentos inválidos voltam ao modelo uma vez; dois fracassos escalam para `MODEL_ESCALATION`; terceiro fracasso pede para reformular.
9. **Toda mensagem gera uma linha em `agent_runs`** com modelo, tokens, custo, latência, ferramentas chamadas e erro.
10. **Exclusão é lógica** (`deleted_at`) para permitir "desfazer".

## Segurança

- Atender só o número em `OWNER_PHONE`. Ignorar grupos, status e outros remetentes, sem responder.
- Webhook exige o header `X-Webhook-Secret` igual a `WEBHOOK_SECRET`.
- A função de envio só aceita `OWNER_PHONE` como destino.
- Nenhuma ferramenta executa shell, apaga arquivos ou envia mensagens a terceiros.
- Nunca logar segredos, conteúdo do `.env` ou números de cartão. `.env` fica fora do git.
- Não expor portas da Evolution API nem do Postgres fora da rede Docker.

## Convenções de código

- Python 3.12, `uv`, `ruff` (lint + format), type hints em tudo, Pydantic v2, SQLAlchemy 2 (estilo 2.0), Alembic para migrações.
- Nomes das ferramentas e dos argumentos exatamente como em `openspec/specs` e em `tests/eval/casos.yaml` (em português: `lancar_gasto`, `total_fatura`...). O resto do código pode usar inglês.
- Mensagens ao usuário em português do Brasil, curtas, sempre ecoando o que foi gravado.
- Funções de ferramenta puras sempre que possível: recebem sessão de banco e `clock`, devolvem dict serializável.

## Testes

- `tests/unit/`: regra de fatura, recorrência, parsing do webhook, allowlist, idempotência, ferramentas contra Postgres de teste.
- `tests/eval/casos.yaml`: a prova. O executor (`tests/eval/test_eval.py`, marcador `eval`) carrega os casos, monta fixtures num banco de teste, fixa `hoje`, roda classificador + agente e compara **só a primeira chamada de ferramenta** com `espera`, seguindo as convenções do cabeçalho do YAML. Ao final, imprime placar por grupo e custo total.
- PyYAML lê datas sem aspas como `datetime.date`: normalizar para string ISO antes de comparar.
- Nunca rodar a prova contra o banco real.
