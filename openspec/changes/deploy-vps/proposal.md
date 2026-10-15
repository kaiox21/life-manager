## Why

O núcleo roda no Mac: com a tampa fechada ou o Mac desligado, o bot não responde e os lembretes não saem. O `SPEC.md` prevê um VPS sempre ligado, com backup e aviso de queda.

## What Changes

- Núcleo num VPS **Hostinger KVM** (x86, Ubuntu 24.04, data center em São Paulo), com as mesmas imagens Docker. Decisão do Kaio em 15/10/2026, depois de uma semana sem capacidade ARM na Oracle. O KVM 1 (1 vCPU / 4 GB, R$ 29,99/mês no contrato longo; renovação R$ 59,99) basta; o KVM 2 (2 vCPU / 8 GB, R$ 43,99) só acelera a transcrição de áudio.
- Só a porta SSH aberta (chave, sem senha); manager da Evolution por túnel SSH.
- Backup diário às 03:00 para o Google Drive (`rclone`), cifrado com `age`; migração dos dados do Mac pelo próprio backup (teste de restauração real).
- Alertas de queda do WhatsApp por ntfy e dead man's switch (healthchecks.io) configurados.
- Troca Mac → VPS sem dois bots ao mesmo tempo; o QR é escaneado de novo.

## Non-goals

- Domínio, HTTPS público ou qualquer porta além do SSH.
- Tailscale e MCP no VPS (entram junto, mas o aceite do MCP já foi feito no Mac).

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `operacao`: a hospedagem deixa de ser provisória no Mac e passa a ser o VPS.

## Impact

- `docker-compose.prod.yml` e `deploy/` (já prontos), `.env` no VPS e conta no ntfy, no healthchecks.io e no Google Drive (rclone).
- Histórico: pausado em 08/10/2026 (Oracle sem capacidade ARM em São Paulo; pré-autorização de US$ 100 no cartão no upgrade Pay As You Go, a estornar). Em 15/10/2026 o Kaio escolheu a Hostinger KVM 1 e, no mesmo dia, **pausou de novo por custo**: R$ 30/mês sem retorno claro. O bot segue no Mac. Quando compensar, retomar na tarefa 2.2 com o `deploy/README.md`. Caminho sem custo que continua aberto: tentativas automáticas de criar a VM gratuita da Oracle (precisa de uma chave de API da conta). A conta Oracle fica sem recursos criados (nada a pagar).
