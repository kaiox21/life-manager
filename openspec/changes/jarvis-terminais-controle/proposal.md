## Why

O `jarvis-terminais` só **avisa**. Quando uma sessão do Claude Code pede permissão, o Kaio ainda precisa achar a janela certa e responder lá. Ele quer **controlar os terminais** de dentro do Jarvis: vê-los, digitar neles, aprovar ou negar pedidos, mandar recados e comandos por voz e abrir ou fechar terminais (pedido de 09/10/2026).

Depois de ver a primeira versão, o Kaio ampliou o pedido no mesmo dia:
- as abas podem ser **só um terminal** (shell), não apenas o Claude Code;
- os terminais abertos **no Terminal.app** também devem aparecer e ser controláveis no Jarvis.

O `jarvis-terminais` deixou "responder à permissão" para "um change seguinte, com desenho próprio", e este é esse change.

## What Changes

- **Terminais compartilhados (tmux).** Cada terminal passa a ser uma sessão de um tmux só do Jarvis. O Terminal.app e o Jarvis se conectam à mesma sessão ao mesmo tempo, e o Kaio vê e digita nos dois. Nada se perde ao reiniciar o Jarvis.
- **Toda janela nova do Terminal.app entra no tmux** e aparece no Jarvis como "Terminal N".
  - Funciona por um bloco no `~/.zshrc`, instalado pelo `install_mac.sh` com backup e removível.
  - O VS Code fica de fora, e também quem definir `JARVIS_SEM_TMUX=1`.
  - Fechar a janela encerra a sessão, como hoje, a não ser que ela esteja aberta numa aba do Jarvis.
- **Abas no painel.** Qualquer terminal pode ser aberto numa aba: terminal real, mesma tela, digitação direta.
  - Com o foco numa aba, o Esc vai para o terminal, e o painel fecha com ⌥⇧Espaço.
- **Abrir e fechar** pelo "+" do painel, por texto ou por voz:
  - "abre um terminal no life-manager" abre um shell;
  - "abre um Claude Code no life-manager" abre o shell e já roda o `claude`;
  - só abre em pastas de uma lista permitida;
  - fechar um terminal com algo rodando pede confirmação.
- **Aprovar ou negar pelo Jarvis.** Quando um Claude Code rodando num terminal do Jarvis pede permissão, o aviso no HUD e no painel ganha os botões **Permitir** e **Negar**. Isso vale também para os terminais abertos no Terminal.app.
  - O diálogo continua no terminal, e vale o que for respondido primeiro.
  - A aprovação **só** sai de um clique do Kaio. Nunca do modelo, nunca da voz.
- **Mandar pelo Jarvis**, por texto ou voz. Para o Claude Code vai como **mensagem**: "Terminal 2, roda os testes". Para um shell vai como **comando** de uma linha: "Terminal 3, roda npm test".
  - Sempre aparece um cartão com o destino e o texto exato.
  - Só envia depois de o Kaio confirmar.
- **Limite de memória.** O Jarvis recusa abrir um terminal novo quando o Mac está com pouca memória livre, e no máximo 4 Claude Code abertos por ele ao mesmo tempo.
- **BREAKING (comportamento):**
  - todo terminal novo do Terminal.app roda dentro do tmux (rolagem pelo tmux; para selecionar texto, Option + arrastar);
  - no painel, o Esc não fecha mais quando o foco está numa aba de terminal.

## Non-goals

- Terminais abertos **antes** da instalação, terminais do VS Code e de outros apps. Esses ficam só com os avisos do `jarvis-terminais`.
- Mandar ao modelo do Jarvis o conteúdo da tela de um terminal. "O que o Terminal 2 está fazendo?" responde com o estado; o conteúdo fica só na tela.
- Abrir o Claude Code pelo Jarvis com as permissões desligadas (`--dangerously-skip-permissions`).
- Comandos de várias linhas ou com teclas de controle mandados pelo Jarvis.
- Sobreviver a um reinício do Mac. O tmux também fecha.

## Capabilities

### New Capabilities
<!-- nenhuma: os requisitos entram na capacidade `jarvis-terminais`, criada pelo change jarvis-terminais (arquivado antes deste) -->

### Modified Capabilities
- `jarvis-terminais`:
  - terminais compartilhados no tmux, inclusive os do Terminal.app;
  - abas no painel;
  - abrir shell ou Claude Code, e fechar;
  - aprovar e negar pelo Jarvis;
  - mandar mensagens e comandos com confirmação;
  - limite;
  - sobrevivência ao reinício.
  - O requisito "Aviso de permissão" deixa de proibir aprovar e negar.
- `ferramentas-locais`: "Sem shell livre" ganha uma exceção explícita. As ferramentas de terminal podem mandar uma mensagem ao Claude Code ou um comando de uma linha a um shell de um terminal do Jarvis, sempre com a confirmação do Kaio.
- `jarvis-painel`: o Esc não fecha o painel quando o foco está numa aba de terminal.

## Impact

- **Dependência nova no Mac:** tmux (Homebrew, 3.8), com configuração própria em `~/Library/Application Support/Jarvis/tmux.conf` e socket `jarvis`.
- **Instalação:** o `install_mac.sh` instala a configuração do tmux, o bloco do `~/.zshrc` (com backup; `--sem-tmux` remove) e um hook global `PermissionRequest` que só age nos terminais do tmux do Jarvis. O hook de anotação do `jarvis-terminais` passa a anotar também o painel do tmux.
- **Cérebro (Python):**
  - lê as sessões do tmux;
  - abre a aba como um pty rodando `tmux attach`;
  - recebe os pedidos de permissão num endereço local;
  - ganha as ferramentas `abrir_terminal`, `mandar_terminal` e `fechar_terminal`.
- **Interface:** abas com `@xterm/xterm` no painel (dependência nova) e botões Permitir e Negar no aviso.
- **Dependência de change:** o `jarvis-terminais` precisa estar aceito e arquivado antes. Ele está com commit local (83d392a), sem aceite.
- **`SPEC.md` e `CLAUDE.md`:**
  - registram a decisão "o Jarvis escreve em terminais e pode rodar comandos de shell com confirmação". Ela muda a regra "nenhuma ferramenta executa shell";
  - registram o tmux em todos os terminais novos e o limite de memória;
  - fecham a questão "Sessões do Claude Code no Jarvis".
