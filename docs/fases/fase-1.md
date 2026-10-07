# Fase 1 — Infra e eco

Status: **concluída em 07/10/2026**, no modo provisório `SELF_CHAT_MODE` (ver desvio 5). Plano aprovado em 07/10/2026; relatório no fim deste arquivo.

Objetivo (do `SPEC.md`): Compose no ar, instância da Evolution conectada ao chip via QR code, webhook chegando no FastAPI, resposta em eco.

Critérios de aceite:

1. Mando "oi" do meu número e recebo "oi".
2. Mensagem de outro número é ignorada, sem resposta.
3. Webhook repetido não gera resposta dupla.

## Evolution API: versão e variáveis (conferido em 07/10/2026)

Fontes: releases do GitHub `EvolutionAPI/evolution-api`, tags no Docker Hub `evoapicloud/evolution-api`, `.env.example` e código-fonte da tag `2.3.7`.

- **Imagem: `evoapicloud/evolution-api:v2.3.7`** (última estável, 05/12/2025, multiarquitetura com arm64). Usa Baileys `7.0.0-rc.9`.
- **Não usar `latest`**: hoje ela aponta para `2.4.0-rc1`, que é pré-lançamento. Existe também `2.4.0-rc2` (17/05/2026), também pré-lançamento.
- A imagem antiga `atendai/evolution-api` não recebe mais atualizações. O repositório oficial usa `evoapicloud/`.

Variáveis que a Evolution exige ou que vamos fixar (passadas pelo `environment:` do compose, **não** por `env_file`: o `LOG_LEVEL` dela tem outro formato e não queremos expor o `.env` inteiro a ela):

| Variável | Valor | Por quê |
| --- | --- | --- |
| `SERVER_TYPE` / `SERVER_PORT` | `http` / `8080` | padrão |
| `SERVER_URL` | `http://localhost:8080` | só usada em links do manager local |
| `AUTHENTICATION_API_KEY` | `${EVOLUTION_API_KEY}` | chave global da API (header `apikey`) |
| `AUTHENTICATION_EXPOSE_IN_FETCH_INSTANCES` | `false` | não devolver chaves na listagem |
| `DATABASE_PROVIDER` | `postgresql` | obrigatório |
| `DATABASE_CONNECTION_URI` | `postgresql://…@postgres:5432/evolution?schema=evolution_api` | banco **separado** (`evolution`) no mesmo Postgres |
| `DATABASE_CONNECTION_CLIENT_NAME` | `evolution` | padrão |
| `DATABASE_SAVE_DATA_*` | `INSTANCE=true`, `NEW_MESSAGE`/`HISTORIC`/`CONTACTS`/`CHATS`/`LABELS`=`false` | a fonte de verdade é o nosso banco; menos cópias de dados pessoais |
| `CACHE_REDIS_ENABLED` / `CACHE_REDIS_URI` | `true` / `redis://redis:6379/6` | a Evolution guarda sessão e cache no Redis |
| `CACHE_REDIS_SAVE_INSTANCES` | `false` | sessão fica no Postgres e no volume |
| `CACHE_LOCAL_ENABLED` | `false` | padrão |
| `WEBHOOK_GLOBAL_ENABLED` | `false` | o webhook global **não** envia headers customizados; usamos webhook por instância |
| `DEL_INSTANCE` | `false` | nunca apagar a instância sozinha |
| `TELEMETRY_ENABLED` | `false` | o padrão é `true` |
| `LOG_LEVEL` | `ERROR,WARN,INFO` | sem `WEBHOOKS`/`VERBOSE`, que logariam conteúdo das mensagens |
| `LANGUAGE` | `pt-BR` | |
| `CONFIG_SESSION_PHONE_CLIENT` | `Assistente` | nome do aparelho no celular |
| `CONFIG_SESSION_PHONE_VERSION` | vazio | só preencher se o QR não aparecer (problema conhecido quando o WhatsApp Web muda de versão) |
| `RABBITMQ_ENABLED`, `SQS_ENABLED`, `WEBSOCKET_ENABLED`, `S3_ENABLED`, integrações (Typebot, Chatwoot…) | `false` | não usamos |

**Webhook com header secreto.** Pelo código da 2.3.7, o webhook por instância aceita `headers` arbitrários e os envia em cada chamada. Na criação da instância (`POST /instance/create`) passamos:

```json
{
  "instanceName": "assistente",
  "integration": "WHATSAPP-BAILEYS",
  "qrcode": true,
  "webhook": {
    "enabled": true,
    "url": "http://app:8000/webhook/evolution",
    "headers": {"X-Webhook-Secret": "<WEBHOOK_SECRET>"},
    "byEvents": false,
    "base64": true,
    "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]
  }
}
```

**Endereçamento LID.** Com Baileys 7, o `remoteJid` pode chegar como `xxxx@lid` em vez do número. A Evolution 2.3.7 já troca pelo `remoteJidAlt` quando existe, mas o nosso parser também lê `remoteJidAlt` por garantia.

## Arquivos

```text
pyproject.toml              # uv, Python 3.12, ruff, pytest (marcador eval já registrado)
uv.lock
Dockerfile                  # python:3.12-slim + uv, multiarquitetura
docker-compose.yml          # evolution-api, postgres, redis, app (+ postgres-test no perfil "test")
                            # o SQL que cria o banco "evolution" vai embutido (configs.content)
alembic.ini
app/
  __init__.py
  main.py                   # FastAPI: POST /webhook/evolution, GET /health
  config.py                 # Settings (pydantic-settings) lidas do .env
  types.py                  # IncomingMessage, OutgoingMessage (tipos próprios)
  security.py               # comparação do segredo, normalização de número, allowlist
  handler.py                # processa a mensagem em background (fase 1: eco)
  channel/
    __init__.py
    evolution.py            # parse_webhook(), send_text(), create_instance(), connect()
    setup.py                # CLI: uv run python -m app.channel.setup  (cria instância e mostra QR)
  db/
    __init__.py
    base.py                 # engine/session async
    models.py               # Message
    repo.py                 # register_incoming() com ON CONFLICT, log_outgoing()
    migrations/             # Alembic (env.py async) + 0001_messages.py
tests/
  conftest.py
  fixtures/evolution/       # payloads MESSAGES_UPSERT de exemplo (JSON)
  unit/
    test_evolution_parse.py
    test_allowlist.py
    test_webhook_secret.py
    test_idempotency.py
    test_send_text.py
```

`app/agent/`, `app/domain/` etc. **não** são criados nesta fase.

## Decisões

1. **Banco da Evolution separado.** Mesmo contêiner Postgres, banco `evolution` criado por script de init; nosso banco é `POSTGRES_DB`. Um backup, uma senha, sem misturar tabelas.
2. **Portas.** Só duas, e só em `127.0.0.1`: Evolution `127.0.0.1:8080` (para abrir `/manager` e escanear o QR) e app `127.0.0.1:8000` (para `/health` em dev). Postgres e Redis sem porta publicada. O webhook vai pela rede interna `http://app:8000`. No VPS (fase 6) a porta da Evolution sai do compose.
3. **SQLAlchemy async** com `psycopg` 3 (a `DATABASE_URL` do `.env.example` já é `postgresql+psycopg`), compatível com FastAPI async e `httpx.AsyncClient`.
4. **Idempotência atômica.** `INSERT … ON CONFLICT (wa_message_id) DO NOTHING RETURNING id`. Sem linha de volta = duplicata = ignora. Resiste a dois webhooks simultâneos, sem corrida entre "consultar" e "inserir".
5. **Ordem no webhook:** header secreto (401 se errado, comparação em tempo constante) → evento ≠ `messages.upsert` vira 200 e ignora → parse → `fromMe` ignora → grupo/status/newsletter/broadcast ignora → remetente fora da allowlist ignora → tipo sem texto ignora (áudio e imagem só na fase 4) → dedupe/grava → 200 → eco em `BackgroundTasks`.
6. **`fromMe` sempre ignorado.** As respostas do bot saem do chip e voltam como `messages.upsert` com `fromMe=true`; sem isso o eco viraria um laço infinito.
7. **Nono dígito.** Números brasileiros antigos às vezes aparecem no JID sem o 9 depois do DDD (`55 61 8xxx-xxxx` em vez de `55 61 98xxx-xxxx`). A allowlist normaliza e aceita as duas formas de `OWNER_PHONE`. `send_text` envia sempre para `OWNER_PHONE` e rejeita qualquer outro destino.
8. **Texto aceito na fase 1:** `message.conversation` e `message.extendedTextMessage.text`.
9. **Saída também é registrada** em `messages` (`direction='out'`, `wa_message_id` devolvido pelo `sendText`), como pede o caminho da mensagem no `SPEC.md`.
10. **Criação da instância por script** (`app.channel.setup`) em vez de curl solto: fica versionado, usa a mesma `EVOLUTION_API_KEY` e garante o header secreto. Fica em `app/channel/`, então continua sendo o único lugar que conhece a Evolution.
11. **Logs** só com metadados (id da mensagem, tipo, decisão tomada), nunca o corpo da mensagem nem chaves.

## Testes

Todos sem rede e sem LLM. O Postgres de teste é um serviço `postgres-test` no perfil `test` do compose (`docker compose --profile test up -d postgres-test`, porta `127.0.0.1:5433`, dados em `tmpfs`). A `TEST_DATABASE_URL` é separada de `DATABASE_URL`, e os testes se recusam a rodar contra um banco cujo nome não termine em `_test`.

- **Parse** (`test_evolution_parse.py`): payloads salvos em `tests/fixtures/evolution/` com texto simples, `extendedTextMessage`, `fromMe`, grupo, status, `@lid` com `remoteJidAlt`, áudio (sem texto), evento `connection.update`. Os primeiros payloads vêm da estrutura documentada; depois de conectar o chip, troco por payloads reais capturados (sem dados pessoais) e registro isso aqui.
- **Allowlist** (`test_allowlist.py`): dono passa; com e sem nono dígito; outro número, grupo, status e newsletter são barrados; `send_text` para outro número levanta erro.
- **Header secreto** (`test_webhook_secret.py`, via `TestClient`): sem header 401; header errado 401; certo 200.
- **Idempotência** (`test_idempotency.py`, contra Postgres de teste): mesmo payload duas vezes gera uma linha de entrada e uma chamada de envio (envio substituído por um dublê).
- **Eco ponta a ponta no app** (sem Evolution): webhook válido do dono gera `send_text("oi")` e linha `out`; outro número não gera nada.
- **`send_text`** com `httpx.MockTransport`: URL, header `apikey` e corpo `{"number", "text"}` corretos.

O aceite real (critérios 1 a 3) é manual com o celular, e o resultado será registrado aqui.

## Passo a passo previsto no plano (versão final no relatório)

1. Abrir o Docker Desktop. Hoje o Docker está instalado, mas o daemon não está rodando.
2. `cp .env.example .env` e preencher `OWNER_PHONE`, `EVOLUTION_API_KEY`, `WEBHOOK_SECRET` e `POSTGRES_PASSWORD` (segredos longos: `openssl rand -hex 32`).
3. `docker compose up -d` e depois `docker compose exec app alembic upgrade head`.
4. `uv run python -m app.channel.setup`: cria a instância com o webhook e o header secreto, e imprime o QR no terminal (ou abrir `http://localhost:8080/manager`).
5. No celular com o chip: WhatsApp Business → Aparelhos conectados → Conectar aparelho → escanear.
6. Do número pessoal, mandar "oi" para o chip.

## Dúvidas para você

1. **Chip e WhatsApp Business**: já estão prontos? Sem isso dá para fazer tudo menos o aceite manual.
2. **Nono dígito**: ok aceitar as duas formas do `OWNER_PHONE` (decisão 7)? Continua sendo um número só.
3. **`.env.example`**: vou acrescentar `TEST_DATABASE_URL` e `APP_WEBHOOK_URL` (padrão `http://app:8000/webhook/evolution`). Nenhuma decisão do `SPEC.md` muda.

## Observação sobre o git

O repositório git que existia era a sua pasta pessoal inteira (`/Users/kaio`, sem commits). Rodei `git init` dentro de `life-manager/`, como o README pede. O repositório da pasta pessoal não foi mexido.

---

# Relatório da fase 1

## O que foi feito

- Projeto `uv` (Python 3.12) com ruff e pytest. O marcador `eval` já fica registrado e excluído por padrão.
- `docker-compose.yml` com `evolution-api` (`v2.3.7`), `postgres:16`, `redis:7` e `app`. Mais o `postgres-test` no perfil `test`.
- `app/channel/evolution.py`: `parse_webhook` → `IncomingMessage`; `EvolutionClient.send_text` só para `OWNER_PHONE`; `create_instance`, `connect` e `connection_state`.
- `app/channel/setup.py`: cria a instância com webhook e header secreto e salva o QR em `data/qrcode.png`.
- `POST /webhook/evolution`: valida o segredo (401), aplica a allowlist, deduplica com `ON CONFLICT`, responde na hora e faz o eco em `BackgroundTasks`. Também `GET /health`.
- Tabela `messages` (migração `0001`), aplicada automaticamente quando o contêiner `app` sobe.
- 37 testes unitários, todos passando (`uv run pytest`: 37 passed). `ruff check` limpo.

## Verificado de verdade (07/10/2026)

| Item | Resultado |
| --- | --- |
| Stack sobe no Mac arm64 | ok: os 4 serviços no ar; `app` healthy |
| Evolution responde | ok: `version 2.3.7`, `whatsappWebVersion 2.3000.1049576524` |
| Banco `evolution` separado + tabela `messages` no nosso banco | ok |
| `app.channel.setup` cria a instância e gera o QR | ok |
| Webhook configurado na instância | ok: `url=http://app:8000/webhook/evolution`, eventos `MESSAGES_UPSERT` e `CONNECTION_UPDATE`, `base64=true`, header `X-Webhook-Secret` presente |
| Evolution → app pela rede interna, com segredo aceito | ok: `POST /webhook/evolution 200` do contêiner da Evolution |
| Postgres e Redis sem porta publicada; Evolution e app só em `127.0.0.1` | ok |

## Critérios de aceite

| Critério | Teste automatizado | Teste real com o celular |
| --- | --- | --- |
| "oi" do meu número volta "oi" | `test_eco_do_dono`, `test_mensagem_para_si_mesmo_ganha_eco_com_marca` | **ok** em 07/10 15:42: "oi" na conversa consigo mesmo voltou "🤖 oi"; em `messages`, uma linha `in` e uma `out` |
| Outro número é ignorado | `test_webhook_ignora_sem_responder[text_stranger]`, `test_outro_numero_nao_grava_nada`, `test_modo_provisorio_ignora` | coberto por teste; confirmar quando alguém escrever para você (nada deve ser respondido) |
| Webhook repetido não responde duas vezes | `test_webhook_repetido_responde_uma_vez`, `test_webhooks_simultaneos_respondem_uma_vez` | coberto pelo teste (difícil de forçar com o celular) |

## Desvios do plano

1. **SQL de init embutido no compose** (`configs.content`) em vez de `docker/postgres/init/`. O Docker Desktop não tem permissão do macOS para montar arquivos de `~/Downloads` ("operation not permitted"). Embutido, o compose funciona em qualquer pasta, sem mexer nas permissões.
2. **Migração roda quando o `app` sobe** (`alembic upgrade head && uvicorn …`). Continua valendo rodar `uv run alembic upgrade head` à mão.
3. **`.env` gerado** a partir do `.env.example`, com `EVOLUTION_API_KEY`, `WEBHOOK_SECRET` e `POSTGRES_PASSWORD` aleatórios (`openssl rand -hex`), permissão 600, ignorado pelo git. **`OWNER_PHONE` ainda está com o valor de exemplo `55`.**
4. Fixtures de payload montados a partir do código-fonte da Evolution 2.3.7, não capturados de mensagens reais. Trocar por capturas reais depois do aceite manual (sem dados pessoais).

5. **Modo provisório `SELF_CHAT_MODE`** (pedido em 07/10/2026; registrado no `SPEC.md` antes do código). Sem o chip, a instância foi conectada ao número do próprio dono, que fala com o bot na conversa consigo mesmo. Com o modo ligado:
   - `fromMe` é aceito só na conversa do dono consigo mesmo;
   - as respostas começam com `🤖 ` e são descartadas quando voltam pelo webhook;
   - mensagens do dono para terceiros e de terceiros para o dono seguem ignoradas.

   Testes em `tests/unit/test_self_chat_mode.py`. Para voltar ao plano original: `SELF_CHAT_MODE=false`, desconectar o aparelho no celular pessoal e escanear o QR com o chip.

Observação do teste real: a resposta enviada pela API não voltou como `messages.upsert` (só 1 webhook no log). A Evolution parece reportar envios pela API como evento `SEND_MESSAGE`, que não assinamos. O filtro pela marca `🤖 ` fica como proteção, caso isso mude.

## Fora desta fase (de propósito)

Áudio, imagem, LLM, demais tabelas, alerta de `CONNECTION_UPDATE` (fase 6). Hoje esse evento chega e é ignorado com 200.

## Passo a passo (versão final)

1. Docker Desktop aberto.
2. No `.env`, preencher `OWNER_PHONE` com o seu número pessoal (`55` + DDD + número, só dígitos). Os segredos já estão gerados.
3. `docker compose up -d --build` e conferir com `docker compose ps`. O `app` fica healthy em cerca de 15 s.
4. `EVOLUTION_API_URL=http://localhost:8080 uv run python -m app.channel.setup`. A instância `assistente` já existe; o comando só gera um QR novo em `data/qrcode.png`.
   Alternativa: abrir `http://localhost:8080/manager` (a chave é a `EVOLUTION_API_KEY` do `.env`).
5. No celular com o chip: WhatsApp Business → ⋮ → Aparelhos conectados → Conectar aparelho → escanear. O QR expira em cerca de 40 s; se expirar, repita o passo 4.
6. Conferir: rodar o passo 4 de novo deve responder "Instância já está conectada."
7. Do número pessoal, mandar "oi" para o chip e receber "oi". De outro número: nada. Acompanhar com `docker compose logs -f app`.
8. Depois de mudar o `.env`: `docker compose up -d app` para o app reler a configuração.

**QR não aparece ou não conecta:** problema conhecido quando o WhatsApp Web muda de versão. Defina `CONFIG_SESSION_PHONE_VERSION` no serviço `evolution-api` com a versão de `https://web.whatsapp.com/check-update?version=0&platform=web` e recrie o contêiner.

**Testes:** `docker compose --profile test up -d postgres-test && uv run pytest`.
