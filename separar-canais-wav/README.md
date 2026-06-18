# Separar Canais WAV

Separa um arquivo WAV **estereo** — em que uma trilha toca no canal esquerdo e
outra no canal direito — em dois arquivos independentes:

- `nome_esquerda.wav` — apenas a trilha do canal esquerdo (L)
- `nome_direita.wav` — apenas a trilha do canal direito (R)

## Recursos

- **Interface grafica** (Tkinter) — sem digitar comandos.
- **Dois modos**: processar um arquivo unico ou uma pasta inteira (todos os `.wav`).
- **Formato de saida selecionavel**:
  - **Mono (1 canal)** — so a trilha isolada.
  - **Estereo centralizado** — a mesma trilha tocando nos dois lados (L e R).
- Suporta WAV PCM de **8, 16, 24 e 32 bits**.
- Processamento em thread separada, com **barra de progresso** e **Cancelar**.

## Como usar

1. Rode `separar_canais_wav.py` (ou o executavel gerado).
2. Clique em **Selecionar arquivo** ou **Selecionar pasta**.
3. Escolha o **formato de saida** (mono ou estereo centralizado).
4. Defina **onde salvar** (mesma pasta ou outra).
5. Clique em **Separar canais**.

## Requisitos (para rodar o `.py`)

- Python 3.8+
- `numpy` (`pip install -r requirements.txt`)

O Tkinter ja vem com o Python no Windows e no Mac. No executavel gerado pela
nuvem (GitHub Actions), o numpy ja vem embutido.

## Observacao

Funciona com arquivos de **2 canais**. Se o WAV tiver 1 canal (mono) ou mais de
2 canais, o programa avisa e nao processa aquele arquivo.
