## Purpose
Fazer o Jarvis tomar a iniciativa quando importa: fechar o dia perguntando pelos gastos não lançados e falar os avisos do núcleo e dos terminais, sem falar fora de hora e sem nunca aprovar nada pela voz.

## ADDED Requirements

### Requirement: Fechamento do dia
"Boa noite" dito ao Jarvis (pela palavra "Jarvis", pelo atalho de voz, digitado ou pelo botão Boa noite do painel) SHALL produzir um fechamento falado, com texto fixo e sem chamar o modelo: quantos gastos com data de hoje foram lançados e o total, o total do mês, a agenda de amanhã com o horário do primeiro compromisso (ou que amanhã está livre) e a pergunta "O senhor teve algum gasto hoje que ainda não lançou?". Valores e somas SHALL vir do núcleo, numa chamada ao `painel`. Depois da pergunta, a próxima fala (por até 2 minutos) SHALL ser tratada como resposta, sem exigir o nome: um gasto segue como pedido normal (com as confirmações de sempre) e uma negativa encerra com uma frase curta, sem chamar o modelo. Só a frase "boa noite" sozinha (com ou sem "Jarvis") dispara o fechamento; frases maiores vão ao modelo. O fechamento SHALL entrar no histórico da conversa.

#### Scenario: Fechamento com gasto esquecido
- **WHEN** às 22h o Kaio diz "Jarvis, boa noite", lançou 2 gastos hoje somando R$ 63,50 e amanhã tem aula às 19h
- **THEN** o Jarvis fala algo como "Boa noite, senhor. Hoje foram 2 gastos, R$ 63,50; no mês, R$ 1.240,00. Amanhã o senhor tem aula às 19h. O senhor teve algum gasto hoje que ainda não lançou?" e, se o Kaio responde "30 de uber no pix" sem dizer o nome, o gasto é lançado como num pedido normal

#### Scenario: Nada a lançar
- **WHEN** depois da pergunta o Kaio diz "não"
- **THEN** o Jarvis responde "Perfeito, senhor. Boa noite." sem chamar o modelo

#### Scenario: Frase maior
- **WHEN** o Kaio digita "boa noite, quanto gastei hoje?"
- **THEN** o pedido vai ao modelo, sem fechamento

#### Scenario: Núcleo fora
- **WHEN** o núcleo não responde
- **THEN** o Jarvis diz que os dados estão indisponíveis agora, sem inventar números

### Requirement: Lembrete de lançamento
Às 21:30 (horário configurável), com o Mac ligado e o Jarvis rodando, se nenhum gasto com data de hoje tiver sido lançado, o Jarvis SHALL perguntar em voz "Senhor, nenhum gasto lançado hoje. Teve algum?" e tratar a próxima fala como no fechamento. A pergunta SHALL sair no máximo uma vez por dia, inclusive se o Jarvis reiniciar; se o Mac estiver dormindo às 21:30, ela SHALL sair quando ele acordar, até o começo do silêncio. Com o núcleo fora, a pergunta não sai.

#### Scenario: Dia sem lançamento
- **WHEN** são 21:30 e não há gasto com data de hoje
- **THEN** o Jarvis faz a pergunta uma vez e não repete no mesmo dia, mesmo reiniciando

#### Scenario: Dia com lançamento
- **WHEN** são 21:30 e já há gasto com data de hoje
- **THEN** o Jarvis não pergunta nada

### Requirement: Avisos falados
Quando o núcleo enviar um lembrete de compromisso, de aniversário ou de fatura perto de fechar, o Jarvis SHALL falar o mesmo texto, limpo para a fala (sem emojis nem parênteses), em até cerca de 1 minuto, uma vez só. Vagas novas do radar SHALL virar a frase "Senhor, o radar encontrou vagas novas; estão no painel."; o boletim de notícias e o resumo do dia do WhatsApp SHALL NOT ser falados. Quando um Claude Code de um terminal pedir permissão, ou terminar um trabalho que durou 2 minutos ou mais, o Jarvis SHALL falar um aviso curto com a pasta do terminal e, na permissão, a ferramenta pedida, nunca o comando; um mesmo terminal SHALL NOT gerar mais de um aviso falado por minuto. A voz SHALL NOT aprovar nem negar pedidos de permissão; o aviso SHALL apenas informar. Avisos que chegaram com o Jarvis desligado não são falados depois, e um aviso que esperou a vez por mais de 5 minutos é descartado.

#### Scenario: Compromisso chegando
- **WHEN** o núcleo envia "⏰ Reunião com o Carlos: hoje às 14:00 — em 30 min."
- **THEN** o Jarvis fala "Reunião com o Carlos: hoje às 14h, em 30 min." uma vez

#### Scenario: Boletim não é falado
- **WHEN** o boletim de notícias sai às 07:30
- **THEN** o Jarvis não fala nada

#### Scenario: Permissão no terminal
- **WHEN** o Claude Code do terminal 2 (life-manager) pede permissão para rodar um comando
- **THEN** o Jarvis fala "Senhor, o Claude Code do life-manager está pedindo permissão para usar Bash." e a resposta continua só pelo botão

#### Scenario: Resposta curta não vira aviso
- **WHEN** o Claude Code termina uma resposta que levou 20 segundos
- **THEN** o Jarvis não fala nada

#### Scenario: Voz não aprova
- **WHEN** com um pedido de permissão aberto o Kaio diz "Jarvis, permite"
- **THEN** o pedido continua aberto, esperando o clique

### Requirement: Silêncio
O Jarvis SHALL NOT falar avisos nem o lembrete de lançamento entre 23:00 e 07:00 (horários configuráveis), e um aviso que chegar enquanto ele fala, ouve ou atende um pedido SHALL esperar a vez. O Kaio SHALL poder pausar os avisos falados por voz, texto ou pelo botão Silenciar do painel por um tempo ("por uma hora", "até amanhã") e retomá-los ("volta a avisar"); a pausa SHALL valer mesmo se o Jarvis reiniciar, e o painel SHALL mostrar até quando ela vale. Pausado, o WhatsApp continua recebendo os avisos normalmente. O fechamento pedido pelo Kaio SHALL funcionar mesmo pausado ou no horário de silêncio.

#### Scenario: Silenciar por uma hora
- **WHEN** o Kaio diz "Jarvis, silencia os avisos por uma hora" e um lembrete sai 20 min depois
- **THEN** o Jarvis não fala o lembrete, o WhatsApp o recebe e o painel mostra "avisos pausados até" a hora certa

#### Scenario: Madrugada
- **WHEN** um Claude Code termina um trabalho longo à 01:00
- **THEN** o Jarvis não fala nada

#### Scenario: Boa noite em silêncio
- **WHEN** os avisos estão pausados e o Kaio diz "Jarvis, boa noite"
- **THEN** o fechamento é falado normalmente
