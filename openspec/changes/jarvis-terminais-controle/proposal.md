## Why

O `jarvis-terminais` só **avisa**: quando uma sessão do Claude Code pede permissão, o Kaio ainda precisa achar a janela certa e responder lá. Ele quer **controlar** as sessões de dentro do Jarvis: vê-las, digitar nelas, aprovar ou negar pedidos, mandar recados por voz e abrir ou fechar sessões (pedido de 09/10/2026). O `jarvis-terminais` deixou "responder à permissão" para "um change seguinte, com desenho próprio", e este é esse change.

## What Changes

- **Terminais de verdade no painel.** O painel ganha abas de terminal. Cada aba roda o `claude` num terminal real: a tela é a mesma do Terminal.app, e o Kaio vê e digita ali. Para fechar o painel com uma aba de terminal em foco, usa-se ⌥⇧Espaço, porque o Esc vai para o Claude Code, que o usa para interromper.
- **Abrir e fechar sessões** pela aba "+", pelo texto ou pela voz ("abre um Claude Code no life-manager"). A sessão nova vira o próximo "Terminal N". Só abre em pastas de uma lista permitida. Fechar uma sessão que está trabalhando pede confirmação.
- **Aprovar ou negar pelo Jarvis.** Quando uma sessão aberta pelo Jarvis pede permissão, o aviso no HUD e no painel ganha os botões **Permitir** e **Negar**. O diálogo continua aparecendo também na aba: vale o que for respondido primeiro. A aprovação **só** sai de um clique ou tecla do Kaio. Nunca do modelo, nunca da voz.
- **Mandar mensagens** para uma sessão: digitando na aba ou pedindo ao Jarvis ("Terminal 2, roda os testes"). Quando o pedido passa pelo Jarvis, ele mostra o texto e o destino e só envia depois que o Kaio confirma.
- **Ver o que cada sessão faz:** a aba mostra a saída e a conversa ao vivo. A lista de terminais marca quais têm aba e quais estão fora do Jarvis.
- **Sessões fora do Jarvis** (Terminal.app, VS Code) continuam como hoje: avisos e estado, sem botões e sem aba.
- **Limite de memória:** no máximo 4 sessões abertas pelo Jarvis ao mesmo tempo (configurável), e o Jarvis recusa abrir mais quando o Mac está com pouca memória livre.
- **BREAKING (comportamento):** no painel, o Esc deixa de fechá-lo quando o foco está numa aba de terminal.

## Non-goals

- Aprovar ou mandar mensagens para sessões abertas fora do Jarvis. O Claude Code não oferece um jeito local e documentado de escrever numa sessão que roda em outro terminal. Para isso existe o Remote Control oficial, pelo app do Claude.
- Sessões que sobrevivem ao reinício do cérebro. Reiniciar o Jarvis fecha as abas. Cada aba fechada assim oferece "retomar" (`claude --resume`).
- Mandar ao modelo do Jarvis o conteúdo da tela ou da conversa de um terminal. "O que o Terminal 2 está fazendo?" responde com o estado, e o conteúdo fica só na tela.
- Abrir sessões com as permissões desligadas (`--dangerously-skip-permissions`) pelo Jarvis.
- Outros programas na aba além do `claude`: shell livre, `npm` direto etc.
- Levar o foco para a janela do Terminal.app.

## Capabilities

### New Capabilities
<!-- nenhuma: os requisitos entram na capacidade `jarvis-terminais`, criada pelo change jarvis-terminais (arquivado antes deste) -->

### Modified Capabilities
- `jarvis-terminais`: abas de terminal no painel, abrir e fechar sessões, aprovar e negar pelo Jarvis (só nas sessões abertas por ele), mandar mensagens com confirmação, limite de sessões. O requisito "Aviso de permissão" deixa de proibir aprovar e negar.
- `ferramentas-locais`: o requisito "Sem shell livre" ganha uma exceção explícita e estreita. As ferramentas de terminal podem escrever **texto** numa sessão do Claude Code aberta pelo Jarvis, com confirmação. O Claude Code pode rodar comandos a partir desse texto, sob as permissões dele.
- `jarvis-painel`: o Esc não fecha o painel quando o foco está numa aba de terminal.

## Impact

- **Cérebro (Python):** novo gerenciador de sessões com terminal real (`pty` da biblioteca padrão), que repassa a saída e a entrada pela conexão local que já existe. Ganha um endereço local para o hook `PermissionRequest` das sessões que ele abre, e as ferramentas `abrir_terminal`, `fechar_terminal` e `mandar_terminal` (as duas que escrevem pedem confirmação).
- **Interface:** abas com `@xterm/xterm` no painel (dependência nova) e botões Permitir e Negar no aviso.
- **Hooks:** o hook global de anotação (`jarvis-terminais`) não muda. As sessões abertas pelo Jarvis recebem, só para elas, um hook `PermissionRequest` extra, que espera a resposta do Jarvis.
- **Dependência:** o `jarvis-terminais` precisa estar aceito e arquivado antes. Ele está com commit local (83d392a), sem aceite.
- **`SPEC.md`:**
  - registra a decisão "o Jarvis escreve em sessões do Claude Code", que muda a regra "nenhuma ferramenta executa comandos" do `CLAUDE.md`;
  - registra o limite de memória;
  - fecha a questão "Sessões do Claude Code no Jarvis".
