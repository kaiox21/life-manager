## MODIFIED Requirements

### Requirement: Ações permitidas
O Jarvis SHALL oferecer só estas ações locais: `abrir_app(nome)`, `buscar_arquivo(texto)` (Spotlight, na pasta pessoal, até 20 resultados), `rodar_atalho(nome)` (só da lista permitida), `controlar_musica(acao)` (tocar, pausar, próxima, anterior, aleatório, repetir e volume de 0 a 100, no Spotify), `tocar_musica(pedido, tipo)` (busca e toca no Spotify deste Mac uma música, artista, álbum, playlist do catálogo ou playlist do Kaio), `timer(minutos, texto)` (notificação do Mac) e `area_transferencia(acao)` (ler pede confirmação), além das ferramentas de terminal, que seguem o requisito "Sem shell livre".

#### Scenario: Atalho fora da lista
- **WHEN** o modelo pede `rodar_atalho("Apagar tudo")` e ele não está na lista permitida
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Volume fora da faixa
- **WHEN** o modelo pede `controlar_musica` com volume 150
- **THEN** a ação é recusada e o motivo volta ao modelo

## ADDED Requirements

### Requirement: Tocar o que o Kaio pedir
`tocar_musica` SHALL buscar o pedido no Spotify pelo tipo indicado (`musica`, `artista`, `album`, `playlist` ou `minha_playlist`) e tocar o primeiro resultado no Spotify deste Mac, sem pedir confirmação. Uma música SHALL tocar dentro do álbum dela, a partir dela, para a reprodução seguir depois que ela acabar. A resposta SHALL dizer o que começou a tocar (nome e, para música e álbum, o artista), para o Kaio poder corrigir. `minha_playlist` SHALL procurar só entre as playlists do Kaio (as dele e as que ele segue), comparando o nome sem diferenciar maiúsculas e acentos e aceitando parte do nome. Sem resultado, o Jarvis SHALL dizer que não encontrou, sem tocar outra coisa. Com o Spotify fechado, o Jarvis SHALL abrir o app e tocar quando ele estiver pronto (até cerca de 10 s); se não ficar pronto, SHALL dizer isso.

#### Scenario: Música pelo nome
- **WHEN** o Kaio diz "Jarvis, toca Tempo Perdido"
- **THEN** começa a tocar "Tempo Perdido" no Spotify do Mac, o Jarvis diz "Tocando Tempo Perdido, da Legião Urbana." e, quando ela acaba, segue a próxima faixa do álbum

#### Scenario: Artista
- **WHEN** o Kaio pede "toca Legião Urbana"
- **THEN** o Spotify toca as músicas da Legião Urbana

#### Scenario: Playlist do Kaio com nome aproximado
- **WHEN** o Kaio tem a playlist "Estudo 📚 foco" e pede "toca minha playlist de estudo"
- **THEN** essa playlist começa a tocar

#### Scenario: Não encontrou
- **WHEN** o Kaio pede uma playlist dele que não existe
- **THEN** o Jarvis diz que não encontrou essa playlist e nada muda no que estava tocando

#### Scenario: Spotify fechado
- **WHEN** o Spotify está fechado e o Kaio pede "toca Djavan"
- **THEN** o Spotify abre e toca Djavan

### Requirement: Conta Spotify do Kaio
O acesso à conta Spotify do Kaio SHALL ser autorizado por ele uma vez, no navegador, sem guardar senha nem segredo de cliente. O Jarvis SHALL pedir só as permissões de ler as playlists dele e controlar o player. A credencial de renovação SHALL ficar no Keychain do macOS e SHALL NOT aparecer em log, `.env` ou arquivo do projeto. Sem a autorização feita (ou revogada pelo Kaio), as ações que precisam da conta SHALL responder que é preciso autorizar o Spotify uma vez, com o comando do login mostrado na interface (não lido em voz alta), e tocar, pausar, próxima e anterior SHALL continuar funcionando sem ela.

#### Scenario: Sem login
- **WHEN** o Kaio nunca fez o login e pede "toca Tempo Perdido"
- **THEN** o Jarvis responde que precisa autorizar o Spotify uma vez, o comando aparece na interface, e "pausa a música" continua funcionando

#### Scenario: Acesso revogado
- **WHEN** o Kaio remove o Jarvis dos apps autorizados na conta Spotify
- **THEN** o próximo pedido de música responde que é preciso autorizar de novo, sem erro técnico

### Requirement: Música baixa enquanto o Jarvis ouve e fala
Com o Spotify tocando, o Jarvis SHALL abaixar o volume do Spotify enquanto ouve um pedido (depois de "Jarvis" ou com o atalho de voz segurado) e enquanto fala, e SHALL voltar ao volume anterior quando terminar. Isso SHALL funcionar sem a autorização da conta. Se o Kaio mudar o volume pelo Jarvis nesse meio-tempo, o volume novo SHALL valer no fim.

#### Scenario: Pedido com música tocando
- **WHEN** o Spotify toca alto e o Kaio diz "Jarvis, quanto eu gastei esse mês?"
- **THEN** a música abaixa enquanto ele ouve e responde, e volta ao volume de antes depois da resposta

#### Scenario: Pedido de volume
- **WHEN** a música está abaixada pelo Jarvis e o Kaio pede "volume 30"
- **THEN** depois da resposta o volume fica em 30, não no de antes
