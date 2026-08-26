# Montar Podcast

Junta vários áudios de uma pasta num arquivo único e longo, na ordem certa e
com transição entre um bloco e o outro.

## Para que serve

Você tem 36 arquivos separados e quer um episódio só, de duas horas, que soe
como uma gravação contínua em vez de uma colagem.

## O que ele resolve

- **Ordem humana.** Arquivos como `1_1`, `2_1`, ... `10_1`, ... `36_1` entram
  na ordem 1, 2, 3 ... 10 ... 36. A ordem alfabética do computador colocaria o
  10 logo depois do 1, e o episódio sairia embaralhado.
- **Transição.** Três opções: pausa curta com o volume baixando e subindo
  (a natural para fala), crossfade (um bloco entra por cima do outro, boa para
  música) ou corte seco.
- **Prévia antes de esperar.** Um botão toca só a emenda entre os dois
  primeiros blocos, para você ouvir a transição sem renderizar duas horas.
- **Volume igual.** Blocos gravados em dias diferentes, ou por pessoas
  diferentes, ficam todos no mesmo nível.
- **Capítulos.** Os marcadores vão gravados dentro do mp3 (o player mostra o
  nome de cada bloco) e um `.txt` com os tempos sai ao lado, pronto para colar
  na descrição do episódio.
- **Reordenar na mão.** Se a numeração dos arquivos não é a ordem que você
  quer, dá para subir, descer e tirar blocos antes de montar.

## Como usar

1. Clique duas vezes em `abrir-montar-podcast.command`.
2. Escolha a pasta com os áudios. A lista já aparece na ordem certa, com a
   duração de cada um e a duração prevista do episódio.
3. Ajuste a ordem se precisar, com **Subir**, **Descer** e **Remover**.
4. Escolha a transição e clique em **Ouvir a prévia da transição** para
   conferir antes de montar.
5. Dê um título, escolha a qualidade e diga onde salvar.
6. Clique em **Montar podcast** e acompanhe a barra. Dá para cancelar no meio.

## Arquivos

| Arquivo | O que é |
|---|---|
| `montar_podcast.py` | O programa |
| `abrir-montar-podcast.command` | Atalho de clique duplo para Mac (só abre) |
| `publicar-montar-podcast.command` | Publica no GitHub a partir do Mac |
| `montar-podcast.bat` | Publica no GitHub a partir do Windows |
| `montar-podcast-build.yml` | Gera o `.exe` e o `.app` pela nuvem |
| `requirements.txt` | Sem dependências externas |

## Requisitos

- Python 3 com Tkinter (o Python do site oficial já vem com ele).
- ffmpeg. Se não estiver instalado, o `.command` baixa uma cópia só para este
  programa na primeira execução. No `.exe` e no `.app` publicados o ffmpeg já
  vem embutido.

## Detalhes de quem quer saber

- A junção é feita numa passada só do ffmpeg, com um grafo de filtros: cada
  bloco é reamostrado para 44,1 kHz estéreo, recebe o fade e entra no `concat`
  (ou no `acrossfade`, na opção de crossfade). Não existe arquivo intermediário
  e nada é decodificado duas vezes.
- Igualar o volume usa `loudnorm` em cada bloco, com alvo de −16 LUFS e pico
  de −1,5 dBTP, que é o padrão das plataformas de podcast.
- A duração prevista bate com a real: a pausa soma tempo (0,8 s por emenda) e
  o crossfade tira (o tempo de sobreposição por emenda).

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
