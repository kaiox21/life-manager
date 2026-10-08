## 1. Código e scripts

- [x] 1.1 `ConnectionMonitor` + ntfy + verificação a cada minuto + `CONNECTION_UPDATE`
- [x] 1.2 Heartbeat para dead man's switch
- [x] 1.3 `deploy/backup.sh` e `deploy/restore.sh` com `age`; ida e volta testada com os dados reais
- [x] 1.4 `docker-compose.prod.yml`, `deploy/bootstrap.sh`, `deploy/deploy.sh`, `deploy/README.md`

## 2. Contas e servidor

- [x] 2.1 Conta Oracle criada e upgrade Pay As You Go
- [ ] 2.2 VM ARM (≤ 2 OCPU / 12 GB) com IP público, ou Hetzner
- [ ] 2.3 ntfy, healthchecks.io e `rclone` com o Google Drive
- [ ] 2.4 `bootstrap.sh` no VPS

## 3. Troca e aceite

- [ ] 3.1 Backup no Mac, `docker compose down` no Mac, restauração no VPS, conferência das contagens e de uma fatura
- [ ] 3.2 Escanear o QR no VPS (túnel SSH)
- [ ] 3.3 Aceite: alerta chega ao desconectar o aparelho e de novo ao reconectar
- [ ] 3.4 Backup remoto diário funcionando; atualizar specs (archive)
