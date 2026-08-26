# PrintShot

Captura uma área fixa da tela, sempre a mesma, com um clique. Ideal para tirar
várias capturas padronizadas (por exemplo, telas de um aplicativo no Chrome
DevTools) com numeração sequencial e nome personalizado.

Versão consolidada e multiplataforma (Windows e Mac) do repositório
[DiegoVSC42/Printshot](https://github.com/DiegoVSC42/Printshot).

## O que foi corrigido para o Mac

- A captura agora usa o utilitário nativo do Mac, que resolve a tela Retina
  (antes a área capturada saía deslocada ou preta).
- Removida a dependência de recursos exclusivos do Windows na seleção de área.
- A configuração passou a ser salva na pasta do usuário, o que permite rodar
  como aplicativo empacotado.
- Corrigidas linhas duplicadas que impediam o programa de abrir.

## Arquivos

| Arquivo | Sistema | O que faz |
|---|---|---|
| `abrir-printshot.command` | Mac | só abre o programa |
| `publicar-printshot.command` | Mac | build do Mac + push + baixa o `.exe` |
| `printshot.bat` | Windows | build do Windows + push + baixa o `.zip` do Mac |

## Como usar

1. Abra o programa e clique em "Selecionar Área"; arraste o mouse sobre a
   região desejada.
2. Refine com o "Ajuste Fino" se precisar (X, Y, largura, altura) e salve.
3. Escolha a pasta de destino e, se quiser, um nome de arquivo e a numeração
   sequencial.
4. Clique em "Capturar Tela". A imagem aparece no preview, é salva na pasta
   (padrão: Downloads) e já vai copiada para a área de transferência, pronta
   para colar. Os botões "Copiar Última Captura" e "Salvar Como" permitem
   copiar de novo ou guardar em outro lugar.

No Mac, na primeira captura o sistema pede permissão de Gravação de Tela em
Ajustes do Sistema, Privacidade e Segurança. Autorize e capture de novo.

## Downloads

- Windows: <https://github.com/DiegoVSC42/Softwares/releases/download/printshot/PrintShot.exe>
- Mac: <https://github.com/DiegoVSC42/Softwares/releases/download/printshot/PrintShot-mac.zip>

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
