## Context

`controlar_musica` (em `jarvis/local_tools.py`) manda AppleScript fixo ao Spotify: tocar, pausar, próxima, anterior. Não há busca: o AppleScript do Spotify não pesquisa o catálogo nem lista as playlists do Kaio. O Kaio é Premium e quer pedir música pelo nome, incluindo as playlists dele.

### Fatos conferidos (10/10/2026)

- **Web API em modo de desenvolvimento** (guia oficial da migração de fevereiro de 2026, developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide):
  - todo app em modo de desenvolvimento exige que o **dono tenha Premium ativo**. Se o Premium cair, o app para até voltar;
  - limite de 1 Client ID por desenvolvedor e 5 usuários por app (aqui só o Kaio);
  - `GET /v1/search` continua, com `limit` de **no máximo 10** (padrão 5);
  - `GET /users/{id}/playlists` saiu; o substituto para o próprio usuário é `GET /me/playlists`;
  - o conteúdo de uma playlist (`items`) só vem para playlists que o usuário tem ou colabora. Aqui não importa: o Jarvis toca a playlist pelo URI, sem ler as faixas;
  - de faixas e artistas saíram `popularity`, `followers` e `available_markets`. Os nomes dos artistas continuam;
  - os endpoints do player ("Get Available Devices", "Start/Resume Playback") não aparecem entre os removidos.
- **Redirecionamento do login** (developer.spotify.com/documentation/web-api/concepts/redirect_uri):
  - `localhost` não é aceito;
  - um IP de loopback explícito, `http://127.0.0.1:PORTA`, é aceito em HTTP;
  - registrado **sem porta**, o app aceita qualquer porta no pedido. Só vale para IP de loopback.
- **AppleScript do Spotify:** `play track "spotify:playlist:…"` é usado por várias ferramentas, mas não tem documentação oficial (resultados de busca de 10/10/2026). Por isso o caminho principal é a Web API, e o AppleScript fica só nas ações simples que já funcionam hoje.

## Goals / Non-Goals

**Goals:**
- "Toca X" toca X em poucos segundos, dizendo o que tocou.
- As playlists do Kaio entram pelo nome aproximado.
- Login uma vez só, sem segredo guardado no projeto.

**Non-Goals:**
- Editar playlists, fila, curtidas, recomendação, outros aparelhos e outros serviços (ver a proposta).

## Decisions

1. **Web API para buscar e tocar; AppleScript continua nas ações simples.**
   - `tocar_musica`:
     1. `GET /v1/search?type=…&limit=5&market=from_token`;
     2. `PUT /v1/me/player/play?device_id=…`: música toca no álbum dela (`context_uri` do álbum + `offset.uri` da faixa), para seguir quando acabar (com `uris=[faixa]` a reprodução pararia no fim); artista, álbum e playlist vão em `context_uri`.
   - `controlar_musica`:
     - aleatório: `PUT /me/player/shuffle`;
     - repetir: `PUT /me/player/repeat`;
     - volume: `PUT /me/player/volume`;
     - tocar, pausar, próxima e anterior continuam no AppleScript de hoje, que funciona sem login e sem rede.
   - Alternativa descartada: só AppleScript. Ele não busca, e o "tocar URI" não tem documentação.

2. **Dispositivo deste Mac.**
   - `GET /me/player/devices` e escolha do dispositivo do tipo `Computer` cujo nome é o nome do Mac (`scutil --get ComputerName`). Se não houver, vale o primeiro `Computer`.
   - Sem dispositivo: `open -a Spotify`, com nova tentativa a cada 1 s por até 10 s.
   - O `device_id` vai no `play`, para não tocar no celular.

3. **Escolha do resultado.**
   - Música, artista, álbum e playlist do catálogo: o primeiro resultado da busca (a ordem é a do Spotify).
   - `minha_playlist`: `GET /me/playlists` paginado (50 por página, até 500). A comparação normaliza os nomes: minúsculas, sem acento, sem emoji nem pontuação. A ordem de preferência é:
     1. nome igual;
     2. nome que contém o pedido;
     3. maior número de palavras do pedido presentes no nome.
   - Empate fica com a primeira na ordem do Spotify. A lista fica em memória por 10 min.
   - A resposta ao modelo traz o nome e o artista do que tocou. O modelo fala "Tocando …".

4. **Login PKCE (`python -m jarvis.spotify_login`).**
   - Cria o `code_verifier`, abre o navegador em `accounts.spotify.com/authorize` e sobe um servidor de uma requisição só em `127.0.0.1:8888` (`/callback`). Confere o `state`, troca o código pelo token e guarda o `refresh_token` no Keychain: `security add-generic-password -U -s jarvis-spotify -a kaio -w …`.
   - Escopos: `playlist-read-private`, `playlist-read-collaborative`, `user-read-playback-state` e `user-modify-playback-state`.
   - No app do Spotify, o redirecionamento registrado é **`http://127.0.0.1:8888/callback`, com porta fixa** (decisão de 10/10/2026, ao criar o app: o painel do Spotify aceita com certeza e o login fica simples). Porta ocupada → o login avisa e para.
   - O `install_mac.sh` avisa como fazer o login se o Keychain não tiver o token. O login nunca roda sozinho.

5. **Tokens no cérebro.**
   - O `access_token` fica só em memória e é renovado com o `refresh_token` do Keychain quando falta 1 min para expirar ou quando a API responde 401.
   - Se a renovação devolver um `refresh_token` novo, o Keychain é atualizado.
   - Se a renovação for recusada (`invalid_grant`), o erro volta ao modelo como "autorize o Spotify de novo: `python -m jarvis.spotify_login`", sem detalhe técnico.
   - Nenhum token vai para o log: o cliente registra só o método, o caminho e o status.

6. **Erros da API → mensagens curtas ao modelo:**
   - 403 de Premium: "O Spotify exige Premium para isso.";
   - 404 de dispositivo: "O Spotify deste Mac não está pronto.";
   - 429: "O Spotify pediu para esperar um pouco." (sem nova tentativa automática);
   - rede fora: "Sem conexão com o Spotify.";
   - timeout de 5 s por chamada.

7. **Modelo.**
   - O Jarvis não tem grupos de ferramentas por intenção (isso é do agente do WhatsApp): todas as ferramentas locais vão em todo turno. `tocar_musica` acrescenta ~150 tokens por pergunta (fração de centavo com o Haiku).
   - Descrição: "Use para tocar algo pelo nome. Para pausar e pular, use `controlar_musica`."
   - Sem login, a resposta traz o comando num cartão (a interface mostra; a voz só diz que é preciso autorizar).
   - O rótulo do passo é "procurando no Spotify…".

8. **Música baixa (ducking), pelo AppleScript** (funciona sem login e sem rede):
   - no começo de um pedido de voz (`wake` ou `voice_start`) e no começo da fala, se o Spotify estiver tocando (`player state is playing`), o cérebro guarda o `sound volume` e põe em 25% dele (mínimo 10);
   - quando a fala termina e não há turno em andamento, volta ao guardado;
   - `controlar_musica(volume=…)` durante o ducking troca o valor guardado (o volume pedido vale no fim);
   - o AppleScript roda fora do laço de eventos (`asyncio.to_thread` ou subprocesso assíncrono), para não atrasar a fala;
   - o Spotify fechado ou parado não é tocado (`application "Spotify" is running` antes de falar com ele, para não abri-lo).

## Risks / Trade-offs

- **[O primeiro resultado não é o que o Kaio queria]** → a resposta diz o que tocou, e o Kaio corrige com outro pedido mais específico ("toca Tempo Perdido da Legião"). O modelo pode pôr o artista no texto da busca.
- **[Spotify muda o modo de desenvolvimento de novo]** → o login e a busca ficam isolados em `jarvis/spotify.py`. As ações simples continuam no AppleScript, sem a API.
- **[Premium cai]** → o app para, e a mensagem do 403 diz por quê.
- **[Token vazado]** → só existe no Keychain e na memória do cérebro. O Kaio revoga em spotify.com/account/apps.
- **[Spotify demora a abrir]** → até 10 s de espera, depois avisa.
- **[Música alta atrapalha a palavra "Jarvis"]** → o ducking só começa depois da palavra; o aceite mede a detecção com música tocando. Se falhar muito, fica para a calibração.
- **[Playlist com nome parecido]** → regra de preferência determinística, e a resposta diz qual tocou.

## Open Questions

- Nenhuma. O nome do app no developer.spotify.com e o Client ID ficam com o Kaio (tarefa 1.1).
