# Primeiro prompt para o Claude Code

Cole o texto abaixo na primeira sessão, com o Claude Code aberto nesta pasta.

---

Leia `CLAUDE.md` e `SPEC.md` inteiros. Vamos começar a **Fase 1 — Infra e eco**.

Contexto: desenvolvo localmente num MacBook Air M5 (arm64) com Docker e depois faço deploy num VPS Oracle ARM (também arm64). Na fase 1 tudo roda local; o deploy é na fase 6.

Objetivo da fase 1:
- Projeto Python com `uv` (`pyproject.toml`, ruff, pytest configurados).
- `docker-compose.yml` com `evolution-api` (v2, integração Baileys), `postgres`, `redis` e `app` (FastAPI). Webhook da Evolution apontando para o `app` pela rede interna do Docker; nenhuma porta da Evolution ou do Postgres exposta fora do que for preciso para eu escanear o QR code localmente.
- `app/channel/evolution.py`: parse do evento `MESSAGES_UPSERT` em um tipo próprio `IncomingMessage`, `send_text` só para `OWNER_PHONE`.
- `POST /webhook/evolution`: valida `X-Webhook-Secret`, aplica a allowlist, deduplica por `wa_message_id`, responde 200 na hora e processa em background, respondendo com eco do texto recebido.
- Tabela `messages` com Alembic (só ela nesta fase).
- Testes unitários para: parse do webhook (use payloads de exemplo salvos em `tests/fixtures/`), allowlist, header secreto e idempotência.
- Um passo a passo em `docs/fases/fase-1.md` de como subir, criar a instância e escanear o QR code.

Antes de escrever código, crie `docs/fases/fase-1.md` com o plano (arquivos, decisões, testes, dúvidas) e espere minha aprovação. Confirme no plano a versão atual da imagem da Evolution API v2 e as variáveis de ambiente que ela exige, consultando a documentação oficial em vez de presumir.

Critérios de aceite (do `SPEC.md`): mando "oi" do meu número e recebo "oi"; mensagem de outro número é ignorada; webhook repetido não gera resposta dupla.
