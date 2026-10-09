## MODIFIED Requirements

### Requirement: Estados visíveis
O HUD SHALL mostrar os estados digitando, ouvindo (forma de onda ao vivo do microfone), transcrevendo, pensando (orbe pulsando e passos como "consultando a agenda…"), respondendo e falando, recebidos por streaming do cérebro; em modo voz, a transcrição SHALL aparecer como a pergunta do turno.

#### Scenario: Consulta à agenda
- **WHEN** o agente chama `buscar_eventos`
- **THEN** o passo "consultando a agenda…" aparece antes da resposta

#### Scenario: Ouvindo
- **WHEN** o atalho de voz está segurado
- **THEN** o HUD mostra a forma de onda reagindo à voz e o estado "ouvindo"
