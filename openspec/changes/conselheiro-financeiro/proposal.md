## Why

Hoje o total da fatura só fica certo se o Kaio lançar cada compra à mão, e o assistente não tem como dizer se uma compra cabe no orçamento. O Kaio pediu, em 29/10/2026, que o life-manager funcione como um conselheiro financeiro: que leia as faturas do cartão exportadas em PDF, lance o que falta e responda "essa compra é segura?" com base nos números reais.

## What Changes

- **Ler fatura em PDF**, pelo WhatsApp (anexar o PDF na conversa) e pelo Jarvis ("lê a fatura do Nubank que baixei"):
  - o texto sai do PDF no núcleo, sem OCR; PDF escaneado (sem texto) ou com senha é recusado com uma resposta curta;
  - antes de ir ao modelo, sequências de 13 a 19 dígitos (número de cartão) são mascaradas;
  - o modelo principal (Haiku) só **transcreve** os itens: data, descrição, valor como aparece, parcela "3/10" e tipo do item (compra, estorno, encargo, pagamento). Ele também transcreve os totais impressos e o vencimento;
  - o Python converte os valores para centavos e **confere a soma**: saldo anterior − pagamentos + itens = total impresso. Se não bater, o resumo mostra a diferença em destaque;
  - o PDF e o texto não ficam guardados.
- **Casar com o que já foi lançado e lançar só o que falta:**
  - um item da fatura casa com um gasto do mesmo cartão quando o valor da parcela é igual e a data está a até 3 dias;
  - os itens que casam ficam como estão, e os que não casam viram gastos com `source='fatura'`;
  - uma compra parcelada vista como "3/10" grava as parcelas 3 a 10, cada uma na fatura certa, porque as parcelas futuras pesam no conselho;
  - o resumo também avisa quais gastos lançados à mão naquele ciclo **não aparecem** na fatura. Nada é apagado;
  - **nada é gravado antes do "sim"**: o resumo vira uma pendência, como já acontece com foto e áudio;
  - importar a mesma fatura de novo não duplica nada, e o resumo diz que ela já foi lida e quando.
- **Renda e contas fixas, informadas uma vez:**
  - "minha renda é 3.500 todo dia 5", "aluguel 900 dia 10", "tira a academia";
  - as ferramentas são `gerenciar_renda` e `gerenciar_conta_fixa`, com exclusão lógica.
- **"Essa compra é segura?":**
  - "posso comprar um fone de 400 em 4x no nubank?" chama `avaliar_compra`;
  - o Python projeta cada mês que a compra atinge: renda − contas fixas − parcelas já comprometidas − média dos gastos avulsos dos últimos 3 meses − a parcela nova;
  - o veredito é fixo no código:
    - **segura:** sobram 20% ou mais da renda em todos os meses;
    - **atenção:** sobra entre 0 e 20%;
    - **arriscada:** algum mês fica negativo;
  - o modelo só explica os números que recebeu, sem fazer conta;
  - sem renda cadastrada, a resposta pede a renda em vez de chutar.

## Non-goals

- Open Finance ou login no banco. A fatura entra só pelo PDF que o Kaio exporta.
- Extrato de conta corrente, como débito e Pix do banco. Só faturas de cartão de crédito.
- OCR de PDF escaneado ou foto de fatura impressa.
- Saldo em conta, limite do cartão, investimentos e metas de economia.
- Pagar a fatura, mexer no app do banco ou dar recomendação de investimento.
- Avisos proativos sobre o orçamento, por exemplo "você passou do limite do mês". Isso fica para outra change.
- Mostrar o orçamento no painel do Jarvis. O conselho aparece na conversa e no cartão da resposta.

## Decisões do SPEC.md que mudam

- **"Fora (por ora)"** listava a importação automática de fatura e "metas e orçamento":
  - a importação de fatura por PDF passa a ser escopo;
  - o orçamento entra só como renda, contas fixas e avaliação de compra;
  - metas continuam fora.
- **"Entrada de gastos"** dizia: "Texto, áudio e foto de recibo; sem importação de fatura". Passa a valer: texto, áudio, foto e PDF da fatura. O risco "total da fatura só é exato se tudo for lançado" ganha a mitigação "importar o PDF".
- **"O LLM nunca faz contas"** continua valendo: na fatura, o modelo transcreve e o Python soma e confere; no conselho, o Python projeta e decide o veredito.

## Capabilities

### New Capabilities
- `importacao-fatura`: leitura do PDF, mascaramento, transcrição pelo modelo, conferência da soma, casamento com os gastos lançados, parcelas futuras, pendência e reimportação.
- `conselho-financeiro`: renda e contas fixas, projeção mensal, veredito fixo e a explicação pelo modelo.

### Modified Capabilities
- `midia`: o WhatsApp passa a aceitar documento PDF de até 10 MB (os outros documentos continuam ignorados).
- `agente`: nova intenção `conselho`. Documento PDF não passa pelo classificador e vai direto à importação. A lista de intenções da spec é corrigida para incluir `vagas`, que já existe no código.
- `ferramentas-locais`: nova ação `importar_fatura(arquivo)` no Jarvis. Ela lê um PDF da pasta pessoal e o entrega ao núcleo pelo MCP.

## Impact

- **Núcleo:**
  - `app/domain/statement.py`: valores em centavos, conferência da soma, casamento e parcelas, tudo puro e testado;
  - `app/domain/budget.py`: projeção e veredito;
  - `app/statements/`: extração do texto e a chamada de transcrição;
  - ferramentas `importar_fatura`, `gerenciar_renda`, `gerenciar_conta_fixa` e `avaliar_compra`;
  - o grupo `conselho` no agente;
  - o canal do WhatsApp lê `documentMessage` com PDF.
- **Banco:** tabelas `statement_imports` e `budget_items`, numa migração Alembic.
- **Dependência nova:** `pypdf`, para extrair o texto. É Python puro e roda no Docker.
- **Jarvis:**
  - ação local `importar_fatura`;
  - cartão com o resumo da fatura e a confirmação que já existe;
  - cartão do conselho.
- **Prova:** os casos novos de `conselho` e da importação precisam entrar em `tests/eval/casos.yaml`. Esse arquivo é somente leitura, então adicioná-los **depende da autorização do Kaio**.
- **Custo estimado:** cerca de US$ 0,003 por fatura com o Haiku (uns 10 mil tokens de entrada e 3 mil de saída) e uma chamada curta por pergunta de conselho. Tudo vai para `agent_runs`.
- **Privacidade:** o texto da fatura, já mascarado, vai à API da Anthropic, como as fotos de recibo já vão hoje. Nada da fatura entra nos logs.
- **Branch:** `feat/conselheiro-financeiro`, a partir de `main`.
