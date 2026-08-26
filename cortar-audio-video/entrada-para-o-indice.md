# Entrada pronta para o índice do repositório

Este arquivo **não** faz parte do programa. Ele guarda o texto que precisa
entrar no índice do repositório `DiegoVSC42/Softwares` **no dia em que o Cortar
Áudio e Vídeo for publicado**. Enquanto ele não for publicado, o texto fica
aqui: os links abaixo apontam para um Release que ainda não existe, e colocá-los
no índice antes da publicação deixaria dois downloads quebrados na página
inicial.

Na hora de publicar, três coisas a fazer:

1. Em `README-repositorio.md` (na máquina Windows, dentro da pasta
   `publicar-todos`), acrescentar a linha da tabela e a seção abaixo, as duas
   em ordem alfabética: depois de "Comparador de Planilhas", antes de
   "Cronômetro de Tempo de Resposta".
2. Em `publicar-todos.bat` (Windows), acrescentar a linha:
   `call :publish "cortar-audio-video" "cortar-audio-video" "cortar-audio-video-build.yml"`
   (no Mac, o `publicar-todos.command` já foi atualizado).
3. Rodar o `publicar-cortar-audio-video.command` (no Mac) ou o
   `cortar-audio-video.bat` (no Windows), que publica só este software.

---

## 1. Linha da tabela do topo

```
| Cortar Áudio e Vídeo | Cortar um trecho pela minutagem, ou partir um arquivo em vários | [.exe](https://github.com/DiegoVSC42/Softwares/releases/download/cortar-audio-video/CortarAudioVideo.exe) | [.zip](https://github.com/DiegoVSC42/Softwares/releases/download/cortar-audio-video/CortarAudioVideo-mac.zip) |
```

## 2. Seção própria

```markdown
## Cortar Áudio e Vídeo

**Caso de uso:**

Guarda só um pedaço de um áudio ou de um vídeo, escolhido pela minutagem, e também parte um arquivo longo em vários menores.

- **Windows:** <https://github.com/DiegoVSC42/Softwares/releases/download/cortar-audio-video/CortarAudioVideo.exe>
- **Mac:** <https://github.com/DiegoVSC42/Softwares/releases/download/cortar-audio-video/CortarAudioVideo-mac.zip>

**Nota (como usar):**

1. Abra o programa.
2. Clique em Escolher arquivo e aponte para o áudio ou o vídeo. Aparecem a duração, o tamanho e se o arquivo tem imagem ou é só som.
3. Escolha como cortar. Exato começa no ponto certo, mas demora mais porque o trecho é gerado de novo. Rápido é quase instantâneo, só que num vídeo o corte cai no ponto-chave mais próximo e pode começar alguns segundos antes.
4. Para guardar um pedaço, use a aba Cortar um trecho. Escreva onde começa e onde termina. Se deixar o começo vazio, pega desde o início. Se deixar o fim vazio, vai da minutagem escrita até o fim do arquivo.
5. A minutagem aceita vários jeitos de escrever: 1:30 é um minuto e meio, 01:02:03 é uma hora, dois minutos e três segundos, 90 são noventa segundos, 5m são cinco minutos. Ao lado do campo aparece o que o programa entendeu, e embaixo o tamanho do arquivo que vai sair.
6. Se quiser mudar o nome ou a pasta do arquivo que vai sair, clique em Trocar. Clique em Cortar e acompanhe a barra (dá para cancelar a qualquer momento).
7. Para partir o arquivo em vários, use a aba Dividir em partes. Diga em quantas partes (2, 3, 10) ou de quantos minutos cada uma, confira a prévia e clique em Dividir.
8. As partes saem numeradas (01, 02, 03) numa pasta ao lado do arquivo original, e no fim o programa mostra a duração de cada uma e confere se a soma bate com o arquivo inteiro.
9. O arquivo original nunca é alterado.
```
