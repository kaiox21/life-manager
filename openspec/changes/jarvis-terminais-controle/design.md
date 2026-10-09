## Context

Motivação: ver `proposal.md`. Este change parte do `jarvis-terminais`, que já tem hooks globais que só anotam eventos, terminais numerados pelo pid do `claude`, aviso no HUD sem foco e coluna no painel. O cérebro (Python, sob launchd) e a interface (Tauri 2 + React) conversam por um WebSocket local com token. O WebSocket já leva quadros binários, hoje o áudio da voz.

**Histórico deste change:**
- A 1ª versão (aprovada e implementada em 09/10/2026) abria o `claude` num pty do próprio cérebro.
- O Kaio testou e ampliou o pedido: abas também de shell, e os terminais do Terminal.app disponíveis no Jarvis.
- O macOS não deixa um programa entrar num terminal aberto por outro: a tela e o teclado de uma janela do Terminal.app são só dele. A solução é o **tmux**, aprovado pelo Kaio em 09/10/2026, junto com "todas as janelas novas" e "comandos de shell com confirmação".

### Fatos conferidos (09/10/2026, Claude Code 2.1.296, tmux 3.8)

**Na documentação oficial:**

- **Hook `PermissionRequest`** (code.claude.com/docs/en/hooks):
  - Saída: `{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"|"deny", "message"?, …}}}`.
  - Regras de deny e ask continuam valendo por cima de um allow.
  - Tempo limite padrão de 600 s. Estourado o tempo, o hook não decide nada.
  - Código de saída diferente de 0 (exceto 2) não bloqueia, e o código 2 não vale para este evento.
- **Configuração:**
  - Hooks de vários níveis de configuração se somam.
  - O processo do hook herda o ambiente do `claude`.
  - Mudanças no `settings.json` valem nas sessões já abertas.
  - Os hooks ficam suspensos até o Kaio aceitar a pergunta de confiança da pasta.
- **Claude Code no tmux** (code.claude.com/docs/en/terminal-config, "Configure tmux"):
  - pede `set -g allow-passthrough on`, `set -s extended-keys on` e `set -as terminal-features 'xterm*:extkeys'`, para Shift+Enter e notificações;
  - o Ctrl+B do Claude Code (mandar tarefa para o fundo) exige apertar duas vezes no tmux, porque é o prefixo padrão.
- **Modos de permissão** (code.claude.com/docs/en/permission-modes):
  - Desde a 2.1.283, o **auto mode** é o modo inicial, e as sessões do Kaio abrem nele.
  - Ainda viram diálogo:
    - regras `ask`;
    - remoções em caminhos críticos, com contagem de 2 min;
    - o recuo depois de 3 bloqueios seguidos ou 20 no total.
- **Remote Control** é o jeito oficial de aprovar pelo app do Claude. Não existe API local para escrever numa sessão de outro terminal.
- **Transcrição** (`~/.claude/projects/…jsonl`): sem esquema documentado. Não é usada.
- **Tauri 2:** eventos não servem para fluxo grande. Aqui não se aplica, porque a saída vai do cérebro ao webview pelo WebSocket.
- **Bibliotecas** (crates.io, npm e GitHub):
  - `@xterm/xterm` 6.0.0 e `@xterm/addon-fit` 0.11.0, de 12/2025, ativos;
  - `tauri-plugin-pty` 0.3.1 está em "Developing!".

**Na prática** (scratchpad, Haiku, centavos):

1. **Pty:**
   - o `claude` roda num pty da biblioteca padrão; teclas e "colar" (bracketed paste) funcionam;
   - com o PATH mínimo do launchd, os hooks dos plugins do Kaio (que chamam `node`) quebram e escrevem erro na conversa, e com o shell de login ficam limpos;
   - aberto por `zsh -l -i -c 'exec …'`, o filho do pty é o próprio processo.
2. **Pasta nova:** o `claude` mostra a pergunta de confiança com **"No, exit" marcado**, e o diálogo só aceita teclas depois de montado (~2 s).
3. **Hook de permissão:**
   - do tipo `command` e do tipo `http`: `allow` roda o comando, `deny` não roda e a mensagem chega, resposta vazia deixa o diálogo seguir;
   - o diálogo aparece **na tela enquanto o hook ainda espera**, e vale a primeira resposta;
   - respondido na tela, o Claude Code não mata o hook nem fecha a requisição.
4. **Bug da 1ª versão:**
   - o `claude` pergunta ao terminal (`CSI c`, `CSI ? u`, `OSC 7501`) ao abrir;
   - reproduzir a tela guardada fazia o xterm responder de novo, e a resposta, que começa com Esc, chegava como tecla: na pergunta de confiança, Esc = sair;
   - as sessões do Kaio fecharam sozinhas em 1 a 9 s.
5. **tmux** (socket isolado, configuração acima mais `escape-time 10` e `window-size latest`):
   - dois clientes (dois ptys) na mesma sessão veem e digitam nos dois sentidos;
   - a janela segue o tamanho do cliente usado por último;
   - a sessão continua quando um cliente sai;
   - `destroy-unattached on` ligado **depois** de o cliente conectar destrói a sessão ao fechar a janela, e ligado antes destrói na hora;
   - `send-keys -l '<cmd>'` + `Enter` roda o comando no shell;
   - `load-buffer` + `paste-buffer -p` entrega uma mensagem ao `claude` como colagem;
   - dentro do tmux, o hook do Claude Code recebe `TMUX` (com o caminho do socket, por exemplo `/private/tmp/tmux-501/jarvis,…`) e `TMUX_PANE` (`%1`);
   - `pane_current_command` mostra "2.1.296" para o `claude` (o nome do binário versionado). Não serve para saber se um terminal roda o Claude Code.
6. **Memória** às 18h:
   - 16 GB de RAM; swap de 9,25 de 10 GB; `kern.memorystatus_level` = 43;
   - cada `claude` usa de 150 a 300 MB;
   - o tmux e cada shell usam poucos MB.

## Goals / Non-Goals

**Goals:**
- A aba se comporta como o Terminal.app.
- Um terminal pode ser usado no Terminal.app e no Jarvis ao mesmo tempo.
- Permitir ou Negar chega à sessão em menos de 300 ms.
- Nenhuma aprovação nem comando sai do modelo sem clique do Kaio.
- Com o Jarvis caído, nenhum pedido fica travado.
- Os terminais sobrevivem ao reinício do Jarvis.

**Non-Goals** (de desenho):
- multiplexador próprio;
- ler a transcrição;
- emulador de terminal no cérebro.

## Decisions

1. **Change revisado, não novo.** O objetivo é o mesmo (controlar terminais pelo Jarvis), só ampliado. O código da 1ª versão é aproveitado:
   - pedidos pendentes e servidor HTTP;
   - pastas permitidas;
   - abas, `TerminalView` e `AlertBar`.

   Ordem: aceitar e arquivar o `jarvis-terminais` e só então arquivar este.

2. **Terminal = sessão de um tmux só do Jarvis.**
   - Socket `-L jarvis` e configuração `~/Library/Application Support/Jarvis/tmux.conf`, instalada pelo `install_mac.sh`. O tmux pessoal do Kaio (`~/.tmux.conf`), se um dia existir, não é tocado.
   - Configuração:
     - as três linhas oficiais do Claude Code;
     - `escape-time 10`, porque o Esc do Claude Code não pode atrasar meio segundo;
     - `window-size latest`;
     - `mouse on`, para rolar com o mouse; para selecionar texto nativo no Terminal.app, Option + arrastar;
     - `history-limit 50000`;
     - `status off`, para parecer um terminal comum;
     - prefixo **Ctrl+]**, no lugar do Ctrl+B, que o Claude Code usa.
   - Alternativa descartada: espelhar a janela do Terminal.app (AppleScript ou Accessibility). Só lê texto, não digita de forma confiável e quebra a cada versão.

3. **Terminal.app entra no tmux pelo `~/.zshrc`.**
   - O `install_mac.sh` acrescenta um bloco marcado (`# >>> jarvis tmux >>>` … `# <<< jarvis tmux <<<`), com backup em `~/.zshrc.bak-jarvis`.
   - O bloco só age se:
     - `TERM_PROGRAM` = `Apple_Terminal`;
     - o shell é interativo;
     - `TMUX` está vazio;
     - `JARVIS_SEM_TMUX` está vazio;
     - `tmux -V` funciona.
   - Faz `exec tmux -L jarvis -f <conf> new-session -c "$PWD" \; set-option destroy-unattached on`. A opção vai **depois** de conectar (fato 5): fechar a janela encerra a sessão, como hoje.
   - Se o `tmux` falhar, o `exec` não acontece e a janela fica num shell normal.
   - `--sem-tmux` remove só o bloco.

4. **Terminais abertos pelo Jarvis.**
   - Comando: `tmux -L jarvis new-session -d -c <pasta> -x 120 -y 32`, sem `destroy-unattached`, porque eles vivem até o Kaio fechar.
   - "Claude Code": manda `claude` + Enter para o shell da sessão. Quando o `claude` sai, sobra o shell, como no Terminal.app. O Jarvis nunca passa `--dangerously-skip-permissions`.
   - Pastas permitidas: como na 1ª versão (`JARVIS_PASTAS`, raízes + 2 níveis, `realpath`).
   - Limite:
     - `kern.memorystatus_level` < `JARVIS_TERMINAIS_MEM_MIN` (20) recusa qualquer terminal novo;
     - no máximo `JARVIS_TERMINAIS_MAX` (4) Claude Code abertos pelo Jarvis rodando ao mesmo tempo.

5. **A aba é um cliente do tmux.**
   - O cérebro abre um pty rodando `tmux -L jarvis attach -t <sessão>` (com `TERM=xterm-256color`) quando uma interface anexa a aba (`term_attach`), e o fecha quando ela desanexa.
   - O tmux redesenha a tela inteira ao conectar. Por isso **não há buffer guardado nem reprodução**, e o bug do fato 4 some por construção. O xterm responde ao vivo às perguntas do tmux, como faria o Terminal.app.
   - Sem aba aberta, não existe cliente nem tráfego.
   - Controle de fluxo como antes: a interface pausa acima de 500 KB pendentes.
   - Teclas da aba: `term_input` vai cru para o pty do cliente, porque é o Kaio digitando.

6. **Lista e numeração.**
   - A cada 1 s, o cérebro roda `tmux -L jarvis list-panes -a -F '#{session_id}|#{pane_id}|#{pane_pid}|#{pane_current_path}|#{pane_current_command}|#{session_attached}'`. Os comandos são fixos, sem shell.
   - Terminal compartilhado = sessão do tmux, com a chave `tmux:<session_id>`. Recebe o menor número livre na mesma numeração do `jarvis-terminais`. Sessões do Claude Code de fora do tmux continuam numeradas pelo pid.
   - O hook de anotação passa a gravar `painel` (`TMUX_PANE`) e `socket` (o nome do socket, tirado de `TMUX`). Um evento de um painel do socket `jarvis` vai para o terminal daquela sessão, e o terminal vira "Claude Code" de `SessionStart` até `SessionEnd`. Não se usa `pane_current_command` (fato 5).
   - "Algo rodando" no shell = `pane_current_command` diferente de `zsh`, `bash`, `sh` e `-zsh`. No Claude Code, o estado é trabalhando ou pedindo permissão.
   - O `tmux` ausente ou sem servidor equivale a uma lista vazia. O `jarvis-terminais` segue como antes.

7. **Aprovar e negar: hook global de comando, só nos terminais compartilhados.**
   - O `install_mac.sh` acrescenta ao `~/.claude/settings.json` uma entrada `PermissionRequest` **síncrona** (sem `async`, `timeout: 600`): `/usr/bin/python3 "<…>/hooks/claude_permission.py" 2>/dev/null || true`.
   - O script (biblioteca padrão):
     - sai na hora, sem imprimir nada, se `TMUX` não for do socket `jarvis`;
     - senão lê `session.json` (porta do hook e token, permissão 600) e faz POST em `http://127.0.0.1:<porta_hook>/permissao`, com o painel e o pedido;
     - espera a resposta e imprime só o JSON da decisão;
     - com o cérebro fora, falha de conexão ou resposta vazia, sai sem imprimir: o diálogo segue (fatos 3 e 5).
   - O cérebro grava a porta do hook no `session.json`. O token é o do WebSocket.
   - Pedido pendente, como na 1ª versão. Termina por:
     - **clique** → `allow`, ou `deny` com "O Kaio negou pelo Jarvis.";
     - **tecla do Kaio na aba** daquele terminal → resposta vazia;
     - **próximo evento** do Claude Code naquele painel (`PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SessionEnd`, outro `PermissionRequest`) → resposta vazia;
     - **sessão encerrada, cérebro parando, ou 590 s** → resposta vazia.
   - Nunca `updatedPermissions`, `updatedInput` nem `interrupt`.
   - O hook assíncrono de anotação anota o mesmo pedido. Num terminal compartilhado ele não gera um segundo aviso, e o prazo de 20 s não vale enquanto houver um pedido aberto.
   - Alternativa descartada: hook `http` por `--settings`, como na 1ª versão. Só servia para o `claude` aberto pelo Jarvis, não para o digitado no Terminal.app.

8. **Mandar texto** (ferramenta `mandar_terminal(numero, texto)` e a confirmação que já existe):
   - O cérebro tira os controles (< 0x20 menos `\t`/`\n`, 0x7f, C1) e corta em 4.000 caracteres.
   - **Claude Code** → `load-buffer` + `paste-buffer -p` (colagem) + `send-keys Enter`. Cartão: "Mensagem para o Terminal N (pasta): …".
   - **Shell** → recusa texto com quebra de linha; senão `send-keys -l '<cmd>'` + `Enter`. Cartão: "Comando no Terminal N (pasta): `<cmd>`".
   - Envia só depois do "Confirmar". O alvo (`pane_id`) é conferido de novo na hora de enviar. Se o terminal fechou ou trocou de shell para Claude Code no meio, o Jarvis recusa e pergunta outra vez.
   - Pela aba, as teclas vão cruas.

9. **Ferramentas do modelo:**
   - `abrir_terminal(pasta, claude=false)`, sem confirmação, porque abrir não executa nada;
   - `mandar_terminal` (decisão 8);
   - `fechar_terminal(numero)`, que é `tmux kill-session`, com confirmação se houver algo rodando;
   - `listar_terminais`, só leitura, ganha o tipo (shell ou Claude Code);
   - **não existe ferramenta de aprovação**, e o prompt diz isso;
   - o modelo nunca recebe a tela.

10. **Interface:**
    - **Lista:** a coluna "Terminais" do painel mostra os terminais compartilhados com "abrir aba".
    - **Barra de abas:** "Central" + abas abertas + "+". O "+" pede a pasta e tem a escolha "Terminal" ou "Claude Code".
    - **Xterm e teclas:** `@xterm/xterm` com `addon-fit`, `scrollback: 5000`, sem WebGL. Só a aba visível fica montada. Esc vai para o terminal; ⌥⇧Espaço fecha o painel; ⌘C copia a seleção.
    - **Botões:** Permitir e Negar no aviso do HUD e no topo do painel, sem foco automático nem atalho de teclado.
    - **Abas lembradas:** as abas que o Kaio deixou abertas ficam no `localStorage` da interface (só os ids das sessões do tmux). Depois de reiniciar, voltam as que ainda existem.

11. **Auto mode.** As sessões do Kaio vão pedir permissão pouco. O valor principal é ver, digitar, abrir e mandar.

## Risks / Trade-offs

- **O Jarvis passa a rodar comandos de shell** (muda a regra de segurança do `CLAUDE.md`) → cartão com o texto exato; uma linha; sem controles; só depois do clique; só nos terminais compartilhados. A aprovação de permissões nunca vem do modelo. A regra do `CLAUDE.md` e o `SPEC.md` são atualizados neste change.
- **Injeção de prompt:** um texto vindo do núcleo, como o título de um evento, pode convencer o modelo a rodar um comando → o cartão de confirmação mostra o comando e nada roda sem clique. O Kaio precisa ler o cartão, e o tipo "Comando" aparece em destaque.
- **Voz mal entendida** → o mesmo cartão.
- **Todo terminal novo roda no tmux** (a rolagem é do tmux; selecionar texto pede Option + arrastar; Ctrl+] é o prefixo) → configuração mínima e status desligado. `JARVIS_SEM_TMUX=1` desliga numa janela, e `--sem-tmux` desliga de vez.
- **Um `~/.zshrc` quebrado deixaria o Kaio sem terminal** → o bloco só faz `exec` depois de `tmux -V` funcionar, com backup. Se tudo falhar, o shell segue normal.
- **Resposta dada no Terminal.app não é vista na hora** (o Jarvis só vê as teclas da própria aba) → os botões ficam até o próximo sinal da sessão. Um clique atrasado é ignorado pelo Claude Code, mas o aviso diria "Permitido" sem ter valido. Para evitar isso, o resultado mostrado é "Enviado ao terminal", não "Permitido".
- **Hook síncrono global em todas as sessões** → fora do socket `jarvis`, o script sai em ~40 ms sem fazer nada. Falha nunca bloqueia (`|| true`, saída vazia).
- **O HUD sem foco pode não receber clique** → conferir no aceite. Se não receber, o clique torna o HUD focável primeiro. Os botões também ficam no painel.
- **Duas telas de tamanhos diferentes** → `window-size latest`: a janela segue quem foi usado por último, e o Claude Code redesenha.
- **Swap cheio** → limiar de memória e no máximo 4 Claude Code abertos pelo Jarvis. O aceite anota a memória.
- **Reinício do Mac** → o tmux fecha junto. Igual a hoje.

## Migration Plan

- Instalar: `brew install tmux` (feito em 09/10/2026, 3.8). Depois `npm run tauri build` e `install_mac.sh`, que gravam a configuração do tmux, o bloco do `~/.zshrc` e o hook de permissão no `~/.claude/settings.json`, todos com backup.
- Janelas do Terminal.app abertas antes da instalação continuam fora. As novas entram.
- Reverter: `install_mac.sh --sem-tmux --sem-terminais` e reinstalar a versão anterior do app. As sessões do tmux continuam vivas até o Kaio fechá-las (`tmux -L jarvis kill-server`).

## Registro da implementação

**1ª versão (09/10/2026):** pty do `claude` direto no cérebro, hook `http` por `--settings`, `abas.json` com "Retomar".
- Testes passaram:
  - 364 em Python;
  - 45 na interface;
  - 3 com o `claude` real (`uv run pytest -m claude tests/jarvis/test_claude_real.py`):
    - permitir e negar;
    - tecla na aba vencendo o hook;
    - porta do hook fechada.
- Instalada às 18h40. No uso do Kaio às 20h27, as sessões fecharam sozinhas (fato 4).
- Depois disso veio a revisão para o tmux.

**Aproveitado:**
- `jarvis/permissions.py` (pedidos e servidor HTTP);
- pastas, limite e limpeza de texto de `jarvis/sessions.py`;
- `jarvis/control.py` (a ser adaptado);
- `AlertBar`, `TerminalTabs` e `TerminalView` (com a reprodução trocada pelo `tmux attach`);
- o servidor com quadros binários.

**Build depois da mudança de pasta:** o cache do Cargo guardava caminhos de `~/Downloads/life-manager`. Apagar só as 50 saídas de build script com o caminho velho resolveu.
