# Estúdio de Vídeo

Uma janela só, com quatro abas, para tudo que se faz com arquivo de vídeo:
baixar, cortar, tirar fotos de dentro e tirar o áudio.

Substitui quatro programas que antes eram separados (Baixador de Vídeos,
Cortar Áudio e Vídeo, Extrair Quadros e Extrair Áudio). O mesmo trabalho, sem
ficar abrindo e fechando janela.

## As quatro abas

| Aba | Para que serve |
|---|---|
| **Baixar** | Baixa vídeo ou só o áudio em MP3 de YouTube, Instagram, TikTok, Google Drive e centenas de outros sites. Escolhe a qualidade, corta por tempo e apaga todos os dados escondidos do arquivo. |
| **Cortar** | Tira um trecho pela minutagem, ou parte um arquivo longo em vários pedaços. Funciona com áudio e com vídeo. |
| **Extrair quadros** | Tira fotos de dentro do vídeo, já recortadas na proporção que você escolher (16:9, 9:16, 1:1 e outras), com uma tela onde você mira exatamente a área que quer. |
| **Extrair áudio** | Tira o áudio de vários vídeos de uma vez, em MP3 ou WAV. Aceita arquivos do computador e também links, colados um a um. |

## O nome do arquivo na aba Cortar

O trecho cortado sai com um nome montado em duas partes, as duas editáveis:

```
Nome: entrevista prefeito     Sufixo: 00-00-04_00-00-09
                                ↓
       entrevista prefeito - 00-00-04_00-00-09.mp4
```

O sufixo já vem preenchido com a minutagem do trecho, começo e fim. Se você
apagar e escrever outra coisa, o programa entende que aquele campo passou a
ser seu e para de reescrevê-lo quando a minutagem mudar. O botão **Voltar ao
padrão** devolve a minutagem a qualquer momento.

Os dois-pontos do relógio viram traço porque nem o Windows nem o Mac aceitam
`:` em nome de arquivo.

## Onde os arquivos são salvos

Todas as abas começam apontando para a sua pasta de **Downloads**. Dá para
trocar em cada aba, mas o ponto de partida é sempre o mesmo, para nenhum
arquivo sumir de vista.

## Como rodar no Mac

1. Dê dois cliques em `abrir-estudio-video.command`.
2. Na primeira vez o Mac pode bloquear, com a mensagem "não foi possível
   verificar o desenvolvedor". Nesse caso clique com o botão direito no
   arquivo, escolha **Abrir** e confirme em **Abrir** de novo.
3. Também na primeira vez o programa leva 1 a 2 minutos se preparando: ele
   procura o ffmpeg (o motor que lê e converte vídeo) e, se não achar na sua
   máquina, baixa uma cópia só para ele. Isso acontece uma única vez.
4. A janela abre na aba **Baixar**. Clique no nome de outra aba, lá em cima,
   para trocar de ferramenta.
5. Cada aba tem um botão laranja, que é a ação principal daquela tela.
   Enquanto o trabalho corre, a barra mostra o progresso e o botão
   **Cancelar** interrompe.
6. No rodapé, à esquerda, aparece uma linha explicando para que serve a aba
   em que você está.

Se você tentar fechar a janela com algum trabalho em andamento, o programa
avisa antes, dizendo qual aba ainda está trabalhando.

## Como rodar no Windows

Baixe o `.exe` do link de download e dê dois cliques. Não precisa instalar
nada: o ffmpeg já vem embutido no programa.

## Detalhes que valem saber

- **A janela nasce do tamanho da sua tela.** Ela se ajusta ao espaço
  disponível, até um limite confortável. Se ainda assim uma tela não couber
  inteira, aparece uma barra de rolagem do lado direito daquela aba, e nada
  fica escondido.
- **Para rolar**, use a roda do mouse ou dois dedos no trackpad, com o
  ponteiro em qualquer lugar da aba. As teclas Page Up, Page Down, Home e End
  também funcionam. Quando o ponteiro está sobre o quadro de mensagens ou
  sobre uma lista, quem rola primeiro é ele; a página só anda depois que ele
  chega ao fim.
- **As abas abrem sob demanda.** A aba só é preparada quando você clica nela
  pela primeira vez, então o programa abre rápido. Se uma aba der problema,
  as outras três continuam funcionando normalmente.
- **A aba Baixar cuida do próprio motor.** Na primeira vez ela busca o
  programa que faz o download e o mantém atualizado sozinha. Precisa de
  internet só nessa hora.
- **O ffmpeg é compartilhado.** As abas Cortar, Extrair quadros e Extrair
  áudio usam o mesmo motor, então ele é baixado uma vez só.

## Se o Mac bloquear ao abrir

O programa não tem certificado pago de desenvolvedor da Apple. Por isso, o
`.zip` baixado do link de download é bloqueado na primeira abertura, com a
mensagem "não pôde verificar a presença de software malicioso". Isso é
comportamento normal do macOS, não é defeito do programa. Para liberar:

1. Clique em **OK** no aviso.
2. Abra **Ajustes do Sistema > Privacidade e Segurança**.
3. Role até o fim e clique em **Abrir Mesmo Assim**, na linha do programa
   bloqueado. Confirme com a senha ou com o Touch ID.
4. Abra o programa de novo e confirme a segunda caixa, que é mais simples.

Só precisa ser feito uma vez por computador.

## Para quem mexe no código

- `estudio_video.py` é a janela: cria as abas, aplica o tema e trata o
  fechamento.
- `tema.py` guarda a paleta e o estilo, aplicados uma única vez para a
  janela inteira. Nenhuma aba define estilo próprio.
- `pastas.py` guarda a pasta padrão de saída (a de Downloads).
- `abas/` tem um arquivo por tela. Cada um expõe `montar(pai)`, que desenha
  a tela dentro do quadro recebido e devolve o objeto do aplicativo. Nenhum
  deles cria janela, define estilo ou chama `mainloop`.
- O quadro que cada aba recebe já vem dentro de uma área rolável, montada por
  `_area_rolavel`. Enquanto o conteúdo couber, ele se comporta como um quadro
  comum (inclusive para telas que ancoram botões com `side="bottom"`).
- Para acrescentar uma aba nova: crie o arquivo em `abas/` com `montar(pai)`
  e adicione uma linha na lista `ABAS`, no topo de `estudio_video.py`.
