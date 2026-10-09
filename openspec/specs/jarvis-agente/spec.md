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
O agente SHALL poder combinar, na mesma conversa, ferramentas do núcleo e ferramentas locais, com a mesma validação e escalada do agente do WhatsApp e nomes de modelo vindos do `.env`; o texto da resposta SHALL chegar por streaming (`token`) e, em modo voz, SHALL ter no máximo duas frases, sem listas nem tabelas, com os detalhes nos cartões.

#### Scenario: Pedido duplo
- **WHEN** o Kaio pede "abre o Safari e me diz meus compromissos de amanhã"
- **THEN** o agente chama `abrir_app` e `buscar_eventos` e responde com o cartão da agenda

#### Scenario: Resposta curta em voz
- **WHEN** o Kaio pergunta por voz "quanto gastei esse mês?"
- **THEN** a resposta falada tem no máximo duas frases e o cartão de gastos traz a lista

### Requirement: Canal local seguro
O cérebro SHALL ouvir só em `127.0.0.1`, com um token gerado a cada execução e exigido pela interface.

#### Scenario: Outro processo tenta conectar
- **WHEN** um processo sem o token abre o WebSocket
- **THEN** a conexão é recusada
