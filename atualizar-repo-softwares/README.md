# Atualizar Softwares

Mantém atualizada uma cópia local do repositório de referência
`DiegoVSC42/Softwares` (onde ficam todos os softwares já publicados),
rodando um `git pull` -- ou o clone inicial, na primeira vez.

## Como usar

1. Abra o programa.
2. Na primeira vez, clique em **Escolher pasta...** e escolha (ou crie) a
   pasta onde a cópia do repositório vai ficar. Da próxima vez o programa já
   lembra essa escolha.
3. Clique em **Atualizar agora**. O log mostra o progresso.
4. **Cancelar** interrompe uma atualização em andamento.

## Requisitos

- Git instalado.
- Python 3 com Tkinter (nenhuma dependência externa) -- só necessário para
  rodar a partir do código-fonte; o `.exe`/`.app` já vem pronto.

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
