## MODIFIED Requirements

### Requirement: Dados do painel
O MCP SHALL expor a ferramenta somente leitura `painel`, sem argumentos e fora dos grupos do agente do WhatsApp, que devolve em JSON: data e hora atuais; eventos de hoje e dos próximos 7 dias (com recorrências expandidas); gastos do mês corrente por categoria e o total do mês, em centavos; a fatura aberta de cada cartão de crédito (total em centavos, fechamento, vencimento e `mes_vencimento`); os últimos 10 registros (gastos lançados e eventos criados, por ordem de criação; nos gastos, a origem `whatsapp` quando vieram de uma mensagem ou `mac` quando vieram pelo MCP); e as vagas dos últimos 14 dias não dispensadas (título, organização, tipo, local, prazo e link), no máximo 8. Somas e datas de fatura SHALL ser calculadas no núcleo, com a mesma regra da ferramenta `total_fatura`.

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
