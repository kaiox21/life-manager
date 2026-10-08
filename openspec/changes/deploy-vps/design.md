## Context

Detalhes e decisões da antiga fase 6: `docs/fases/fase-6.md`. Passo a passo: `deploy/README.md`.

## Decisions

- Mesmo `docker-compose.yml` + `docker-compose.prod.yml` (rotação de logs). Deploy por `git pull` no VPS (`deploy/deploy.sh`).
- Backup: `pg_dump` dos dois bancos, cifrado com `age`; chave privada só no Mac; retenção de 30 dias; falha gera alerta.
- `ConnectionMonitor`: alerta com mais de 2 min fora, e na volta; verificação a cada minuto mais o `CONNECTION_UPDATE`.
- Troca: desligar o bot do Mac, restaurar no VPS, escanear o QR de novo.
- Oracle: criar com no máximo 2 OCPU / 12 GB. A criação inline da rede não deixou marcar o IP público: adicionar um IP efêmero depois, ou criar a rede pelo VCN Wizard.

## Risks / Trade-offs

- [Oracle sem capacidade] → Tentativas automáticas com chave de API, ou Hetzner CAX11 (~€4–5/mês).
- [Chave privada do backup perdida] → Cópia no gerenciador de senhas.
