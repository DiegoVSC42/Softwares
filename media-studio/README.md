# Media Studio

Video, áudio, imagem e transcrição numa janela só, sempre aberta, sem
precisar procurar qual dos quatro programas tem a ferramenta que você quer.

Versão atual: **v1.22.4**

## De onde ele vem

O Media Studio une, numa única janela, as telas que já existiam em quatro
programas separados:

- **Video Studio** (`estudio-video/`)
- **Audio Studio** (`estudio-audio/`)
- **Image Studio** (`estudio-imagem/`)
- **Transcript Studio** (`transcript-studio/`)

Os quatro **continuam existindo como código-fonte**, nas suas próprias
pastas — nada foi apagado. O Media Studio só reaproveita as telas de cada
um (cada aba é literalmente o mesmo arquivo `.py`, copiado sem mudar a
lógica), então uma correção feita aqui não se propaga sozinha para lá, e
vice-versa. O que muda é o **instalado no Mac**: os quatro apps separados
saem da pasta Aplicativos e dão lugar a este único ícone.

## Duas camadas de abas

1. **Categoria**, em cima: Vídeo, Áudio, Imagem, Transcrição, Web.
2. **Ferramenta**, dentro de cada categoria — a mesma lista de abas que
   cada programa já tinha.

| Categoria | Ferramentas |
|---|---|
| Vídeo | Baixar · Cortar e dividir · Extrair quadros · Extrair áudio |
| Áudio | Cortar e dividir · Extrair áudio · Converter e comprimir · Unir áudios · Separar canais |
| Imagem | Comprimir · Redimensionar · Figurinhas · PrintShot |
| Transcrição | Transcrever · Limpar transcrição · Sincronizar · Nomes de Rondônia |
| Web | Salvar em PDF |

## A aba Salvar em PDF

Guarda uma matéria ou página aberta da internet em PDF, no formato de leitura:
logo do site, título, autor, data, imagens e texto, sem menu nem propaganda.
Se a página não informar o logo, ou ele não puder ser desenhado, o nome do
site aparece escrito no lugar.

1. Abra a categoria **Web**.
2. Cole um ou vários links, um por linha.
3. Clique em **Salvar em PDF**.
4. O arquivo sai na pasta de Downloads, com o título da matéria e o nome do
   site. Um PDF que já existe nunca é apagado: o novo ganha um número no fim.

Se um link falhar, os outros continuam, e o motivo aparece no registro.

**Conteúdo pago não é aberto.** Se a própria página disser que é só para
assinantes, o programa para e avisa, sem tentar pegar o texto. Quem tem
assinatura pode entrar no site pelo navegador e usar Arquivo > Imprimir >
Salvar como PDF.

## A aba Transcrever

Transforma áudio ou vídeo em texto **aqui no computador, sem internet**. Usa o
Whisper, o mesmo tipo de inteligência artificial que serviços como o
TurboScribe usam por trás, só que rodando na própria máquina: o áudio não sai
dela.

**Na primeira vez**, a aba pede para **Preparar**. É a única vez que precisa
de internet: ela instala o motor e baixa o modelo, uns 2 GB, o que leva de um
a cinco minutos. A peça que separa quem fala (ver abaixo) vem junto. Tudo fica guardado em
`~/Library/Application Support/MediaStudio/Transcricao`, fora do aplicativo,
então reinstalar ou atualizar o Media Studio não baixa nada de novo.

Depois disso, é pôr os arquivos na fila (MP3, M4A, WAV, MP4, MOV e quase
qualquer outro) e clicar em **Transcrever tudo**. O texto vai aparecendo na
tela enquanto ele ouve, com a previsão de quanto falta. Num Mac com chip Apple
ele usa a placa de vídeo: medido num M1 Pro, 4,5 minutos de áudio saíram em 25 segundos.

O campo **Nomes e palavras difíceis** ajuda com o que o Whisper não conhece:
nomes de pessoas, de cidades, siglas. Escreva separados por vírgula.

**O que sai** é o mesmo formato da aba **Limpar transcrição** (título, data,
quem fala e os horários entre parênteses), em Word e/ou Texto, mais uma
legenda `.srt` se você marcar. Por isso a aba **Sincronizar** abre o arquivo
direto.

### Separar quem fala

Com a caixa **Separar quem fala** marcada (ela vem desmarcada), o programa
**descobre sozinho quantas pessoas falam** e divide o texto por pessoa:
**Palestrante 1**, **Palestrante 2**, **Palestrante 3**..., na ordem em que cada
voz aparece na gravação. Também sem internet: um segundo motor reconhece as
vozes enquanto o Whisper escreve, então quase não custa tempo. Medido num M1
Pro, 9 minutos de entrevista saíram em 27 segundos separando.

Nos testes, ele acertou quantas pessoas falavam em 12 de 12 gravações, com 1,
2, 3 e 4 pessoas, entre vozes sintéticas e gravações de gente de verdade.

### Quem é quem: o nome de cada pessoa

Assim que um arquivo fica pronto, aparece a caixa **Quem é quem**, com **um
campo de nome para cada pessoa encontrada**. Em cima de cada campo está o que
aquela pessoa disse primeiro, com o horário, por exemplo
"Palestrante 2 · (0:06) Claro, o programa atende...". Assim dá para saber
quem é quem sem adivinhar.

Escreva os nomes e aperte **Enter** (ou clique em **Gravar os nomes**). O
Word, o texto e a legenda daquele arquivo são regravados com os nomes no
lugar de "Palestrante 1, 2...", e a aba **Sincronizar** continua abrindo o
arquivo do mesmo jeito. Dá para mudar um nome quantas vezes quiser.

- **Vários arquivos na fila:** cada um tem as suas pessoas e os seus nomes.
  A lista no alto da caixa troca de arquivo. Dá para ir dando nomes ao
  primeiro enquanto o segundo ainda está sendo transcrito.
- **A mesma pessoa apareceu duas vezes?** Dê o mesmo nome às duas: no
  arquivo, elas viram uma pessoa só.
- **Na legenda (.srt)** o nome aparece só quando a pessoa troca, como em
  legenda de entrevista ("Ana: Bom dia.").

Quem preparou o motor antes da versão 1.20 recebe, ao marcar a caixa pela
primeira vez, o pedido para baixar só a peça que separa as vozes (uns 95 MB,
com internet, uma vez só).

Sem a caixa marcada, tudo sai em nome de "Palestrante 1", como antes, e a
troca de nomes é feita na aba **Sincronizar**.

**Limites conhecidos:** duas pessoas de voz muito parecida podem sair como
uma só, e aí a correção é na aba **Sincronizar**. E quando duas pessoas falam
sem pausa nenhuma entre uma e outra, o Whisper às vezes junta as duas falas
num trecho só, que fica inteiro com uma pessoa. Nos testes, foi 1 trecho em
cada 100.

## A aba Figurinhas

Aceita **PNG e GIF**. Cada imagem ganha um quadro do tamanho do próprio
desenho, com uma margem em volta, e o desenho fica centralizado. Dá para
forçar o quadro quadrado (1:1, como o WhatsApp pede) e limitar o lado maior
(512 px é a medida das figurinhas do WhatsApp).

**GIF animado continua animado.** A conta não é feita quadro a quadro: se
fosse, cada quadro teria um recorte diferente e o desenho ficaria pulando
dentro da figurinha. O programa mede a área que o desenho ocupa somando
**todos** os quadros e aplica esse mesmo recorte à animação inteira, então o
movimento fica exatamente onde estava. A velocidade de cada quadro e a
repetição do GIF original são mantidas.

A prévia, na direita, também anda: com um GIF selecionado você vê a animação
rodando já dentro do quadro novo, antes de gerar arquivo nenhum.

A extensão é preservada: PNG entra, PNG sai; GIF entra, GIF sai.

## A aba Sincronizar

Põe o vídeo e a legenda lado a lado para você conferir, ouvindo, quem está
falando em cada trecho, e corrigir o que a transcrição errou.

Você entrega o vídeo e a legenda que saiu da aba de limpar. A tela de trabalho
mostra a legenda à esquerda e o vídeo à direita. A fala que está tocando fica
acesa e a lista acompanha sozinha. Um clique em **qualquer lugar da fala**
(o horário, o texto, o espaço em volta) leva o vídeo até ela. Clicando no
texto, o mesmo clique ainda deixa o cursor onde você clicou, pronto para
corrigir a escrita, sem segundo clique nenhum. **Enter** confirma a correção e
fecha a edição (não quebra a fala em duas linhas), e **Esc** desfaz o que você
digitou naquela fala.

A **ordem dos falantes** é sua: arraste os nomes na coluna da direita para
colocá-los onde quiser. É essa ordem que o menu de troca de falante usa, e ela
fica guardada — quem passa o dia corrigindo decora a posição de cada um, e a
lista mudar de lugar sozinha custa caro.

Cada pessoa tem uma **cor**, e ela é sua: clique no nome na coluna da direita
e escolha entre dezesseis cores com nome (vermelho, vinho, rosa, laranja,
amarelo, bege, marrom, verde, verde-água, ciano, azul, azul-escuro, roxo,
lilás, chumbo e branco). Dá para casar a cor com a roupa de cada um, que é como
a gente reconhece quem é quem num grupo gravado, e a escolha fica guardada para
as próximas vezes que você abrir aquela entrevista.

Um clique **seleciona** aquela fala, e só ela. Para pegar mais de uma,
**⌘+clique** soma falas soltas e **shift+clique** seleciona de uma até outra
(o quadradinho à esquerda faz o mesmo); com duas ou mais, aparece uma barra
laranja dizendo quantas são. **Esc** limpa a seleção.

Clicar no nome de quem fala abre a lista de falantes, e a troca vale para **o
que estiver selecionado** — uma fala ou as dez que você juntou. Há também o
alcance **dali em diante**, que corrige até mudar de falante; ele vale só
naquela vez, e o menu seguinte volta ao normal. Feita a troca, a seleção se
desfaz sozinha, para a próxima correção começar limpa. Quando a entrevista tem
muita gente, a lista de falantes abre em duas colunas, para não passar da
altura da tela.

**Dividir uma fala em duas** (quando a transcrição juntou duas pessoas numa
linha só): pare o vídeo no instante em que a segunda começa a falar, clique no
texto exatamente no ponto do corte e use o **✂ Dividir** (ou ⌘+Enter). O texto
se parte ali, a segunda metade nasce com o horário em que o vídeo está, e já
fica selecionada para você dizer quem fala nela. Se o vídeo estiver longe
daquele trecho, o horário é estimado pelo tamanho do texto de cada lado.
Com o vídeo parado, clicar no texto não o move: é isso que permite pausar no
instante certo e depois posicionar o cursor sem perder o ponto.

**Errou alguma coisa?** **⌘Z** (ou o botão **⤾ Desfazer**) volta atrás na
última divisão, junção, troca de falante ou renomeação, até quarenta passos.
Dentro do texto, o ⌘Z continua sendo o do navegador, desfazendo o que você
digitou. E para juntar duas falas numa só, selecione as duas seguidas com
⌘+clique e use **⤿ Juntar numa fala só**, na barra laranja.

Os botões **↻ Repetir**, **✂ Dividir**, **⤢ Vídeo grande** e **⤾ Desfazer** ficam na barra da
busca, do lado da legenda, e não no painel do vídeo: assim continuam à mão com
a janela em meia tela.

O **⤢ Vídeo grande** engorda o painel da direita e deixa só o vídeo nele, sem
os controles embaixo. É a saída para quem trabalha numa tela só e não quer
mandar o vídeo para uma janela separada.

Para entender uma fala atravessada, use o **↻ Repetir** (ou a tecla **R**): ele
toca a mesma fala sem parar, quantas vezes você precisar. Com várias falas
selecionadas, repete o trecho inteiro, do começo da primeira até o fim da
última. O trecho em repetição fica com um filete verde na lateral, e clicar em
outra fala leva a repetição junto.

A largura das duas colunas é sua: arraste a divisória no meio (dois cliques
nela voltam ao normal). Quem trabalha com dois monitores pode mandar o vídeo
para uma **janela separada** e arrastá-la para a outra tela; é o mesmo vídeo
mudado de lugar, não uma cópia, então ele continua de onde estava e tudo
continua respondendo.

A coluna da direita se recolhe: o botão **Ocultar painel**, na barra de cima,
dá a tela inteira para a legenda. Quando o vídeo vai para a outra janela ela se
recolhe sozinha, porque já não tem o que mostrar, e o botão **Mostrar painel**
a traz de volta quando você precisar da sincronia ou da lista de falantes. O
botão **Trazer o vídeo** também aparece lá em cima, para não ficar escondido
junto com o painel.

A janela do vídeo nunca fica órfã: ela se fecha sozinha quando você fecha a
aba da legenda, e também quando o programa é fechado. Nesse último caso a tela
do navegador avisa em vermelho que não salva mais, para você não corrigir meia
hora de entrevista achando que está tudo sendo guardado.

Passando o mouse em qualquer botão, aparece **o que ele faz e o atalho dele**
(⌘S salvar, R repetir, ⌘Z desfazer, ⌘+Enter dividir, J e L pular cinco
segundos, espaço tocar e pausar).

A barra de cima (salvar, contagem, painel) e a busca **não rolam nunca**: quem
rola é só a lista de falas. Vale também com a janela estreita, meia tela, que é
como se trabalha quando o vídeo está no outro monitor.

**O título e o nome do arquivo são seus:** clique no título, no alto da tela, e
troque os dois. O título é a primeira linha do documento; o nome é como o
`.docx` e o `.txt` vão se chamar na pasta. A escolha fica guardada e vale já no
próximo salvamento, inclusive nos automáticos.

Ao gravar, uma faixa verde fica na tela com **o nome dos arquivos e a pasta
em que eles foram parar**, mais um botão **Mostrar no Finder** que abre a pasta
já com o arquivo selecionado. A faixa não some sozinha: você fecha quando
quiser.

No fim, **Salvar corrigido** grava um `.docx` e um `.txt` novos na pasta
escolhida, no mesmo formato da aba de limpar. O original não é tocado.

**Por que essa tela abre no navegador:** porque o Tkinter não toca vídeo e
principalmente não toca **som**, e sem ouvir não há como conferir quem fala.
Então o vídeo toca onde toca bem, que é o navegador que você já tem. Nada sai
do seu computador: o programa serve o vídeo só para ele mesmo, em `127.0.0.1`,
com uma senha nova a cada sessão. Deixe o Media Studio aberto enquanto
trabalha, porque é ele que está servindo o vídeo.

**Se pular no vídeo estiver demorando uma eternidade**, o problema não é o
programa: é como o arquivo foi gravado. Num MP4 sem "faststart", o índice do
vídeo fica no **fim** do arquivo, e para pular para o minuto 36 o navegador tem
que baixar quase o arquivo inteiro antes. O programa detecta isso na hora em
que você escolhe o vídeo e se oferece para preparar uma cópia: leva alguns
segundos, não recodifica nada e não perde um pixel de qualidade, só move o
índice para o começo. A partir daí os pulos são instantâneos.

O navegador toca **MP4, MOV, M4V e WEBM**. Outros formatos o programa avisa
antes; nesse caso, converta para MP4 na categoria Vídeo.

## Telas que aparecem em mais de uma categoria

"Cortar e dividir" e "Extrair áudio" aparecem em Vídeo **e** em Áudio de
propósito: é a mesma tela (`compartilhado/cortar_dividir.py` e
`compartilhado/extrair_audio.py`, sincronizadas por
`abas-compartilhadas/sincronizar.py`), só que montada duas vezes — igual
já funcionava com os dois programas separados. A aba **Sincronizar** segue a
mesma regra: a fonte é `abas-compartilhadas/aba_sincronizar.py`, porque ela
também existe no Transcript Studio. O parâmetro `foco` de cada
aba só muda a ordem dos filtros do diálogo de arquivo; não muda o que a
ferramenta faz.

Cada ferramenta só é montada na primeira vez que a pessoa clica nela — o
programa abre rápido e, se uma ferramenta falhar, todas as outras
continuam funcionando.

## Estilo

`tema.py` é a união dos quatro `tema.py` que existiam (três deles
idênticos entre si; o do Transcript Studio havia evoluído sozinho e
corrigido um defeito real no Checkbutton do modo escuro — ver comentário
no próprio arquivo). Nenhum nome de estilo foi removido: tudo que qualquer
aba dos quatro usava continua existindo, com o mesmo comportamento.

## Mandar para outro Mac

O aplicativo do `criar-media-studio-mac.command` usa o Python desta máquina e
não roda em outro computador. Para outra pessoa, o arquivo certo é o
`MediaStudio-mac.zip`, que leva tudo dentro e abre em Mac com macOS 12 ou mais
novo. A transcrição é a exceção: ela precisa de um Python 3.10 ou mais novo
instalado no Mac de quem usa.

1. Descompactar o `.zip` com clique duplo.
2. Arrastar o Media Studio para a pasta Aplicativos. Sem isso, o programa abre,
   mas não consegue se atualizar depois.
3. Abrir o programa.

## Se o Mac bloquear ao abrir

O programa não tem certificado pago da Apple, então o Mac bloqueia a primeira
abertura com a mensagem "não pôde verificar a presença de software malicioso".
É normal, e só precisa ser feito uma vez por computador:

1. Clicar em OK no aviso.
2. Abrir **Ajustes do Sistema > Privacidade e Segurança**.
3. Rolar até o fim e clicar em **Abrir Mesmo Assim** na linha do Media Studio,
   confirmando com senha ou Touch ID.
4. Abrir o programa de novo e confirmar a segunda caixa.

## Publicar versão nova

1. Subir o número de `APP_VERSION` no `media_studio.py`. Sem isso, ninguém
   recebe o aviso, e o publicador para com essa explicação.
2. Clique duplo em `publicar-media-studio.command`. Leva uns 15 minutos.
3. Quem tem o programa vê o aviso "Atualizar agora?" na próxima vez que abrir.
