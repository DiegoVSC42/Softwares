# Audio Studio

Uma janela só, com quatro abas, para tudo que se faz com arquivo de som:
cortar, dividir, juntar, tirar o áudio de um vídeo, montar episódio e separar
vozes.

## As quatro abas

| Aba | Para que serve |
|---|---|
| **Cortar e dividir** | Três coisas: tirar um trecho pela minutagem, partir um arquivo longo em vários pedaços (com a opção de cortar no silêncio, para não partir palavra no meio) e juntar os pedaços de volta na ordem certa. |
| **Extrair áudio** | Tira o áudio de vários vídeos de uma vez, em MP3 ou WAV. Aceita arquivos do computador e também links do YouTube, Instagram, TikTok, Drive e Dropbox. |
| **Unir áudios** | Junta vários áudios de uma pasta num arquivo só, na ordem certa e com transição entre um bloco e o outro. A lista começa vazia: você escolhe a pasta. |
| **Separar canais** | Separa uma gravação com duas vozes em canais diferentes (o caso da entrevista gravada em estéreo) em dois arquivos, um por voz. |

Os arquivos originais nunca são alterados: o programa sempre grava arquivos
novos.

## O fluxo que essas abas montam juntas

O caso que deu origem a elas é uma entrevista longa que precisa passar por um
serviço externo que só aceita arquivos curtos:

1. **Extrair áudio**, se a entrevista veio em vídeo.
2. **Cortar e dividir** → "Dividir em partes", pedindo pedaços de 30 minutos e
   marcando "cortar no silêncio". As partes saem numeradas.
3. Você trata as partes no serviço de fora. Os nomes voltam com sufixo, tipo
   `01_entrevista_enhanced.wav` — a numeração sobrevive.
4. **Cortar e dividir** → "Juntar de volta", que reconhece a ordem pela
   numeração e devolve um arquivo só, sem descompasso.

## Duas abas são compartilhadas com o Video Studio

**Cortar e dividir** e **Extrair áudio** são as mesmas telas que existem no
Video Studio. Não são cópias: é o mesmo código, montado nas duas janelas. A
diferença é que aqui elas abrem o diálogo de escolha de arquivo já com o
filtro de áudio na frente, e lá com o de vídeo. As duas tratam os dois tipos
nos dois lugares.

Corrigir uma corrige as duas. Para quem mexe no código, a fonte está em
`abas-compartilhadas/`, na pasta Scripts.

## Onde os arquivos são salvos

Todas as abas começam apontando para a sua pasta de **Downloads**. Dá para
trocar em cada aba, mas o ponto de partida é sempre o mesmo, para nenhum
arquivo sumir de vista.

## Como rodar no Mac

1. Dê dois cliques em `abrir-audio-studio.command`.
2. Na primeira vez o Mac pode bloquear, com a mensagem "não foi possível
   verificar o desenvolvedor". Nesse caso clique com o botão direito no
   arquivo, escolha **Abrir** e confirme em **Abrir** de novo.
3. Também na primeira vez o programa leva 1 a 2 minutos se preparando: ele
   monta um ambiente próprio com as bibliotecas que usa e procura o ffmpeg (o
   motor que lê e converte som), baixando uma cópia se não achar na sua
   máquina. Isso acontece uma única vez.
4. A janela abre na aba **Cortar e dividir**. Clique no nome de outra aba, lá
   em cima, para trocar de ferramenta.
5. Cada aba tem um botão laranja, que é a ação principal daquela tela.
   Enquanto o trabalho corre, a barra mostra o progresso e o botão
   **Cancelar** interrompe.
6. No rodapé, à esquerda, aparece uma linha explicando para que serve a aba em
   que você está.

Se você tentar fechar a janela com algum trabalho em andamento, o programa
avisa antes, dizendo qual aba ainda está trabalhando.

## Detalhes que valem saber

- **A aba Separar canais lê arquivos WAV.** Se o seu arquivo estiver em outro
  formato, converta antes na aba Cortar e dividir.
- **Nenhuma aba sai catando arquivo sozinha.** Todas começam vazias, e só
  entra na fila o que você escolher.
- **A ordem no Unir áudios é a humana, não a do computador.** Arquivos como
  `1_1`, `2_1`, ... `10_1`, ... `36_1` entram na ordem 1, 2, 3 ... 10 ... 36. A
  ordem alfabética do computador colocaria o 10 logo depois do 1.
- **A janela nasce do tamanho da sua tela**, e se alguma aba não couber
  inteira aparece uma barra de rolagem do lado direito. Para rolar, use a roda
  do mouse ou dois dedos no trackpad, com o ponteiro em qualquer lugar da aba.

## Para quem mexe no código

- `estudio_audio.py` é a janela: cria as abas, aplica o tema e trata o
  fechamento.
- `tema.py` guarda a paleta e o estilo, aplicados uma única vez para a janela
  inteira. Nenhuma aba define estilo próprio.
- `pastas.py` guarda a pasta padrão de saída (a de Downloads).
- `abas/` tem um arquivo por tela. Cada um expõe `montar(pai)`. As abas
  compartilhadas são arquivos finos, que só chamam a tela em `compartilhado/`
  dizendo que aqui o foco é áudio.
- `compartilhado/` tem cópias geradas: **não edite nada ali**. A fonte está em
  `abas-compartilhadas/`, na pasta Scripts, e o `sincronizar.py` de lá
  atualiza todos os estúdios de uma vez.
- `medir_abas.py` não faz parte do programa: é a ferramenta de conferência.
  Ela abre o Studio com a fonte do Mac (a maior) e diz, aba por aba, se o
  conteúdo cabe sem rolar. Rode depois de mexer em qualquer layout.
