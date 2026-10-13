## Why

Hoje o Jarvis só fala quando é chamado. O maior risco do projeto, segundo o `SPEC.md`, é o Kaio parar de lançar os gastos, e os avisos importantes (compromisso daqui a pouco, Claude Code pedindo permissão) chegam só no WhatsApp ou numa barra que ele pode não estar vendo. O Kaio aprovou em 10/10/2026 a lista de funcionalidades novas do Jarvis. Esta é a primeira: um Jarvis que **puxa** o Kaio, com fechamento do dia e avisos falados.

## What Changes

- **"Jarvis, boa noite": fechamento do dia**, falado, com texto fixo e sem chamar o modelo:
  - quantos gastos com data de hoje foram lançados e o total, e o total do mês;
  - a agenda de amanhã, com o horário do primeiro compromisso;
  - a pergunta *"O senhor teve algum gasto hoje que ainda não lançou?"*;
  - depois disso, ele ouve a resposta sem exigir o nome. "30 de uber no pix" é lançado como hoje (com o cartão de confirmação de sempre), e "não" encerra.
  - Funciona pela palavra ("Jarvis, boa noite"), pelo atalho de voz, digitado e pelo botão **Boa noite** do painel.
- **Lembrete de lançamento:** às 21:30, se o Mac estiver ligado e nenhum gasto com data de hoje tiver sido lançado, o Jarvis pergunta em voz: *"Senhor, nenhum gasto lançado hoje. Teve algum?"*. Ele ouve a resposta como no fechamento. Uma vez por dia, no máximo.
- **Avisos falados:**
  - **lembretes do núcleo**: compromisso, aniversário e fatura perto de fechar são falados quando saem no WhatsApp, com o Mac ligado. Vagas novas viram uma frase curta ("Senhor, o radar encontrou vagas novas; estão no painel."). O boletim de notícias e o resumo das 07:30 não são falados: o "Hey Jarvis" já fala os dois;
  - **terminais:** quando um Claude Code pede permissão, ou termina um trabalho que levou 2 minutos ou mais, ele fala (*"Senhor, o Claude Code do life-manager está pedindo permissão para usar Bash."*). Cada resposta curta do Claude Code não vira aviso. Responder continua sendo só pelo clique: a voz nunca aprova nem nega;
  - o resumo do dia, o fechamento e o lembrete entram no histórico da conversa, para os pedidos seguintes terem o contexto.
- **Silêncio:**
  - nada é falado entre 23:00 e 07:00, nem enquanto o Jarvis já está falando ou ouvindo (o aviso espera a vez);
  - "Jarvis, silencia os avisos por uma hora" (ou "até amanhã"), ou o botão **Silenciar** do painel, pausa os avisos falados; "Jarvis, volta a avisar" retoma. O painel mostra até quando estão pausados;
  - a pausa é lembrada se o Jarvis reiniciar.
- **Núcleo:**
  - nova ferramenta MCP somente leitura `avisos_recentes(desde)`, que devolve os avisos enviados depois de um instante, com o tipo e o texto;
  - cada aviso enviado passa a ser gravado em `messages` com o tipo `aviso_<tipo>` (`aviso_evento`, `aviso_fatura`, `aviso_vagas`…);
  - o `painel` passa a trazer os gastos com data de hoje (total e quantidade), para o fechamento sair de uma chamada só.

## Non-goals

- Aprovar ou negar pedidos de permissão por voz.
- Falar avisos com o Mac bloqueado ou dormindo.
- Mudar quando o núcleo manda os lembretes (antecedências e horários continuam os de hoje).
- Detectar reunião ou chamada sozinho (a pausa é por voz ou pelo botão).
- Resumo semanal, modo foco, prazos da UnB e notas por voz: ficam para os próximos changes da lista.

## Capabilities

### New Capabilities
- `jarvis-proativo`: fechamento do dia, lembrete de lançamento, avisos falados (núcleo e terminais), silêncio e os botões Boa noite e Silenciar.

### Modified Capabilities
- `mcp`: ferramenta somente leitura `avisos_recentes`; `painel` com os gastos de hoje.
- `lembretes`: o envio de cada aviso é registrado em `messages` com o tipo `aviso_<tipo>`, para o Jarvis poder repeti-lo.

## Impact

- **Núcleo:**
  - `app/reminders/delivery.py` e `app/db/repo.py` passam a gravar o tipo `aviso_<tipo>` (vale para lembretes, radar e boletim, que usam o mesmo `deliver`);
  - `app/mcp_server.py` ganha `avisos_recentes`, registrada à parte como o `painel` (fora de `ALL_TOOLS`, sem linha em `agent_runs`: o Jarvis a chama a cada minuto);
  - `app/agent/tools/painel.py` ganha `hoje`.
  - Não há migração: `messages.type` já é texto livre.
- **Cérebro:**
  - `jarvis/briefing.py` ganha o texto do fechamento e a limpeza do texto falado dos avisos;
  - `jarvis/proactive.py`, novo: consulta os avisos a cada minuto, fala os de terminal, faz o lembrete das 21:30, cuida do silêncio e da fila de fala;
  - `jarvis/agent.py`: "boa noite" detectado antes do modelo, resposta "não" sem o modelo, e resumo, fechamento e lembrete no histórico;
  - `jarvis/wake.py`: depois do fechamento (e do lembrete), a escuta espera a resposta sem o nome;
  - `jarvis/terminals.py`: o aviso "terminou" leva quanto tempo o trabalho durou;
  - ferramenta local `silenciar_avisos`.
- **Interface:** botões **Boa noite** e **Silenciar** entre os modos do painel (o `jarvis-painel-hud` deixou o lugar reservado) e o aviso "avisos pausados até 15:40".
- **Estado:** a pausa dos avisos e o "já perguntei hoje" ficam em `~/Library/Application Support/Jarvis/proativo.json`, arquivo só do cérebro (o `config.json` é reescrito também pelo app).
- **Custo:** o fechamento, o lembrete e os avisos não chamam o modelo. A resposta "30 de uber no pix" é um turno normal, que custa uma fração de centavo com o Haiku.
- **Ordem de arquivamento:** depois de `radar-vagas` e `boletim-noticias`, porque os três mudam o requisito "Dados do painel".
- **`SPEC.md`:** decisão do Jarvis proativo (o que fala, quando se cala, voz nunca aprova).
