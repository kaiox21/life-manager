## ADDED Requirements

### Requirement: Ativação pela palavra "Jarvis"
Com a escuta ligada, uma frase que comece com "Jarvis" SHALL ativar o Jarvis sem tocar no teclado: o HUD SHALL aparecer sem roubar o foco do app em uso (ou o painel, se estiver aberto, cuida da fala), e o que for dito depois de "Jarvis", até uma pausa, SHALL virar o pedido, respondido como no push-to-talk. "Jarvis" sozinho SHALL abrir o HUD ouvindo e esperar o pedido por alguns segundos; sem pedido, o HUD SHALL voltar a como estava sem chamar o modelo. A palavra "Jarvis" no começo SHALL ser tirada do texto do pedido.

#### Scenario: Pedido numa frase
- **WHEN** a escuta está ligada, o Kaio está em outro app e diz "Jarvis, o que eu tenho amanhã?"
- **THEN** o HUD aparece sem tirar o foco do app, mostra "o que eu tenho amanhã?" como pergunta e o Jarvis responde falando

#### Scenario: Só o nome
- **WHEN** o Kaio diz "Jarvis", espera o HUD aparecer e depois diz "abre o Spotify"
- **THEN** o Jarvis abre o Spotify

#### Scenario: Só o nome e silêncio
- **WHEN** o Kaio diz "Jarvis" e não fala mais nada
- **THEN** o HUD volta a como estava, sem chamar o modelo

#### Scenario: Painel aberto
- **WHEN** o painel está aberto e o Kaio diz "Jarvis, quanto eu gastei esse mês?"
- **THEN** a pergunta e a resposta aparecem no painel, e o HUD não aparece por cima

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
