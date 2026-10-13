## Purpose
Mandar ao Kaio, todo dia de manhã, as notícias mais relevantes dos temas dele e do futebol (Flamengo e Barcelona primeiro), de fontes grandes, sem inventar e sem repetir.

## ADDED Requirements

### Requirement: Boletim diário
O núcleo SHALL montar um boletim por dia, conferindo a cada 30 minutos entre 07:30 e 22:00 (America/Sao_Paulo) e na subida do app se o boletim de hoje ainda não saiu com sucesso, com no máximo 2 tentativas por dia. O boletim SHALL ter até 5 notícias gerais dos temas configurados em `config/noticias.yaml` e uma seção de futebol com até 3 notícias, priorizando os times configurados (Flamengo e Barcelona). A busca SHALL usar no máximo `NOTICIAS_MAX_BUSCAS` buscas (padrão 8), restritas aos domínios de fontes do perfil. Cada boletim SHALL gerar uma linha em `agent_runs` (canal `noticias`) com modelo, tokens, buscas, custo e erro. Com `NOTICIAS_ATIVO=false`, nada roda.

#### Scenario: Manhã normal
- **WHEN** são 07:30 e o boletim de hoje ainda não saiu
- **THEN** o núcleo pesquisa, monta o boletim e o entrega

#### Scenario: Mac dormindo às 07:30
- **WHEN** o Mac acorda às 09:10 sem o boletim de hoje
- **THEN** o boletim sai na checagem seguinte, no mesmo dia

### Requirement: Notícia verificada, recente e sem repetição
Uma notícia SHALL entrar só se o link dela tiver aparecido nos resultados da busca do próprio boletim, for de um domínio da lista de fontes e não for mais velha que ~36 horas quando a data aparecer no resultado. Título e resumo SHALL estar sempre em português (traduzidos quando a fonte é estrangeira), com o link original, e o nome da fonte SHALL vir do domínio do link, não do texto do modelo. O mesmo fato vindo de fontes diferentes SHALL aparecer uma vez só. Uma notícia com o mesmo link, ou com título quase igual ao de uma enviada nos 3 dias anteriores, SHALL NOT voltar.

#### Scenario: Link inventado
- **WHEN** o modelo devolve uma notícia com um link que não veio da busca
- **THEN** ela é descartada

#### Scenario: Mesmo fato no dia seguinte
- **WHEN** a notícia "STF julga X" saiu ontem e hoje outra fonte traz o mesmo título quase igual
- **THEN** ela não entra no boletim de hoje

### Requirement: Entrega do boletim
O boletim SHALL ir ao WhatsApp do Kaio numa mensagem de texto fixo (sem LLM na redação), com as notícias gerais e depois a seção de futebol, cada uma com título, uma linha de resumo, fonte e link; boletim sem nenhuma notícia SHALL NOT mandar mensagem. O painel do Jarvis SHALL mostrar a edição mais recente do boletim com a data dela (antes do boletim de hoje sair, a de ontem), e o resumo falado do "Hey Jarvis" SHALL ler os títulos das 3 primeiras notícias gerais, cortados em cerca de 70 caracteres, depois da agenda, sempre que houver um boletim: o de hoje ou, antes de ele sair, o mais recente, dizendo de quando é ("Nas notícias de ontem: …"); o resumo inteiro SHALL caber em cerca de 30 segundos de fala.

#### Scenario: Boletim com futebol
- **WHEN** o boletim tem 5 notícias gerais e "Flamengo vence o Palmeiras por 2 a 1"
- **THEN** a mensagem traz as 5 e, numa seção "⚽ Futebol", a do Flamengo, com fonte e link

#### Scenario: Hey Jarvis de manhã
- **WHEN** às 08:00 o Kaio diz "Hey Jarvis" e o boletim de hoje já saiu
- **THEN** depois do clima e da agenda o Jarvis fala as 3 primeiras manchetes

#### Scenario: Hey Jarvis antes do boletim de hoje
- **WHEN** às 06:30 o Kaio diz "Hey Jarvis" e o boletim de hoje ainda não saiu
- **THEN** o Jarvis fala as 3 primeiras manchetes de ontem, começando por "Nas notícias de ontem"

#### Scenario: Fonte estrangeira
- **WHEN** a notícia de mundo vem da BBC em inglês
- **THEN** o título e o resumo aparecem em português, com a fonte "BBC" e o link original

#### Scenario: Madrugada
- **WHEN** à 01:00 o Kaio abre o painel
- **THEN** o cartão mostra "Notícias de ontem" com o boletim do dia anterior
