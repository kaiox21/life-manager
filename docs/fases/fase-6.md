# Fase 6 — Endurecimento e deploy

Status: **em implementação** (08/10/2026). Plano aprovado em 08/10/2026 ("segue a fase 6").

Padrões enquanto as dúvidas não forem respondidas:
- servidor: Oracle, com Hetzner como plano B;
- backup: via `rclone` (serve para R2, B2 ou Google Drive; o destino é configurado na hora);
- alerta: ntfy.

Objetivo (do `SPEC.md`): deploy no VPS, backup, logs e alerta quando a instância da Evolution desconectar (`CONNECTION_UPDATE`).

Critérios de aceite:

1. Restauração de backup testada.
2. O Kaio recebe aviso quando o WhatsApp cai.

## Como fica a infraestrutura

```text
VPS Oracle (ARM, São Paulo)            fora do VPS
┌───────────────────────────────┐
│ docker compose                │      ┌─────────────────────────────┐
│  evolution-api ─┐             │      │ armazenamento de backup     │
│  postgres       ├ rede interna│ ───► │ (pg_dump cifrado, 30 dias)  │
│  redis          │             │      └─────────────────────────────┘
│  app ───────────┘             │      ┌─────────────────────────────┐
│  backup (cron diário)         │ ───► │ canal de alerta (fora do    │
└───────────────────────────────┘      │ WhatsApp) + dead man switch │
  porta aberta: só SSH (chave)         └─────────────────────────────┘
```

**Nenhuma porta além do SSH.** A Evolution conecta para fora (WhatsApp), e o webhook continua na rede interna do Docker, então não precisa de domínio nem de HTTPS público. O manager da Evolution (para o QR) é acessado por túnel SSH (`ssh -L 8080:localhost:8080`).

## Arquivos

```text
docker-compose.prod.yml        # sobrescreve o de dev: sem portas publicadas (só 127.0.0.1 p/ túnel),
                               # rotação de logs, restart, serviço de backup
deploy/
  bootstrap.sh                 # 1ª vez no VPS: Docker, firewall (só SSH), usuário, fuso, swap
  deploy.sh                    # do Mac: git pull no VPS + docker compose up --build + migrações
  backup.sh                    # pg_dump (os 2 bancos) | gzip | age (chave pública) -> destino; apaga > 30 dias
  restore.sh                   # baixa, decifra com a chave privada (fica no Mac) e restaura num banco
  README.md                    # passo a passo
app/
  alerts.py                    # Notifier fora do WhatsApp (dúvida 3) + dead man's switch (ping periódico)
  main.py                      # CONNECTION_UPDATE -> alerta quando a instância cai e quando volta
  scheduler.py                 # job de heartbeat (ping a cada 5 min)
tests/unit/
  test_connection_alert.py     # parse do connection.update; avisa na queda e na volta, sem repetir
```

## Decisões

1. **Mesmo `docker-compose.yml` + um arquivo `prod` por cima**: as mesmas imagens do Mac (arm64 nos dois, como previa o `SPEC.md`).
   - Em produção: Evolution e app sem porta pública; o manager só por túnel SSH.
   - Logs do Docker com rotação (`max-size 10m`, 5 arquivos).
2. **Deploy por git**:
   - O VPS clona o repositório público e o `deploy.sh` faz `git pull` e `docker compose up -d --build`. A migração já roda na subida do app.
   - O `.env` vai uma vez por `scp`, com permissão 600, e nunca passa pelo git.
   - O `data/meios_pagamento.yaml` não é necessário: os dados vão no dump (decisão 6).
3. **Alerta do WhatsApp por outro canal.** Quando o WhatsApp cai, o bot não consegue avisar pelo próprio WhatsApp.
   - O evento `CONNECTION_UPDATE` (já assinado desde a fase 1) dispara o alerta pelo canal da dúvida 3, na queda (`state=close`) e na volta (`state=open`).
   - Não repete o aviso enquanto o estado não muda.
4. **Dead man's switch**: o app manda um "estou vivo" a cada 5 min para um serviço externo (ex.: healthchecks.io, grátis). Se o VPS inteiro cair, o serviço avisa por e-mail. Sem isso, uma queda total passaria em silêncio.
5. **Backup diário às 03:00**:
   - `pg_dump` do banco do app **e** do banco da Evolution (a sessão do WhatsApp).
   - Cifrado com `age`: a chave pública fica no VPS e a **privada só no seu Mac**. Quem invadir o VPS ou o armazenamento não lê os backups.
   - Enviado para fora do VPS (dúvida 2); retenção de 30 dias.
   - Falha no backup gera alerta.
6. **Migração dos dados reais = teste de restauração.** Para levar ao VPS o que já existe no Mac (gastos, eventos, pessoas, cartões), uso o próprio `backup.sh` no Mac e o `restore.sh` no VPS. Isso cumpre o critério 1 de verdade, com conferência de contagem de linhas e de uma fatura antes e depois.
7. **Troca do Mac pelo VPS sem dois bots ao mesmo tempo**:
   - Primeiro o bot do Mac é desligado (`docker compose down`); depois o VPS sobe.
   - A sessão do WhatsApp: escaneio o QR de novo no VPS (mais simples e seguro do que copiar a sessão).
   - Ordem e checklist no `deploy/README.md`.
8. **Firewall**: security list da Oracle e `iptables`/`ufw` só com a porta 22; SSH só com chave, sem senha.
9. **Whisper no VPS**: o modelo `small` baixa uma vez no volume. O VPS ARM tem CPU suficiente (4 OCPU / 24 GB na cota gratuita).
10. **Hetzner como plano B** (do `SPEC.md`): se a Oracle não tiver capacidade ARM em São Paulo, os scripts são os mesmos (CAX11, ARM, ~€4/mês). Só muda o `bootstrap.sh` do firewall.

## Testes

- Unitários (sem rede):
  - `connection.update` → alerta na queda e na volta, sem repetir;
  - `Notifier` falso;
  - heartbeat chamado pelo scheduler.
- `backup.sh` + `restore.sh` no Mac, com um banco descartável: dump, cifra, decifra, restaura e confere.
- Aceite real:
  - (1) restauração dos dados do Mac no VPS, com a contagem e uma fatura conferidas;
  - (2) desconectar o aparelho "Assistente" no celular e ver o alerta chegar pelo canal escolhido; reconectar e ver o aviso de volta.

## O que você vai precisar fazer

1. Criar a conta na Oracle Cloud (pay-as-you-go, região São Paulo, cartão só para verificação) e criar a VM **Ampere A1** (Ubuntu 24.04, 4 OCPU / 24 GB). Mando o passo a passo; a VM recebe a sua chave SSH pública.
2. Criar a conta do destino de backup (dúvida 2) e do canal de alerta (dúvida 3).
3. Escanear o QR de novo quando o bot subir no VPS.

## Dúvidas para você

1. **Oracle**: você já tem conta? Se a criação da VM ARM falhar por falta de capacidade (acontece), vamos de Hetzner direto ou tentamos a Oracle mais algumas vezes?
2. **Onde guardar os backups** (fora do VPS):
   - **Cloudflare R2** (recomendado): 10 GB grátis, sem taxa de download.
   - Backblaze B2: 10 GB grátis.
   - Google Drive, via `rclone`, na sua conta.
3. **Canal do alerta** quando o WhatsApp cair:
   - **ntfy** (recomendado): app de notificação no celular, grátis, um POST simples, tópico secreto.
   - Bot do Telegram.
   - E-mail.
