# Renomeador em Lote de Arquivos

Programa com janela (interface gráfica) que renomeia todos os arquivos de uma
pasta de uma vez: adicionar prefixo, adicionar sufixo, remover texto do
início/fim, remover uma quantidade de caracteres, localizar e substituir,
numerar em sequência e converter maiúsculas/minúsculas. Mostra uma prévia
antes de aplicar e permite desfazer a última operação.

O que ele faz, na ordem em que aplica:

1. Remove uma quantidade de caracteres do início e/ou do final do nome.
2. Remove um texto exato do início e/ou do final do nome.
3. Localiza um texto e substitui por outro, em qualquer parte do nome.
4. Converte para MAIÚSCULAS, minúsculas ou Capitalizado.
5. Adiciona um prefixo e/ou um sufixo (o sufixo entra antes da extensão).
6. Numera os arquivos em sequência (001, 002, 003...), no início ou no fim
   do nome, com o número de dígitos e o número inicial que você escolher.

Outros recursos:

- Filtro por extensão (ex.: `.jpg,.png`) para renomear só um tipo de arquivo.
- Opção de incluir subpastas.
- Prévia com o nome atual e o nome novo lado a lado antes de aplicar qualquer coisa.
- Avisos de erro na prévia (nome duplicado, nome que já existe, nome que ficaria vazio) — esses itens são ignorados na hora de aplicar.
- Botão "Desfazer Última Operação", para reverter a última renomeação feita na sessão.
- Barra de progresso e botão Cancelar durante a renomeação.

## Como rodar no Mac

1. Clique duas vezes em `abrir-renomeador-lote-arquivos.command`.
2. Na primeira vez, o Mac pode bloquear ("não é possível verificar o
   desenvolvedor"). Clique com o botão direito no arquivo, escolha Abrir e
   confirme em Abrir. Também na primeira vez, o programa demora 1 a 2 minutos
   preparando o ambiente.
3. Na janela: clique em "Selecionar Pasta..." e escolha a pasta com os arquivos.
4. Preencha as regras que quiser usar (prefixo, sufixo, remover texto, etc.) —
   pode combinar mais de uma.
5. Clique em "Atualizar Prévia" para ver como os nomes vão ficar.
6. Confira a prévia e clique em "Aplicar Renomeação".
7. Se algo sair errado, use "Desfazer Última Operação" logo em seguida.

## Como rodar no Windows

1. Clique duas vezes em `RenomeadorLoteArquivos.exe` (na pasta
   `D:\Softwares\Windows`, gerado pelo `renomeador-lote-arquivos.bat`).
2. Siga os mesmos passos 3 a 7 acima.

## Publicação

- Mac: `publicar-renomeador-lote-arquivos.command` gera o aplicativo do Mac,
  envia ao GitHub e baixa o programa do Windows.
- Windows: `renomeador-lote-arquivos.bat` gera o programa do Windows, envia ao
  GitHub e baixa o pacote do Mac.

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
