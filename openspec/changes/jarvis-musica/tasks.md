## 1. Conta e login

- [x] 1.1 (Kaio) Criar o app em developer.spotify.com com redirecionamento `http://127.0.0.1:8888/callback` e a Web API marcada; pôr `SPOTIFY_CLIENT_ID` no `.env` (feito em 10/10/2026)
- [x] 1.2 `jarvis/spotify_login.py`: PKCE (verifier/challenge S256, `state`), servidor de uma requisição em `127.0.0.1:8888` (porta ocupada → avisa), troca do código, `refresh_token` no Keychain (`security add-generic-password -U -s jarvis-spotify`); testes com o servidor de tokens falso e o `security` falso (sem rede); aviso no `install_mac.sh` quando o Keychain não tem o token

## 2. Cliente da Web API

- [x] 2.1 `jarvis/spotify.py`: token em memória com renovação (1 min antes ou no 401; troca de `refresh_token` atualiza o Keychain; `invalid_grant` → erro "autorize de novo"), timeout de 5 s, erros traduzidos (403 Premium, 404 dispositivo, 429, rede), log sem token; testes com `httpx.MockTransport`
- [x] 2.2 Busca (`/v1/search`, `limit=5`, `market=BR`) por tipo, playlists do Kaio (`/me/playlists` paginado, cache de 10 min, escolha por nome normalizado: igual > contém > mais palavras), dispositivo deste Mac (`Computer` com o nome do Mac, senão o primeiro; sem nenhum → `open -a Spotify` e nova tentativa por 10 s) e `play` com `context_uri` (música no álbum dela, com `offset`); testes

## 3. Ferramentas

- [x] 3.1 `tocar_musica(pedido, tipo)` em `local_tools.py` (resposta com nome e artista; não encontrou → nada toca) e `controlar_musica` com `aleatorio`, `repetir` e `volume` (0–100, validado) pela API, mantendo tocar/pausar/próxima/anterior no AppleScript; rótulo "procurando no Spotify…"; descrições para o modelo; testes em `test_local_tools.py`
- [ ] 3.2 Conferência manual da escolha do modelo com o Haiku (a prova em `tests/eval/` cobre só o núcleo, não as ferramentas do Jarvis): "toca Tempo Perdido" → `tocar_musica(tipo=musica)`, "toca Legião Urbana" → `artista`, "toca minha playlist de estudo" → `minha_playlist`, "pausa" → `controlar_musica`; ajustar as descrições se errar (custa frações de centavo, avisar antes)

- [x] 3.3 Música baixa: guardar o volume e abaixar o Spotify (só se estiver aberto e tocando) no começo de um pedido de voz e da fala, voltar ao fim; volume pedido no meio vale no fim; AppleScript fora do laço de eventos; testes com o executor falso

## 4. Fechamento

- [ ] 4.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `openspec validate --all --strict`, `bash jarvis/install_mac.sh`
- [ ] 4.2 Aceite real com o Kaio: login; "toca Tempo Perdido" (fala o que tocou); "toca Legião Urbana"; "toca minha playlist de …" com nome aproximado; playlist inexistente; Spotify fechado; "volume 30", "aleatório"; "pausa" sem login (revogar e conferir a mensagem); música abaixando durante um pedido e voltando; "Jarvis" detectado com música tocando
- [ ] 4.3 `SPEC.md` (decisão da música: Web API com PKCE, Keychain, Premium obrigatório desde 02/2026) e `/opsx:archive`
