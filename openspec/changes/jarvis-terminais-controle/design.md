## Context

Motivação: ver `proposal.md`. Este change parte do `jarvis-terminais`, que já tem hooks globais que só anotam eventos, terminais numerados pelo pid do `claude`, aviso no HUD sem foco e coluna no painel. O cérebro (Python, sob launchd) e a interface (Tauri 2 + React) conversam por um WebSocket local com token. O WebSocket já leva quadros binários, hoje o áudio da voz.

### Fatos conferidos (09/10/2026, Claude Code 2.1.296)

**Na documentação oficial:**

- **Hook `PermissionRequest`** (code.claude.com/docs/en/hooks):
  - Saída: `{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"|"deny", "message"?, "interrupt"?, "updatedInput"?, "updatedPermissions"?}}}`.
  - Regras de deny e ask continuam valendo por cima de um allow.
  - Tempo limite padrão de 600 s para hooks `command` e `http`. Estourado o tempo, a saída é descartada e o hook não decide nada.
- **Hook `http`:**
  - É um POST com o JSON do evento no corpo.
  - Os headers aceitam `$VAR`, desde que a variável esteja em `allowedEnvVars`.
  - Erros (conexão recusada, status fora de 2xx) não bloqueiam: "non-blocking error, execution continues".
- **Configuração:**
  - `--settings` aceita um arquivo ou um JSON inline.
  - Hooks de vários níveis de configuração se somam, não se substituem.
  - O processo do hook herda o ambiente do `claude`.
  - Mudanças no `settings.json` valem nas sessões já abertas.
  - Os hooks, inclusive os globais, ficam suspensos até o Kaio aceitar a pergunta de confiança da pasta.
- **Modos de permissão** (code.claude.com/docs/en/permission-modes):
  - Desde a 2.1.283, o **auto mode** é o modo inicial das sessões de terminal, e as sessões do Kaio abrem nele.
  - No auto mode, ainda viram diálogo:
    - regras `ask`;
    - remoções em caminhos críticos, com contagem regressiva de 2 min;
    - o recuo depois de 3 bloqueios seguidos ou 20 no total do classificador.
  - Em `bypassPermissions` quase nada pergunta.
- **Remote Control** (`/remote-control`): é o jeito oficial de aprovar e mandar mensagens a uma sessão local, pelo app ou pelo claude.ai. Não existe API local documentada para escrever numa sessão que roda em outro terminal.
- **Transcrição:** `~/.claude/projects/<projeto>/<sessão>.jsonl` não tem esquema documentado. Não é usada.
- **Tauri 2** (v2.tauri.app/develop/calling-frontend): o sistema de eventos "is not designed for low latency or high throughput". Para fluxos, a recomendação é `Channel`. Isso não se aplica aqui, porque a saída do terminal vai do cérebro direto para o webview pelo WebSocket, sem passar pelo Rust.
- **Bibliotecas** (crates.io, npm e GitHub):
  - `tauri-plugin-pty` 0.3.1 (07/2026): README "Developing!", um mantenedor só, usa `portable-pty` 0.9.0 (02/2025, maduro, do wezterm).
  - `@xterm/xterm` 6.0.0 e `@xterm/addon-fit` 0.11.0, de 12/2025, ativos. O pacote antigo `xterm` está obsoleto.
  - xterm.js: `scrollback` padrão de 1000 linhas. O guia de controle de fluxo diz que o buffer de escrita descarta o que passa de ~50 MB.

**Na prática** (scratchpad, `claude` num pty aberto por Python, modelo Haiku, custo de centavos):

1. O `claude` roda direito num pty da biblioteca padrão (`pty.openpty` + `subprocess`), lido por um emulador de tela. As teclas e o "colar" com várias linhas (bracketed paste) funcionam.
2. Com o PATH mínimo do launchd, os hooks dos plugins do Kaio, que chamam `node`, falharam e escreveram "hook error" na conversa. Com o PATH do shell de login, tudo saiu limpo.
3. A primeira sessão numa pasta nova mostra a pergunta de confiança com **"No, exit" marcado**: um Enter sem olhar encerra a sessão.
4. Hook `PermissionRequest` do tipo `command` e do tipo `http` (servidor local, `Authorization: Bearer $JARVIS_HOOK_TOKEN` em `allowedEnvVars`):
   - `allow` roda o comando, com "Allowed by PermissionRequest hook" na tela;
   - `deny` não roda e a mensagem do Jarvis chega ao modelo;
   - resposta vazia faz o diálogo normal seguir;
   - a variável `JARVIS_TERMINAL` chegou ao hook.
5. **O diálogo aparece na tela enquanto o hook ainda espera**, e vale o que vier primeiro:
   - o Kaio respondeu "1" na tela e o comando rodou;
   - a negação mandada depois pelo hook foi ignorada;
   - o Claude Code **não fecha** a requisição HTTP nem mata o hook quando o Kaio responde na tela: o servidor segurou 20 s e entregou a resposta sem erro.
6. No modo padrão (`--permission-mode default`), comandos só de leitura (`date`, `which`) rodam sem pedir.
7. Aberto como `/bin/zsh -l -i -c 'exec "$0" "$@"' claude …`, com o PATH mínimo do launchd, o filho do pty **é** o processo `claude` (mesmo pid, `comm` = `claude`). Matar o pai com SIGKILL derruba o `claude` junto, porque o pty fecha.
8. Memória do Mac às 18h:
   - 16 GB de RAM; swap de 9,25 GB usados de 10 GB; `kern.memorystatus_level` = 43;
   - cada `claude` usa de 150 a 300 MB (RSS), e três sessões somavam 701 MB.

## Goals / Non-Goals

**Goals:**
- A aba se comporta como o Terminal.app.
- Permitir ou Negar chega à sessão em menos de 300 ms.
- Nenhuma aprovação vem do modelo.
- Com o Jarvis caído, nenhum pedido fica travado.
- Somadas, as sessões do Jarvis respeitam um teto de memória.

**Non-Goals** (de desenho):
- multiplexador próprio;
- sessões que sobrevivem ao reinício do cérebro;
- ler a transcrição;
- terminal sem o `claude`.

## Decisions

1. **Change novo, não revisão do `jarvis-terminais`.** O `jarvis-terminais` está implementado, testado e com commit local (83d392a). O escopo dele é só leitura, e ele mesmo adiou "responder à permissão" para um desenho próprio. Este change muda o modelo de confiança: o Jarvis passa a **escrever** em sessões. Misturar os dois deixaria um aceite pendente sem fim. Ordem: aceitar e arquivar o `jarvis-terminais` e só então aplicar este. Os deltas daqui modificam requisitos que só existem depois desse arquivamento.

2. **O terminal mora no cérebro (Python), não no Rust do Tauri.**
   - O cérebro abre cada sessão com `pty.openpty()` da biblioteca padrão e lê e escreve com `asyncio` (`loop.add_reader`).
   - A saída vai para a interface em quadros binários no WebSocket que já existe (1 byte de tipo + id da sessão + bytes). A entrada vem em JSON (`term_input`, `term_resize`).
   - Motivos:
     - quem resolve o hook, as ferramentas do modelo e a numeração já é o cérebro;
     - a casca Rust continua "sem regra";
     - dá para testar com `pytest`;
     - não entra dependência nova no Python.
   - Alternativa: `tauri-plugin-pty` ou `portable-pty` no Rust. O plugin está em "Developing!" e tem um mantenedor só. Com `portable-pty` à mão, seria preciso criar uma ponte Rust ↔ cérebro para os recados e as aprovações.
   - Custo aceito: reiniciar o cérebro (launchd `kickstart`) encerra as sessões, e cada aba oferece "Retomar" (decisão 9).

3. **Como a sessão é aberta.**
   - Comando: `/bin/zsh -l -i -c 'exec "$0" "$@"' claude --settings '<json>'`, na pasta escolhida.
     - O shell de login e interativo dá ao `claude` e aos hooks dos plugins o PATH do Kaio (fato 2).
     - O `exec` faz o pid do filho do pty ser o próprio `claude`, o mesmo pid que os hooks globais anotam. Assim a numeração do `jarvis-terminais` vale sem mudança, e o terminal só ganha a marca `aba: true`.
   - Ambiente:
     - `TERM=xterm-256color` e `COLORTERM=truecolor`;
     - `JARVIS_TERMINAL=<id>`;
     - `JARVIS_HOOK_TOKEN=<token próprio da sessão>`.
   - Sem `--permission-mode`: a sessão abre no modo padrão do Kaio. Nunca com `--dangerously-skip-permissions`.
   - Pastas permitidas: `JARVIS_PASTAS`, com padrão `~/Projetos pessoais`, `~/AmicusIA` e `~/Faculdade`.
     - Aceita a pasta-raiz ou uma subpasta até 2 níveis abaixo, achada pelo nome ("life-manager").
     - O caminho é resolvido com `realpath` e precisa ficar dentro de uma raiz.
     - Se o nome for ambíguo, o Jarvis devolve as opções.

4. **Aprovar e negar: hook `http` só nas sessões do Jarvis.**
   - O `--settings` inline de cada sessão aberta pelo Jarvis acrescenta:
     ```
     PermissionRequest → {"type":"http", "url":"http://127.0.0.1:<porta>/permissao",
       "headers":{"Authorization":"Bearer $JARVIS_HOOK_TOKEN"},
       "allowedEnvVars":["JARVIS_HOOK_TOKEN"], "timeout":600}
     ```
   - A porta é sorteada a cada execução do cérebro. Isso não é problema, porque ela vai junto com cada sessão aberta naquela execução.
   - O endereço é um servidor HTTP mínimo em `asyncio`, só em `127.0.0.1`. Ele aceita só `POST /permissao`, com corpo de até 256 KB, e confere o token com `compare_digest` para saber a sessão. Fica separado do WebSocket porque a biblioteca `websockets` não lê corpo de POST.
   - O cérebro segura a requisição como **pedido pendente** e manda à interface `terminal_alert` com `pedido_id` e os botões. A requisição termina por um destes caminhos:
     - **clique** → `allow`, ou `deny` com a `message` "O Kaio negou pelo Jarvis.";
     - **próximo evento daquela sessão** nos hooks globais (`PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, outro `PermissionRequest`) → resposta vazia (`{}`), porque o Kaio respondeu na aba (fato 5);
     - **tecla do Kaio na aba daquela sessão** enquanto o pedido está aberto → resposta vazia e botões somem. Sem isso, um comando demorado aprovado na aba deixaria os botões na tela até o `PostToolUse` (minutos), e um clique tardio mostraria "permitido" sem ter valido;
     - **sessão encerrada, cérebro parando, ou 590 s** → resposta vazia.
   - O hook global assíncrono do `jarvis-terminais` também anota o mesmo `PermissionRequest`. Para sessões com aba, o aviso sai do pedido HTTP (que tem `pedido_id`), e o evento do arquivo só atualiza o estado, sem um segundo aviso. O prazo de 20 s do `jarvis-terminais` vale só para as sessões de fora.
   - O token vai no ambiente (`$JARVIS_HOOK_TOKEN`), não no JSON do `--settings`, porque a linha de comando aparece no `ps`.
   - Nunca usa `updatedPermissions` ("sempre permitir"), `updatedInput` nem `interrupt`.
   - Se o cérebro estiver fora, a conexão é recusada, o erro não bloqueia e o diálogo da aba segue (fato 4). Nada fica travado.
   - Um clique que chega depois de o pedido ser resolvido é ignorado, e a interface mostra "já respondido".
   - Alternativas descartadas:
     - escrever "1" ou Esc no pty para escolher no diálogo: depende do desenho da tela, que muda a cada versão;
     - hook `command` com espera: deixa processos pendurados (fato 5);
     - Agent SDK ou `-p` com `canUseTool`: perde o terminal de verdade que o Kaio pediu.

5. **Mandar mensagem:** texto puro dentro de bracketed paste (`ESC[200~ … ESC[201~`) seguido de `\r`.
   - Antes, o cérebro tira os caracteres de controle (< 0x20, exceto `\n` e `\t`, e o 0x7f) e corta em 4.000 caracteres.
   - Pela aba, as teclas do Kaio vão cruas (é ele digitando).
   - Pelo modelo, a ferramenta `mandar_terminal(numero, texto)` gera um `confirm` no fluxo de confirmação que já existe, com o destino e o texto final. Só envia com "Confirmar".

6. **Ferramentas do modelo:**
   - `abrir_terminal(pasta)`: sem confirmação. Abrir não executa nada até o Kaio escrever.
   - `mandar_terminal(numero, texto)`: com confirmação.
   - `fechar_terminal(numero)`: confirmação se a sessão estiver trabalhando ou pedindo permissão. Encerra com SIGHUP e, depois de 5 s, SIGKILL.
   - `listar_terminais`: continua só leitura.
   - **Não existe ferramenta de aprovação.** O prompt do Jarvis diz que permissões só se respondem pelo botão ou na aba.
   - O modelo nunca recebe o conteúdo da tela.

7. **Interface.**
   - Painel: barra de abas (`Terminal N · pasta`, bolinha de estado, botão "+", "×").
   - Cada aba tem um `@xterm/xterm` com `addon-fit` e `scrollback: 5000`, sem o addon WebGL (economiza memória da GPU; o renderizador padrão basta).
   - Só a aba visível fica montada no DOM. Ao trocar de aba ou reabrir o painel, o cérebro reenvia o buffer circular da sessão (512 KB) e força um `resize`, para o `claude` redesenhar a tela.
   - Controle de fluxo: o `write` do xterm devolve um callback, e a interface pausa a leitura acima de 500 KB pendentes (guia do xterm.js).
   - O Esc numa aba vai para o terminal; o ⌥⇧Espaço continua fechando o painel. ⌘C e ⌘V copiam e colam; Ctrl-C vai para o `claude`.
   - Os botões Permitir e Negar ficam no aviso do HUD e no topo do painel, separados e sem atalho de teclado global (um Enter perdido não aprova nada).

8. **Memória.**
   - `JARVIS_TERMINAIS_MAX=4`.
   - Antes de abrir, o cérebro lê `sysctl kern.memorystatus_level` (% de memória livre que o macOS informa) e recusa abaixo de `JARVIS_TERMINAIS_MEM_MIN=20`.
   - Sessões de fora não contam.
   - Custo estimado: até ~1,2 GB para 4 sessões, mais alguns MB por aba no webview e 512 KB por sessão no cérebro.

9. **Retomar.** O `session_id` atual de cada sessão vem dos hooks globais (`SessionStart`). Quando o cérebro sobe e acha terminais de abas da execução anterior (gravados em `~/Library/Application Support/Jarvis/abas.json`, com permissão 600: número, pasta e `session_id`), ele mostra cada um como "encerrado", com o botão "Retomar". O botão abre `claude --resume <session_id>` na mesma pasta.

10. **Avisos em auto mode.** Nada muda no desenho, mas na prática as sessões do Kaio vão pedir permissão pouco (ver os fatos). O valor principal deste change é ver, digitar e mandar recados. Os botões aparecem nos casos que sobram: regras `ask`, recuo do classificador e remoções críticas.

## Risks / Trade-offs

- [O Jarvis passa a escrever em sessões que rodam comandos (muda a regra de segurança do `CLAUDE.md`)] → só texto, só nas sessões abertas por ele e só com confirmação quando vem do modelo; aprovação nunca vem do modelo. A regra do `CLAUDE.md` e o `SPEC.md` são atualizados neste change.
- [Injeção de prompt: um texto vindo do núcleo, como o título de um evento, convence o modelo a mandar um comando a um terminal] → o cartão de confirmação mostra o texto exato e o destino, e nada é enviado sem clique.
- [Voz mal entendida] → mesmo cartão, e aprovação por voz não existe.
- [Clicar Permitir sem ler] → o aviso mostra a ferramenta e o resumo do pedido; Permitir vale para um pedido só.
- [O HUD sem foco pode não receber clique] → hoje ele abre com `set_focusable(false)`, e isso precisa ser testado na tarefa 4.2. Se não receber, clicar no aviso torna o HUD focável primeiro. Os botões também ficam no painel.
- [Quem tem o token do WebSocket (arquivo 600 do Kaio) pode digitar nas sessões] → é o mesmo usuário, que já pode abrir um terminal. Mantém-se o canal só em `127.0.0.1`.
- [Um processo do Kaio lê o `JARVIS_HOOK_TOKEN` no ambiente do `claude` e forja pedidos] → no máximo cria um aviso falso. Aprovar exige o clique, e a resposta só vai para a requisição que o hook abriu.
- [Reiniciar o cérebro mata as sessões no meio de uma tarefa] → aviso no painel antes do `kickstart` e no `install_mac.sh`; "Retomar" continua a conversa (o trabalho em andamento no turno se perde).
- [A pergunta de confiança vem com "No, exit" marcado] → aparece na aba e o Kaio responde. O aviso de "esperando você" não cobre esse caso, porque os hooks ficam suspensos até a confiança ser dada.
- [Remoção crítica no auto mode tem contagem de 2 min e o `PermissionRequest` pode não disparar nela] → não documentado; conferir no aceite e anotar aqui.
- [O desenho da tela do `claude` muda] → o Jarvis não lê a tela; só repassa bytes.
- [Esc roubado em terminal de fora: o HUD de aviso abre sem foco e, com a correção do Esc instalada às 17:42, pega o Esc global; o Kaio, digitando no Terminal.app, aperta Esc para interromper o Claude e o Esc fecha o HUD em vez de chegar ao terminal] → é do `jarvis-terminais`: conferir no aceite dele (tarefa 0.1). Se acontecer, o aviso de terminal não deve pegar o Esc (só o HUD aberto pela voz).
- [Swap cheio] → teto de 4 sessões e limiar de memória livre; o aceite anota a memória com 4 abas abertas.

## Migration Plan

- Dependência nova só na interface: `@xterm/xterm` e `@xterm/addon-fit`. No Python, nenhuma.
- Instalação: `npm run tauri build` e `install_mac.sh`. Os hooks globais não mudam, porque o hook de aprovação vai por `--settings` só nas sessões do Jarvis. Não há nada a migrar em `~/.claude/settings.json`.
- Reverter: reinstalar a versão anterior. As sessões abertas pelo Jarvis morrem junto, e as de fora não são afetadas.

## Registro da implementação (09/10/2026)

- **Módulos novos:**
  - `jarvis/sessions.py`: pty, pastas permitidas, limite e `abas.json`.
  - `jarvis/permissions.py`: servidor HTTP do hook e pedidos pendentes.
  - `jarvis/control.py`: liga as sessões, os pedidos, a numeração, o WebSocket e as ferramentas.
  - Interface: `TerminalTabs`, `TerminalView` (`@xterm/xterm` 6.0.0 + `addon-fit` 0.11.0) e `AlertBar`.
- **Ambiente da sessão:** é mínimo, com HOME, USER, LANG, TERM e as variáveis `JARVIS_*`. O resto vem do shell de login. Teste confirma que uma `ANTHROPIC_API_KEY` presente no ambiente do cérebro **não** chega ao `claude`. Sem esse cuidado, a sessão poderia passar a cobrar da chave de API em vez de usar o login do Claude Code.
- **Terminal de controle:** o filho do pty ganha o pty como terminal de controle (`setsid` + `TIOCSCTTY`). Assim o SIGWINCH do redimensionamento e o SIGHUP do fechamento chegam ao `claude`.
- **Teste real** (`uv run pytest -m claude tests/jarvis/test_claude_real.py`, 3 testes, ~30 s, Haiku na conta Max), passou:
  - permitir e negar pelo Jarvis;
  - tecla na aba vencendo o hook;
  - porta do hook fechada, com o diálogo seguindo normalmente.
  - Marcador `claude` próprio, para não misturar com a prova do núcleo (`eval`).
- **Pergunta de confiança:** o diálogo só aceita teclas depois de montado. O teste espera ~2 s antes de responder. Na aba isso não importa, porque quem responde é o Kaio.
- **Fluxo de saída:** a saída de uma sessão só vai para a interface que anexou a aba (`term_attach`), e não para o HUD. Ao anexar, o cérebro manda o buffer (512 KB) e um SIGWINCH para o `claude` redesenhar.
- **Build depois da mudança de pasta:** o cache do Cargo guardava caminhos absolutos de `~/Downloads/life-manager`. Apagar só as 50 saídas de build script com o caminho velho resolveu, sem `cargo clean`.
- Teste de fumaça no app instalado (09/10/2026, 18h41), pelo WebSocket real:
  - `term_open` em life-manager virou "Terminal 3" (os Terminais 1 e 2 eram sessões do Terminal.app);
  - a tela chegou;
  - `term_close` removeu a aba;
  - o `abas.json` ficou com permissão 600.
  - A pasta life-manager pediu confiança de novo, porque o caminho mudou de `~/Downloads`.
