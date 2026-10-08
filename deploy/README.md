# Deploy no VPS (fase 6)

Passo a passo para tirar o bot do Mac e colocar num VPS ARM (Oracle; Hetzner como plano B).
**Ordem importa**: nunca deixe dois bots conectados ao mesmo WhatsApp ao mesmo tempo.

## 0. Uma vez, no Mac

```bash
# chave SSH para entrar no VPS (se ainda não tiver)
ssh-keygen -t ed25519 -C "life-manager"   # Enter em tudo; gera ~/.ssh/id_ed25519(.pub)
cat ~/.ssh/id_ed25519.pub                 # isto vai no campo "SSH keys" ao criar a VM
```

A chave **privada do backup** já está em `~/.config/life-manager/backup.key` (só no Mac).
Guarde uma cópia num lugar seguro (ex.: gerenciador de senhas): sem ela, os backups não abrem.

## 1. Criar o VPS

**Oracle Cloud** (cloud.oracle.com):
1. Crie a conta (região **Brazil East (São Paulo)**). O cartão é só verificação.
2. Faça o **upgrade para Pay As You Go** (continua grátis dentro da cota; evita a VM ser recolhida por ociosidade).
3. *Compute → Instances → Create instance*:
   - imagem **Canonical Ubuntu 24.04**;
   - shape **VM.Standard.A1.Flex** (Ampere), **no máximo 2 OCPU e 12 GB** (cota Always Free desde 15/06/2026; acima disso, conta Pay As You Go é cobrada);
   - em *Add SSH keys*, cole a sua `id_ed25519.pub`.
4. Se aparecer "Out of capacity", tente outro *availability domain* ou mais tarde.
   Persistindo: **Hetzner** CAX11 (ARM, Ubuntu 24.04), com os mesmos passos daqui para frente.
5. Anote o IP público. O usuário é `ubuntu`.

## 2. Preparar o VPS

```bash
ssh ubuntu@IP
curl -fsSL https://raw.githubusercontent.com/kaiox21/life-manager/main/deploy/bootstrap.sh | bash
exit   # sair e entrar de novo para valer o grupo docker
```

## 3. Contas externas (alerta, dead man's switch, backup)

- **ntfy** (alerta quando o WhatsApp cai):
  1. instale o app ntfy no celular;
  2. inscreva-se num tópico com nome longo e aleatório (ex.: o resultado de `openssl rand -hex 12`);
  3. no `.env`: `ALERT_NTFY_URL=https://ntfy.sh/<tópico>`.
- **healthchecks.io** (avisa por e-mail se o VPS inteiro parar):
  1. crie a conta e dois checks: "app" (período 5 min, tolerância 10 min) e "backup" (período 1 dia, tolerância 2 h);
  2. URLs de ping no `.env`: `HEALTHCHECK_URL` e `HEALTHCHECK_BACKUP_URL`.
- **Backup** (ex.: Cloudflare R2):
  1. crie um bucket e um token de API (leitura e escrita nesse bucket);
  2. no VPS, rode `rclone config`;
  3. crie um remote `r2` (tipo S3, provider Cloudflare, com o *Access Key*, o *Secret* e o *endpoint* da conta);
  4. no `.env`: `BACKUP_DEST=r2:<bucket>`.

## 4. Levar os dados e trocar Mac → VPS

No Mac:

```bash
cd ~/Downloads/life-manager
deploy/backup.sh ~/life-manager-migracao        # backup cifrado dos dados atuais
docker compose down                              # DESLIGA o bot do Mac (Docker continua instalado)
for f in ~/life-manager-migracao/*-assistente.dump.age; do
  age -d -i ~/.config/life-manager/backup.key "$f" > /tmp/assistente.dump
done
scp .env ubuntu@IP:~/life-manager/.env
scp /tmp/assistente.dump ubuntu@IP:/tmp/ && rm /tmp/assistente.dump
```

No VPS:

```bash
cd ~/life-manager && chmod 600 .env
P="-f docker-compose.yml -f docker-compose.prod.yml"
docker compose $P up -d postgres && sleep 10
COMPOSE_FILES="$P" deploy/restore.sh /tmp/assistente.dump assistente && rm /tmp/assistente.dump
docker compose $P up -d --build
```

Conferir que os números batem com os do Mac (critério 1 da fase 6):

```bash
docker compose $P exec -T postgres psql -U app -d assistente -tAc \
 'select (select count(*) from expenses),(select count(*) from events),(select count(*) from people),(select count(*) from payment_methods)'
```

## 5. Conectar o WhatsApp de novo (QR)

```bash
# no Mac, deixe o túnel aberto:
ssh -L 8080:localhost:8080 ubuntu@IP
# em outro terminal do Mac:
cd ~/Downloads/life-manager
EVOLUTION_API_URL=http://localhost:8080 uv run python -m app.channel.setup && open data/qrcode.png
```

No celular: Aparelhos conectados → **desconecte o aparelho antigo "Assistente"** → Conectar aparelho → escaneie.

## 6. Aceite

1. **Backup**:
   - restauração conferida no passo 4;
   - backup remoto: `COMPOSE_FILES="$P" deploy/backup.sh` no VPS e conferir o arquivo no bucket.
2. **Alerta**:
   - no celular, desconecte o aparelho "Assistente";
   - em até ~3 min deve chegar "WhatsApp fora do ar" no ntfy;
   - reconecte (passo 5) e deve chegar "WhatsApp voltou".

## Dia a dia

- Atualizar: no Mac, `deploy/deploy.sh ubuntu@IP`.
- Logs: `ssh ubuntu@IP 'cd life-manager && docker compose logs -f app'`.
- Backup roda sozinho às 03:00 (cron); log em `~/backup.log` no VPS.
