## 1. Núcleo

- [ ] 1.1 `log_outgoing(type=…)` e `deliver` gravando `type="aviso_<kind>"`; testes de entrega conferindo a linha em `messages`
- [ ] 1.2 Ferramenta MCP `avisos_recentes(desde)` registrada à parte (sem `agent_runs`, máx. 20, ordem de envio, com o tipo, sem o prefixo do modo provisório, só `aviso_*`); testes
- [ ] 1.3 `painel` com `hoje` (total e quantidade dos gastos com data de hoje, sem os desfeitos); teste

## 2. Fechamento do dia

- [ ] 2.1 `briefing.evening(now, panel)` e `briefing.spoken_notice(tipo, texto)`; testes com relógio fixo
- [ ] 2.2 `brain`: `is_good_night` no começo do `_ask`, `brain.evening` (uma chamada ao `painel`, eventos, fala, histórico), janela de resposta de 2 min (negativa sem modelo), resumo no histórico; evento `evening` no servidor; testes
- [ ] 2.3 `WakeService`: depois do turno, `wants_answer()` → `wait_request()`; `expect_answer()` para o lembrete; testes

## 3. Proativo

- [ ] 3.1 `jarvis/proactive.py`: fila com descarte em 5 min, condições de fala, avisos do núcleo a cada 60 s, estado em `proativo.json`; testes com relógio e núcleo falsos
- [ ] 3.2 Terminais: `trabalho_desde` e `duracao` no `terminou`; avisos ligados por um único ponto (`watch_terminals` e `control.broadcast`); `permissao` e `terminou ≥ 2 min`, um por terminal por minuto; teste de que "permite" não chega a `permissions.resolve`
- [ ] 3.3 Lembrete de lançamento (`JARVIS_LEMBRETE_GASTOS`), uma vez por dia, recuperado ao acordar até o silêncio, `expect_answer()`, entra no histórico; testes
- [ ] 3.4 Ferramenta local `silenciar_avisos`, ações `avisos_pausar_1h`/`avisos_retomar` no `local_action`, `avisos` nos dados do painel, `JARVIS_SILENCIO`; testes

## 4. Interface

- [ ] 4.1 Botões Boa noite e Silenciar nos modos do painel (Silenciar mostra "Avisos HH:MM" quando pausado); tipos e testes

## 5. Fechamento

- [ ] 5.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, testes da interface, `openspec validate --all --strict`; reconstruir o núcleo (`docker compose up -d --build app`), o app e reiniciar o cérebro
- [ ] 5.2 Aceite real com o Kaio: "Jarvis, boa noite" com gasto esquecido e com "não"; botão Boa noite; aviso de evento falado (evento daqui a 35 min com aviso de 30); Claude Code num trabalho longo terminando e pedindo permissão; resposta curta sem aviso; "silencia por uma hora", botão Silenciar e "volta a avisar"; lembrete das 21:30 num dia sem gasto; nada falado depois das 23:00
- [ ] 5.3 `SPEC.md` (Jarvis proativo: o que fala, quando se cala, voz nunca aprova) e `/opsx:archive` depois de `radar-vagas` e `boletim-noticias`; atualizar `docs/proximos-passos.md`
