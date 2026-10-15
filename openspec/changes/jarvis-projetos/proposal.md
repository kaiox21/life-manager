## Why

Começar a trabalhar num projeto hoje são três gestos (achar a pasta, abrir o editor, abrir um terminal nela) e escrever um e-mail ou mensagem formal é uma tela a mais. O Jarvis já abre terminais em pastas permitidas e já escreve na área de transferência; falta juntar isso em dois pedidos de uma frase. É o item 3 da lista aprovada em 10/10/2026 (`docs/proximos-passos.md`).

## What Changes

- **Abrir projeto por voz ou texto:** "Jarvis, abre o NC Barber" abre a pasta no VS Code e um terminal do Jarvis nela (ou reaproveita um shell livre que já esteja nessa pasta). "Abre o life-manager com um Claude Code" abre o terminal já rodando o Claude Code. Só pastas da lista permitida dos terminais (`JARVIS_PASTAS`); o nome é casado sem ligar para maiúsculas, acentos, espaços e hífens ("NC Barber" acha `NC-BARBER`); mais de uma pasta com o mesmo nome vira pergunta. Sem o VS Code instalado, abre só o terminal e diz. Com o painel aberto, ele fecha para o editor aparecer, e a resposta é uma frase fixa montada do resultado (sem nova chamada ao modelo).
- **Rascunhos:** "escreve um e-mail pro professor de redes pedindo a segunda chamada" ou "faz uma mensagem pro Netto avisando que o site volta amanhã" produz o texto **em nome do Kaio** (sem a persona do mordomo), copia o corpo para a área de transferência, mostra um cartão no painel com destinatário, assunto e texto completo (botão **Copiar**) e guarda o rascunho num arquivo local. O turno termina com a frase fixa "Rascunho pronto no painel e na área de transferência, senhor.", sem nova chamada ao modelo: o Jarvis nunca lê o texto, e o texto nunca vai para o log.
- **Nunca envia.** Não existe ação de envio: nem e-mail, nem WhatsApp, nem nada. "Manda esse e-mail" recebe um não e a lembrança de que o texto está na área de transferência.
- Duas ferramentas locais novas, sem confirmação: `abrir_projeto(nome, claude)` e `rascunho(tipo, para, assunto, texto)`.

## Non-goals

- Abrir o Mail ou o WhatsApp com o texto preenchido (`mailto:`): fica para depois, se o fluxo copiar-e-colar incomodar.
- Listar ou reabrir rascunhos antigos por voz: os arquivos ficam guardados, a ferramenta de consulta não entra agora.
- Outro editor além do VS Code (o nome do app fica configurável, só isso).
- Criar projetos, clonar repositórios ou rodar comandos ao abrir (o requisito "Sem shell livre" continua intacto).

## Capabilities

### New Capabilities
- `jarvis-projetos`: abrir um projeto (editor + terminal) pelo nome, em pastas permitidas; rascunhos de e-mail e mensagem na área de transferência e no painel, sem envio.

### Modified Capabilities
- `ferramentas-locais`: o requisito "Ações permitidas" ganha `abrir_projeto` e `rascunho`. Este change é o quarto a mexer nesse requisito (depois de `jarvis-musica`, `jarvis-proativo` e `jarvis-estudo`): o delta traz o texto completo e o archive tem que ser **depois** de `jarvis-estudo`.

## Impact

- `jarvis/sessions.py` (casamento de nomes no `Folders`), `jarvis/local_tools.py` (duas ferramentas), `jarvis/cards.py` (cartão de rascunho), `jarvis/agent.py` (turno encerrado com fala fixa, regras no prompt, rótulos de passo, ação local do botão Copiar, texto fora do log), `jarvis/events.py` e `jarvis/server.py` (evento `panel_close`, ação local com texto), `jarvis-ui` (cartão `rascunho`, fechar o painel pelo evento), `.env.example` (`JARVIS_EDITOR`), `SPEC.md` (linha nova na tabela de decisões), testes do cérebro e da interface.
- Custo: um rascunho é uma chamada normal ao Haiku com umas centenas de tokens de saída (na casa de US$ 0,001). A checagem real com o modelo antes do aceite custa uns US$ 0,002.
- Decisões do `SPEC.md` que a mudança toca: "Terminais no Jarvis" (abrir projeto reaproveita os terminais compartilhados e a lista de pastas) e a regra de segurança "nenhuma ferramenta envia mensagens a terceiros" (reafirmada: o rascunho nunca sai do Mac).
