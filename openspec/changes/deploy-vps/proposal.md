## Why

O núcleo roda no Mac: com a tampa fechada ou o Mac desligado, o bot não responde e os lembretes não saem. O `SPEC.md` prevê um VPS ARM sempre ligado, com backup e aviso de queda.

## What Changes

- Núcleo num VPS ARM: Oracle Always Free (até 2 OCPU / 12 GB desde 15/06/2026) ou Hetzner (plano B), com as mesmas imagens Docker.
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
- Status: **pausado** em 08/10/2026. A Oracle está sem capacidade ARM em São Paulo; o Kaio decidiu manter o bot no Mac por enquanto. Houve uma pré-autorização de US$ 100 no cartão no upgrade Pay As You Go, que deve ser estornada.
