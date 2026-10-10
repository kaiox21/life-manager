# Próximos passos

O que falta fazer, com o Kaio presente, para fechar os changes abertos. Atualizado em 10/10/2026.

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

## Decisão pendente

- **Painel em tela cheia a cada "Jarvis, …".** Hoje qualquer pedido pela palavra abre o painel. Para pedidos rápidos ("Jarvis, toca Djavan"), talvez seja melhor o painel abrir só com "Hey Jarvis" sozinho (o resumo do dia). Decida depois de usar por uns dias.

## Fora do Jarvis

- **`deploy-vps`** (5 de 12 tarefas): criar a VM, configurar ntfy, healthchecks e backup com `rclone`, migrar o banco do Mac, escanear o QR do WhatsApp no VPS e fazer o aceite do alerta e do backup diário.
