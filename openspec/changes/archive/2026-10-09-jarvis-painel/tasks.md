## 1. Núcleo: ferramenta `painel`

- [x] 1.1 Montagem dos dados do painel no núcleo (agenda de hoje e 7 dias, mês por categoria e total, fatura aberta de cada cartão via `open_statement_month` + a mesma soma de `total_fatura`, registro dos últimos 10 com parcelas agrupadas e origem `whatsapp`/`mac` nos gastos); testes contra o Postgres de teste com `clock` fixo em 09/10/2026: fatura do Nubank igual à de `total_fatura`, excluídos fora, parcelada uma vez só, virada de mês
- [x] 1.2 Registrar `painel` só no MCP, como `contexto` (fora dos grupos do agente e sem o `_wrap`: sem `agent_runs` e sem sync do Calendar); teste chamando pelo servidor MCP de teste e conferindo que nada é gravado e o `after_write` não é chamado

## 2. Cérebro

- [x] 2.1 Mensagem `panel` → chama `painel` pelo MCP sem o modelo e devolve o evento `panel` (dados + últimas perguntas do histórico); erro do núcleo vira `panel` com `erro`; `done` ganha `wrote: true` quando o turno chamou ferramenta de escrita; `painel` fora das ferramentas entregues ao modelo; testes com cliente MCP falso (nenhuma chamada ao LLM)

## 3. Janela e atalhos

- [x] 3.1 Verificar primeiro `set_simple_fullscreen` numa janela `painel` com a política `Accessory` (barra de menus, Dock, monitor em uso, Esc devolvendo o foco ao app anterior); se falhar, janela sem bordas do tamanho do monitor acima da barra de menus; registrar o resultado no `design.md` com data
- [x] 3.2 Janela `painel` pré-criada e escondida; atalho global ⌥⇧Espaço e item "Painel" no menu da barra abrem/fecham; Esc fecha; perder o foco não fecha; `jarvis://ptt` com `target` (painel visível → não mostra o HUD); ⌥Espaço com o painel aberto foca o campo do painel; conferir à mão no `tauri dev` e medir a memória do WebView extra

## 4. Interface do painel

- [x] 4.1 Rota pelo rótulo da janela; conexão própria com o cérebro; pedido `panel` ao abrir, a cada 60 s visível e após `done` com `wrote`; timer e animação parados quando escondido; testes do estado (dados, erro com "núcleo indisponível" e horário da última atualização, atualização após escrita)
- [x] 4.2 Layout em grade (relógio/data, agenda, gastos por categoria + faturas, registro) no estilo da referência, só com números vindos do núcleo; testes de componente com dados de exemplo (dia livre, sem cartão de crédito, lista longa)
- [x] 4.3 Orbe de partículas em Canvas 2D com anéis SVG e os estados ocioso/ouvindo/pensando/falando; "Reduzir movimento" → quadro estático; medir CPU do WebView com o painel aberto (meta < 10%; se passar, 30 fps ou menos partículas) e anotar no `design.md`
- [x] 4.4 Conversa no painel: campo de texto, push-to-talk, pergunta/passos/resposta/cartões sob o orbe, reaproveitando `useJarvis`; testes de componente

## 5. Fechamento

- [x] 5.1 `uv run pytest`, `ruff`, testes da UI e `npm run tauri build` + `install_mac.sh`; a prova do núcleo não precisa rodar (prompt, ferramentas do agente e modelos não mudam)
- [x] 5.2 Aceite com o Kaio: ⌥⇧Espaço abre em menos de 300 ms e com dados em menos de 1 s; lançar um gasto pelo WhatsApp e ver no painel; "gastei 30 de Uber no Nubank" por voz com o painel aberto e ver Transporte, total e fatura atualizarem; Esc fecha e devolve o app anterior; núcleo parado mostra "núcleo indisponível"
- [x] 5.3 Arquivar o `jarvis-voz` antes; `SPEC.md` (fechar a questão "Painel central de comando", mapa de capacidades com `jarvis-painel`), relatório no `design.md` e arquivar
