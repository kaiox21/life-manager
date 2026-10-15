## Context

Ver `proposal.md` (Why). O que já existe e é reaproveitado:

- `Folders` (`jarvis/sessions.py`): raízes permitidas (`JARVIS_PASTAS`; padrão `~/Projetos pessoais`, `~/AmicusIA`, `~/Faculdade`), até 2 níveis abaixo, e `resolve(nome)` que devolve `pasta`, `opcoes` ou `erro`. Hoje o casamento é só por nome exato sem distinção de maiúsculas: "NC Barber" não acha `NC-BARBER`.
- `Control.open(pasta, claude)` (`jarvis/control.py`): abre uma sessão tmux na pasta, aba no painel, limites de memória e de Claude Code; `Terminals` sabe pasta, tipo e se o shell está livre; `open_tab(sessao)` marca a aba sem criar terminal.
- `area_transferencia(escrever)` usa `pbcopy` sem confirmação; `cards.py` converte resultados em cartões tipados e a interface só desenha; botões do painel mandam `{"type": "local", "acao": ...}` ao cérebro.
- O cérebro roda pelo launchd com PATH mínimo: ferramentas de linha de comando do VS Code (`code`) não são garantidas.

Fatos conferidos no código em 15/10/2026 (análise crítica):
- O painel é uma janela `alwaysOnTop: true` (`jarvis-ui/src-tauri/tauri.conf.json`) em tela cheia simples (`lib.rs`): um app aberto por trás não fica visível. Não existe evento do cérebro para fechar o painel.
- O evento `terminal_opened` só é consumido pela promessa do botão "+" (`useJarvis.ts`); quando o modelo abre um terminal, a aba aparece pelo evento `terminals`, mas a vista não muda.
- `_run_loop` (`jarvis/agent.py`) sempre volta ao modelo depois de rodar as ferramentas; não há como encerrar o turno com texto fixo a partir de uma ferramenta.
- O adaptador da Anthropic usa `max_tokens` 4.096 por padrão (`app/agent/llm.py`): o rascunho de 6.000 caracteres (~2.000 tokens) cabe com folga.
- `/Applications/Visual Studio Code.app` existe; `code` está em `/opt/homebrew/bin` (não usado).

## Goals / Non-Goals

**Goals:**
- Dois pedidos de uma frase, sem confirmação, sem comando novo rodando em shell.
- O rascunho nunca sai do Mac, nunca é lido em voz alta e nunca vai para o log.

**Non-Goals:**
- `mailto:`/abrir o Mail preenchido, consulta de rascunhos antigos por voz, outro editor além do configurado (ver proposal).

## Decisions

- **Casamento de nomes no `Folders`.** `resolve` passa a comparar nomes normalizados: minúsculas, sem acentos (NFKD), sem espaços, hífens e sublinhados. Vale também para `abrir_terminal`, que fica mais tolerante sem mudar de requisito. Alternativa descartada: um `config/projetos.yaml` com apelidos; é mais um arquivo para manter e o problema real era a grafia, não o apelido.
- **Editor por `open -a`.** `open -a "<JARVIS_EDITOR>" <pasta>` (padrão `Visual Studio Code`) funciona sem PATH e sem a ferramenta `code`; se o app não existir, `open` falha e a ferramenta devolve `editor: "não encontrei o app …"` e segue com o terminal.
- **Terminal: reaproveitar antes de abrir.** Se `Terminals` tem um terminal de shell livre cuja pasta é a resolvida, `abrir_projeto` chama `open_tab` nele (a aba fica aberta) em vez de criar outro; senão chama `Control.open(pasta, claude)`. Com `claude=true` sempre abre um novo (um Claude Code na pasta é o que foi pedido). Nenhum comando é enviado ao shell. Não há troca de aba na interface: o editor vem para a frente e o painel fecha.
- **Painel fecha ao abrir projeto.** Evento novo `panel_close` em `jarvis/events.py`, emitido pelo cérebro depois de `abrir_projeto` com sucesso; a interface trata como o Esc (mesma rotina que fecha o painel hoje). Alternativa descartada: a interface reagir ao cartão "Projeto"; cartões são só desenho.
- **Turno encerrado com fala fixa.** `abrir_projeto` e `rascunho` devolvem, além do resultado, um campo `_fala` (texto fixo). Em `_run_loop`, quando a rodada teve uma única chamada e o resultado trouxe `_fala`, o cérebro não chama o modelo de novo: o texto vira a resposta do turno (falado e no painel) e entra no histórico como mensagem do assistente, para manter a alternância de papéis. `for_model` nunca manda `_fala` nem o texto do rascunho de volta ao modelo. Frases: "Rascunho pronto no painel e na área de transferência, senhor."; "<pasta> aberto no <editor>, senhor. Terminal <n>." e, sem editor, "<pasta> aberto no Terminal <n>, senhor. Não encontrei o <editor>." Alternativa descartada: regra de prompt "não leia o texto"; o modelo teria o e-mail no contexto e a garantia seria fraca; a fala fixa ainda economiza uma chamada (~1,5 s).
- **`rascunho` é a ferramenta; o modelo escreve o texto.** Argumentos: `tipo` (`email` | `mensagem` | `texto`), `para` (opcional, até 120), `assunto` (opcional, até 200), `texto` (1 a 6.000; limite próprio, maior que os 2.000 da `area_transferencia`). A ferramenta: `pbcopy` do corpo; grava `~/Library/Application Support/Jarvis/rascunhos/AAAA-MM-DD-HHMM-<slug>.md` (cabeçalho com tipo, para e assunto; mantém os 50 mais novos); devolve `{status: "pronto", tipo, para, assunto, caracteres, arquivo, _fala}`. O cartão `rascunho` leva o texto completo. Alternativa descartada: uma segunda chamada ao modelo só para redigir; dobraria custo e latência sem ganho.
- **Texto fora do log.** O log de chamadas de ferramenta (`_run_call`) registra os argumentos de `rascunho` com `texto` trocado por `<N caracteres>`; a ferramenta loga tipo, destinatário e tamanho. Teste com `caplog`.
- **Regras no prompt da persona.** Uma regra nova: o texto do rascunho é do Kaio (primeira pessoa, pt-BR, assinatura "Kaio", sem "senhor" nem menção ao Jarvis) e vai inteiro em `texto`; o Jarvis nunca envia nada e nunca propõe terminal ou app para enviar um rascunho ("manda esse e-mail" → não envia, o texto está na área de transferência). `STEP_LABELS`: `abrir_projeto` → "abrindo o projeto…", `rascunho` → "escrevendo o rascunho…".
- **Botão Copiar.** O evento local ganha um campo opcional `texto` (até 6.000): `{"type": "local", "acao": "rascunho_copiar", "texto": …}` → `pbcopy`. Alternativa descartada: `navigator.clipboard` na interface; manter a escrita na área de transferência num único lugar (o cérebro) e sem depender de permissão do webview.
- **Nunca envia.** Não há ferramenta de envio no Jarvis nem no MCP do núcleo (o envio do núcleo só vai para o próprio dono, pelo WhatsApp, e não é exposto). O caminho residual é `mandar_terminal` com um comando de e-mail: já exige o clique do Kaio no cartão, e a regra do prompt proíbe propor.
- **Verificação com o modelo real antes do aceite** (como no modo estudo): 4 pedidos de escolha de ferramenta, 1 rascunho para olhar persona e assinatura, e "manda esse e-mail" para ver a recusa. Custo estimado US$ 0,002; avisar antes de rodar.
  Resultado (15/10/2026, `claude-haiku-5-5`, US$ 0,0009): 5 de 5. "Jarvis, abre o NC Barber" → `abrir_projeto(nome="NC Barber")`; "abre o life-manager com um Claude Code" → `claude=true`; o e-mail para o professor veio com `tipo=email`, assunto "Pedido de prova de segunda chamada", texto em primeira pessoa, formal, assinado "Kaio", sem "senhor"; a mensagem para o Netto veio como `tipo=mensagem`, sem assunto, informal e assinada; "manda esse e-mail" não chamou ferramenta e respondeu "Não envio e-mails, senhor. O texto está na área de transferência; basta colá-lo no seu cliente de e-mail e enviar."

## Risks / Trade-offs

- [Nome ambíguo depois da normalização] → `opcoes` vira pergunta; nada abre sozinho.
- [Rascunho com a voz do mordomo] → regra no prompt + checagem real; se escapar, ajustar a regra, não o código.
- [Área de transferência sobrescrita antes de colar] → o cartão e o arquivo guardam o texto; botão Copiar.
- [Texto do pedido com instruções embutidas] → o rascunho é texto produzido pelo modelo e só vai para clipboard, cartão e arquivo; nenhuma ação deriva do conteúdo.
- [Fala fixa perde o humor do Jarvis nessas duas respostas] → aceito pelo Kaio em 15/10/2026, em troca da garantia e da velocidade.
- [Painel fecha num pedido digitado nele] → é o comportamento pedido; a frase ainda é falada e o cartão fica no histórico da conversa.
- [Editor abre numa janela nova a cada pedido] → `open -a` reaproveita a instância do VS Code e abre a pasta numa janela; aceitável.
