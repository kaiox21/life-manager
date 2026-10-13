## Context

- `EvolutionClient.send_text` faz `POST /message/sendText/{instância}` e só chama `raise_for_status()`.
- O `ConnectionMonitor` recebe só estados (webhook `CONNECTION_UPDATE` e `connectionState` a cada minuto).
- **Fato de 13/10/2026:** com `connectionState` = `open`, o envio voltava 428 e `{"error":"Precondition Required","message":"Connection Closed"}` no log da Evolution v2.3.7. `docker compose restart evolution-api` reconectou ("CONNECTED TO WHATSAPP") sem QR. A rota de reinício da instância na v2.3.7 é `POST /instance/restart/{instância}` (conferida no código da Evolution dentro do container).

## Decisions

1. **Falha que conta como conexão morta:** HTTP 428, ou corpo/erro com "Connection Closed". Outros erros (400 de número inválido, 500 genérico) seguem como hoje, sem reinício.
2. **No `send_text`:**
   1. falhou com conexão morta → `restart()`;
   2. espera `connectionState` = `open` (a cada 2 s, até 30 s);
   3. reenvia uma vez;
   4. se ainda falhar, levanta o erro (quem chamou já trata: os avisos liberam a reserva e tentam no ciclo seguinte).
   - O reinício fica protegido por um intervalo mínimo de 5 min, guardado no próprio cliente.
3. **Monitor:** `observe_send(ok, now)`.
   - Falha de conexão marca `_down_since` (se ainda não marcado) e alerta depois dos 2 min, como o estado.
   - Envio bem-sucedido equivale a `open`.
   - O cliente recebe o monitor por injeção opcional, para não criar dependência circular.

## Risks / Trade-offs

- **[Reiniciar derruba a conexão por alguns segundos]** → só acontece quando ela já está morta para envio, e no máximo a cada 5 min.
- **[A sessão caiu de verdade (pede QR)]** → o reinício não resolve, e o alerta do ntfy avisa como antes.
