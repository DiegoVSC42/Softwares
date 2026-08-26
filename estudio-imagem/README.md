# Estúdio de Imagem

Uma janela só, com quatro abas, para tudo que se faz com arquivo de imagem:
deixar mais leve, mudar tamanho e proporção, virar figurinha e capturar tela.

Reúne três programas que antes eram separados (Comprimir Imagem, Normalizador
de Figurinhas e PrintShot) e traz uma ferramenta nova, o Redimensionador.

## As quatro abas

| Aba | Para que serve |
|---|---|
| **Comprimir** | Reduz o peso de fotos até caber num tamanho máximo que você define (por exemplo 300 KB por arquivo). Procura sozinho a maior qualidade que ainda respeita o limite, e só diminui o tamanho em pixels quando não há outro jeito. Também aceita link. |
| **Redimensionar** | Muda tamanho e proporção de várias fotos de uma vez, nos formatos de campanha (feed, Stories, capa). Você escolhe o que fazer com a sobra da foto. |
| **Figurinhas** | Ajusta vários PNGs de uma vez para o padrão de figurinha, detectando sozinho onde está o desenho e montando um quadro com margem em volta. Tem prévia: clique num arquivo da lista para ver como ele vai ficar, com a transparência visível. |
| **PrintShot** | Captura sempre a mesma área da tela, com um clique, numerando as capturas em sequência. |

As imagens originais nunca são alteradas: o programa sempre grava arquivos
novos.

## O enquadramento, na aba Redimensionar

Quando a foto não tem a proporção que você pediu, sobra imagem. Você escolhe o
que fazer com essa sobra:

- **Cortar pelo centro** — preenche o quadro cortando a sobra, sempre pelo
  meio. É o ponto de partida: a foto que precisar de outro enquadramento você
  mira na mão, na prévia (veja abaixo).
- **Encaixar inteira, com fundo** — não corta nada: encaixa a foto toda e
  preenche a sobra, com uma cor que você escolhe ou com a própria foto
  desfocada, como se vê nos Stories.

Trocar entre os dois refaz os enquadramentos que você tiver ajustado à mão,
porque você está pedindo outro critério. O programa avisa no registro quando
isso acontece.

## A prévia, e como mirar cada foto

A aba Redimensionar mostra dois quadros: **Antes**, com a foto inteira e uma
moldura laranja marcando onde o corte vai cair, e **Depois**, com o resultado
final. Clicar num arquivo da lista troca a prévia.

A moldura é sua para mexer:

- **Arraste a moldura com o mouse**, direto no quadro "Antes".
- Ou use as **três barras** embaixo: Horizontal e Vertical movem o recorte,
  e Tamanho aproxima ou afasta o enquadramento.
- As duas formas conversam: arrastar move as barras, e mexer nas barras move
  a moldura.

O ajuste **fica guardado por foto**. Se você enquadrar a foto 3, olhar a 4 e
voltar para a 3, o seu enquadramento continua lá. As fotos que você já ajustou
aparecem marcadas na lista, para não se perder no meio do lote.

Dois botões ajudam:

- **Voltar ao automático** — apaga o seu ajuste naquela foto e devolve o
  enquadramento que o programa tinha escolhido.
- **Aplicar a todas** — copia o enquadramento atual para as outras fotos da
  fila. Num lote de fotos parecidas, resolve tudo de uma vez.

Trocar de proporção não apaga o seu trabalho: o programa mantém o ponto que
você mirou e só ajusta a moldura ao formato novo. Já trocar a estratégia de
enquadramento refaz tudo, porque aí o critério é outro.

## Onde os arquivos são salvos

Todas as abas começam apontando para a sua pasta de **Downloads**. Dá para
trocar em cada aba, mas o ponto de partida é sempre o mesmo, para nenhum
arquivo sumir de vista.

## Como rodar no Mac

1. Dê dois cliques em `abrir-estudio-imagem.command`.
2. Na primeira vez o Mac pode bloquear, com a mensagem "não foi possível
   verificar o desenvolvedor". Nesse caso clique com o botão direito no
   arquivo, escolha **Abrir** e confirme em **Abrir** de novo.
3. Também na primeira vez o programa leva 1 a 2 minutos se preparando, porque
   instala as bibliotecas que abrem e gravam imagem. Isso acontece uma única
   vez.
4. A janela abre na aba **Comprimir**. Clique no nome de outra aba, lá em
   cima, para trocar de ferramenta.
5. Cada aba tem um botão laranja, que é a ação principal daquela tela.
   Enquanto o trabalho corre, a barra mostra o progresso e o botão
   **Cancelar** interrompe.
6. No rodapé, à esquerda, aparece uma linha explicando para que serve a aba em
   que você está.

Se você tentar fechar a janela com algum trabalho em andamento, o programa
avisa antes, dizendo qual aba ainda está trabalhando.

## Detalhes que valem saber

- **A captura de tela precisa de permissão.** No Mac, na primeira vez que você
  usar a aba PrintShot, o sistema vai pedir autorização de Gravação de Tela.
  Como agora quem captura é o Estúdio de Imagem, e não mais o PrintShot
  avulso, a permissão precisa ser dada de novo, para este programa.
- **A janela some na hora de marcar a área.** Isso é de propósito: senão o
  próprio programa apareceria dentro da captura.
- **A janela nasce do tamanho da sua tela**, e se alguma aba não couber
  inteira aparece uma barra de rolagem do lado direito. Para rolar, use a roda
  do mouse ou dois dedos no trackpad, com o ponteiro em qualquer lugar da aba.

## Para quem mexe no código

- `estudio_imagem.py` é a janela: cria as abas, aplica o tema e trata o
  fechamento.
- `tema.py` guarda a paleta e o estilo, aplicados uma única vez para a janela
  inteira. Nenhuma aba define estilo próprio.
- `pastas.py` guarda a pasta padrão de saída (a de Downloads).
- `abas/` tem um arquivo por tela. Cada um expõe `montar(pai)`, que desenha a
  tela dentro do quadro recebido e devolve o objeto do aplicativo. Nenhum
  deles cria janela principal, define estilo ou chama `mainloop`.
- `medir_abas.py` não faz parte do programa: é a ferramenta de conferência.
  Ela abre o Estúdio com a fonte do Mac (a maior) e diz, aba por aba, se o
  conteúdo cabe sem rolar. Rode depois de mexer em qualquer layout.
- Para acrescentar uma aba nova: crie o arquivo em `abas/` com `montar(pai)` e
  adicione uma linha na lista `ABAS`, no topo de `estudio_imagem.py`.
