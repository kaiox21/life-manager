## 0. Antes de começar

- [ ] 0.1 Aceite do `jarvis-terminais` (tarefas 4.2 e 4.3 dele, incluindo: com um aviso de terminal na tela, o Esc no Terminal.app ainda interrompe o Claude?) e `/opsx:archive jarvis-terminais`; verificar com `openspec list --specs` e `openspec validate jarvis-terminais-controle --strict`

## 1. tmux e Terminal.app

- [x] 1.1 `jarvis/tmux.conf` (as 3 linhas oficiais do Claude Code, `escape-time 10`, `window-size latest`, `mouse on`, `history-limit 50000`, `status off`, prefixo Ctrl+]) copiado pelo `install_mac.sh` para `~/Library/Application Support/Jarvis/`; teste que carrega o arquivo num servidor isolado (`tmux -L <teste> -f`) e confere as opções
- [x] 1.2 Bloco do `~/.zshrc` (`jarvis/hooks/zshrc.py`, biblioteca padrão): instala entre marcadores com backup, sem duplicar e sem mexer no resto; `--remover`; o bloco só age em `Apple_Terminal` interativo, sem `TMUX`, sem `JARVIS_SEM_TMUX` e com `tmux -V` funcionando, e faz `exec tmux -L jarvis -f <conf> new-session -c "$PWD" \; set-option destroy-unattached on \; set-option @jarvis_origem terminal`; testes com arquivo temporário e teste rodando `zsh -i` com `TERM_PROGRAM=Apple_Terminal` e um `tmux` falso que falha (o shell continua)
- [x] 1.3 `install_mac.sh`: tmux.conf, bloco do `.zshrc`, `--sem-tmux`; avisa se o tmux não estiver instalado (`brew install tmux`) e segue sem o bloco

## 2. Cérebro: terminais do tmux

- [x] 2.1 Pastas permitidas, limite de memória e limpeza de texto (`jarvis/sessions.py`: `Folders`, `memory_level`, `clean_text`), com testes (da 1ª versão)
- [x] 2.2 `jarvis/tmux.py`: chama o `tmux` sempre com ambiente mínimo; lista sessões e painéis (`list-panes -a -F …` com `@jarvis_origem`, `@jarvis_aba` e clientes conectados; comandos fixos, sem shell); abre sessão (`new-session -d -c` + `@jarvis_origem jarvis`); manda `claude`; mata sessão; manda comando (`send-keys C-e C-u` + `-l` + Enter) e mensagem (`load-buffer` + `paste-buffer -p` + Enter); tmux ausente = lista vazia; testes contra um servidor tmux isolado (pulados sem tmux), incluindo: uma variável do ambiente do cérebro não aparece num terminal aberto pelo Jarvis; linha pela metade é apagada antes do comando
- [x] 2.3 Abas e cliente: abrir aba grava `@jarvis_aba` e desliga `destroy-unattached`; fechar aba apaga a marca e, em sessão vinda do Terminal.app, religa `destroy-unattached` (sem janela, a sessão acaba); a barra de abas vem das sessões marcadas; cliente da aba = pty rodando `tmux -L jarvis attach -t <sessão>`, aberto no `term_attach` e fechado no `term_detach`/desconexão, sem buffer guardado; resize; pausa; testes com servidor isolado: o que se digita num cliente aparece no outro; sessão do Terminal.app marcada sobrevive sem cliente nenhum; aba fechada sem janela encerra a sessão
- [x] 2.4 Numeração: sessão do tmux = terminal (chave `tmux:<session_id>`), na mesma numeração do `jarvis-terminais`; hook de anotação grava `painel` e `socket`; evento de painel do socket `jarvis` vai para o terminal da sessão e marca Claude Code de `SessionStart` a `SessionEnd`; "algo rodando" no shell por `pane_current_command`, e `claude` sem eventos dos hooks conta como "algo rodando"; testes em `test_terminals.py`
- [x] 2.5 Retirar da 1ª versão o que o tmux substitui: `claude` direto no pty, `--settings` com hook http, `abas.json` e "Retomar"; testes ajustados

## 3. Permissões

- [x] 3.1 Pedidos pendentes e servidor HTTP mínimo (`jarvis/permissions.py`: clique, resposta vazia, pedido novo encerra o anterior, prazo, recusas), com testes (da 1ª versão)
- [x] 3.2 Hook global `jarvis/hooks/claude_permission.py` (biblioteca padrão, síncrono, `timeout: 600`, `2>/dev/null || true`): sai calado fora do socket `jarvis`; senão lê porta e token do `session.json` e espera a decisão; cérebro fora = sai calado; `install.py` instala e `--sem-terminais` remove; o cérebro grava a porta do hook no `session.json`; testes do script (fora do tmux, cérebro fora, allow, deny) e da instalação
- [x] 3.3 Pedido ligado ao terminal pelo painel; resolve por clique, tecla na aba, próximo evento do painel, sessão encerrada, parada ou 590 s; um aviso só; sem prazo de 20 s com pedido aberto; resultado de um clique mostrado como "Enviado ao terminal"; testes
- [x] 3.4 Teste real (`-m claude`, Haiku, centavos): `claude` num terminal do tmux isolado com o hook global de teste: permitir, negar, resposta no outro cliente vencendo, cérebro fora

## 4. Canal e ferramentas

- [x] 4.1 WebSocket: `term_attach`/`term_detach`/`term_input`/`term_resize`/`term_pause`/`term_open` (pasta + claude)/`term_close`/`permission_answer`; evento `terminals` com tipo (shell/Claude Code) e "aberto no Terminal.app"; testes em `test_server.py` e `test_control.py`
- [x] 4.2 Ferramentas `abrir_terminal(pasta, claude)` (limite: 4 Claude Code rodando nos terminais compartilhados, e memória), `mandar_terminal` (mensagem só com o Claude Code em "terminou"/"esperando você"; comando de uma linha só com o shell livre; cartão com tipo e texto exato; alvo e condições conferidos de novo ao enviar) e `fechar_terminal` (confirma se algo roda ou se há janela do Terminal.app conectada, avisando que ela fecha junto); prompt: sem aprovação pelo modelo, sem tela para o modelo; testes com o modelo roteirizado (mensagem confirmada e cancelada, comando confirmado e cancelado, várias linhas recusadas, sessão de fora recusada, "permite o terminal 3" sem efeito, mensagem recusada com o Claude Code pedindo permissão, comando recusado com programa rodando, terminal que ficou ocupado entre a confirmação e o envio)

## 5. Interface

- [x] 5.1 `AlertBar` com Permitir/Negar, `TerminalTabs`, `TerminalView` com `@xterm/xterm` 6 (controle de fluxo, Esc para o terminal, ⌘C), com testes (da 1ª versão)
- [ ] 5.2 Ajustes para o tmux: sem reprodução da tela guardada (o tmux redesenha); "+" com Terminal ou Claude Code; coluna "Terminais" com "abrir aba" e o tipo; barra de abas vinda do cérebro (só a aba em primeiro plano no `localStorage`); × com confirmação quando o terminal vai acabar com algo rodando; "Enviado ao terminal"; testes (`npx vitest run`)
- [ ] 5.4 HUD aberto por aviso de terminal não pega o Esc global (só o HUD da voz pega); teste de componente e conferência no app: com o aviso na tela, o Esc no Terminal.app interrompe o Claude Code
- [ ] 5.3 Conferir no app que o HUD aberto sem foco recebe o clique; se não receber, aplicar a alternativa do `design.md`

## 6. Fechamento

- [ ] 6.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `npx vitest run`, `openspec validate --all --strict`, `npm run tauri build -- --bundles app` e `bash jarvis/install_mac.sh`; a prova do núcleo (`uv run pytest -m eval`) não precisa rodar porque o núcleo e seus prompts não mudam
- [ ] 6.2 Aceite real com o Kaio, com a memória anotada (`kern.memorystatus_level` e swap):
  - janela nova do Terminal.app aparece no Jarvis e abre numa aba, e o que se digita num lado aparece no outro;
  - fechar a janela encerra a sessão;
  - `JARVIS_SEM_TMUX=1` abre sem tmux;
  - "+" abre Terminal e Claude Code (pasta nova com a pergunta de confiança);
  - Esc na aba;
  - Permitir e Negar pelo HUD num Claude Code aberto no Terminal.app;
  - resposta na aba com o aviso aberto;
  - por voz:
    - "Terminal 2, roda os testes" (Claude Code) com confirmação;
    - "Terminal 3, roda git status" (shell) com confirmação;
    - "permite o terminal 3" recusado;
  - "Terminal 2, roda os testes" com o Terminal 2 pedindo permissão: recusado, e o pedido continua aberto;
  - comando com `npm test` rodando: recusado;
  - Esc no Terminal.app com o aviso na tela interrompe o Claude Code;
  - fechar a janela do Terminal.app de um terminal que está numa aba, fechar o painel e reabrir: o terminal continua;
  - quinto Claude Code recusado;
  - fechar terminal trabalhando com confirmação;
  - reiniciar o cérebro: terminais continuam;
  - VS Code só com aviso;
  - anotar no `design.md` se a remoção crítica no auto mode passa pelo hook
- [ ] 6.3 `SPEC.md` (decisão "o Jarvis escreve em terminais e roda comandos de shell com confirmação", tmux em todos os terminais novos, limite de memória, fecha "Sessões do Claude Code no Jarvis"), regra de segurança do `CLAUDE.md` e `/opsx:archive`
