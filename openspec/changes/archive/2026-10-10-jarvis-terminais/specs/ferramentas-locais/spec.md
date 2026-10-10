## ADDED Requirements

### Requirement: Listar terminais
O Jarvis SHALL ter a ferramenta local somente leitura `listar_terminais`, que devolve os terminais abertos (número, pasta, estado e, se houver, a ferramenta do pedido de permissão pendente), sem executar nada; o resumo do pedido vai só para o cartão na tela, não para o modelo.

#### Scenario: Nenhum terminal
- **WHEN** não há sessão do Claude Code aberta
- **THEN** `listar_terminais` devolve a lista vazia e o Jarvis diz que não há terminais abertos
