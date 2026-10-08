# operacao Specification

## Purpose
Manter o núcleo seguro, com backup restaurável e avisos quando algo cai, rodando no Mac até haver um VPS.

## Requirements

### Requirement: Hospedagem
O núcleo SHALL rodar em Docker Compose (evolution-api v2.3.7, postgres 16, redis 7, app) com Postgres e Redis sem porta publicada e Evolution e app só em `127.0.0.1`. Provisoriamente roda no Mac; o deploy num VPS ARM (Oracle Always Free até 2 OCPU / 12 GB, Hetzner como plano B) usa `docker-compose.prod.yml` e os scripts de `deploy/`.

#### Scenario: Acesso ao manager da Evolution no VPS
- **WHEN** é preciso escanear o QR no VPS
- **THEN** o acesso é por túnel SSH, sem expor portas

### Requirement: Segredos e dados reais
Segredos SHALL ficar só no `.env` (fora do git), nunca em logs; cartões, pessoas e telefone reais nunca vão para o repositório público.

#### Scenario: Commit
- **WHEN** há mudanças para commitar
- **THEN** a busca por número, chaves e dados reais não encontra nada nos arquivos staged

### Requirement: Backup cifrado
`deploy/backup.sh` SHALL fazer `pg_dump` dos bancos do app e da Evolution, cifrar com `age` (chave pública em `deploy/backup.pub`, privada só no Mac em `~/.config/life-manager/backup.key`), enviar a uma pasta local ou a um remote do `rclone` (Google Drive escolhido) e apagar o que passa de 30 dias; `deploy/restore.sh` SHALL restaurar num banco recriado.

#### Scenario: Ida e volta
- **WHEN** um backup é restaurado num banco novo
- **THEN** as contagens e a fatura conferida batem com a origem

### Requirement: Alerta de queda do WhatsApp
O `ConnectionMonitor` SHALL avisar por um canal fora do WhatsApp (ntfy, ou só log sem configuração) quando a instância fica fora do ar ou a Evolution não responde por mais de 2 minutos, e quando volta, sem repetir, alimentado pelo `CONNECTION_UPDATE` e por verificação a cada minuto.

#### Scenario: Reconexão rápida
- **WHEN** a instância cai e volta em menos de 2 minutos
- **THEN** nenhum alerta é enviado

### Requirement: Dead man's switch
Com `HEALTHCHECK_URL` configurado, o app SHALL fazer um ping a cada 5 minutos para um serviço externo que avisa se o servidor inteiro parar.

#### Scenario: Sem configuração
- **WHEN** `HEALTHCHECK_URL` está vazio
- **THEN** nenhum ping é feito
