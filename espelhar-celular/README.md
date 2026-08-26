# Espelhar Celular

Assista ao celular (YouTube e qualquer aplicativo) na tela do computador, com o som saindo no computador e a tela do celular apagada, economizando bateria.

## O que ele faz

1. Conecta o celular pelo cabo USB (ou por Wi-Fi, opcional).
2. Mostra a imagem do celular numa janela do computador.
3. O som toca no computador e a tela do celular apaga sozinha.
4. Você escolhe a qualidade: Máxima (mais nítida) ou Equilibrada (mais leve).

## Preparo do celular (uma vez só)

1. Abra Configurações e toque sete vezes em "Número da versão" (em "Sobre o telefone") para liberar o modo de desenvolvedor.
2. Em "Opções do desenvolvedor", ligue a "Depuração USB".
3. Ao conectar o cabo pela primeira vez, aceite o aviso "Permitir depuração USB" no celular.

## Como rodar (Mac)

1. Dê dois cliques em `abrir-espelhar-celular.command`.
2. Na primeira vez, o Mac pode bloquear: clique com o botão direito no arquivo, escolha Abrir e depois Abrir de novo.
3. Se o programa avisar que falta o espelhador (scrcpy), aceite instalar; demora alguns minutos só na primeira vez.
4. Conecte o cabo, escolha a qualidade e clique em "Conectar e espelhar".

## Publicação

- Mac: `publicar-espelhar-celular.command`
- Windows: `espelhar-celular.bat`

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
