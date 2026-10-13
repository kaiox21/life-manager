## Purpose
Montar e desmontar o ambiente de estudo do Kaio com um pedido só: Foco do macOS, playlist de estudo e silêncio dos avisos, em blocos com a pausa proposta na hora certa, sem chamar o modelo para o relógio nem para as perguntas.

## ADDED Requirements

### Requirement: Iniciar o modo estudo
Ao pedido de modo estudo (pela voz, digitado ou pelo botão Estudo do painel), o Jarvis SHALL, nesta ordem e com o que estiver disponível: ligar o Foco "Não Perturbe" do macOS pelo atalho configurado; tocar a playlist de estudo configurada do Kaio no Spotify; e reter os avisos falados até o fim do modo. O bloco SHALL durar os minutos pedidos (1 a 240; padrão configurável, 50) e a pausa, os pedidos (0 a 60; padrão configurável, 10). A resposta SHALL dizer o que foi ligado e o que não pôde ser (Foco sem atalhos, Spotify sem autorização), sem impedir o modo. Um modo já em andamento SHALL ser substituído pelo novo pedido, sem perguntar. O modo SHALL NOT pedir confirmação.

#### Scenario: Pedido completo
- **WHEN** o Kaio diz "Jarvis, modo estudo por 50 minutos" com os atalhos do Foco criados e o Spotify autorizado
- **THEN** o Foco liga, a playlist de estudo começa a tocar, os avisos falados param e o Jarvis diz que o bloco vai até a hora certa (por exemplo "Modo estudo até as 20h50, senhor. Foco ligado e playlist de estudo tocando.")

#### Scenario: Sem os atalhos do Foco
- **WHEN** os atalhos do Foco não existem no app Atalhos
- **THEN** o modo começa sem o Foco, a música e o silêncio funcionam, e a resposta diz que o Foco não foi ligado porque os atalhos não existem

#### Scenario: Sem o Spotify autorizado
- **WHEN** o Spotify não está autorizado
- **THEN** o modo começa sem música, o Foco e o silêncio funcionam, e a resposta diz que a playlist não tocou

#### Scenario: Pelo botão
- **WHEN** o Kaio clica em Estudo no painel com nenhum modo em andamento
- **THEN** começa um bloco com os minutos padrão, sem chamar o modelo, e a resposta fixa aparece no painel e é falada

### Requirement: Fim do bloco e pausa proposta
Quando o bloco acabar, o Jarvis SHALL falar "Senhor, acabaram os N minutos de estudo. Pausa de M minutos?" (ou, com pausa de 0 minutos, "Mais N minutos?") e tratar a próxima fala, por até 2 minutos, como resposta, sem exigir o nome: uma afirmativa começa a pausa (Foco e música continuam; os avisos seguem retidos); uma negativa encerra o modo com "Perfeito, senhor. Modo estudo encerrado."; qualquer outra coisa vai ao modelo como pedido normal; sem resposta em 2 minutos, o modo encerra em silêncio. Quando a pausa acabar, o Jarvis SHALL falar "Senhor, a pausa acabou. Mais N minutos?" com as mesmas regras: afirmativa começa outro bloco igual, negativa ou silêncio encerra. Essas falas SHALL sair mesmo com os avisos pausados ou no horário de silêncio, SHALL NOT chamar o modelo e SHALL entrar no histórico da conversa.

#### Scenario: Pausa aceita e novo bloco
- **WHEN** o bloco de 50 minutos acaba e o Kaio responde "sim", e 10 minutos depois responde "sim" de novo
- **THEN** o Jarvis fala a pergunta da pausa, começa a pausa, fala a pergunta do novo bloco, e começa outro bloco de 50 minutos com o Foco ainda ligado

#### Scenario: Não quer pausa
- **WHEN** o bloco acaba e o Kaio responde "não"
- **THEN** o Jarvis diz "Perfeito, senhor. Modo estudo encerrado.", o Foco desliga, os avisos voltam e a música fica como está

#### Scenario: Pedido diferente na resposta
- **WHEN** o bloco acaba e o Kaio responde "mais 25 minutos"
- **THEN** o pedido vai ao modelo, que inicia um bloco de 25 minutos

#### Scenario: Sem resposta
- **WHEN** o bloco acaba e o Kaio não responde em 2 minutos
- **THEN** o modo encerra sem falar nada, o Foco desliga e os avisos voltam

### Requirement: Encerrar e consultar
"Para o estudo" (ou equivalente), o botão Estudo com um modo em andamento, ou "quanto falta do estudo?" SHALL, respectivamente, encerrar o modo (Foco desligado, avisos de volta, música como está, resposta curta) ou dizer a fase e o que falta. Encerrar sem modo em andamento SHALL responder que não há modo estudo ativo.

#### Scenario: Encerrar no meio
- **WHEN** faltam 20 minutos do bloco e o Kaio diz "Jarvis, para o estudo"
- **THEN** o Foco desliga, os avisos falados voltam, a música continua e o Jarvis confirma o fim

#### Scenario: Quanto falta
- **WHEN** o Kaio pergunta "quanto falta do estudo?" na pausa
- **THEN** o Jarvis diz que está na pausa e quantos minutos faltam

### Requirement: O relógio sobrevive a dormir e reiniciar
O fim do bloco e da pausa SHALL ser uma hora marcada, não uma contagem. Se o Mac dormir e acordar antes da hora, o modo continua; se acordar depois dela, o modo SHALL encerrar em silêncio (Foco desligado) sem perguntar. Se o cérebro reiniciar durante o modo, ele SHALL retomá-lo na mesma fase; se reiniciar depois da hora marcada, SHALL encerrar o modo e desligar o Foco.

#### Scenario: Mac dormiu além do fim
- **WHEN** o bloco ia até as 20h50 e o Mac acorda às 21h30
- **THEN** o modo encerra sem fala, o Foco desliga e os avisos voltam

#### Scenario: Cérebro reiniciou no meio
- **WHEN** o cérebro reinicia às 20h30 com um bloco marcado até as 20h50
- **THEN** o painel volta a mostrar "Estudo 20 min" e às 20h50 a pausa é proposta

### Requirement: Silêncio durante o modo
Enquanto o modo estudo durar (bloco e pausa), o Jarvis SHALL NOT falar avisos (lembretes do núcleo, terminais, pergunta dos gastos); eles SHALL NOT ser falados depois do modo, e o WhatsApp SHALL continuar recebendo-os normalmente. As falas do próprio modo e os pedidos do Kaio funcionam normalmente. O painel SHALL mostrar o modo no botão Estudo ("Estudo 37 min", "Pausa 8 min") e no estado ("estudo · faltam 37 min").

#### Scenario: Lembrete durante o estudo
- **WHEN** um lembrete de compromisso sai no WhatsApp durante o bloco
- **THEN** o Jarvis não o fala, nem depois; o WhatsApp o recebe

#### Scenario: Pedido durante o estudo
- **WHEN** o Kaio diz "Jarvis, que horas são?" durante o bloco
- **THEN** o Jarvis responde normalmente e o modo continua
