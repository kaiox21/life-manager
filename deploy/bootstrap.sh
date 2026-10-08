#!/usr/bin/env bash
# Preparação do VPS (Ubuntu 24.04, ARM). Rodar UMA vez, no VPS, como usuário com sudo:
#   curl -fsSL https://raw.githubusercontent.com/kaiox21/life-manager/main/deploy/bootstrap.sh | bash
set -euo pipefail

sudo timedatectl set-timezone America/Sao_Paulo

# Docker (repositório oficial) + ferramentas de backup
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
sudo apt-get update -y
sudo apt-get install -y age rclone git unattended-upgrades
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# Swap de 4 GB (whisper + build das imagens)
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# SSH só com chave
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl reload ssh

# Firewall: a imagem Ubuntu da Oracle já vem com iptables liberando só a 22.
# Fora da Oracle (ex.: Hetzner), usa ufw.
if ! sudo iptables -S INPUT | grep -q -- '--dport 22'; then
  sudo apt-get install -y ufw
  sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw --force enable
fi

# Código
[ -d ~/life-manager ] || git clone https://github.com/kaiox21/life-manager.git ~/life-manager

# Backup diário às 03:00
( crontab -l 2>/dev/null | grep -v 'deploy/backup.sh'; \
  echo '0 3 * * * cd ~/life-manager && COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml" deploy/backup.sh >> ~/backup.log 2>&1' ) | crontab -

echo "Pronto. Saia e entre de novo (grupo docker), copie o .env e rode deploy/deploy.sh do Mac."
