## ADDED Requirements

### Requirement: Ativação pela palavra "Jarvis"
Com a escuta ligada, uma frase que comece com "Jarvis" (ou "Hey/Ei/Ô Jarvis") SHALL ativar o Jarvis sem tocar no teclado e sem abrir nenhuma janela: o que for dito depois do nome, até uma pausa, SHALL virar o pedido, respondido só por voz pelo mesmo caminho do push-to-talk. O nome no começo SHALL ser tirado do texto do pedido. Se o painel já estiver aberto, a pergunta e a resposta SHALL aparecer nele; o HUD SHALL NOT ser mostrado pela palavra, e o foco do app em uso SHALL NOT mudar.

#### Scenario: Pedido numa frase
- **WHEN** a escuta está ligada, o Kaio está em outro app e diz "Jarvis, o que eu tenho amanhã?"
- **THEN** nenhuma janela aparece, o foco continua no app, e o Jarvis responde falando

#### Scenario: Painel aberto
- **WHEN** o painel está aberto e o Kaio diz "Jarvis, quanto eu gastei esse mês?"
- **THEN** a pergunta e a resposta aparecem no painel, e o HUD não aparece por cima

### Requirement: Resumo do dia ao chamar só o nome
"Hey Jarvis" ou "Jarvis" sozinho SHALL fazer o Jarvis falar um resumo do dia, montado com texto fixo e sem chamar o modelo de linguagem: cumprimento pela hora do dia, a temperatura agora com máxima e mínima (e a chance de chuva quando for de 30% ou mais), os compromissos de hoje com o horário, a fatura de cartão que fecha ou vence nos próximos 3 dias e os pedidos de permissão de terminal esperando resposta. Partes sem nada SHALL ser omitidas, e um dia sem compromissos SHALL dizer isso numa frase. Sem internet ou com o clima fora, o resumo SHALL sair sem o clima; com o núcleo fora, SHALL dizer que a agenda está indisponível. O clima SHALL vir de um serviço sem chave, recebendo só a latitude e a longitude configuradas. Depois do resumo, o Jarvis SHALL ouvir um pedido por alguns segundos sem exigir o nome de novo; sem fala, volta a esperar a palavra.

#### Scenario: Bom dia
- **WHEN** às 8h o Kaio diz "Hey Jarvis", tem aula às 19h e reunião às 14h, e fazem 22 °C
- **THEN** o Jarvis fala algo como "Bom dia, senhor. Agora fazem 22 graus em Brasília, máxima de 31 e mínima de 18. Hoje o senhor tem reunião às 14h e aula às 19h." sem abrir janela e sem chamar o modelo

#### Scenario: Pedido logo depois do resumo
- **WHEN** o Jarvis termina o resumo e o Kaio diz "quanto eu gastei esse mês?"
- **THEN** o Jarvis responde ao pedido sem que o Kaio repita o nome

#### Scenario: Sem internet
- **WHEN** o Mac está sem internet e o Kaio diz "Hey Jarvis"
- **THEN** o resumo sai com a agenda e sem o clima

### Requirement: Escuta ligada e desligada
O Kaio SHALL poder ligar e desligar a escuta da palavra "Jarvis" pelo menu da barra ("Ouvir 'Jarvis'"), com a escolha lembrada entre reinícios do Mac e do Jarvis. Desligada, o Jarvis SHALL NOT capturar o microfone fora do push-to-talk. Ligada, o indicador de microfone do macOS fica aceso, e o menu SHALL mostrar que a escuta está ligada. O push-to-talk SHALL funcionar igual com a escuta ligada ou desligada.

#### Scenario: Desligar
- **WHEN** o Kaio desmarca "Ouvir 'Jarvis'" no menu da barra
- **THEN** o microfone é fechado, o ponto laranja do macOS some e dizer "Jarvis" não faz nada

#### Scenario: Lembrar depois de reiniciar
- **WHEN** o Kaio deixa a escuta ligada e reinicia o Mac
- **THEN** depois do login a escuta volta ligada

### Requirement: Escuta local e leve
A detecção da palavra SHALL rodar no Mac, sem rede e sem chave de serviço, e o áudio da escuta SHALL NOT sair do Mac nem ser guardado. Só o trecho do pedido, depois de "Jarvis", SHALL ser transcrito; o resto do áudio SHALL ser descartado na hora. A escuta SHALL usar no máximo cerca de 5% de um núcleo de CPU em média, e o Jarvis SHALL registrar no log cada ativação (hora e confiança, sem áudio nem texto), para medir alarmes falsos.

#### Scenario: Conversa sem a palavra
- **WHEN** o Kaio conversa com alguém perto do Mac por uma hora sem dizer "Jarvis"
- **THEN** nada é transcrito nem enviado ao modelo, e o log não mostra ativações (ou mostra no máximo uma)

#### Scenario: Sem internet
- **WHEN** o Mac está sem internet e o Kaio diz "Jarvis, que horas são?"
- **THEN** a palavra é detectada e o pedido segue pelo mesmo caminho da voz (a resposta depende do modelo, como hoje)

### Requirement: Sem ativação pela própria voz
A escuta SHALL ficar pausada enquanto o Jarvis estiver falando e enquanto o atalho de voz estiver segurado, e SHALL voltar logo depois.

#### Scenario: Resposta com o nome
- **WHEN** o Jarvis fala uma resposta que contém a palavra "Jarvis"
- **THEN** ele não se ativa sozinho

#### Scenario: Push-to-talk com a escuta ligada
- **WHEN** a escuta está ligada e o Kaio segura ⌘⇧Espaço e diz "Jarvis, abre o Safari"
- **THEN** o pedido é atendido uma vez só, pelo push-to-talk
