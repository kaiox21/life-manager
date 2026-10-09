## 0. Antes de começar

- [ ] 0.1 Aceite do `jarvis-terminais` (tarefas 4.2 e 4.3 dele, incluindo: com um aviso de terminal na tela, o Esc no Terminal.app ainda interrompe o Claude?) e `/opsx:archive jarvis-terminais`; verificar com `openspec list --specs` que a capacidade `jarvis-terminais` existe em `openspec/specs` e com `openspec validate jarvis-terminais-controle --strict`

## 1. Sessões no cérebro

- [x] 1.1 `jarvis/sessions.py`: abre o `claude` num pty (`/bin/zsh -l -i -c 'exec "$0" "$@"' claude --settings <json>`, `TERM`, `JARVIS_TERMINAL`, `JARVIS_HOOK_TOKEN`), lê e escreve com `asyncio`, buffer circular de 512 KB, `resize` (TIOCSWINSZ), encerra (SIGHUP e, 5 s depois, SIGKILL), nunca passa `--dangerously-skip-permissions`; testes com um programa falso no lugar do `claude` (eco, resize, encerrar, buffer) e teste de que o pid da sessão é o do programa (o `exec` funcionou)
- [x] 1.2 Pastas permitidas (`JARVIS_PASTAS`, até 2 níveis, `realpath` dentro da raiz, nome ambíguo devolve opções) e limite (`JARVIS_TERMINAIS_MAX`, `kern.memorystatus_level` < `JARVIS_TERMINAIS_MEM_MIN`); testes com pastas temporárias, `..`, link simbólico para fora, quinta sessão e memória baixa (leitura de memória injetável)
- [x] 1.3 Ligar ao `Terminals` do `jarvis-terminais`: sessão aberta pelo Jarvis = mesmo pid, ganha `aba: true` e o menor número livre; `abas.json` (600) e "encerrado / Retomar" (`claude --resume <session_id>`) depois do reinício; testes

## 2. Permissões

- [x] 2.1 Servidor HTTP mínimo em `127.0.0.1` (porta sorteada, só `POST /permissao`, corpo até 256 KB, token por sessão com `compare_digest`); testes de token errado, corpo grande, rota errada
- [x] 2.2 Pedido pendente: guarda a requisição, manda `terminal_alert` com `pedido_id`; resolve por clique (`allow` ou `deny` com "O Kaio negou pelo Jarvis."), por próximo evento da sessão nos hooks globais, por tecla do Kaio na aba daquela sessão, por sessão encerrada, por parada do cérebro ou por 590 s (resposta `{}`); clique atrasado responde "já respondido"; um aviso só por pedido (o evento do arquivo não repete o aviso de uma sessão com aba); nunca `updatedPermissions`, `updatedInput` nem `interrupt`; testes de cada caminho
- [x] 2.3 Teste de integração com o `claude` de verdade num pty (Haiku na conta do Claude Code, centavos; marcador `claude` em vez de `eval` para não misturar com a prova do núcleo; `uv run pytest -m claude tests/jarvis/test_claude_real.py`): allow, deny, resposta na aba vencendo o hook e cérebro fora (diálogo segue)

## 3. Canal e ferramentas

- [x] 3.1 WebSocket: quadros binários de saída (tipo + id + bytes), `term_input`, `term_resize`, `term_attach` (reenvia o buffer), `term_open`, `term_close`, `permission_answer`; só para sessões abertas pelo Jarvis; testes em `test_server.py`
- [x] 3.2 Ferramentas `abrir_terminal`, `mandar_terminal` (limpa controles, corta em 4.000, cartão de confirmação com destino e texto final) e `fechar_terminal` (confirma se trabalhando); prompt do Jarvis diz que permissões só pelo botão ou na aba e que o conteúdo da tela não chega ao modelo; testes com o modelo roteirizado (recado confirmado e cancelado, sessão de fora recusada, "permite o terminal 3" sem efeito, pasta fora da lista)

## 4. Interface

- [x] 4.1 `@xterm/xterm` 6 + `@xterm/addon-fit`; abas no painel (número, pasta, estado, "+", "×", "Retomar"), só a aba visível montada, controle de fluxo, Esc vai para o terminal e ⌥⇧Espaço fecha o painel, ⌘C/⌘V; testes de componente (`npx vitest run`)
- [ ] 4.2 Botões Permitir e Negar no aviso do HUD e no painel (só para `aba: true`), estado "já respondido"; conferir no app que o HUD aberto sem foco recebe o clique, e se não receber, aplicar a alternativa do `design.md`; testes de componente

## 5. Fechamento

- [x] 5.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `npx vitest run`, `openspec validate --all --strict`, `npm run tauri build` e `bash jarvis/install_mac.sh`; a prova do núcleo (`uv run pytest -m eval`) não precisa rodar porque o núcleo e seus prompts não mudam
- [ ] 5.2 Aceite real com o Kaio, com a memória anotada (`kern.memorystatus_level` e swap) antes e com 4 abas:
  - abrir pela voz e pelo "+" (pasta nova com a pergunta de confiança);
  - digitar e Esc na aba;
  - Permitir e Negar pelo HUD;
  - responder na aba com o aviso aberto;
  - "Terminal 2, roda os testes" com confirmação;
  - "permite o terminal 3" recusado;
  - quinta sessão recusada;
  - fechar trabalhando com confirmação;
  - reiniciar o cérebro e "Retomar";
  - sessão no Terminal.app só com aviso;
  - anotar no `design.md` se a remoção crítica no auto mode passa pelo hook
- [ ] 5.3 `SPEC.md` (decisão "o Jarvis escreve em sessões do Claude Code", limite de memória, fecha "Sessões do Claude Code no Jarvis"), regra de segurança do `CLAUDE.md` ("nenhuma ferramenta executa shell" ganha a exceção das ferramentas de terminal) e `/opsx:archive`
