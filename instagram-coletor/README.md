# Instagram Coletor

Baixa fotos, carrosséis, reels e stories do Instagram e monta uma planilha com
os dados de cada publicação (legenda, data, curtidas, hashtags e link).

## Caso de uso

Puxar o material e os números de um perfil (o seu, o do candidato ou o do
adversário) para análise e para reaproveitamento de conteúdo.

## O que dá para fazer

**Por link**

- Post único, carrossel (baixa todas as fotos e vídeos), Reel, IGTV e link de compartilhamento.
- Vários links de uma vez, um por linha.

**Por perfil**

- Feed inteiro, só Reels, Stories das últimas 24 horas, Destaques, fotos em que
  a pessoa foi marcada e a foto de perfil em alta resolução.
- Limite de quantidade (ex.: só os 30 posts mais recentes).

**Planilha de metadados (.xlsx)**

- Uma linha por arquivo, com: usuário, data, tipo, link do post, legenda,
  curtidas, hashtags, menções, localização, nome do arquivo e shortcode.
- Pode ser gerada com ou sem baixar a mídia.

**Filtros**

- Só imagens, só vídeos, incluir ou não os posts fixados, salvar um `.json` por post.

## Login

O Instagram exige conta logada para quase tudo. A ferramenta puxa os cookies de
um navegador em que você já está logado (Chrome, Firefox, Edge, Brave, Opera,
Chromium, Vivaldi) ou de um arquivo `cookies.txt`. Use o botão "Testar login"
para conferir antes de coletar.

O Safari não entra na lista: no Mac ele guarda os cookies num arquivo que o
sistema protege, e a leitura falha.

- Perfil privado só funciona se a conta logada seguir o perfil.
- Baixar muita coisa de uma vez pode gerar bloqueio temporário. Use o limite de
  posts e faça em lotes.

## Como usar

1. Abra o programa.
2. Escolha a pasta de destino.
3. Em "Login", selecione o navegador em que você está logado no Instagram.
4. Escolha a aba: "Links" para colar links, ou "Perfil inteiro" para digitar o @.
5. Marque o que quer em "Opções" (baixar mídia, gerar planilha, só imagens etc.).
6. Clique em "Coletar" e acompanhe o progresso. Dá para cancelar a qualquer momento.
7. Ao terminar, clique em "Abrir pasta" para ver os arquivos e a planilha.

## Arquivos para clicar

| Arquivo | Sistema | O que faz |
|---|---|---|
| `abrir-instagram-coletor.command` | Mac | abre o programa |
| `publicar-instagram-coletor.command` | Mac | gera o aplicativo do Mac, envia pro GitHub e baixa o `.exe` do Windows |
| `instagram-coletor.bat` | Windows | gera o `.exe`, envia pro GitHub e baixa o `.zip` do Mac |

## Janela preta no Mac

O Mac vem com uma versão antiga da parte gráfica (Tk 8.5), que desenha a janela
preta. O atalho já procura sozinho uma versão boa do Python. Se mesmo assim a
janela sair preta, instale o Python oficial em
https://www.python.org/downloads/macos/ e abra o programa de novo.

## Aviso

Use apenas para conteúdo público ou próprio, respeitando os termos do Instagram
e a legislação de dados. A ferramenta não burla privacidade: ela apenas acessa
o que a conta logada já poderia ver no navegador.
