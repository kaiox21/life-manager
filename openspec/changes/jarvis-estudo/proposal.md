## Why

O Kaio estuda à noite (Licenciatura em Computação na UnB, aulas às 19h) e o maior inimigo é a distração: notificações, o Jarvis falando avisos, a música errada. Hoje ele consegue cada parte por um pedido separado ("toca minha playlist de estudo", "timer de 50 minutos", "silencia os avisos") e o Foco do macOS fica fora do alcance do Jarvis. Esta é a segunda funcionalidade da lista aprovada em 10/10/2026: um pedido só que monta o ambiente de estudo e o desmonta no fim, com a pausa proposta na hora certa.

## What Changes

- **"Jarvis, modo estudo por 50 minutos"** (pela voz, digitado ou pelo botão **Estudo** do painel) liga, nesta ordem, o que estiver disponível:
  1. o **Foco "Não Perturbe"** do macOS, por dois atalhos do app Atalhos que o Kaio cria uma vez (ligar e desligar). Sem os atalhos, o modo funciona sem o Foco e avisa uma vez;
  2. a **playlist de estudo** do Kaio no Spotify (nome configurável; padrão: a playlist dele cujo nome contém "estudo"). Sem o Spotify autorizado, o modo segue sem música e diz isso;
  3. o **silêncio dos avisos falados** (lembretes, terminais, pergunta dos gastos) enquanto o modo durar. O WhatsApp continua recebendo tudo.
  - Sem minutos, o bloco é de **50 minutos**; a pausa, de **10**. Os dois são configuráveis no pedido ("modo estudo por 25 minutos com pausa de 5").
- **Fim do bloco:** o Jarvis fala *"Senhor, acabaram os 50 minutos de estudo. Pausa de 10 minutos?"* e ouve a resposta sem exigir o nome:
  - "sim" começa a pausa (o Foco e a música continuam; o relógio do painel passa a contar a pausa). No fim dela: *"Senhor, a pausa acabou. Mais 50 minutos?"*. "sim" começa outro bloco; "não" encerra;
  - "não" encerra o modo: *"Perfeito, senhor. Modo estudo encerrado."*;
  - outra coisa ("mais 25 minutos") vai ao modelo como pedido normal;
  - sem resposta em 2 minutos, o modo encerra em silêncio (o Foco desliga, os avisos voltam). Nenhuma dessas falas chama o modelo.
- **"Jarvis, para o estudo"** (ou o botão Estudo de novo, ou "quanto falta do estudo?") a qualquer momento: encerra ou informa. Encerrar desliga o Foco e devolve os avisos; a música fica como está.
- **O relógio sobrevive:** o fim do bloco é uma hora marcada, não uma contagem. Se o Mac dormir e acordar antes do fim, o modo continua; se acordar depois do fim, o Jarvis encerra o modo (Foco desligado) sem perguntar nada. Se o cérebro reiniciar no meio, ele retoma o bloco.
- **Painel:** o botão **Estudo** entra nos modos (o `jarvis-painel-hud` deixou o lugar). Parado, inicia 50 minutos; rodando, mostra o que falta ("Estudo 37 min", "Pausa 8 min") e um clique encerra. O estado do painel diz "estudo · faltam 37 min".
- **Ferramenta local nova** `modo_estudo(acao, minutos, pausa)`, sem confirmação: só mexe em Foco, música e na voz do próprio Jarvis.

## Non-goals

- Bloquear sites ou apps, ou escolher um Foco diferente de "Não Perturbe" (um par de atalhos só).
- Histórico ou estatística de blocos estudados.
- Começar o modo sozinho pela agenda ("aula às 19h"): o Kaio pede.
- Criar os atalhos do Foco pelo Jarvis: o app Atalhos não tem caminho oficial para isso; o Kaio cria os dois uma vez (uns 2 minutos, instruções em `docs/proximos-passos.md`).

## Capabilities

### New Capabilities
- `jarvis-estudo`: o modo estudo (Foco, playlist, silêncio, blocos com pausa proposta, botão Estudo).

### Modified Capabilities
- `ferramentas-locais`: `modo_estudo` entra na lista de ações permitidas (sem confirmação).

## Impact

- **Núcleo:** nada muda.
- **Cérebro:**
  - `jarvis/study.py`, novo: o modo (fases bloco/pausa, hora marcada do fim, retomada depois de dormir ou reiniciar), o Foco pelos atalhos (`shortcuts run`, só se o nome está em `shortcuts list`, com limite de 10 s) e a playlist pelo Spotify;
  - `jarvis/proactive.py`: os avisos ficam retidos enquanto o modo dura (`hold`), e o estado do modo vai no mesmo `proativo.json`;
  - `jarvis/agent.py`: a janela de resposta sem o nome (do `jarvis-proativo`) ganha o "sim" com ação, para as duas perguntas do modo; `local_action` ganha o botão Estudo;
  - `jarvis/local_tools.py`: ferramenta `modo_estudo`;
  - `.env`: `JARVIS_FOCO_LIGAR` / `JARVIS_FOCO_DESLIGAR` (nomes dos atalhos; padrão "Jarvis Foco" e "Jarvis Foco Fim"), `JARVIS_PLAYLIST_ESTUDO` (padrão "estudo"), `JARVIS_ESTUDO_MINUTOS` (50) e `JARVIS_ESTUDO_PAUSA` (10).
- **Interface:** botão Estudo nos modos do painel, o que falta no rótulo e no estado; tipo `estudo` nos dados locais do painel.
- **Custo:** iniciar pela voz é um turno normal do modelo (fração de centavo com o Haiku); o botão, as perguntas e as respostas "sim"/"não" não chamam o modelo.
- **Dependências:** usa a janela de resposta, a fila de avisos e o `proativo.json` do `jarvis-proativo`.
- **Ordem de arquivamento:** depois de `jarvis-proativo` (que depende de `radar-vagas`, `boletim-noticias` e `jarvis-musica`), porque os dois mudam "Ações permitidas" e este usa o que aquele criou.
- **`SPEC.md`:** decisão do modo estudo (o Foco só por atalhos do Kaio; o Jarvis nunca cria atalhos; silêncio = Foco é um só).
