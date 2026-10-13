## 1. Dados e configuração

- [x] 1.1 Migração Alembic: tabela `job_leads` (URL única, código V+sequência único) e `vagas` no CHECK de `sent_reminders.kind`; modelo SQLAlchemy
- [x] 1.2 `config/vagas.yaml` no `.gitignore` e `config/vagas.example.yaml` genérico versionado (perfil: tipos, local, áreas, restrição de horário, consultas sugeridas) e `VAGAS_ATIVO`, `VAGAS_MODELO`, `VAGAS_MAX_BUSCAS` em `app/config.py` e `.env.example`

## 2. Radar

- [x] 2.1 `app/vagas/radar.py`: conversa com `web_search` + `registrar_vagas` (Pydantic), URLs permitidas dos resultados da busca, normalização, descarte de inventadas/vencidas/repetidas, pontuação, gravação em `job_leads` e linha em `agent_runs` (canal `vagas`); testes com LLM falso (URL inventada, repetida, vencida, ordem)
- [x] 2.2 `app/vagas/templates.py` (mensagem fixa, até 8) e entrega pelo `deliver` com reserva `kind='vagas'`; checagem por hora das 08:00 às 22:00 + na subida (≥ 72 h desde a última rodada sem erro; até 2 tentativas por dia); testes com relógio fixo (Mac acordando às 11:00, rodada que falha)

## 3. Conversa e painel

- [x] 3.1 Intenção `vagas` no classificador, ferramentas `listar_vagas` e `dispensar_vaga` por código ou título (grupo `vagas`; título ambíguo volta opções); testes das ferramentas. **Os 3 casos na prova ficaram de fora:** `tests/eval/casos.yaml` é somente leitura (spec do agente, "Prova de acerto"); pendente da autorização do Kaio para alterá-lo (v01 "quais vagas novas apareceram?" → `listar_vagas`; v02 "tem algum estágio novo pra mim?" → `listar_vagas`; v03 "não tenho interesse na V12" → `dispensar_vaga(vaga='V12')`)
- [x] 3.2 `painel` com `vagas` (até 8, 14 dias, sem dispensadas); cartão "Vagas" no Jarvis (links abrem no navegador); testes

## 4. Fechamento

- [ ] 4.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `uv run alembic upgrade head`, `openspec validate --all --strict`; prova (`uv run pytest -m eval`, avisar o custo antes)
- [ ] 4.2 Primeira rodada real com o Kaio (custo anotado), ajuste do perfil, "não tenho interesse na N" pelo WhatsApp e pelo Jarvis
- [ ] 4.3 `SPEC.md` (decisão do radar: link verificado, sem repetição, custo) e `/opsx:archive`
