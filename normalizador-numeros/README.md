# Normalizador de Números

Programa com janela (interface gráfica) que formata listas de telefones
brasileiros de uma vez só. Cole os números ou carregue um arquivo, escolha o
formato e clique em Normalizar.

O que ele faz:

1. Limpa tudo que não é número (parênteses, traços, espaços).
2. Trata o código do país (55), colocando ou tirando conforme o formato.
3. Completa o 9 na frente de celulares antigos de 8 dígitos.
4. Aplica um DDD padrão nos números que vierem sem DDD (opcional).
5. Remove números repetidos (opcional).
6. Separa os inválidos, mostrando o motivo de cada um.
7. Modo "Manter inválidos": a saída fica alinhada linha a linha com a entrada
   (inválidos e células vazias permanecem no lugar), pronta para copiar e colar
   de volta na coluna da planilha sem bagunçar a ordem.

Formatos de saída: WhatsApp (5562999998888), Internacional (+55 62 99999-8888),
Nacional ((62) 99999-8888) e somente dígitos com DDD.

## Como rodar no Mac

1. Clique duas vezes em `abrir-normalizador-numeros.command`.
2. Na primeira vez, o Mac pode bloquear ("não é possível verificar o
   desenvolvedor"). Clique com o botão direito no arquivo, escolha Abrir e
   confirme em Abrir. Também na primeira vez, o programa demora 1 a 2 minutos
   preparando o ambiente.
3. A janela abre. Cole os números ou clique em Carregar arquivo.
4. Escolha o formato, informe o DDD padrão se quiser e clique em Normalizar.
5. Use Copiar resultado ou Salvar resultado para aproveitar a lista.

## Como rodar no Windows

1. Clique duas vezes em `NormalizadorNumeros.exe` (na pasta
   `D:\Softwares\Windows`, gerado pelo `normalizador-numeros.bat`).

## Publicação

- Mac: `publicar-normalizador-numeros.command` gera o aplicativo do Mac, envia
  ao GitHub e baixa o programa do Windows.
- Windows: `normalizador-numeros.bat` gera o programa do Windows, envia ao
  GitHub e baixa o pacote do Mac.
