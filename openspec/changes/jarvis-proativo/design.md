## Context

- **Já existe:**
  - o resumo do dia por "Hey Jarvis" (`JarvisBrain.briefing`, texto fixo de `jarvis/briefing.py`, eventos `heard`/`token`/`done` e fala direta pelo `speaker`); o botão Resumo do painel usa o mesmo caminho (`{"type": "briefing"}`);
  - a espera de pedido sem o nome depois do resumo (`WakeListener.wait_request`, `brain._waiting_request`), hoje só depois de "Hey Jarvis" sozinho (`so_nome`);
  - os avisos de terminal (`terminal_alert`, com `tipo` `permissao`/`espera`/`terminou`), que saem de **dois lugares**: `watch_terminals` em `__main__.py` (eventos dos hooks) e `TerminalControl._on_request` (pedido de permissão de um terminal compartilhado, por `control.broadcast`). O `terminou` vem do hook `Stop`, que dispara **ao fim de cada resposta** do Claude Code;
  - os lembretes do núcleo saem por `deliver` (`app/reminders/delivery.py`), que também entrega o radar de vagas (`kind="vagas"`) e o boletim (`kind="noticias"`), e registra em `messages` como `type="text"`, igual a uma resposta comum;
  - as ferramentas de `ALL_TOOLS` no MCP gravam uma linha em `agent_runs` a cada chamada; `painel` e `contexto` são registradas à parte e não gravam;
  - o `config.json` do Jarvis é lido pelo cérebro e reescrito pelo app (Tauri, escolha "Ouvir Jarvis");
  - o painel HUD tem os modos Resumo, Música e Terminais, com o lugar de Boa noite e Silenciar reservado pelo `jarvis-painel-hud`.
- O Jarvis fala com o núcleo só pelo MCP (spec `jarvis-agente`, "Núcleo só pelo MCP").

## Goals / Non-Goals

**Goals:**
- O fechamento, o lembrete e os avisos não chamam o modelo.
- Uma fonte de verdade para os lembretes (o núcleo decide quando avisar; o Jarvis repete).
- Nunca falar por cima de uma conversa nem na madrugada, e não virar ruído.

**Non-Goals:** ver a proposta.

## Decisions

1. **"Boa noite" detectado antes do modelo.**
   - `is_good_night(text)`: texto normalizado (sem acento, pontuação e "Jarvis" no começo ou no fim) igual a "boa noite". Frases maiores vão ao modelo.
   - A verificação fica no começo de `brain._ask`, o que cobre a palavra, o atalho de voz e o texto. O botão manda `{"type": "evening"}`, que chama `brain.evening` direto.
   - Mesmos eventos do resumo: `heard`, `token(texto)` e `done`.

2. **Dados do fechamento: uma chamada ao `painel`.**
   - O `painel` ganha `hoje: {total_centavos, total, lancamentos}` (gastos com `spent_on` = hoje, não desfeitos).
   - O fechamento usa `hoje`, `mes.total` e os eventos de amanhã dentro de `agenda.proximos`. Uma chamada, nenhuma linha em `agent_runs`, o mesmo tratamento de "núcleo indisponível" do resumo.
   - "Gasto de hoje" é pela data do gasto, não pela hora do lançamento: o que importa é se o dia foi registrado.
   - O texto fica em `briefing.evening(now, panel)`, função pura testada com relógio fixo.

3. **Resposta à pergunta.**
   - Depois do fechamento e do lembrete, o cérebro marca `_answer_until = agora + 2 min`.
   - Na próxima fala dentro do prazo, uma negativa normalizada ("não", "nada", "nenhum", "não tive", "tudo lançado", "já lancei") responde "Perfeito, senhor. Boa noite." (ou "Perfeito, senhor." depois do lembrete), sem o modelo. Qualquer outra coisa vai ao modelo; o histórico já tem a pergunta, então "30 de uber no pix" vira `lancar_gasto` com as confirmações de sempre.
   - **Pela palavra:** o `WakeService` pergunta ao cérebro (`wants_answer()`) depois de cada turno; se sim, chama `wait_request()` em vez de `done()`, como depois do resumo, e marca `_waiting_request`.
   - **Pelo lembrete:** o serviço proativo chama `wake.expect_answer()`, que faz o mesmo se a escuta estiver ligada e parada. Sem a escuta, o Kaio responde pelo atalho ou digitando.
   - **Histórico:** o resumo entra como (`user: "Jarvis"`, `assistant: texto`), o fechamento como (`user: "boa noite"`, `assistant: texto`) e o lembrete como (`user: "[lembrete das 21:30]"`, `assistant: pergunta`), para manter a alternância de papéis que a API exige.

4. **Avisos do núcleo pelo MCP.**
   - `log_outgoing(..., type="text")` ganha o parâmetro; `deliver` passa `type=f"aviso_{notice.kind}"`. Vale para lembretes, radar e boletim. Sem migração.
   - `avisos_recentes(desde)` é registrada à parte, como o `painel`: o Jarvis a chama a cada 60 s, e em `ALL_TOOLS` isso daria 1.440 linhas por dia em `agent_runs`. Lê `messages` com `direction='out'`, `type LIKE 'aviso\_%'` e `created_at > desde`, em ordem, no máximo 20, tirando o prefixo do modo provisório (`BOT_MARK`).
   - **No Jarvis:** `desde` começa na subida e avança pelo `hora` do último aviso recebido. Sem estado em disco: depois de reiniciar, só valem os avisos novos.
   - **O que é falado** (`briefing.spoken_notice(tipo, texto)`):
     - `evento` e `fatura`: o texto sem emojis, sem trechos entre parênteses, com " — " virando vírgula e "14:00" virando "14h" (e "14:30" virando "14h30");
     - `vagas`: "Senhor, o radar encontrou vagas novas; estão no painel.";
     - `noticias`, `resumo` e tipos desconhecidos: nada.

5. **Avisos de terminal.**
   - `Terminal` ganha `trabalho_desde`, marcado no `UserPromptSubmit`; o aviso `terminou` leva `duracao` (segundos).
   - O serviço proativo recebe todos os `terminal_alert` por um único ponto: um `notify` passado a `watch_terminals` e envolvido em `control.broadcast`.
   - São falados `permissao` (sempre) e `terminou` com `duracao ≥ 120`. `espera` não.
   - Um terminal fala no máximo uma vez por minuto (chave = número do terminal), o que também absorve o mesmo pedido chegando pelos dois caminhos.
   - Textos: "Senhor, o Claude Code do <pasta> está pedindo permissão para usar <ferramenta>." e "Senhor, o Claude Code do <pasta> terminou." Nunca o resumo do comando (pode ter segredo).
   - **Só informa:** não existe caminho da voz para `permissions.resolve`; "permite" vai ao modelo, que não tem ferramenta para isso. Teste confere.

6. **Fila e silêncio (`jarvis/proactive.py`).**
   - Uma fila de falas pendentes. A cada 1 s, fala a próxima se: não está pausado nem no silêncio; `brain.wake_paused()` é falso (não fala, não há turno nem atalho); a escuta não está colhendo um pedido (`wake.busy()`).
   - Fala que espera mais de 5 min é descartada.
   - A fala proativa passa pelo `speaker` e entra no histórico só quando é o lembrete (os outros avisos não pedem resposta).
   - `JARVIS_SILENCIO` (padrão `23:00-07:00`), `JARVIS_LEMBRETE_GASTOS` (padrão `21:30`; vazio desliga).
   - Estado em `~/Library/Application Support/Jarvis/proativo.json`, arquivo só do cérebro: `{"pausa_ate": ISO | null, "lembrete_em": "AAAA-MM-DD"}`. Gravado inteiro a cada mudança (arquivo temporário + `replace`).
   - **Lembrete:** a cada minuto, entre `JARVIS_LEMBRETE_GASTOS` e o começo do silêncio, se `lembrete_em` não é hoje, chama `painel`; com `hoje.lancamentos == 0` põe a pergunta na fila; marca `lembrete_em` só quando a pergunta é falada de fato (ou quando há gasto). Núcleo fora: tenta no minuto seguinte. Um Mac que acorda às 22:10 pergunta logo; às 23:05, não.

7. **Pausa: ferramenta local e botão.**
   - `silenciar_avisos(acao, minutos)`: `pausar` (minutos de 1 a 720) ou `pausar_ate_amanha` (até o fim do silêncio, 07:00) ou `retomar`. Sem confirmação: só controla a voz do próprio Jarvis.
   - O botão Silenciar manda `{"type": "local", "acao": "avisos_pausar_1h"}` (ou `avisos_retomar` quando já está pausado), pela lista fechada de `local_action`.
   - O painel recebe `avisos: {pausa_ate}` junto dos dados locais (`panel_extras`), e o botão vira "Avisos 15:40" enquanto pausado.

8. **Falas proativas e a música baixa.** Passam pelo mesmo `speaker`, que marca "falando"; o `Ducker` abaixa o Spotify sozinho.

## Risks / Trade-offs

- **[Aviso repetido ao reiniciar]** → `desde` começa na subida. Pode perder um aviso do minuto da reinicialização; o WhatsApp tem o aviso.
- **[WhatsApp falhou e o aviso não foi registrado]** → o Jarvis também não fala, porque `deliver` só registra depois de enviar. O próximo ciclo reenvia e aí ele fala.
- **[Chato demais]** → silêncio na madrugada, pausa, `espera` fora, `terminou` só para trabalho de 2 min ou mais, um aviso por terminal por minuto, lembrete uma vez por dia. O aceite mede um dia normal.
- **[Falar em reunião ou chamada]** → pausa por voz ou pelo botão.
- **["Boa noite" no meio de outra frase]** → só a frase exata dispara.
- **[Injeção pela voz para aprovar permissão]** → nenhuma ferramenta aprova; só o clique.
- **[Corrida no arquivo de estado]** → arquivo próprio do cérebro, um único processo escreve.

## Open Questions

- Nenhuma. Os horários padrão (21:30, 23:00 às 07:00) e o limite de 2 min do `terminou` podem mudar depois do aceite.
