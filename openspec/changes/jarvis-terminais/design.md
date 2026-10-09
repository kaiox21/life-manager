## Context

O Claude Code tem hooks oficiais: um comando roda em cada evento e recebe um JSON no stdin. Conferido em code.claude.com/docs/en/hooks em 09/10/2026:
- campos comuns: `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`;
- `PermissionRequest`: dispara **antes** de o diálogo de permissão aparecer, com `tool_name` e `tool_input`. Sem `decision` na saída, o diálogo normal aparece igual. `async: true` é aceito;
- `Notification` com `notification_type` (`permission_prompt`, `idle_prompt`…) e `message`; `idle_prompt` vem ~60 s depois de o Claude terminar, se o Kaio não digitou;
- `Stop` (terminou de responder), `UserPromptSubmit` (`prompt`), `SessionStart` (`source`, `session_title`), `SessionEnd` (motivo no matcher), `PostToolUse` / `PostToolUseFailure`;
- configuração em `~/.claude/settings.json` (todas as sessões do Mac), formato `{"hooks": {"Evento": [{"matcher": "...", "hooks": [{"type": "command", "command": "...", "async": true}]}]}}`.

O Claude Code também mantém `~/.claude/sessions/<pid>.json` (pid, `sessionId`, `cwd`, `name`, `status`). É interno e sem documentação, então não é usado. Motivação: ver `proposal.md`.

## Goals / Non-Goals

**Goals:** aviso de permissão em menos de 1 s depois de o Claude Code pedir; numeração estável; nada de conteúdo das conversas guardado; instalação reversível.

**Non-Goals:** responder à permissão pelo Jarvis (próximo change); focar a aba exata do terminal.

## Decisions

0. **Terminal = processo do Claude Code, não `session_id`.** O `session_id` muda com `/clear` e ao retomar uma conversa (`SessionEnd` + `SessionStart` com `source: clear`/`resume`), o que trocaria o número do terminal no meio do uso. O hook não recebe o pid, mas é filho dele: conferido em 09/10/2026 que um comando rodado pelo Claude Code tem a cadeia `sh → zsh → claude`. O script sobe pelos pais (`ps -o ppid=,comm=`) até o processo `claude` e anota o pid. Esse pid é a chave do terminal, e `os.kill(pid, 0)` diz se ele ainda está aberto (sem depender do `~/.claude/sessions`). Se não achar o `claude` na cadeia, usa o `session_id`.
1. **Hook = script curto que só anota.** `claude_event.py`, só biblioteca padrão, rodado pelo `/usr/bin/python3` do macOS (sem `uv`, que demora para subir). O `install.py` copia o script para `~/Library/Application Support/Jarvis/hooks/`, um caminho estável que não muda se o repositório sair de `~/Downloads`. **Nunca falha para fora:** o comando do hook é `/usr/bin/python3 "<script>" >/dev/null 2>&1 || true`. Sem isso, um script ausente faz o Python sair com código 2 (conferido em 09/10/2026), e código 2 num hook pode **bloquear** a ação. Além disso, a saída de um hook assíncrono é entregue à conversa no turno seguinte, então qualquer erro impresso entraria no contexto de todas as sessões. Ele lê o JSON do stdin, **extrai só campos permitidos** e acrescenta uma linha em `~/Library/Application Support/Jarvis/claude-events.jsonl` (permissão 600). Campos guardados: `t` (hora), `evento`, `pid` (do `claude`), `sessao` (`session_id`), `pasta` (`cwd`), `nome` (`session_title`, quando houver), `tipo` (`notification_type`), `ferramenta` (`tool_name`) e `resumo`. O `resumo` é o comando (`Bash`), o caminho (`Edit`/`Write`/`Read`), a URL (`WebFetch`) ou o nome da ferramenta MCP, cortado em 120 caracteres. Nunca guarda `prompt`, `message` livre, conteúdo de arquivo nem saída de comando. Alternativas: `cat >>` direto (guardaria o JSON inteiro, com prompts e conteúdo de arquivos); hook HTTP para o cérebro (a porta do cérebro muda a cada execução e exigiria o token no `settings.json`).
2. **Eventos usados**, todos com `async: true` (não atrasam o Claude Code):

   | Evento | Estado do terminal |
   | --- | --- |
   | `SessionStart` | aberto (trabalhando) |
   | `UserPromptSubmit` | trabalhando (sem guardar o texto) |
   | `PermissionRequest` | pedindo permissão (com ferramenta e resumo) → **aviso** |
   | `PostToolUse`, `PostToolUseFailure` | trabalhando (a permissão foi respondida) |
   | `Notification` `idle_prompt` | esperando você → **aviso** |
   | `Stop` | terminou (marca discreta, sem tirar o HUD do lugar) |
   | `SessionEnd` | fechado (sai da lista e libera o número) |

   O `PostToolUse` dispara a cada ferramenta. O custo é subir um Python curto (~40 ms) em segundo plano, sem bloquear.

   **Limite conhecido:** não existe evento no momento em que o Kaio aprova. O `PostToolUse` só vem quando a ferramenta **termina**: um `npm test` de 5 minutos aprovado continuaria como "pedindo permissão" por 5 minutos. Se o Kaio nega, nem `PostToolUse` vem. Por isso o estado "pedindo permissão" vale até o próximo evento da sessão **ou 20 s**. Depois disso vira "trabalhando", e o aviso some junto. É o melhor possível sem ler a tela do terminal.
3. **Cérebro lê o arquivo** (`jarvis/terminals.py`): acompanha o fim do arquivo a cada 300 ms (sem dependência nova). Mantém um mapa processo → terminal: número = menor livre na primeira vez que vê o processo; estado; pasta (último pedaço do `cwd`); hora em que foi visto; pedido pendente. A cada mudança manda `terminals` (lista) a todas as conexões; nos avisos manda também `terminal_alert`. Terminais cujo processo fechou (`os.kill(pid, 0)` falha, conferido a cada 30 s) ou sem evento há 12 h saem da lista. O arquivo é reduzido às últimas 2.000 linhas quando passa de 1 MB.
4. **Interface:** `terminal_alert` mostra o HUD **sem foco** (como na voz), com um cartão de aviso no topo e o toque de "começar a ouvir". O aviso some quando o terminal sai de "pedindo permissão"/"esperando você", ou depois de 20 s. Com o painel aberto, o aviso aparece no painel e não no HUD. Painel: coluna "Terminais" (lugar da lista de perguntas da sessão no rodapé, ao lado do registro).
5. **Ferramenta local `listar_terminais`** devolve a lista atual. O cartão `terminais` é montado com a lista completa, mas o texto que vai para o modelo leva só número, pasta, estado e ferramenta, **sem o resumo** do pedido (comandos podem conter segredos). Nada executa nada.
6. **Instalação:** `install_mac.sh` chama `python3 jarvis/hooks/install.py` para mesclar os hooks no `~/.claude/settings.json`: backup em `settings.json.bak-jarvis`, só acrescenta entradas marcadas com o caminho do script do Jarvis e não mexe nas outras. Rodar de novo não duplica. `--sem-terminais` remove só as entradas do Jarvis.
7. **Sessões com permissões liberadas** (`--dangerously-skip-permissions`, modo `bypassPermissions`) não pedem permissão. Para elas só valem "esperando você" e "terminou".

## Risks / Trade-offs

- [Hooks globais tocam também as sessões de trabalho] → só anotam um arquivo local e não decidem nada. O Kaio pode desligar com `--sem-terminais` ou `disableAllHooks`.
- [O `/usr/bin/python3` some ou muda] → o hook falha calado (exit ≠ 0 não bloqueia o Claude Code). O `install.py` confere se ele existe antes de instalar.
- [Formato dos eventos muda numa versão do Claude Code] → o script lê com `.get` e ignora o que não reconhece. Teste com JSON de exemplo copiado da documentação.
- [Resumo do comando pode conter segredo (ex.: `curl -H "Authorization: …"`)] → o arquivo fica só no Mac, com permissão 600. O resumo é cortado em 120 caracteres e nunca vai para o modelo.
- [Hooks editados com sessões já abertas] → não confirmei na documentação se as sessões abertas passam a usar os hooks sem reiniciar. O aceite usa sessões abertas depois da instalação, e o resultado fica anotado aqui.
- [Saber qual janela é o "Terminal 1"] → o aviso mostra a pasta e a hora em que o terminal foi visto. Duas sessões na mesma pasta se distinguem pela hora. Mudar o título da aba do terminal fica para depois (o próprio Claude Code também mexe no título).

## Open Questions

- Falar o aviso em voz alta ("Senhor, o terminal 1 pede permissão") além de mostrar? A proposta é só mostrar, com uma variável `JARVIS_TERMINAIS_FALA` para ligar depois.

## Registro da implementação (09/10/2026)

- Hooks instalados em `~/.claude/settings.json` pelo `install_mac.sh`: os 8 eventos, `async: true`, com o comando terminando em `|| true`. As outras chaves do arquivo foram conferidas como iguais às de antes. Backup em `settings.json.bak-jarvis`.
- Observado: a sessão do Claude Code que já estava aberta (a que fez a instalação) passou a gerar eventos sozinha, alguns segundos depois de o `settings.json` mudar, sem reiniciar. O pid veio certo (o processo `claude` da sessão) e o arquivo ficou com permissão 600.
