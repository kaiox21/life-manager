## MODIFIED Requirements

### Requirement: Alerta de queda do WhatsApp
O `ConnectionMonitor` SHALL avisar por um canal fora do WhatsApp (ntfy, ou só log sem configuração) quando a instância fica fora do ar, a Evolution não responde ou os envios falham com a conexão fechada (mesmo com o estado informado como `open`) por mais de 2 minutos, e quando volta (estado `open` ou um envio bem-sucedido), sem repetir, alimentado pelo `CONNECTION_UPDATE`, por verificação a cada minuto e pelo resultado dos envios. Antes de dar o envio por perdido, o núcleo SHALL reiniciar a conexão da instância (no máximo uma vez a cada 5 minutos), esperar até 30 s ela voltar a `open` e tentar o envio de novo uma vez.

#### Scenario: Reconexão rápida
- **WHEN** a instância cai e volta em menos de 2 minutos
- **THEN** nenhum alerta é enviado

#### Scenario: Conexão morta com estado "open"
- **WHEN** a Evolution informa `open`, mas o envio de um lembrete volta 428 "Connection Closed"
- **THEN** o núcleo reinicia a conexão, espera ela voltar e o lembrete sai na segunda tentativa, sem alerta

#### Scenario: Sessão realmente perdida
- **WHEN** depois do reinício os envios continuam falhando por mais de 2 minutos
- **THEN** sai um alerta pelo ntfy dizendo que pode ser preciso escanear o QR, e o núcleo não reinicia de novo antes de 5 minutos
