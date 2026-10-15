# Deploy no VPS (fase 6)

Passo a passo para tirar o bot do Mac e colocar num VPS (Hostinger KVM, Ubuntu 24.04; decisão de 15/10/2026).
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

**Hostinger** (hostinger.com/br/vps):
1. Plano **KVM 1** (1 vCPU, 4 GB, 50 GB NVMe) basta. O KVM 2 (2 vCPU, 8 GB) só deixa a transcrição de áudio mais rápida.
   Confira o prazo no checkout: o preço mensal anunciado é o do contrato longo, pago adiantado, e a renovação custa cerca do dobro.
2. Localização **Brasil (São Paulo)**; sistema **Ubuntu 24.04 LTS** limpo (sem painel nem template de app).
3. No hPanel do VPS, em *Configurações → Chaves SSH*, adicione a sua `id_ed25519.pub`. A senha de root é só para emergência: o bootstrap desliga o login por senha.
4. Anote o IP público. O usuário é `root`.

Plano B, com os mesmos passos daqui para frente: **Hetzner** CAX11 (ARM, Ubuntu 24.04).

## 2. Preparar o VPS

```bash
ssh root@IP
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
cd ~/"Projetos pessoais"/life-manager
deploy/backup.sh ~/life-manager-migracao        # backup cifrado dos dados atuais
docker compose down                              # DESLIGA o bot do Mac (Docker continua instalado)
for f in ~/life-manager-migracao/*-assistente.dump.age; do
  age -d -i ~/.config/life-manager/backup.key "$f" > /tmp/assistente.dump
done
scp .env root@IP:~/life-manager/.env
scp /tmp/assistente.dump root@IP:/tmp/ && rm /tmp/assistente.dump
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
ssh -L 8080:localhost:8080 root@IP
# em outro terminal do Mac:
cd ~/"Projetos pessoais"/life-manager
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

- Atualizar: no Mac, `deploy/deploy.sh root@IP`.
- Logs: `ssh root@IP 'cd life-manager && docker compose logs -f app'`.
- Backup roda sozinho às 03:00 (cron); log em `~/backup.log` no VPS.
