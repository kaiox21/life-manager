## Context

Detalhes e decisões da antiga fase 6: `docs/fases/fase-6.md`. Passo a passo: `deploy/README.md`.

## Decisions

- Mesmo `docker-compose.yml` + `docker-compose.prod.yml` (rotação de logs). Deploy por `git pull` no VPS (`deploy/deploy.sh`).
- Backup: `pg_dump` dos dois bancos, cifrado com `age`; chave privada só no Mac; retenção de 30 dias; falha gera alerta.
- `ConnectionMonitor`: alerta com mais de 2 min fora, e na volta; verificação a cada minuto mais o `CONNECTION_UPDATE`.
- Troca: desligar o bot do Mac, restaurar no VPS, escanear o QR de novo.
- Hostinger (15/10/2026): plano KVM, Ubuntu 24.04 x86, data center em São Paulo, usuário `root` (é o que o painel entrega); chave SSH do Mac cadastrada no hPanel antes de criar; `bootstrap.sh` desliga o login por senha e liga o `ufw` (fora da Oracle não há iptables pré-configurado). As imagens Docker são multi-arquitetura: nada muda no compose.
- Fatos (15/10/2026, hostinger.com/br/vps): KVM 1 = 1 vCPU, 4 GB, 50 GB NVMe, 4 TB; KVM 2 = 2 vCPU, 8 GB, 100 GB. Preços promocionais R$ 29,99 e R$ 43,99 por mês no contrato longo pago adiantado; renovação R$ 59,99 e R$ 77,99.
- Oracle (histórico): criar com no máximo 2 OCPU / 12 GB. A criação inline da rede não deixou marcar o IP público. Sem capacidade ARM em São Paulo de 08 a 15/10/2026; descartada.

## Risks / Trade-offs

- [Renovação da Hostinger ~2× o promocional] → Reavaliar na renovação; Hetzner CAX11 (~€5/mês) continua como plano B, com os mesmos scripts.
- [1 vCPU no KVM 1] → Transcrição de áudio e build das imagens mais lentos; se incomodar, upgrade para o KVM 2 sem reinstalar.
- [Chave privada do backup perdida] → Cópia no gerenciador de senhas.
