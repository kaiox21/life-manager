## Context

Ver `proposal.md` (Why). O que já existe e é reaproveitado:

- `Folders` (`jarvis/sessions.py`): raízes permitidas (`JARVIS_PASTAS`; padrão `~/Projetos pessoais`, `~/AmicusIA`, `~/Faculdade`), até 2 níveis abaixo, e `resolve(nome)` que devolve `pasta`, `opcoes` ou `erro`. Hoje o casamento é só por nome exato sem distinção de maiúsculas: "NC Barber" não acha `NC-BARBER`.
- `Control.open(pasta, claude)` (`jarvis/control.py`): abre uma sessão tmux na pasta, aba no painel, limites de memória e de Claude Code; `Terminals` sabe pasta, tipo e se o shell está livre.
- `area_transferencia(escrever)` usa `pbcopy` sem confirmação; `cards.py` converte resultados em cartões tipados e a interface só desenha; botões do painel mandam `{"type": "local", "acao": ...}` ao cérebro.
- O cérebro roda pelo launchd com PATH mínimo: ferramentas de linha de comando do VS Code (`code`) não são garantidas.

## Goals / Non-Goals

**Goals:**
- Dois pedidos de uma frase, sem confirmação, sem comando novo rodando em shell.
- O rascunho nunca sai do Mac e nunca é lido em voz alta.

**Non-Goals:**
- `mailto:`/abrir o Mail preenchido, consulta de rascunhos antigos por voz, outro editor além do configurado (ver proposal).

## Decisions

- **Casamento de nomes no `Folders`.** `resolve` passa a comparar nomes normalizados: minúsculas, sem acentos (NFKD), sem espaços, hífens e sublinhados. Vale também para `abrir_terminal`, que fica mais tolerante sem mudar de requisito. Alternativa descartada: um `config/projetos.yaml` com apelidos; é mais um arquivo para manter e o problema real era a grafia, não o apelido.
- **Editor por `open -a`.** `open -a "<JARVIS_EDITOR>" <pasta>` (padrão `Visual Studio Code`) funciona sem PATH e sem a ferramenta `code`; se o app não existir, `open` falha e a ferramenta devolve `editor: "não encontrei o app …"` e segue com o terminal. Fato conferido em 15/10/2026 neste Mac: `/Applications/Visual Studio Code.app` existe e `code` está em `/opt/homebrew/bin` (não usado).
- **Terminal: reaproveitar antes de abrir.** Se `Terminals` tem um terminal de shell livre cuja pasta é a resolvida, `abrir_projeto` abre a aba dele (`open_tab`) em vez de criar outro; senão chama `Control.open(pasta, claude)`. Com `claude=true` sempre abre um novo (um Claude Code na pasta é o que foi pedido). Nenhum comando é enviado ao shell.
- **`rascunho` é a ferramenta; o modelo escreve o texto.** Argumentos: `tipo` (`email` | `mensagem` | `texto`), `para` (opcional, até 120), `assunto` (opcional, até 200), `texto` (1 a 6.000; limite próprio, maior que os 2.000 da `area_transferencia`). A ferramenta: `pbcopy` do corpo; grava `~/Library/Application Support/Jarvis/rascunhos/AAAA-MM-DD-HHMM-<slug>.md` (cabeçalho com tipo, para e assunto; mantém os 50 mais novos); devolve `{status: "pronto", tipo, para, assunto, caracteres, arquivo}`. O cartão `rascunho` leva o texto completo. Alternativa descartada: uma segunda chamada ao modelo só para redigir; dobraria custo e latência sem ganho.
- **Regras no prompt da persona.** Uma regra nova: o texto do rascunho é do Kaio (primeira pessoa, pt-BR, assinatura "Kaio", sem "senhor" nem menção ao Jarvis), vai inteiro em `texto`, e a fala é só uma frase dizendo que está pronto. `STEP_LABELS`: `abrir_projeto` → "abrindo o projeto…", `rascunho` → "escrevendo o rascunho…".
- **Botão Copiar.** O evento local ganha um campo opcional `texto` (até 6.000): `{"type": "local", "acao": "rascunho_copiar", "texto": …}` → `pbcopy`. Alternativa descartada: `navigator.clipboard` na interface; manter a escrita na área de transferência num único lugar (o cérebro) e sem depender de permissão do webview.
- **Nunca envia.** Não há ferramenta de envio no Jarvis nem no MCP do núcleo (o envio do núcleo só vai para o próprio dono, pelo WhatsApp, e não é exposto). A regra entra na spec e no prompt para a resposta a "manda esse e-mail" ser direta.
- **Verificação com o modelo real antes do aceite** (como no modo estudo): 4 pedidos de escolha de ferramenta e 1 rascunho para olhar persona e assinatura. Custo estimado US$ 0,002; avisar antes de rodar.

## Risks / Trade-offs

- [Nome ambíguo depois da normalização] → `opcoes` vira pergunta; nada abre sozinho.
- [Rascunho com a voz do mordomo] → regra no prompt + checagem real; se escapar, ajustar a regra, não o código.
- [Área de transferência sobrescrita antes de colar] → o cartão e o arquivo guardam o texto; botão Copiar.
- [Texto do pedido com instruções embutidas] → o rascunho é texto produzido pelo modelo e só vai para clipboard, cartão e arquivo; nenhuma ação deriva do conteúdo.
- [Editor abre numa janela nova a cada pedido] → `open -a` reaproveita a instância do VS Code e abre a pasta numa janela; aceitável.
