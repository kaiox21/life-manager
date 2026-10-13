## Purpose
Encontrar sozinho, a cada 3 dias, oportunidades que combinam com o Kaio (estágio, bolsa de pesquisa, monitoria, dev júnior), sem inventar vaga e sem repetir, e avisá-lo pelo WhatsApp e no painel.

## ADDED Requirements

### Requirement: Radar periódico
O núcleo SHALL rodar o radar quando a última rodada **bem-sucedida** tiver sido há 72 horas ou mais, conferindo isso a cada hora entre 08:00 e 22:00 (America/Sao_Paulo) e na subida do app; uma rodada que falha SHALL ser tentada de novo na checagem seguinte, no máximo 2 tentativas por dia. O radar pesquisa na internet oportunidades do perfil configurado em `config/vagas.yaml` (tipos, local, áreas de interesse e restrições de horário; arquivo fora do git), usando no máximo `VAGAS_MAX_BUSCAS` buscas (padrão 12). Com `VAGAS_ATIVO=false`, nada roda. Cada rodada SHALL gerar uma linha em `agent_runs` (canal `vagas`) com modelo, tokens, buscas, custo e erro, se houver.

#### Scenario: Rodada no horário
- **WHEN** são 08:00 e a última rodada foi há 3 dias
- **THEN** o núcleo pesquisa, registra a rodada em `agent_runs` e entrega as vagas novas

#### Scenario: Mac dormindo às 08:00
- **WHEN** o Mac acorda às 11:00 e a última rodada bem-sucedida foi há 3 dias
- **THEN** a rodada acontece na checagem das 11:00 ou 12:00, no mesmo dia

#### Scenario: Rodada que falhou
- **WHEN** a rodada das 08:00 falha (rede fora)
- **THEN** ela é tentada de novo na checagem seguinte, e no máximo 2 vezes naquele dia

### Requirement: Só vaga com link verificado
Uma vaga SHALL entrar só se o link dela tiver aparecido nos resultados da busca da própria rodada; vaga sem link, com link fora dos resultados ou fora do perfil (tipo ou local fora do configurado, ou horário que a própria vaga informa como noturno ou em conflito com o curso noturno) SHALL ser descartada; vaga sem horário informado NÃO é descartada por isso. Quando a busca só traz a página de listagem (por exemplo, as vagas de uma empresa), a vaga entra com o link da listagem e o resumo diz o que é. Cada vaga guarda título, organização, tipo (`estagio`, `bolsa`, `monitoria`, `junior`), local, prazo (quando informado) e um resumo de uma linha.

#### Scenario: Link inventado
- **WHEN** o modelo devolve uma vaga com uma URL que não está entre os resultados da busca
- **THEN** a vaga é descartada e não aparece para o Kaio

### Requirement: Sem repetir
Vagas SHALL ser registradas pela URL normalizada (sem parâmetros de rastreio, sem barra final) e ganhar um código curto e estável (V1, V2… em ordem de registro); uma vaga já registrada SHALL NOT ser entregue de novo, mesmo que reapareça em outra rodada. Vagas com prazo vencido SHALL NOT ser entregues.

#### Scenario: Vaga reaparece
- **WHEN** a mesma vaga do Gupy aparece em duas rodadas
- **THEN** ela só é avisada na primeira

### Requirement: Entrega
Ao fim de uma rodada com vagas novas, o núcleo SHALL mandar ao WhatsApp do Kaio uma mensagem de texto fixo (sem LLM na redação) com até 8 vagas, ordenadas pelas áreas de interesse e pelo prazo mais próximo, cada uma com o código, título, organização, tipo, local, prazo (ou "sem prazo informado") e link; rodada sem vaga nova SHALL NOT mandar mensagem. O painel do Jarvis SHALL mostrar as vagas dos últimos 14 dias que não foram dispensadas.

#### Scenario: Vagas novas
- **WHEN** a rodada encontra 3 vagas novas
- **THEN** o Kaio recebe uma mensagem "🔎 3 vagas novas" com as três, e elas aparecem no cartão Vagas do painel

#### Scenario: Nada novo
- **WHEN** a rodada não encontra vaga nova
- **THEN** nenhuma mensagem é enviada

### Requirement: Consulta e dispensa
O Kaio SHALL poder perguntar pelas vagas recentes (WhatsApp ou Jarvis) e receber a lista dos últimos 14 dias não dispensadas, com os mesmos códigos da mensagem, e SHALL poder dispensar uma vaga pelo código ou pelo título ("não tenho interesse na V12"), que some das listas e do painel; código ou título que não identifica uma vaga só SHALL voltar as opções, sem dispensar nada. As duas ações vêm de ferramentas do núcleo (`listar_vagas`, `dispensar_vaga`); dispensar não apaga o registro (continua valendo para não repetir).

#### Scenario: Código da mensagem e da lista é o mesmo
- **WHEN** a mensagem de segunda trouxe a V12 e a de quinta trouxe a V15, e o Kaio pede a lista
- **THEN** as duas aparecem como V12 e V15, e "não tenho interesse na V12" esconde a de segunda

#### Scenario: Dispensar
- **WHEN** o Kaio diz "não tenho interesse na vaga da Fulano Tech"
- **THEN** a vaga some da lista e do painel e não volta nas próximas rodadas
