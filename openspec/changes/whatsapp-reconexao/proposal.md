## Why

Em 13/10/2026 o WhatsApp parou de enviar sem ninguém saber. A Evolution dizia que a instância estava `open`, mas todo envio voltava 428 ("Connection Closed"). O provável é o Mac ter dormido à noite e a conexão do WhatsApp Web ter caído por dentro. O `ConnectionMonitor` confia nesse estado e não alertou, então lembretes e avisos deixariam de sair até alguém notar. Um `docker compose restart evolution-api` reconectou sem QR.

## What Changes

- **Envio que falha com a conexão morta se recupera sozinho.**
  - Se a Evolution responde 428 ou "Connection Closed" a um envio, o núcleo reinicia a conexão da instância (`POST /instance/restart/{instância}`, que reconecta sem pedir QR quando a sessão é válida).
  - Depois espera ela voltar a `open`, por até 30 s, e tenta o envio de novo, uma vez.
- **O monitor passa a contar o envio, não só o estado.** Uma falha de envio com a conexão morta conta como queda, mesmo com o estado `open`. O alerta sai pelo ntfy depois dos mesmos 2 minutos de tolerância. Um envio bem-sucedido conta como volta.
- O reinício acontece no máximo uma vez a cada 5 minutos, para não ficar em laço se a sessão tiver mesmo caído (aí o alerta pede o QR, como hoje).

## Non-goals

- Escanear o QR sozinho ou trocar a Evolution.
- Reenviar mensagens que já falharam antes desta mudança. Os avisos têm a própria reserva e tentam de novo no próximo ciclo.

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `operacao`: o alerta de queda considera falha de envio, e o núcleo tenta reconectar sozinho antes de alertar.

## Impact

- `app/channel/evolution.py`: `restart()` e a nova tentativa no `send_text`.
- `app/alerts.py`: `ConnectionMonitor.observe_send(ok)`.
- A Evolution não muda de configuração.
