## MODIFIED Requirements

### Requirement: Conteúdo do painel
O painel SHALL mostrar, no layout HUD aprovado (orbe ao centro cercado de anéis, colunas laterais em cartões de cantos chanfrados, paleta azul-marinho): relógio e data em anel, com o próximo compromisso; compromissos de hoje numa linha do tempo, com o próximo destacado, e os dos próximos 7 dias; o mês em anel, com o total do mês e os gastos por categoria; a fatura aberta de cada cartão de crédito, com total, fechamento, vencimento e dias até fechar; um registro com os últimos lançamentos e eventos criados (por qualquer canal) e as perguntas feitas ao Jarvis na sessão; o clima de agora com máxima, mínima e chance de chuva; memória livre, swap e bateria do Mac; os terminais com o estado de cada um; a música tocando no Spotify; um lançador de projetos (a lista que o Kaio configurar ou, sem ela, as pastas de projeto usadas mais recentemente, sempre dentro das pastas permitidas); e botões de modo, só para funções que já existem (Resumo, Música, Terminais). Um dado indisponível (clima sem internet, Spotify fechado) SHALL aparecer como indisponível no seu cartão sem esconder os outros.

#### Scenario: Gasto lançado pelo WhatsApp
- **WHEN** o Kaio lança "47 no almoço no Nubank" pelo WhatsApp e depois abre o painel
- **THEN** o gasto aparece no registro, a categoria Alimentação e o total do mês incluem o valor, e a fatura aberta do Nubank também

#### Scenario: Dia sem compromissos
- **WHEN** não há eventos hoje
- **THEN** a linha do tempo diz que o dia está livre e mostra os próximos compromissos da semana

#### Scenario: Botão Resumo
- **WHEN** o Kaio clica em Resumo
- **THEN** o Jarvis fala o resumo do dia, o mesmo do "Hey Jarvis", e o texto aparece na conversa

#### Scenario: Projeto no lançador
- **WHEN** o Kaio clica em "life-manager" no lançador
- **THEN** abre um terminal nessa pasta na área de terminais do painel

#### Scenario: Sem internet
- **WHEN** o Mac está sem internet e o Kaio abre o painel
- **THEN** o cartão do clima diz que o clima está indisponível e os demais cartões aparecem normalmente

### Requirement: Números vindos do núcleo
Todos os valores, somas, datas de fatura e listas de agenda e gastos do painel SHALL vir prontos do núcleo pelo MCP; os dados locais (clima, memória, swap, bateria, música, projetos) e os dias até o fechamento SHALL vir prontos do cérebro; a interface SHALL só desenhar, sem calcular totais, e abrir ou atualizar o painel SHALL NOT chamar o modelo de linguagem.

#### Scenario: Abrir sem custo
- **WHEN** o Kaio abre o painel
- **THEN** os dados chegam sem nenhuma chamada ao LLM (nenhum token gasto)

### Requirement: Movimento acessível
As animações do painel (orbe de partículas, pulso da voz, transições) SHALL respeitar a preferência "Reduzir movimento" do macOS e SHALL parar quando o painel fechar. Os anéis e medidores SHALL ser desenhados parados, mudando só quando o dado muda.

#### Scenario: Reduzir movimento ligado
- **WHEN** "Reduzir movimento" está ligado no macOS
- **THEN** o orbe aparece estático, sem pulso da voz, e as transições são só de opacidade

#### Scenario: Painel aberto e parado
- **WHEN** o painel está aberto sem conversa nem fala por um minuto
- **THEN** só o orbe se move, devagar, e nenhum anel ou medidor fica animando

## ADDED Requirements

### Requirement: Orbe reage à resposta
Enquanto o Jarvis fala, o orbe do painel SHALL pulsar acompanhando o volume real da voz que está tocando (mais alto, maior e mais brilhante; pausa entre frases, menor), e enquanto o texto da resposta chega (com ou sem voz) SHALL ficar visivelmente mais rápido e brilhante que parado. Ao fim da resposta e da fala, SHALL voltar ao movimento de parado. O pulso SHALL chegar ao painel aberto qualquer que seja a origem da fala (HUD, palavra "Jarvis", fala proativa), e uma interface escondida SHALL ignorá-lo.

#### Scenario: Resposta falada
- **WHEN** o Kaio pergunta "quanto gastei esse mês?" e o Jarvis responde em voz
- **THEN** o orbe pulsa no ritmo da fala e volta ao normal quando a voz termina

#### Scenario: Pedido feito pelo HUD com o painel aberto
- **WHEN** o painel está aberto e uma resposta começa a ser falada a partir de outra janela
- **THEN** o orbe do painel pulsa com a voz do mesmo jeito

#### Scenario: Resposta digitada
- **WHEN** o Kaio digita a pergunta no painel e a resposta chega só em texto
- **THEN** o orbe acelera e brilha enquanto o texto chega e volta ao normal no fim
