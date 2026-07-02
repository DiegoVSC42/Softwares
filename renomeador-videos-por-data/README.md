# Renomeador de Vídeos por Data

Uma ferramenta com interface gráfica (GUI) para renomear arquivos de vídeo extraindo a data do sufixo e organizando-os cronologicamente.

## Funcionalidades

- ✅ Extrai datas do sufixo dos arquivos (formato DD-MM-YYYY)
- ✅ Remove o sufixo de data do nome original
- ✅ Adiciona prefixo YYYYMMDD para ordenação cronológica
- ✅ Numera os arquivos sequencialmente (01, 02, 03...)
- ✅ Preview dos renomeamentos antes de executar
- ✅ Cancela operações longas com botão de cancelamento
- ✅ Interface amigável com status em tempo real

## Como usar

1. Execute o arquivo `renomeador_videos.exe` (ou `python renomeador_videos.py`)
2. Clique em "Selecionar Pasta" e escolha a pasta com os vídeos
3. Clique em "Atualizar Preview" para ver como os arquivos serão renomeados
4. Revise os nomes no preview
5. Clique em "Executar Renomeação" para aplicar as mudanças

## Formato de Renomeamento

**Antes:**
```
LIVE - Pré-campanha de vereador_os primeiros passos para a vitória nas urnas_-01-06-2026.mp4
```

**Depois:**
```
2026-01-06-LIVE - Pré-campanha de vereador_os primeiros passos para a vitória nas urnas.mp4
```

- `2026-01-06` = Data em formato ISO 8601 (YYYY-MM-DD)
- `LIVE - Pré-campanha...` = Nome original (sem o sufixo de data)

Os arquivos ficam em **ordem cronológica automática** apenas pelo prefixo de data!

## Requisitos

- Python 3.6+
- Tkinter (incluído na maioria das instalações de Python)

## Arquivos

- `renomeador_videos.py` - Script principal
- `renomeador-videos-por-data.bat` - Executável para Windows
