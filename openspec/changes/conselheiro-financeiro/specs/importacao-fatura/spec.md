## Purpose
Ler a fatura do cartão exportada em PDF, conferir a soma no código, casar os itens com os gastos já lançados e lançar só o que falta, sempre depois do "sim" do Kaio.

## ADDED Requirements

### Requirement: Entrada da fatura
A importação SHALL aceitar um PDF de até 10 MB vindo do WhatsApp (documento anexado, com a legenda como `cartao`) ou do Jarvis (ferramenta MCP `importar_fatura_pdf(pdf_base64, cartao?)`, escondida do modelo do Jarvis e chamada pela ação local `importar_fatura`). O texto SHALL ser extraído no núcleo, sem OCR. PDF sem texto extraível, com senha ou que não seja PDF SHALL ser recusado com uma resposta curta que diz o motivo. O PDF e o texto extraído SHALL NOT ser guardados em disco nem no banco; `messages.body` guarda só a legenda.

#### Scenario: PDF escaneado
- **WHEN** chega um PDF cujas páginas são só imagem
- **THEN** a resposta diz que a fatura precisa ser o PDF exportado pelo app do banco e nada é gravado

#### Scenario: PDF com senha
- **WHEN** chega um PDF protegido por senha
- **THEN** a resposta pede o PDF sem senha e nada é gravado

### Requirement: Mascaramento antes do modelo
Antes de enviar o texto ao modelo, toda sequência de 13 a 19 dígitos (com ou sem espaços, pontos ou hífens entre grupos) SHALL ser trocada por `****` mais os 4 últimos dígitos. Nenhum log SHALL conter o texto da fatura, só a contagem de itens, o cartão e os totais.

#### Scenario: Número completo do cartão no PDF
- **WHEN** o texto traz "5162 9012 3456 7890"
- **THEN** o modelo recebe "****7890"

### Requirement: Transcrição pelo modelo, contas no código
O modelo principal SHALL apenas transcrever, numa chamada de ferramenta forçada: o emissor e o final do cartão, a data de vencimento, os totais impressos (total da fatura, saldo anterior, pagamentos recebidos) e cada item, com data, descrição, valor exatamente como impresso, parcela ("3/10") quando houver e tipo (`compra`, `estorno`, `encargo`, `pagamento`). Valores SHALL ser convertidos para centavos pelo código; o modelo SHALL NOT somar nem converter. Linhas de valor zero (ex.: "IOF 0,00") são descartadas. Data sem ano ganha o ano do vencimento, ou o anterior se cairia depois do vencimento. Transcrição inválida segue a validação e a escalada do agente.

#### Scenario: Valor com milhar
- **WHEN** o item é impresso como "R$ 1.234,56"
- **THEN** o código grava 123456 centavos

### Requirement: Conferência da soma
O código SHALL conferir, em centavos, que saldo anterior − pagamentos recebidos + compras + encargos − estornos é igual ao total impresso. Se não bater, o resumo SHALL mostrar a diferença em destaque antes da pergunta, e a importação continua dependendo do "sim". Fatura sem total impresso legível SHALL ser recusada.

#### Scenario: Soma confere
- **WHEN** os itens transcritos somam exatamente o total impresso
- **THEN** o resumo diz "soma confere com o total da fatura"

#### Scenario: Item perdido na transcrição
- **WHEN** a soma dos itens fica R$ 45,90 abaixo do total impresso
- **THEN** o resumo começa com "Atenção: os itens somam R$ 45,90 a menos que o total da fatura"

### Requirement: Cartão e ciclo da fatura
O cartão SHALL ser resolvido pela legenda ou pelo argumento `cartao` e, se eles não resolverem, pelo emissor transcrito, com a mesma resolução de meio de pagamento dos gastos, e só entre meios de crédito; ambíguo ou inexistente devolve `opcoes` para perguntar. Pelo WhatsApp, como o PDF não é guardado, a resposta pede para mandar o PDF de novo com o nome do cartão na legenda; pelo Jarvis, o modelo pergunta e chama de novo com `cartao`. O ciclo é o mês do vencimento impresso: os itens importados SHALL ter `statement_month` igual ao dia 1 desse mês, mesmo quando a regra da fatura daria outro mês para a data da compra.

#### Scenario: Legenda que não é cartão
- **WHEN** o PDF chega com a legenda "fatura de outubro" e o emissor impresso não é um cartão cadastrado
- **THEN** a resposta lista os cartões de crédito e pede o PDF de novo com o cartão na legenda

#### Scenario: Compra processada depois do fechamento
- **WHEN** uma compra de 31/10 aparece na fatura que vence em 08/11
- **THEN** ela entra com `statement_month = 2026-11-01`

### Requirement: Casamento com gastos lançados
Cada item de compra ou encargo SHALL casar com no máximo um gasto ativo do mesmo cartão, com o mesmo valor da parcela (até 1 centavo de diferença em compra parcelada, pelo arredondamento do rateio), a mesma parcela (número e total), e `spent_on` a até 3 dias da data do item; havendo mais de um candidato, vence o de data mais próxima e depois o de descrição mais parecida. Itens que casam SHALL ficar como estão. Gastos ativos do mesmo cartão e do mesmo ciclo que não casaram com nenhum item SHALL ser listados no resumo como "lançados por você e fora da fatura", sem serem alterados.

#### Scenario: Almoço já lançado
- **WHEN** o Kaio lançou "almoço 47,90 nubank" em 15/10 e a fatura traz "RESTAURANTE X 47,90" em 16/10
- **THEN** o item casa e não é lançado de novo

#### Scenario: Gasto lançado que não está na fatura
- **WHEN** há um gasto de R$ 30,00 no Nubank no ciclo e nenhum item corresponde
- **THEN** o resumo cita esse gasto e ele continua gravado

### Requirement: Lançamento do que falta
Itens de compra e encargo sem par SHALL virar gastos com `source='fatura'`, categoria sugerida pelo modelo dentre as categorias existentes (padrão "Outros") e `merchant` igual à descrição impressa. Um item parcelado "k/N" SHALL gerar as parcelas k a N num mesmo `purchase_group`, cada uma um mês depois da anterior, com o valor da parcela impresso, `installment_no` e `installment_total` preenchidos, e `spent_on` igual à data impressa da compra; as parcelas futuras que já existem casadas não são duplicadas. Estornos SHALL ser lançados como gasto de valor negativo na mesma fatura; pagamentos recebidos SHALL NOT virar gasto.

#### Scenario: Compra parcelada nova
- **WHEN** a fatura de novembro traz "LOJA Y 03/10 R$ 120,00" sem par
- **THEN** são gravadas as parcelas 3 a 10 de R$ 120,00, de novembro de 2026 a junho de 2027

#### Scenario: Pagamento da fatura anterior
- **WHEN** a fatura traz "PAGAMENTO RECEBIDO -R$ 2.000,00"
- **THEN** nada é lançado por esse item

### Requirement: Confirmação da importação
A importação SHALL criar uma pendência (expira em 30 minutos) com um resumo fixo montado pelo código: cartão e vencimento, número de itens e total impresso, a conferência da soma, quantos já estavam lançados, quantos e quanto serão lançados (com a lista dos novos), e os gastos fora da fatura. Só o "sim" grava, numa transação única; "não" descarta. Pelo Jarvis, o resumo aparece num cartão com a mesma confirmação.

#### Scenario: Sim depois do resumo
- **WHEN** o resumo diz "12 novos, R$ 845,10" e o Kaio responde "sim"
- **THEN** os 12 itens são gravados e a resposta ecoa "Lancei 12 gastos da fatura do Nubank (venc. 08/11), R$ 845,10"

### Requirement: Reimportação
Cada importação confirmada SHALL ficar registrada (cartão, ciclo, total impresso, impressão digital do arquivo, data). Uma fatura do mesmo cartão e ciclo lida de novo SHALL seguir o mesmo casamento, de modo que nada se duplica, e o resumo SHALL dizer quando ela foi importada antes.

#### Scenario: Mesma fatura duas vezes
- **WHEN** o Kaio manda de novo a fatura já importada
- **THEN** o resumo diz "já importada em 29/10; nada novo para lançar" e não cria pendência

### Requirement: Registro e custo
Cada leitura de fatura SHALL gerar uma linha em `agent_runs` com a intenção `fatura`, o modelo, tokens, custo, latência e as etapas (`extracao`, `transcricao`), sem o conteúdo da fatura.

#### Scenario: Leitura registrada
- **WHEN** uma fatura é lida
- **THEN** `agent_runs` registra tokens e custo e `tools_called` não contém descrições dos itens
