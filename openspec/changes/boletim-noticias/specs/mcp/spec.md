## MODIFIED Requirements

### Requirement: Dados do painel
O MCP SHALL expor a ferramenta somente leitura `painel`, sem argumentos e fora dos grupos do agente do WhatsApp, que devolve em JSON: data e hora atuais; eventos de hoje e dos próximos 7 dias (com recorrências expandidas); gastos do mês corrente por categoria e o total do mês, em centavos; a fatura aberta de cada cartão de crédito (total em centavos, fechamento, vencimento e `mes_vencimento`); os últimos 10 registros (gastos lançados e eventos criados, por ordem de criação; nos gastos, a origem `whatsapp` quando vieram de uma mensagem ou `mac` quando vieram pelo MCP); as vagas dos últimos 14 dias não dispensadas (código, título, organização, tipo, local, prazo e link), no máximo 8; e a edição mais recente do boletim de notícias (data da edição e, por notícia, título, resumo, fonte, link e se é de futebol), quando existir. Somas e datas de fatura SHALL ser calculadas no núcleo, com a mesma regra da ferramenta `total_fatura`.

#### Scenario: Fatura aberta igual à da conversa
- **WHEN** o Jarvis chama `painel` em 09/10/2026
- **THEN** o total da fatura aberta do Nubank é o mesmo que `total_fatura` devolve para o Nubank com o `mes_vencimento` da fatura aberta

#### Scenario: Sem escrita
- **WHEN** `painel` é chamada
- **THEN** nada é gravado no banco, nem em `agent_runs`, e o sync do Google Calendar não é disparado

#### Scenario: Excluídos não aparecem
- **WHEN** um gasto foi desfeito (`deleted_at` preenchido)
- **THEN** ele não entra nas somas nem no registro do `painel`

#### Scenario: Vagas no painel
- **WHEN** há 2 vagas encontradas há 5 dias e 1 dispensada
- **THEN** o `painel` traz só as 2 não dispensadas

#### Scenario: Boletim no painel
- **WHEN** o boletim de hoje saiu com 5 notícias gerais e 2 de futebol
- **THEN** o `painel` traz a edição de hoje com as 7, as de futebol marcadas

#### Scenario: Antes do boletim de hoje
- **WHEN** são 06:00 e o boletim de hoje ainda não saiu
- **THEN** o `painel` traz a edição de ontem, com a data dela
