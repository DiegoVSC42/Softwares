# Extrair Quadros

Tira fotos (quadros) de dentro de um vídeo, já cortadas na proporção que você
escolher, com uma tela de preview onde você define exatamente a área que quer
aproveitar.

Feito para o caso mais comum: o vídeo foi gravado em pé (vertical, de celular)
e você precisa de imagens deitadas (16:9) para usar em outro lugar. Mas serve
para qualquer combinação: 9:16 para Reels, 1:1 para feed, 4:5 para Instagram,
21:9 para cinema, e por aí vai.

## O que ele faz

- Abre qualquer vídeo comum (MP4, MOV, MKV, AVI e outros).
- Mostra o quadro na tela e a imagem **acompanha o arrasto da barra**, como um
  scrub de editor de vídeo.
- Deixa **digitar o tempo à mão** (`1:30`, `90`, `1h05m`) e ir direto para lá.
- Tem uma segunda barra, de **ajuste fino**, que é a mesma posição vista de
  perto: ela cobre só um trecho curto do vídeo (1 s, 4 s, 20 s ou 2 min), com
  o tempo escrito nas duas pontas, então cada milímetro de arrasto vale bem
  menos tempo.
- Mostra uma moldura laranja que você **arrasta** com o mouse para escolher a
  área, com linhas dos terços para ajudar a compor.
- Deixa escolher a **proporção**: 16:9, 9:16, 1:1, 4:5, 5:4, 4:3, 3:4, 3:2,
  2:3, 21:9, 2:1, ou livre (o quadro inteiro do vídeo).
- Deixa **aumentar ou diminuir** a moldura, sempre mantendo a proporção.
- Deixa escolher o **trecho** do vídeo (começo e fim) e **quantos quadros por
  segundo** sair (1 por segundo, 1 a cada 2 segundos, 10 por segundo, todos).
- Salva os quadros em PNG ou JPG, no tamanho do recorte ou já redimensionados
  (4K, 2560, Full HD, 1440, HD, 1080, 720 ou 500 px de largura). Quando há
  redimensionamento, o tamanho sai exato: 16:9 com largura 1920 dá 1920 x 1080.

## Como rodar no Mac

1. Dê **clique duplo** em `abrir-extrair-quadros-video.command`.
   - Se o Mac reclamar que não consegue verificar o desenvolvedor, clique com o
     **botão direito** no arquivo, escolha **Abrir** e confirme em **Abrir**.
2. Na primeira vez, ele prepara o ambiente e, se precisar, baixa o motor de
   vídeo (ffmpeg). Leva 1 a 2 minutos. Nas próximas vezes abre na hora.
3. Dentro do programa:
   1. Clique em **Escolher vídeo** e selecione o arquivo.
   2. Chegue no ponto que interessa de três jeitos, à sua escolha: digite o
      tempo em **Ir para** e aperte Enter; arraste a barra **Percorrer o vídeo
      inteiro** (a imagem corre junto); ou use a barra de **Ajuste fino**, logo
      abaixo. As duas barras mostram a mesma posição: a de cima cobre o vídeo
      todo, a de baixo cobre só o trecho escrito nas suas pontas, o que dá
      muito mais precisão. Quando você sai desse trecho pela barra de cima ou
      pelo campo de tempo, ele se muda sozinho para perto de onde você foi, e
      o botão **Recentrar** faz isso na hora. Os botões `< quadro` e
      `quadro >` dão o acerto final, e o número do quadro aparece ao lado do
      campo de tempo.
   3. Escolha a **proporção** que você quer (16:9, 9:16, 1:1, 4:5 e outras).
   4. **Arraste a moldura laranja** até onde você quer que fique o corte. Use a
      barra **Tamanho da moldura** para apertar ou abrir o enquadramento.
   5. Preencha **Começo** e **Fim** (pode digitar `1:30`, `90`, `1h05m`, ou
      clicar em **usar a posição atual**). Deixar em branco significa do início
      e até o fim.
   6. Escolha **Quadros/s**: `1` sai um quadro por segundo, `0.5` sai um a cada
      dois segundos, `todos` sai tudo.
   7. Escolha o formato (JPG para arquivo menor, PNG para qualidade máxima), o
      tamanho e a pasta de saída.
   8. Clique em **Extrair quadros** e acompanhe a barra. Dá para cancelar.
4. No fim, clique em **Abrir pasta** para ver as imagens.

## Como rodar no Windows

Baixe o `.exe` do link abaixo e dê clique duplo. Não precisa instalar nada.

## Downloads

- **Windows:** <https://github.com/DiegoVSC42/Softwares/releases/download/extrair-quadros-video/ExtrairQuadros.exe>
- **Mac (Apple Silicon):** <https://github.com/DiegoVSC42/Softwares/releases/download/extrair-quadros-video/ExtrairQuadros-mac.zip>
- **Mac (Intel):** <https://github.com/DiegoVSC42/Softwares/releases/download/extrair-quadros-video/ExtrairQuadros-mac-intel.zip>

Para saber qual Mac é o seu: menu Apple (canto superior esquerdo) >
**Sobre Este Mac**. Se aparecer "Chip: Apple M1" (ou M2, M3, M4...), baixe o
primeiro link do Mac. Se aparecer "Processador: Intel...", baixe o segundo.

## Se o Mac bloquear ao abrir

O `.zip` baixado do link acima não tem certificado pago da Apple, então na
primeira abertura o Mac mostra um aviso dizendo que não pôde verificar a
presença de software malicioso. É normal. Faça assim, uma única vez por
computador:

1. Clique em **OK** no aviso.
2. Abra **Ajustes do Sistema > Privacidade e Segurança**.
3. Role até o fim e clique em **Abrir Mesmo Assim** na linha do programa,
   confirmando com a senha ou o Touch ID.
4. Abra o programa de novo e confirme a segunda caixa, mais simples.

## Publicar uma versão nova

- **No Mac:** clique duplo em `publicar-extrair-quadros-video.command`.
- **No Windows:** clique duplo em `extrair-quadros-video.bat`.

Os dois fazem tudo num clique: geram o executável da própria máquina, enviam o
código para o GitHub, esperam a nuvem montar os executáveis das outras
plataformas e baixam tudo para a pasta de distribuição.

## Detalhes técnicos

- Interface em Tkinter, sem biblioteca de fora, com paleta escura definida na
  mão (o tema padrão do Tk no macOS não acompanha o modo escuro do sistema e
  deixa campo claro com letra clara).
- Processamento com `ffmpeg` (filtros `fps` e `crop`), embutido no executável.
- As dimensões do vídeo são medidas a partir de um quadro decodificado de
  verdade, e não do cabeçalho do arquivo. Isso garante que vídeo gravado de
  lado (com a rotação guardada nos metadados) seja cortado no lugar certo.

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
