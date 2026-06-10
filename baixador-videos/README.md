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

### Publicar (1 clique)

O executável **não é gerado no seu PC** — ele é compilado na nuvem (o `.app`
do Mac só pode ser montado num Mac). Um único script faz tudo:

**`baixador-videos.bat`** — envia o código, aguarda o build na nuvem terminar e baixa
os executáveis prontos direto para as pastas de distribuição:
- `D:\Softwares\Windows\BaixadorDeVideos.exe`
- `D:\Softwares\Mac\BaixadorDeVideos-mac.zip`

Requisitos (instalar uma vez): **Git** e **GitHub CLI** (`gh`). Após instalar o
`gh`, rode `gh auth login` uma vez.

## Estrutura

```
baixador-videos/
├── baixador_videos.py        # app com a GUI
├── requirements.txt
├── README.md
├── baixador-videos.bat       # envia + builda na nuvem + baixa os executaveis
└── .github/workflows/build.yml
```
