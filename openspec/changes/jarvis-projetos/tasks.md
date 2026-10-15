## 1. Abrir projeto

- [x] 1.1 `Folders.resolve` casa nomes normalizados (minúsculas, sem acentos, espaços, hífens e sublinhados) e devolve `opcoes` quando há mais de uma pasta; testes em `tests/jarvis/test_sessions.py` ("NC Barber" → `NC-BARBER`, "plataforma de estudos" → `plataforma-estudos`, dois `sisdec` → opções, fora da lista → erro)
- [x] 1.2 Ferramenta `abrir_projeto(nome, claude)` em `jarvis/local_tools.py`: resolve a pasta, abre o editor com `open -a "<JARVIS_EDITOR>"` (falha → segue sem editor e diz), reaproveita um shell livre na pasta (`open_tab`) ou chama `Control.open`; devolve `{status, pasta, editor, terminal, _fala}` com a frase fixa; testes com runner e controle falsos (editor ausente, terminal reaproveitado, `claude=true` abre novo, pasta fora da lista, opções, frase)
- [x] 1.3 Catálogo, `STEP_LABELS["abrir_projeto"]`, cartão "Projeto" em `cards.py`, `JARVIS_EDITOR` no `.env.example` e no `__main__`; teste do schema em `tests/jarvis/test_local_tools.py` e do cartão em `tests/jarvis/test_cards.py`
- [x] 1.4 Evento `panel_close` em `jarvis/events.py`, emitido pelo cérebro depois de `abrir_projeto` com sucesso; teste em `tests/jarvis/test_panel_extras.py` de que o evento sai só no sucesso

## 2. Turno com fala fixa e rascunhos

- [x] 2.1 Mecanismo em `jarvis/agent.py`: resultado de ferramenta com `_fala` encerra o turno sem nova chamada ao modelo (fala, token/done, histórico com a mensagem do assistente); `for_model` nunca devolve `_fala` nem `texto` de rascunho ao modelo; teste com LLM falso de que há uma só chamada ao modelo e a fala é a fixa
- [x] 2.2 Ferramenta `rascunho(tipo, para, assunto, texto)`: validação (texto 1 a 6.000), `pbcopy` do corpo, arquivo em `~/Library/Application Support/Jarvis/rascunhos/` (mantém os 50 mais novos), retorno com `arquivo`, `caracteres` e `_fala`; testes com pasta temporária (grava, rotaciona em 50, recusa texto longo, copia)
- [x] 2.3 Cartão `rascunho` em `cards.py` (título "Rascunho · e-mail para …", `to`, `subject`, `text`, `file`), regra da persona no prompt (texto em nome do Kaio, sem "senhor"; nunca envia nem propõe terminal ou app para enviar) e `STEP_LABELS["rascunho"]`; testes do cartão e de que o prompt contém as regras
- [x] 2.4 Texto fora do log: `_run_call` registra `rascunho` com `texto` trocado por `<N caracteres>`; teste com `caplog` de que nenhuma linha contém o texto
- [x] 2.5 Ação local `rascunho_copiar` com campo `texto` (até 6.000) em `jarvis/server.py` e `agent.local_action`; teste em `tests/jarvis/test_panel_extras.py` de que o texto chega ao `pbcopy` e de que texto maior é ignorado

## 3. Interface

- [x] 3.1 Tipo `rascunho` em `jarvis-ui/src/lib/types.ts`, `DraftCard` em `Cards.tsx` (destinatário, assunto, texto com quebras preservadas, botão Copiar que manda `{type: "local", acao: "rascunho_copiar", texto}`), estilos em `panel.css`; teste novo em `Cards.test.tsx`
- [x] 3.2 Evento `panel_close` em `useJarvis.ts`: fecha o painel pela mesma rotina do Esc (`invoke("hide_panel")`); coberto por `tsc` e pelo aceite (o hook não tem teste unitário); `cd jarvis-ui && npx tsc --noEmit && npx vitest run` passando (68 testes)

## 4. Verificação, documentação e aceite

- [x] 4.1 `uv run ruff check . && uv run ruff format --check . && uv run pytest tests/jarvis` e os testes da interface passando; `openspec validate jarvis-projetos --strict`
- [x] 4.2 Checagem com o modelo real (avisar o custo antes; ~US$ 0,002): "abre o NC Barber" → `abrir_projeto(nome="NC Barber")`; "abre o life-manager com um Claude Code" → `claude=true`; "escreve um e-mail pro professor de redes pedindo a segunda chamada" → `rascunho(tipo="email", …)`; "faz uma mensagem pro Netto avisando que o site volta amanhã" → `rascunho(tipo="mensagem", …)`; o rascunho sem "senhor" e assinado "Kaio"; "manda esse e-mail" → recusa sem ferramenta; registrar resultado e custo no `design.md`
- [x] 4.3 Documentação: linha "Projetos e rascunhos" na tabela de decisões do `SPEC.md`; seção de aceite em `docs/proximos-passos.md` (abrir o NC Barber por voz com o painel aberto, pedido com terminal já aberto, rascunho de e-mail, botão Copiar, "manda esse e-mail"); item 3 da lista marcado como implementado
- [ ] 4.4 Aceite real do Kaio pela lista da seção; ajustes que surgirem
- [ ] 4.5 Archive depois de `jarvis-estudo` (ordem em "Ações permitidas": musica → proativo → estudo → projetos); deltas em `openspec/specs`
