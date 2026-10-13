## Purpose
Encontrar sozinho, a cada 3 dias, oportunidades que combinam com o Kaio (estágio, bolsa de pesquisa, monitoria, dev júnior), sem inventar vaga e sem repetir, e avisá-lo pelo WhatsApp e no painel.

## ADDED Requirements

### Requirement: Radar periódico
A cada 3 dias, às 08:00 (America/Sao_Paulo), o núcleo SHALL pesquisar na internet oportunidades do perfil configurado em `config/vagas.yaml` (tipos, local, áreas de interesse e restrições de horário), usando no máximo `VAGAS_MAX_BUSCAS` buscas (padrão 12). Se o núcleo estava desligado no horário, a rodada SHALL acontecer na subida seguinte, desde que a última tenha sido há mais de 3 dias. Com `VAGAS_ATIVO=false`, nada roda. Cada rodada SHALL gerar uma linha em `agent_runs` (canal `vagas`) com modelo, tokens, buscas e custo.

#### Scenario: Rodada no horário
- **WHEN** são 08:00 e a última rodada foi há 3 dias
- **THEN** o núcleo pesquisa, registra a rodada em `agent_runs` e entrega as vagas novas

#### Scenario: Mac desligado no horário
- **WHEN** o núcleo sobe às 10:00 e a última rodada foi há 4 dias
- **THEN** a rodada acontece logo na subida

### Requirement: Só vaga com link verificado
Uma vaga SHALL entrar só se o link dela tiver aparecido nos resultados da busca da própria rodada; vaga sem link, com link fora dos resultados ou fora do perfil (tipo, local ou horário incompatível com curso noturno) SHALL ser descartada. Cada vaga guarda título, organização, tipo (`estagio`, `bolsa`, `monitoria`, `junior`), local, prazo (quando informado) e um resumo de uma linha.

#### Scenario: Link inventado
- **WHEN** o modelo devolve uma vaga com uma URL que não está entre os resultados da busca
- **THEN** a vaga é descartada e não aparece para o Kaio

### Requirement: Sem repetir
Vagas SHALL ser registradas pela URL normalizada (sem parâmetros de rastreio, sem barra final); uma vaga já registrada SHALL NOT ser entregue de novo, mesmo que reapareça em outra rodada. Vagas com prazo vencido SHALL NOT ser entregues.

#### Scenario: Vaga reaparece
- **WHEN** a mesma vaga do Gupy aparece em duas rodadas
- **THEN** ela só é avisada na primeira

### Requirement: Entrega
Ao fim de uma rodada com vagas novas, o núcleo SHALL mandar ao WhatsApp do Kaio uma mensagem de texto fixo (sem LLM na redação) com até 8 vagas, ordenadas pelas áreas de interesse e pelo prazo mais próximo, cada uma com título, organização, tipo, local, prazo (ou "sem prazo informado") e link; rodada sem vaga nova SHALL NOT mandar mensagem. O painel do Jarvis SHALL mostrar as vagas dos últimos 14 dias que não foram dispensadas.

#### Scenario: Vagas novas
- **WHEN** a rodada encontra 3 vagas novas
- **THEN** o Kaio recebe uma mensagem "🔎 3 vagas novas" com as três, e elas aparecem no cartão Vagas do painel

#### Scenario: Nada novo
- **WHEN** a rodada não encontra vaga nova
- **THEN** nenhuma mensagem é enviada

### Requirement: Consulta e dispensa
O Kaio SHALL poder perguntar pelas vagas recentes (WhatsApp ou Jarvis) e receber a lista dos últimos 14 dias não dispensadas, e SHALL poder dispensar uma vaga ("não tenho interesse na 2"), que some das listas e do painel. As duas ações vêm de ferramentas do núcleo (`listar_vagas`, `dispensar_vaga`); dispensar não apaga o registro (continua valendo para não repetir).

#### Scenario: Dispensar
- **WHEN** o Kaio diz "não tenho interesse na vaga da Fulano Tech"
- **THEN** a vaga some da lista e do painel e não volta nas próximas rodadas
