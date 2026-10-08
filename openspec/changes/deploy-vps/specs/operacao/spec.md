## MODIFIED Requirements

### Requirement: Hospedagem
O núcleo SHALL rodar num VPS ARM (Oracle Always Free até 2 OCPU / 12 GB, ou Hetzner como plano B) em Docker Compose com `docker-compose.prod.yml` (evolution-api v2.3.7, postgres 16, redis 7, app), com só a porta SSH aberta (chave, sem senha), Postgres e Redis sem porta publicada e Evolution e app só em `127.0.0.1`. Um único bot fica conectado ao WhatsApp por vez.

#### Scenario: Acesso ao manager da Evolution no VPS
- **WHEN** é preciso escanear o QR no VPS
- **THEN** o acesso é por túnel SSH, sem expor portas

#### Scenario: Mac fechado
- **WHEN** o Mac está desligado
- **THEN** o bot continua respondendo e os lembretes continuam saindo
