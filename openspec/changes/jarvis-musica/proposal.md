## Why

Hoje o Jarvis só abre o Spotify e faz tocar, pausar, próxima e anterior (`controlar_musica`). O Kaio quer pedir o que ouvir: "toca Legião Urbana", "toca Tempo Perdido", "toca minha playlist de estudo" (pedido de 10/10/2026). Para escolher a música, é preciso buscar no catálogo e nas playlists dele, e só a Web API oficial do Spotify faz isso. Ela pede Premium, e o Kaio é Premium.

## What Changes

- **Nova ferramenta `tocar_musica(pedido, tipo)`:** busca e toca no Spotify do Mac.
  - `tipo` pode ser `musica`, `artista`, `album`, `playlist` ou `minha_playlist`. O modelo escolhe pelo pedido: "toca Tempo Perdido" vira música, "toca Legião" vira artista, "toca minha playlist de estudo" vira `minha_playlist`.
  - Toca o primeiro resultado da busca. A resposta diz o que está tocando ("Tocando Tempo Perdido, da Legião Urbana."), para o Kaio corrigir se veio a coisa errada.
  - As playlists do Kaio (as dele e as que ele segue) entram pelo nome, com comparação tolerante a acentos e a pedaços do nome.
  - Se o Spotify estiver fechado, o Jarvis abre o app e espera ele aparecer como dispositivo.
- **`controlar_musica` ganha `aleatorio`, `repetir` e `volume`** (0 a 100), pela Web API. Tocar, pausar, próxima e anterior continuam pelo AppleScript, que funciona mesmo sem o login.
- **Login uma vez só:** `python -m jarvis.spotify_login` abre o navegador, o Kaio autoriza o app (PKCE, sem segredo de cliente) e o token de renovação fica no Keychain do macOS. Daí em diante o Jarvis renova o acesso sozinho.
- **Configuração:** o Kaio cria um app em developer.spotify.com (é dono, com Premium) e põe o Client ID no `.env` (`SPOTIFY_CLIENT_ID`). Não há segredo de cliente.
- **Música baixa enquanto o Jarvis ouve e fala:** o Spotify abaixa durante um pedido de voz e durante a resposta, e volta ao volume de antes (AppleScript, sem login).
- Uma música pedida toca dentro do álbum dela, para não parar quando acabar.
- Tocar não pede confirmação: não grava nada nem envia nada a terceiros, e a música errada se corrige com outro pedido.

## Non-goals

- Criar ou editar playlists, curtir músicas ou mexer na fila. Fica para depois, se o Kaio pedir.
- Recomendação ("toca algo parecido", "toca algo animado"). O Jarvis só toca o que foi pedido pelo nome.
- Tocar em outro aparelho (celular, caixa de som): só o Spotify deste Mac.
- Apple Music e outros serviços.
- Escolher entre vários resultados por voz ("qual das três?").

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `ferramentas-locais`: a lista de ações permitidas ganha `tocar_musica`, e `controlar_musica` ganha aleatório, repetir e volume; a música abaixa enquanto o Jarvis ouve e fala. Entra também o acesso à conta Spotify do Kaio: login PKCE, token no Keychain, só leitura das playlists e controle do player.

## Impact

- **Cérebro (Python):**
  - `jarvis/spotify.py` é novo: cliente da Web API com `httpx`, renovação de token, busca, playlists do Kaio, dispositivo e player;
  - `jarvis/spotify_login.py` é novo: login PKCE com redirecionamento para `http://127.0.0.1:<porta>/callback`;
  - `jarvis/local_tools.py`: ferramenta `tocar_musica`, `controlar_musica` ampliada e rótulos de passo em `agent.py`.
- **Dependências:** nenhuma nova (`httpx` já existe; o Keychain é usado pelo `security` do macOS).
- **Rede:** api.spotify.com e accounts.spotify.com, só quando o Kaio pede música.
- **Segredos:** o token de renovação fica no Keychain, nunca no log nem no `.env`. O Client ID não é segredo.
- **Custo:** zero no Spotify (o Premium o Kaio já tem). No modelo, a ferramenta a mais no grupo de ferramentas locais cabe no mesmo turno.
- **`SPEC.md`:** decisão da música (Web API com PKCE, Keychain, Premium obrigatório desde fevereiro de 2026).
