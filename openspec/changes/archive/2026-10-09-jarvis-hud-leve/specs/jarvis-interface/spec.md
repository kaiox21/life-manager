## MODIFIED Requirements

### Requirement: Estados visíveis
O HUD SHALL mostrar os estados digitando, ouvindo (forma de onda ao vivo do microfone), transcrevendo, pensando (orbe pulsando e passos como "consultando a agenda…"), respondendo e falando, recebidos por streaming do cérebro; com o Jarvis parado (online, sem ouvir, pensar ou falar), o orbe SHALL ficar parado, sem animação, e voltar a se mexer assim que houver atividade; em modo voz, a transcrição SHALL aparecer como a pergunta do turno.

#### Scenario: Consulta à agenda
- **WHEN** o agente chama `buscar_eventos`
- **THEN** o passo "consultando a agenda…" aparece antes da resposta

#### Scenario: Ouvindo
- **WHEN** o atalho de voz está segurado
- **THEN** o HUD mostra a forma de onda reagindo à voz e o estado "ouvindo"

#### Scenario: HUD aberto e parado
- **WHEN** o HUD fica aberto sem conversa em andamento
- **THEN** o orbe fica parado e o Jarvis gasta menos de 5% de CPU (app e processos do WebKit somados)
