# jarvis-agente Specification

## Purpose
Cérebro do Jarvis no Mac: entender o pedido e agir combinando as ferramentas do núcleo (só pelo MCP) e as ferramentas locais, com os mesmos cuidados do agente do WhatsApp.

## Requirements

### Requirement: Núcleo só pelo MCP
O agente do Jarvis SHALL acessar agenda e gastos exclusivamente pelas ferramentas MCP do núcleo, chamando `contexto` no início da conversa; nunca acessa o banco diretamente.

#### Scenario: Compromissos de amanhã
- **WHEN** o Kaio pede "o que eu tenho amanhã?"
- **THEN** o agente copia a data de amanhã do `contexto` e chama `buscar_eventos` pelo MCP

### Requirement: Ferramentas combinadas
O agente SHALL poder combinar, na mesma conversa, ferramentas do núcleo e ferramentas locais, com a mesma validação e escalada do agente do WhatsApp e nomes de modelo vindos do `.env`.

#### Scenario: Pedido duplo
- **WHEN** o Kaio pede "abre o Safari e me diz meus compromissos de amanhã"
- **THEN** o agente chama `abrir_app` e `buscar_eventos` e responde com o cartão da agenda

### Requirement: Canal local seguro
O cérebro SHALL ouvir só em `127.0.0.1`, com um token gerado a cada execução e exigido pela interface.

#### Scenario: Outro processo tenta conectar
- **WHEN** um processo sem o token abre o WebSocket
- **THEN** a conexão é recusada
