# Baixador de Vídeos

Programa com janela (Tkinter) para baixar vídeos e áudios da internet, com
remoção de todos os metadados do arquivo.

## O que ele faz

- Baixa vídeo por link, com escolha de qualidade (melhor, 1080p, 720p, 480p, 360p).
- Deixa escolher o nome do arquivo de saída (opcional). Vazio, usa o título do
  vídeo. Em playlist, cada item sai numerado ("Nome - 1", "Nome - 2"…).
- Baixa somente o áudio em MP3.
- Corta o vídeo por tempo: campos opcionais de "início" e "fim" (formato
  hh:mm:ss) baixam o vídeo completo e cortam o trecho escolhido logo em
  seguida, sem recodificar. Dá para preencher só um dos dois (do início até
  X, ou de X até o fim). O YouTube não deixa baixar só o trecho direto do
  site de forma confiável (testado: o recurso nativo do motor de download
  ignorava o início pedido e trazia o arquivo maior do que devia), por isso
  o corte é feito depois, no arquivo já baixado.
- Baixa uma playlist inteira.
- Remove **todos** os metadados do arquivo baixado: título, autor, canal,
  descrição, capa embutida, capítulos, data de gravação, nome do aparelho,
  marca do programa que gerou o arquivo e a data original do arquivo.
- Limpa os metadados de arquivos que já estão no computador (botão
  "Limpar arquivos que já tenho…").
- Usa os cookies do navegador quando o site pede login ou verificação.
- Instala e atualiza sozinho, em segundo plano, o que o YouTube exige hoje: o
  motor de download (yt-dlp) e o motor de JavaScript (Deno). Isso não aparece
  na tela — o programa cuida disso sem precisar de nenhum clique.
- Ao terminar o download, pergunta se quer abrir a pasta onde o arquivo foi
  salvo.

A limpeza não recodifica: a imagem e o som ficam idênticos, só as informações
extras somem.

## Por que o motor fica fora do programa

O motor de download é o `yt-dlp`. Os sites mudam toda hora e um motor velho
começa a devolver o erro "403 Forbidden" (acesso negado). Por isso ele não vai
mais dentro do executável: fica guardado numa pasta do usuário e pode ser
atualizado pelo próprio programa, sozinho e em segundo plano, sem precisar
gerar um programa novo nem aparecer na tela. Quando um download falha com
403, o programa atualiza o motor sozinho e tenta de novo.

Onde ele fica:

- Mac: `~/Library/Application Support/BaixadorDeVideos/yt-dlp`
- Windows: `%LOCALAPPDATA%\BaixadorDeVideos\yt-dlp.exe`

## Como rodar

### Mac

1. Clique duas vezes em `abrir-baixador-videos.command`.
2. Na primeira vez o Mac pode avisar que "não foi possível verificar o
   desenvolvedor": clique com o botão direito no arquivo, escolha **Abrir** e
   depois **Abrir** de novo.
3. Na primeira abertura o programa baixa sozinho, em segundo plano, o motor
   de download e o motor de JavaScript (2 a 4 minutos, uma vez só). Isso não
   aparece na tela; o status embaixo mostra "Pronto." quando termina.
4. Cole o link, escolha a qualidade e, se quiser, digite o nome do arquivo no
   campo "Nome do arquivo (opcional)". Para baixar só um trecho, preencha
   "início" e/ou "fim" no formato hh:mm:ss (ex.: 1:23:45). Confira a caixa
   "Remover TODOS os metadados" (já vem marcada) e clique em **Baixar**.
5. Ao terminar, o programa pergunta se quer abrir a pasta onde o arquivo foi
   salvo. O arquivo fica na pasta escolhida em "Salvar em" (por padrão,
   Downloads).

### Windows

1. Clique duas vezes no `BaixadorDeVideos.exe` (pasta `D:\Softwares\Windows`).
2. O restante é igual ao Mac.

## O erro 403 do YouTube, e por que ele acontecia

O YouTube passou a exigir duas coisas que o motor sozinho não resolvia:

1. **Um motor de JavaScript.** O site manda um desafio que só é resolvido
   rodando JavaScript. Sem isso, os endereços de download saem sem assinatura e
   o YouTube responde "403 Forbidden". O programa agora instala o **Deno**
   sozinho (cerca de 40 MB, uma vez só) e o usa. Se você já tiver Deno ou Node
   na máquina, ele aproveita e não baixa nada.
2. **O aparelho certo na hora de pedir o vídeo.** O motor escolhia sozinho um
   "cliente" que o YouTube recusa. O programa agora pede pelo cliente que
   funciona, e só volta à escolha automática na segunda tentativa, caso um dia
   esse caminho mude.

Se ainda assim der 403 (o programa já tenta atualizar o motor e tentar de
novo sozinho, por outro caminho, uma vez):

1. Marque **Usar cookies do navegador** e escolha o navegador em que você
   está logado no site. No Mac, o Chrome pode pedir permissão do chaveiro e
   o Safari exige Acesso Total ao Disco para o programa.
2. Se continuar, feche e abra o programa de novo.

## Publicar uma nova versão

- No Mac: clique duas vezes em `publicar-baixador-videos.command`.
- No Windows: clique duas vezes em `baixador-videos.bat`.

Cada um gera o executável da própria máquina, envia o código para o GitHub,
espera a nuvem montar o executável do outro sistema e baixa o resultado.

Link de download fixo:
https://github.com/DiegoVSC42/Softwares/releases/tag/baixador-videos

## Versão

- v1.6.0 — tira da tela a seção técnica do motor de download (ele continua
  se instalando e se atualizando sozinho, só que em segundo plano); ao
  terminar o download, pergunta se quer abrir a pasta de destino.
- v1.5.1 — corrige o corte por tempo: agora corta no arquivo já baixado
  (confiável), em vez de usar o recurso nativo do motor de download que
  ignorava o início pedido nos vídeos do YouTube.
- v1.5.0 — corte por tempo (início e/ou fim) na hora de baixar.
- v1.4.0 — campo opcional de nome do arquivo de saída (vazio = título do
  vídeo; em playlist, numera cada item).
- v1.3.0 — instala o motor de JavaScript (Deno) e pede o vídeo pelo cliente
  que o YouTube aceita. É a correção do erro 403.
- v1.2.0 — motor de download atualizável (fim do erro 403 por motor velho),
  cookies do navegador, retentativa automática.
- v1.1.0 — remoção de metadados, limpeza de arquivos existentes e versão no
  rodapé da janela.
