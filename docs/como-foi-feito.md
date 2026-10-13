# Como foi feito

Este projeto é escrito em pareamento com o **Claude Code** (Anthropic). Esta página existe porque a pergunta "o que você fez e o que a IA fez?" é justa, e a resposta curta é: a IA gera; as decisões, a análise crítica e o aceite são do autor. O detalhe está abaixo.

## O ciclo de cada funcionalidade

Toda mudança segue o mesmo caminho, com o [OpenSpec](https://github.com/Fission-AI/OpenSpec):

1. **Pedido em linguagem natural.** "Quero que o Jarvis me mande todo dia as notícias mais relevantes."
2. **Perguntas de produto.** Quais temas? Quantas? Onde entregar? Essas respostas são do autor, e mudam o que o sistema faz.
3. **Proposta.** `proposal.md` (o quê e por quê), deltas em `specs/` (requisitos com cenários *WHEN/THEN*), `design.md` (como, com os fatos conferidos em documentação oficial e a data), `tasks.md`.
4. **Análise crítica, sempre.** Antes de aprovar, o autor pergunta: *"tem erro de premissa ou de requisito? está sólida?"* A resposta vira correções na proposta. Exemplos reais: o painel ficaria vazio de madrugada (passou a mostrar a edição de ontem com a data); a fonte da notícia viria do modelo (passou a sair do domínio do link); duas mudanças editavam o mesmo requisito (ordem de arquivamento definida).
5. **Aprovação e implementação.** Com testes unitários sem rede, e a prova contra o modelo real quando prompt, ferramenta ou modelo mudam.
6. **Aceite em uso real.** O autor usa; o que falha volta como ajuste. Só depois a mudança é arquivada e os deltas entram em `openspec/specs`.

As regras que não se negociam (o LLM nunca faz contas, dinheiro em centavos, datas com fuso, só um módulo conhece o WhatsApp, nenhuma ferramenta executa shell) estão em [`CLAUDE.md`](../CLAUDE.md) e valem em toda sessão.

## O que o processo pegou

Casos em que a primeira versão estava errada e a medição, o aceite ou a análise crítica corrigiram:

- **Palavra de ativação.** Alimentar o detector continuamente parecia a solução para "só entende a primeira vez". Medido em vozes sintéticas, caiu de 66% para 52%. Revertido; a correção certa foi a sensibilidade (88%) e só abrir o painel depois que a transcrição confirma o nome.
- **Voz "craquelada".** A hipótese inicial (modo de latência do serviço de voz) não resolveu. Instrumentando a saída de áudio: 36 a 76 *underruns* por frase. Uma thread dedicada de escrita com fila zerou.
- **Boletim de notícias, primeira rodada real.** A API de busca recusa o pedido inteiro se um domínio da lista bloqueia o robô (BBC, Reuters, UOL…). A lista foi refeita com 31 fontes conferidas uma a uma, e o código passou a tentar de novo sem os domínios recusados. Na mesma rodada, o modelo colocou o fato de uma notícia no link de outra: nasceu o filtro "o título tem que bater com a página".
- **Radar de vagas, primeira rodada real.** 3 das 7 "vagas" eram páginas de resultado de busca de agregadores. Entrou um filtro por padrão de URL e um corte por idade da publicação.
- **WhatsApp "conectado" e morto.** A instância dizia `open` e devolvia `428 Connection Closed`. O envio passou a reiniciar a instância e tentar de novo uma vez.
- **Memória.** Um cérebro órfão do Jarvis com 1,4 GB e 19 GB de swap: o serviço passou a rodar o Python direto (sem o gerenciador de pacotes no meio) e o Docker ganhou um teto de memória.

## O que não é decisão da IA

- **Produto:** o que entra, o que fica de fora, quantas notícias, quais temas, o que o painel mostra.
- **Custo:** quanto gastar por mês, quando rodar a prova, qual modelo em cada etapa. Tudo é medido em `agent_runs`.
- **Segurança:** o que fica fora do git (`.env`, perfis pessoais), que só o dono é atendido, que nenhuma ferramenta executa shell sem um cartão de confirmação.
- **Aceite:** se funcionou no uso real. "Passou nos testes" não é "está pronto".

## Custos de desenvolvimento e de operação

A prova custa centavos por rodada e é impressa no fim. A operação, com boletim diário e radar a cada 3 dias, fica perto de US$ 3 por mês. O preço de cada modelo está em configuração (`MODEL_PRICES`), e o custo por mensagem é calculado no código, não estimado.
