# Extrair Audio de Video

Ferramenta com interface grafica (GUI) para extrair a faixa de audio de um ou
varios videos de uma vez (lote).

## Formatos de saida

- **MP3** — com bitrate ajustavel (96k a 320k).
- **WAV** — PCM 16-bit, sem perdas.
- **M4A / AAC** — com bitrate ajustavel (96k a 320k).

## Como usar

1. Abra o **ExtrairAudio** (`.exe` no Windows, `.app` no Mac).
2. Em **Videos de entrada**, clique em *Adicionar videos...* (varios de uma vez)
   ou *Adicionar pasta...* para varrer uma pasta inteira.
3. Em **Formato de saida**, escolha MP3, WAV ou M4A/AAC e o bitrate.
4. Em **Pasta de destino**, escolha onde salvar os audios.
5. Clique em **Extrair audio**. Acompanhe o progresso por arquivo e por lote.
   Use **Cancelar** a qualquer momento.

Os arquivos de saida usam o nome do video original. Se ja existir um arquivo
com o mesmo nome, um sufixo `(1)`, `(2)`... eh adicionado para nao sobrescrever.

## Requisitos

O **ffmpeg ja vem embutido** no executavel — nao e preciso instalar nada.

Para rodar o codigo direto (em desenvolvimento), e preciso ter Python 3.10+ e o
ffmpeg disponivel no PATH:

```
python extrair_audio.py
```

## Empacotar / distribuir

O build dos executaveis (Windows `.exe` e Mac `.zip`) e feito na nuvem pelo
GitHub Actions. Use o script de um clique:

```
extrair-audio.bat
```

Ele envia o codigo para o repositorio `DiegoVSC42/Softwares`, aguarda o build
terminar e baixa os executaveis para `D:\Softwares\Windows` e `D:\Softwares\Mac`.
Requer **Git** e **GitHub CLI** (`gh`) instalados e logados.
