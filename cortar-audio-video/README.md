# Cortar Áudio e Vídeo

Tira um pedaço de um áudio ou de um vídeo pela minutagem, e também parte um
arquivo em vários.

## Para que serve

Dois usos, na mesma janela:

- **Guardar só um trecho.** Você diz onde começa e onde termina, e sai um
  arquivo novo só com aquele pedaço. O arquivo original não é tocado.
- **Partir em vários.** Um arquivo longo vira 2, 3, 10 arquivos, ou vira
  pedaços de 10 minutos cada.

Funciona com áudio (mp3, wav, m4a, flac, ogg...) e com vídeo (mp4, mov, mkv,
avi, webm...).

## As regras da minutagem

- **Começo vazio:** pega desde o início do arquivo.
- **Fim vazio:** pega da minutagem de começo até o fim do arquivo.
- **Os dois vazios:** não tem o que cortar (aí é o caso de usar a outra aba).

Dá para escrever a minutagem de vários jeitos, e o programa mostra ao lado o
que entendeu antes de você clicar em nada:

| Você escreve | Ele entende |
|---|---|
| `1:30` | 1 minuto e 30 segundos |
| `01:02:03` | 1 hora, 2 minutos e 3 segundos |
| `90` | 90 segundos |
| `5m` | 5 minutos |
| `1h30m` | 1 hora e 30 minutos |
| `2min30s` | 2 minutos e 30 segundos |

## Exato ou rápido

- **Exato (o padrão).** O corte começa no segundo que você pediu, no ponto
  certo. Para isso o trecho é recodificado, então demora mais — e num vídeo
  longo pode demorar bastante.
- **Rápido.** Não recodifica nada: copia os dados como estão. É quase
  instantâneo, mas o vídeo só pode ser cortado nos pontos-chave da imagem,
  então o começo pode sair alguns segundos antes do pedido. Em áudio a
  diferença é de frações de segundo.

## Como usar

1. Clique duas vezes em `abrir-cortar-audio-video.command`.
2. Clique em **Escolher arquivo** e aponte para o áudio ou o vídeo.
3. Escolha **Exato** ou **Rápido**.
4. Na aba **Cortar um trecho**: escreva o começo e o fim (ou deixe um deles
   vazio) e clique em **Cortar**.
5. Na aba **Dividir em partes**: diga em quantas partes, ou de quantos minutos
   cada, e clique em **Dividir**.

## Arquivos

| Arquivo | O que é |
|---|---|
| `cortar_audio_video.py` | O programa |
| `abrir-cortar-audio-video.command` | Atalho de clique duplo para Mac (só abre) |
| `publicar-cortar-audio-video.command` | Publica no GitHub a partir do Mac |
| `cortar-audio-video.bat` | Publica no GitHub a partir do Windows |
| `cortar-audio-video-build.yml` | Build do `.exe` e do `.app` na nuvem |
| `requirements.txt` | Sem dependências externas |

## Requisitos

- Python 3 com Tkinter (o Python do site oficial já vem com ele).
- ffmpeg. Se não estiver instalado, o `.command` baixa uma cópia só para este
  programa na primeira execução. No executável publicado ele já vem embutido.

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
