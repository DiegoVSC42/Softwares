# Dividir e Juntar Áudio

Quebra um áudio longo em partes menores, para você tratar cada parte num
serviço externo, e depois junta tudo de volta num arquivo só, sem descompasso.

## Para que serve

Um caso típico: uma entrevista de 2 horas que precisa passar por um serviço de
melhoria de voz ou de transcrição, mas o serviço só aceita arquivos curtos.
O programa divide em 4 partes de 30 minutos, você trata as 4, e depois ele
junta na ordem certa.

## O que ele resolve

- **Ordem.** As partes saem numeradas (`01_`, `02_`, ...), e a numeração
  sobrevive mesmo quando o serviço externo cola sufixo no nome do arquivo
  (`01_entrevista_enhanced.wav`).
- **Corte no lugar certo.** Dá para cortar no tempo exato ou pedir para o
  programa procurar o silêncio mais próximo, para não partir palavra no meio.
- **Nada some no meio.** O corte é feito numa passada só pelo ffmpeg, então o
  fim de uma parte é exatamente o começo da seguinte. Sem sobra, sem falta.
- **Formatos diferentes na volta.** Se o serviço devolver uma parte em WAV
  48 kHz estéreo e outra em MP3 mono, a junção normaliza tudo.
- **Conferência.** Um manifesto `.json` guarda a duração original de cada
  parte. Na hora de juntar, o programa compara e avisa se alguma parte voltou
  mais curta (sinal de que o serviço aparou silêncio ou pontas).

## Como usar

1. Clique duas vezes em `abrir-dividir-juntar-audio.command`.
2. Aba **1. Dividir**: escolha o áudio, diga em quantas partes (ou de quantos
   minutos cada), escolha onde cortar e clique em **Dividir**.
3. Leve as partes para o serviço de tratamento.
4. Traga os arquivos tratados de volta para a mesma pasta.
5. Aba **2. Juntar**: clique em **Carregar manifesto**, aponte para o
   `manifesto_*.json` e depois para a pasta com as partes tratadas.
6. Confira o log e clique em **Juntar e salvar**.

## Arquivos

| Arquivo | O que é |
|---|---|
| `dividir_juntar_audio.py` | O programa |
| `abrir-dividir-juntar-audio.command` | Atalho de clique duplo para Mac |
| `requirements.txt` | Sem dependências externas |

## Requisitos

- Python 3 com Tkinter (o Python do site oficial já vem com ele).
- ffmpeg. Se não estiver instalado, o `.command` baixa uma cópia só para este
  programa na primeira execução.

## Atualização automática

Ao abrir, o programa confere sozinho se existe versão nova publicada. Se
existir, ele pergunta **"Atualizar agora?"**. Clicando em Sim, ele baixa a
versão nova, se substitui e reabre já atualizado, sem você precisar entrar no
GitHub nem trocar arquivo nenhum na mão. Clicando em Não, o programa abre
normalmente e pergunta de novo na próxima vez.

Sem internet, nada disso aparece e o programa funciona igual.
