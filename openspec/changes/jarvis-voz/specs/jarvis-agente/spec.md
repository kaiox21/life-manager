## MODIFIED Requirements

### Requirement: Ferramentas combinadas
O agente SHALL poder combinar, na mesma conversa, ferramentas do núcleo e ferramentas locais, com a mesma validação e escalada do agente do WhatsApp e nomes de modelo vindos do `.env`; o texto da resposta SHALL chegar por streaming (`token`) e, em modo voz, SHALL ter no máximo duas frases, sem listas nem tabelas, com os detalhes nos cartões.

#### Scenario: Pedido duplo
- **WHEN** o Kaio pede "abre o Safari e me diz meus compromissos de amanhã"
- **THEN** o agente chama `abrir_app` e `buscar_eventos` e responde com o cartão da agenda

#### Scenario: Resposta curta em voz
- **WHEN** o Kaio pergunta por voz "quanto gastei esse mês?"
- **THEN** a resposta falada tem no máximo duas frases e o cartão de gastos traz a lista
