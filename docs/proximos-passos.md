# Próximos passos

O que falta fazer, com o Kaio presente, para fechar os changes abertos. Atualizado em 13/10/2026.

Quando terminar uma sessão de testes, conte ao Claude o que deu certo e o que falhou. Ele confere o log (`~/Library/Logs/Jarvis/brain.log`), marca as tarefas, atualiza o `SPEC.md` e arquiva com `/opsx:archive`.

## Sessão de voz (lugar tranquilo, uns 30 min)

Dá para fazer numa sessão só, as duas partes em sequência.

### 1. Calibração da palavra "Jarvis" (`jarvis-wake-word`, tarefa 4.1)

Peça ao Claude: "vamos calibrar".

1. Ele pausa o Jarvis.
2. Uma janela no centro da tela mostra cada frase; no bipe (*tink*), fale. São 20 frases em uns 2 minutos.
3. Entre os sons *Glass*, 5 minutos de fala normal **sem dizer "Jarvis"**: conversa, leitura em voz alta ou vídeo em português.
4. Ele analisa, ajusta a sensibilidade e religa o Jarvis. O áudio é apagado no fim.

**Meta:** ≥ 90% de acertos e nenhum alarme falso nos 5 minutos.

### 2. Aceite da palavra de ativação (`jarvis-wake-word`, tarefa 4.2)

Anote a memória e a CPU do Jarvis no Monitor de Atividade antes e depois.

- [ ] "Hey Jarvis" com outro app na frente: o painel abre e ele fala o resumo do dia (clima, compromissos). Tempo até começar a falar: ~4 s.
- [ ] Logo depois do resumo, um pedido **sem** repetir o nome ("quanto eu gastei esse mês?").
- [ ] "Jarvis, o que eu tenho amanhã?" de uma vez: o painel abre e ele responde falando.
- [ ] "Hey Jarvis" e silêncio: ele fala o resumo e volta a esperar o nome.
- [ ] "Hey Jarvis" sem internet: o resumo sai sem o clima.
- [ ] Com o painel já aberto: a conversa aparece nele.
- [ ] Desmarcar "Ouvir 'Jarvis'" no menu da barra: o ponto laranja some e chamar não faz nada. Marcar de novo: ele volta.
- [ ] Reiniciar o Mac: a escolha do menu é lembrada.
- [ ] Uma resposta que contém "Jarvis" não ativa o Jarvis sozinho.
- [ ] Segurar ⌘⇧Espaço e dizer "Jarvis, abre o Safari": atende uma vez só.
- [ ] Uma hora de uso normal (vídeo, conversa): contar as ativações sem querer no log (`grep "palavra detectada"`).
- [ ] Nenhum pedido novo de permissão de microfone além do de sempre.

### 3. Aceite da música (`jarvis-musica`, tarefa 4.2)

Já testado em 10/10: login e "toca …" por texto (tocou no Mac em 1,7 s).

- [ ] "Jarvis, toca Tempo Perdido": ele diz "Tocando Tempo Perdido, da Legião Urbana" e, quando a música acaba, segue no álbum.
- [ ] "Jarvis, toca Legião Urbana" (artista).
- [ ] "Jarvis, toca minha playlist de …" com o nome aproximado de uma das suas playlists.
- [ ] Uma playlist sua que não existe: ele diz que não encontrou e nada muda.
- [ ] Com o Spotify fechado, "Jarvis, toca Djavan": o Spotify abre e toca.
- [ ] "Jarvis, volume 30" e "Jarvis, aleatório".
- [ ] Com música tocando, "Jarvis, que horas são?": a música abaixa enquanto ele ouve e responde, e volta ao volume de antes.
- [ ] Com música tocando, o "Jarvis" ainda é detectado.
- [ ] Conferência da escolha do modelo (tarefa 3.2): "toca Tempo Perdido" vira música, "toca Legião Urbana" vira artista, "toca minha playlist de estudo" vira playlist sua, "pausa" vira controle. Custa frações de centavo.
- [ ] Sem login: remover o Jarvis em spotify.com/account/apps e pedir uma música. Ele diz que é preciso autorizar, e o comando aparece no painel. "Pausa" continua funcionando. Depois, refazer o login: `uv run python -m jarvis.spotify_login`.

### 4. Aceite do Jarvis proativo (`jarvis-proativo`, tarefa 5.2)

Dá para começar hoje: às 21:30, sem gasto lançado no dia, ele pergunta sozinho.

- [ ] Às 21:30, num dia sem gasto: "Senhor, nenhum gasto lançado hoje. Teve algum?". Responder sem dizer o nome ("30 de uber no pix" ou "não"). Não pergunta de novo no mesmo dia.
- [ ] "Jarvis, boa noite": gastos de hoje e do mês, a agenda de amanhã e a pergunta. Responder "não" sem o nome: "Perfeito, senhor. Boa noite."
- [ ] O mesmo pelo botão **Boa noite** do painel.
- [ ] Criar um evento para daqui a 35 min com aviso de 30: o aviso chega no WhatsApp e ele fala.
- [ ] Um Claude Code num trabalho de 2 min ou mais: ele avisa quando termina. Uma resposta curta: nada.
- [ ] Um Claude Code pedindo permissão: ele avisa a ferramenta (nunca o comando) e "Jarvis, permite" não aprova.
- [ ] "Jarvis, silencia os avisos por uma hora": o botão vira "Avisos HH:MM" e nada é falado; "Jarvis, volta a avisar" (ou o botão) retoma.
- [ ] Depois das 23:00, nada é falado.
- [ ] Num dia normal, contar se os avisos incomodaram (o log mostra cada fala: `grep proativo ~/Library/Logs/Jarvis/brain.log`).

### 5. Aceite do modo estudo (`jarvis-estudo`, tarefa 4.3)

Antes: crie os dois atalhos no app Atalhos (item 2 da lista abaixo) e confira com `shortcuts list`.

- [ ] "Jarvis, modo estudo por 25 minutos com pausa de 5": o Foco liga (o ícone aparece na barra), a playlist de estudo toca e ele diz até que horas vai. O botão Estudo mostra "Estudo 25 min".
- [ ] Durante o bloco, um aviso (evento daqui a 35 min com aviso de 30, ou um Claude Code pedindo permissão): nada é falado; o WhatsApp recebe.
- [ ] No fim: "Senhor, acabaram os 25 minutos de estudo. Pausa de 5 minutos?". Responder "sim" sem o nome. No fim da pausa, "Mais 25 minutos?": responder "não". O Foco desliga.
- [ ] Pelo botão **Estudo**: começa 50 min sem chamar o modelo; outro clique encerra.
- [ ] "Jarvis, para o estudo" no meio: Foco desliga, avisos voltam, música continua.
- [ ] Sem os atalhos (renomeie um deles): o modo começa e ele diz "sem o Foco".
- [ ] Com o Foco ligado pelo modo, trocar de app algumas vezes: o Foco continua ligado (um relato antigo diz que desligava).
- [ ] Fechar a tampa do Mac durante o bloco e abrir depois do fim: o modo encerra sem falar e o Foco desliga.

## Funcionalidades novas do Jarvis (aprovadas em 10/10/2026)

Ordem de implementação, um change do OpenSpec por vez:

1. **`jarvis-proativo`** (implementado em 13/10; falta o aceite acima): "Jarvis, boa noite" com o fechamento do dia, lembrete de lançamento às 21:30, avisos falados (lembretes do núcleo e terminais) e silêncio.
2. **`jarvis-estudo`** (implementado em 13/10 na branch `feat/jarvis-estudo`; falta o aceite acima): "Jarvis, modo estudo por 50 minutos" liga o Foco do macOS, toca a playlist de estudo, retém os avisos e propõe a pausa no fim do bloco. **Antes do aceite, crie dois atalhos no app Atalhos** (uns 2 minutos): "Jarvis Foco" com a ação "Definir Foco" → Não Perturbe, ligado "até ser desativado"; e "Jarvis Foco Fim" com a mesma ação desligando. Confira com `shortcuts list` no Terminal.
3. **Abrir projetos e rascunhos**: "Jarvis, abre o NC Barber" (VS Code e terminal na pasta) e "escreve um e-mail pro professor…" (o texto vai para a área de transferência e o painel; nunca envia).
4. **Notas rápidas por voz**: "anota que…" e "o que eu anotei sobre…" (tabela nova no núcleo; sem segredos).
5. **Prazos da UnB no resumo do dia** (API do Aprender3).
6. **Resumo semanal** no domingo.
7. Mais para frente: "o que é isso na minha tela?" (visão) e orçamento e metas por categoria.

O `roteador-dificuldade` está proposto (branch `feat/roteador-dificuldade`), mas parado: a recomendação é reduzi-lo à medição (casos difíceis na prova) antes de construir.

## Decisão pendente

- **Painel em tela cheia a cada "Jarvis, …".** Hoje qualquer pedido pela palavra abre o painel. Para pedidos rápidos ("Jarvis, toca Djavan"), talvez seja melhor o painel abrir só com "Hey Jarvis" sozinho (o resumo do dia). Decida depois de usar por uns dias.

## Vitrine (README)

- **Gravar dois GIFs curtos** (⌘⇧5 grava a tela; o Claude converte para GIF e põe no README, em `docs/midia/`):
  - `hey-jarvis`: com outro app na frente, dizer "Hey Jarvis"; o painel abre e ele fala o resumo. Uns 15 s.
  - `painel`: o HUD com a conversa, a agenda, as notícias e as vagas. Uns 10 s.

## Fora do Jarvis

- **`deploy-vps`** (5 de 12 tarefas): criar a VM, configurar ntfy, healthchecks e backup com `rclone`, migrar o banco do Mac, escanear o QR do WhatsApp no VPS e fazer o aceite do alerta e do backup diário.
