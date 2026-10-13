## Context

- **Já existe (do `jarvis-proativo`, implementado em 13/10/2026, ainda em aceite):**
  - a fila de falas proativas e o silêncio (`jarvis/proactive.py`), com estado em `proativo.json`;
  - a janela de resposta sem o nome (`JarvisBrain._open_answer`): hoje só a negativa tem resposta fixa; o resto vai ao modelo;
  - `_say_fixed`: texto fixo na tela, na voz e no histórico;
  - `local_action` (botões do painel, lista fechada) e `avisos` nos dados locais do painel.
- **Já existe (do `jarvis-musica`):** `Spotify.search("minha_playlist", nome)` e `play`, com o erro de login tratado; `timer` com `display notification`.
- **Já existe:** `rodar_atalho` roda `shortcuts run <nome>` pelo `run_command` (limite de 20 s), só para nomes em `atalhos_permitidos` do `config.json`.
- **Fatos conferidos em 13/10/2026 neste Mac:**
  - `shortcuts list` está vazio: o Kaio ainda não tem nenhum atalho. O Foco depende dele criar dois.
  - `shortcuts run "nome-inexistente"` **não terminou em 2 minutos** (ficou preso, sem erro). Nunca chamar `run` sem antes conferir o nome em `shortcuts list`, e sempre com limite de tempo.
  - Não há `config.json` neste Mac (o Jarvis roda com os padrões). Por isso os nomes dos atalhos e da playlist vão no `.env`, que o Kaio já edita.
- **Fato de documentação de terceiros (13/10/2026):** o app Atalhos tem a ação "Definir Foco" (*Set Focus*), com a opção de ligar "até ser desativado" e a de desligar; `shortcuts run "<nome>"` roda qualquer atalho pelo Terminal ([heyfocus.com](https://heyfocus.com/blog/how-to-turn-on-mac-focus-mode-from-the-terminal/)). Há um relato da era do Monterey de que um Foco ligado por automação desligava ao trocar de app ([fórum do Keyboard Maestro](https://forum.keyboardmaestro.com/t/wanted-a-dnd-do-not-disturb-macro-that-works-with-monterey/25108)); o aceite confere se isso acontece aqui.
- **Fato do macOS:** com o Foco "Não Perturbe" ligado, as notificações (inclusive as do `timer`) ficam escondidas; a voz do Jarvis é áudio comum e não é afetada. Por isso o fim do bloco é falado, não notificado.

## Goals / Non-Goals

**Goals:**
- Um pedido monta tudo; o fim e a pausa são falados sem o modelo.
- O relógio é uma hora marcada e sobrevive a dormir e reiniciar; o Foco nunca fica ligado por acidente.
- O Jarvis nunca cria, altera ou roda atalho que não esteja configurado e listado.

**Non-Goals:** ver a proposta.

## Decisions

1. **O modo vive em `jarvis/study.py` (`StudyMode`), com o relógio no laço de 1 s do proativo.**
   - Estado: `fase` (`bloco` | `pausa` | `pergunta`), `ate` (ISO, hora marcada), `minutos`, `pausa`, `foco_ligado`. Gravado em `proativo.json` na chave `estudo` a cada mudança (o arquivo já é só do cérebro).
   - `Proactive.step()` chama `study.tick()` a cada segundo. Alternativa descartada: `asyncio.sleep(minutos*60)`, como o `timer`, que não sobrevive a dormir nem a reiniciar.
   - `tick()`: se `agora >= ate` e a fase é `bloco` ou `pausa`, decide: `agora - ate > 10 min` (o Mac dormiu além do fim) → encerra em silêncio; senão → faz a pergunta da fase. Na subida, o mesmo `tick()` retoma ou encerra o que estava gravado.

2. **Foco pelos atalhos, com três portas.**
   - Nomes em `JARVIS_FOCO_LIGAR` / `JARVIS_FOCO_DESLIGAR` (padrão "Jarvis Foco" / "Jarvis Foco Fim").
   - Antes de ligar: `shortcuts list` (limite 10 s) e o nome tem que estar na lista, exato. Senão, o modo segue sem Foco e a resposta diz "os atalhos do Foco não existem". Isso evita o `run` preso.
   - `shortcuts run <nome>` com limite de 10 s pelo `run_command` (que já tem 20 s). Falha ou timeout → `foco_ligado=False`, dito na resposta, modo segue.
   - Desligar: só se `foco_ligado` (não roda o atalho de desligar à toa). Ao encerrar por qualquer caminho (pedido, "não", silêncio, Mac dormiu, reinício depois da hora), o desligar roda.
   - Alternativa descartada: ligar o Foco por `defaults`/AppleScript: não há caminho oficial desde o Monterey; o app Atalhos é o único documentado.
   - O Jarvis não passa pela lista `atalhos_permitidos`: esses dois nomes são configuração própria e o modelo não escolhe o nome (a ferramenta `modo_estudo` não recebe nome de atalho).

3. **Playlist pelo Spotify do `jarvis-musica`.**
   - `JARVIS_PLAYLIST_ESTUDO` (padrão "estudo") é buscada com `search("minha_playlist", nome)` e tocada com `play`. `SpotifyError` de login ou nada encontrado → sem música, dito na resposta, modo segue.
   - A música não é tocada de novo na pausa nem no novo bloco (continua o que estiver tocando), e não é parada ao encerrar: "para a música" é outro pedido.

4. **Silêncio dos avisos: `Proactive.hold("estudo", on)`.**
   - Um conjunto de motivos de retenção, como o `Ducker`. Com um motivo ativo, `_put` descarta (os avisos não esperam o fim do modo: perderiam o sentido, e o WhatsApp os tem) e `tick` não fala.
   - As falas do próprio modo não passam pela fila: usam `brain.study_prompt` (abaixo), que fala mesmo com os avisos pausados ou no horário de silêncio. O Kaio pediu o modo; a pergunta é parte dele.
   - O botão Silenciar mostra "Estudo" enquanto o modo dura (`avisos.pausa_ate` continua o que era; o painel decide pelo `estudo`).

5. **As perguntas usam a janela de resposta do `jarvis-proativo`, generalizada.**
   - `_open_answer(no_reply, *, yes_reply=None, on_yes=None, on_no=None, timeout=120)`: uma afirmativa normalizada ("sim", "pode", "claro", "bora", "isso", "pode ser", "quero") responde `yes_reply` e chama `on_yes`; a negativa, `no_reply` e `on_no`; o resto vai ao modelo, como hoje. Sem resposta até `timeout`, `on_timeout` (encerrar o modo). O fechamento do dia e o lembrete de gastos continuam usando só a negativa.
   - `brain.study_prompt(rid, text, ...)`: `_say_fixed` com `user` sintético "[modo estudo]" (histórico alternado) e `_open_answer`. Pela palavra, o `WakeService.expect_answer` do proativo já põe a escuta esperando a resposta sem o nome.
   - Textos: "Senhor, acabaram os N minutos de estudo. Pausa de M minutos?" / "Senhor, a pausa acabou. Mais N minutos?" / respostas "Pausa de M minutos, senhor." / "Mais N minutos, senhor." / "Perfeito, senhor. Modo estudo encerrado.". Com `pausa=0`, o fim do bloco pergunta direto "Mais N minutos?".

6. **Ferramenta `modo_estudo(acao, minutos, pausa)`.**
   - `acao`: `iniciar` (minutos 1–240, padrão `JARVIS_ESTUDO_MINUTOS`=50; pausa 0–60, padrão `JARVIS_ESTUDO_PAUSA`=10), `parar`, `status`.
   - Devolve `{fase, ate, minutos, pausa, foco, musica, avisos}` para o modelo dizer o que ligou. `iniciar` com modo em andamento substitui (sem pergunta: o Kaio acabou de pedir).
   - Sem confirmação: só mexe em Foco, música e na voz do próprio Jarvis (requisito "Ações permitidas").

7. **Painel.**
   - Dados locais: `estudo: {fase, ate, minutos, pausa} | null` junto de `avisos`.
   - Botão `hud-mode--f` (esquerda, 40%, espelho do Silenciar): "Estudo" → `local_action("estudo_iniciar")` (padrões, sem o modelo, resposta fixa "Modo estudo até as HH:MM, senhor." falada); rodando → "Estudo 37 min" / "Pausa 8 min", clique → `local_action("estudo_parar")`. O painel recalcula o rótulo pelo relógio local a cada segundo (`useNow`), sem consultar o cérebro; `on_change` do proativo manda o painel de novo nas mudanças de fase.
   - Estado do painel: "estudo · faltam 37 min" / "pausa · faltam 8 min".

8. **Ordem de ligar e o que a resposta diz.** Foco → música → silêncio, porque o Foco é o que mais demora (até 10 s) e a música confirma na hora que algo aconteceu. A resposta fixa do botão e o resultado da ferramenta listam o que ligou e o que não ligou, para o modelo não inventar.

## Risks / Trade-offs

- **[`shortcuts run` preso]** → nome conferido em `shortcuts list` antes, limite de 10 s, e o modo nunca depende do Foco para começar.
- **[Foco fica ligado depois de um crash]** → `foco_ligado` no `proativo.json`; na subida, estado expirado ou inválido → roda o desligar e limpa.
- **[Foco desliga ao trocar de app (relato do Monterey)]** → o aceite confere; se acontecer, a mitigação é religar a cada minuto durante o bloco (fica anotado, não construído).
- **[Avisos perdidos durante o estudo]** → por desenho: o WhatsApp os tem; o resumo do dia e o fechamento continuam mostrando compromissos e faturas.
- **[Pergunta não ouvida]** → sem resposta em 2 min o modo encerra e o Foco desliga: o estado seguro é "notificações de volta".
- **[Mac dormiu e acordou 5 min depois do fim]** → pergunta mesmo assim (até 10 min de atraso); além disso, encerra em silêncio.
- **[Dois pedidos de estudo seguidos]** → o segundo substitui o primeiro; o Foco não é religado se já estava ligado.

## Open Questions

- Nenhuma. Os padrões (50/10, nomes dos atalhos e da playlist) ficam no `.env` e podem mudar depois do aceite.
