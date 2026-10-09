## Why

O Kaio roda várias sessões do Claude Code ao mesmo tempo e só descobre que uma parou pedindo permissão quando volta ao terminal. Ele quer o Jarvis como **gerenciador de terminais**: cada sessão vira "Terminal 1", "Terminal 2"…, e quando uma precisa de permissão aparece na hora "Terminal 1 está pedindo para rodar `npm test`" (pedido de 08/10/2026, detalhado em 09/10/2026).

## What Changes

- Cada sessão do Claude Code aberta neste Mac ganha um **número estável** ("Terminal 1", "Terminal 2"…), mostrado junto com o nome da pasta, que fica até ela fechar.
- **Pedido de permissão**: o HUD aparece na hora, sem roubar o foco, com um toque curto e um aviso do tipo "**Terminal 1** (life-manager) está pedindo para rodar `npm test`". O aviso diz a ferramenta e um resumo do pedido (o comando, o arquivo ou a URL).
- Também vira aviso quando uma sessão **fica esperando você** (parada aguardando resposta) e, de forma mais discreta, quando **termina** uma tarefa.
- **Lista de terminais** no painel (nova coluna) e por pergunta ao Jarvis ("como estão meus terminais?"): número, pasta e estado (trabalhando, pedindo permissão, esperando você, terminou).
- Como o Jarvis sabe: **hooks oficiais do Claude Code** nas configurações globais (`~/.claude/settings.json`), instalados pelo `install_mac.sh` com backup. Eles só anotam o evento num arquivo local do Jarvis; nada sai do Mac e nenhum hook decide nada.

## Non-goals

- **Responder** à permissão pelo Jarvis (Permitir/Negar). Fica para um change seguinte, depois de ver os avisos funcionando: é poder de aprovar comandos à distância e merece desenho próprio.
- Levar o foco para a janela ou aba exata do terminal ao clicar no aviso.
- Ler ou mostrar o conteúdo das conversas (só o resumo do pedido de permissão).
- Sessões do Claude Code fora deste Mac (nuvem, outro computador).

## Capabilities

### New Capabilities
- `jarvis-terminais`: acompanhar as sessões do Claude Code deste Mac como terminais numerados, avisar pedidos de permissão e esperas, e listá-las no painel e por pergunta.

### Modified Capabilities
- `ferramentas-locais`: nova ferramenta local de leitura `listar_terminais`, para o Jarvis responder sobre os terminais.

## Impact

- **Novo:** `jarvis/hooks/claude_event.py` (script do hook, só biblioteca padrão), `jarvis/terminals.py` (lê os eventos, numera e mantém o estado), testes.
- **Cérebro:** observa o arquivo de eventos e manda à interface `terminals` (lista) e `terminal_alert` (aviso); `listar_terminais` nas ferramentas locais.
- **Interface:** aviso no HUD (aparece sem foco), coluna "Terminais" no painel.
- **Instalação:** `install_mac.sh` mescla os hooks em `~/.claude/settings.json` (com backup e sem apagar o que já existe) e ganha `--sem-terminais` para remover.
- **`SPEC.md`:** fecha a questão "Sessões do Claude Code no Jarvis" e registra que os hooks valem para todas as sessões do Mac.
