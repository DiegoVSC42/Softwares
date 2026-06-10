# Baixador de Vídeos

Aplicativo com interface gráfica (Tkinter) para baixar vídeos usando
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Funciona no **Windows** e no **Mac**.

## Recursos

- Seleção de qualidade: melhor disponível, 1080p, 720p, 480p, 360p.
- Download somente do áudio em **MP3**.
- Suporte a **playlists** (baixa todos os vídeos da lista).
- Escolha da pasta de destino.
- Barra de progresso **com porcentagem**, status, registro e botão **Cancelar**.

No executável final, o **yt-dlp** e o **ffmpeg** já vêm embutidos — o usuário
não precisa instalar nada.

## Rodar a partir do código (desenvolvimento)

Requer Python 3.9+ e o ffmpeg instalado no sistema (apenas para rodar via
código; no executável o ffmpeg é embutido).

```bash
pip install -r requirements.txt
python baixador_videos.py
```

No Windows o ffmpeg pode ser instalado com `winget install ffmpeg`; no Mac,
com `brew install ffmpeg`.

## Gerar os executáveis (Windows .exe e Mac .app)

O build é feito automaticamente na nuvem pelo **GitHub Actions** (arquivo
`.github/workflows/build.yml`), que baixa o ffmpeg de cada sistema e o embute no
executável com o PyInstaller:

- **Windows**: `BaixadorDeVideos.exe` (onefile, sem console).
- **Mac**: `BaixadorDeVideos.app` compactado em `.zip` (`BaixadorDeVideos-mac.zip`).

Para disparar: faça o push do projeto para o repositório no GitHub (use o
`enviar-github.bat`). Ao final do workflow, baixe os artefatos da aba **Actions**.

## Estrutura

```
baixador-videos/
├── baixador_videos.py        # app com a GUI
├── requirements.txt
├── README.md
├── enviar-github.bat         # envio de um clique para o GitHub
└── .github/workflows/build.yml
```
