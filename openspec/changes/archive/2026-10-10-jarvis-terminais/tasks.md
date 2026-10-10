## 1. Hooks

- [x] 1.1 `jarvis/hooks/claude_event.py` (biblioteca padrão, Python 3.9+): acha o pid do `claude` subindo pelos processos pais, lê o JSON do stdin, extrai só os campos permitidos e o resumo (Bash, Edit/Write/Read, WebFetch, MCP), grava uma linha no `claude-events.jsonl` (600) num único `write`; nunca imprime nada; testes com JSON de exemplo de cada evento, confirmando que `prompt`, `message` e conteúdos não são gravados
- [x] 1.2 `jarvis/hooks/install.py`: copia o script para `~/Library/Application Support/Jarvis/hooks/`, mescla os hooks (`async: true`, comando `... >/dev/null 2>&1 || true`) no `~/.claude/settings.json` com backup, sem duplicar e sem mexer no resto; `--remover`; testes com arquivo temporário (com e sem hooks já existentes) e teste de que o comando instalado sai com 0 mesmo com o script apagado

## 2. Cérebro

- [x] 2.1 `jarvis/terminals.py`: lê o arquivo de eventos, numera por processo (menor livre), atualiza estados ("pedindo permissão" vale até o próximo evento ou 20 s), expira por processo fechado ou 12 h, reduz o arquivo; testes com eventos de exemplo (duas sessões, `/clear` mantém o número, número liberado, permissão pedida e respondida, permissão sem resposta por 20 s, espera, fim)
- [x] 2.2 Eventos `terminals` e `terminal_alert` para todas as conexões; ferramenta local `listar_terminais` e cartão `terminais` (o modelo recebe a lista sem os resumos); testes

## 3. Interface

- [x] 3.1 Aviso no HUD sem foco (toque, cartão no topo, some ao resolver ou em 20 s); com o painel aberto, aviso no painel; testes de componente
- [x] 3.2 Coluna "Terminais" no painel; testes de componente

## 4. Fechamento

- [x] 4.1 `uv run pytest`, `ruff`, testes da UI, `npm run tauri build`, `install_mac.sh` (com os hooks); a prova do núcleo não precisa rodar (o núcleo não muda)
- [x] 4.2 Aceite com o Kaio (sessões abertas depois da instalação; anotar se as que já estavam abertas também passaram a avisar): duas sessões numeradas; pedido de permissão aparece em < 1 s sem roubar o foco e some ao responder; "esperando você"; "como estão meus terminais?"; `install_mac.sh --sem-terminais` remove os hooks
- [x] 4.3 `SPEC.md` (fecha "Sessões do Claude Code no Jarvis"; registra os hooks globais) e arquivar
