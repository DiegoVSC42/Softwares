# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/extrair_audio.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

# -*- coding: utf-8 -*-
"""
Extrair Audio de Video - aba do Estudio de Video.

Extrai a faixa de audio de um ou varios videos de uma vez (lote),
nos formatos:
  - MP3 (com bitrate ajustavel)
  - WAV (PCM 16-bit, sem perdas)
  - M4A / AAC (com bitrate ajustavel)

Recursos:
  - selecao de varios arquivos OU de uma pasta inteira;
  - fila de LINKS: endereco de arquivo (Google Drive, Dropbox, OneDrive ou
    link que termina em .mp4/.mov/...) ou endereco de site de video
    (YouTube, Instagram, TikTok...). O programa decide sozinho qual e qual;
  - escolha da pasta de destino (comeca na pasta de Downloads);
  - progresso em tempo real por arquivo e por lote;
  - botao Cancelar (operacao roda em thread separada);
  - log de status.

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.

O motor de download de sites de video (yt-dlp) e o mesmo da aba "Baixar":
este arquivo importa as funcoes de la, em vez de duplicar o codigo.

Esta tela nao cria janela nem define estilo: a janela e o estilo sao do
programa principal (`estudio_video.py` + `tema.py`).
"""

import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from pathlib import Path
from shutil import which
from tkinter import (
    StringVar, END, DISABLED, NORMAL,
    filedialog, messagebox, ttk, scrolledtext,
)

import pastas
import tema
from tema import (
    COR_CAMPO, COR_TEXTO, COR_BORDA, COR_DESTAQUE, COR_BOTAO,
    COR_BOTAO_HOVER,
)

# O motor de download (yt-dlp), o motor de JavaScript e o contexto SSL sao
# os mesmos da aba "Baixar". Importar de la evita duas copias do mesmo
# codigo (e dois lugares para corrigir quando o YouTube mudar de ideia).
# O motor de download mora num modulo proprio, e nao mais na aba "Baixar":
# esta tela aparece tambem no Audio Studio, onde aquela aba nem existe.
from compartilhado import motor_download as motor_video


APP_NAME = "Extrair Audio de Video"
APP_VERSION = "1.1.0"

# Extensoes de video aceitas ao varrer uma pasta
EXTENSOES_VIDEO = {
    ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ts", ".m2ts",
}

# Extensoes de audio que tambem servem de entrada (um link pode devolver um
# arquivo de som puro; o ffmpeg converte do mesmo jeito).
EXTENSOES_AUDIO = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
}

EXTENSOES_MIDIA = EXTENSOES_VIDEO | EXTENSOES_AUDIO

# Formatos de saida -> rotulo amigavel
FORMATO_MP3 = "MP3 (com bitrate)"
FORMATO_WAV = "WAV (sem perdas)"
FORMATO_M4A = "M4A / AAC (com bitrate)"
FORMATOS = [FORMATO_MP3, FORMATO_WAV, FORMATO_M4A]

BITRATES = ["96k", "128k", "192k", "256k", "320k"]


# ---------------------------------------------------------------------------
# Localizacao do ffmpeg embutido
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def find_ffmpeg() -> str | None:
    """Retorna o caminho do executavel ffmpeg, ou None se nao encontrado.

    Procura, nesta ordem:
      1. ffmpeg embutido junto ao executavel (via PyInstaller --add-binary)
      2. ffmpeg disponivel no PATH do sistema
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"

    candidates = [
        resource_path(exe),
        resource_path(os.path.join("ffmpeg", exe)),
        resource_path(os.path.join("bin", exe)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    found = which("ffmpeg")
    if found:
        return found

    return None


# ---------------------------------------------------------------------------
# Helpers de parsing de tempo do ffmpeg
# ---------------------------------------------------------------------------
RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
RE_TEMPO = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def _hms_para_seg(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


# ---------------------------------------------------------------------------
# Links: descobrir de que tipo e o endereco colado
# ---------------------------------------------------------------------------
NAVEGADOR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Servicos que guardam ARQUIVO: o endereco aponta para um arquivo salvo, e o
# jeito de pegar e baixar direto (sem motor de video).
DOMINIOS_ARQUIVO = (
    "drive.google.com", "docs.google.com", "drive.usercontent.google.com",
    "dropbox.com", "dropboxusercontent.com",
    "1drv.ms", "onedrive.live.com", "sharepoint.com",
    "we.tl", "wetransfer.com",
)

# Sites de VIDEO: a pagina nao e o arquivo; quem sabe achar o arquivo la
# dentro e o motor de download (yt-dlp).
DOMINIOS_VIDEO = (
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "facebook.com", "fb.watch", "twitter.com", "x.com", "vimeo.com",
    "twitch.tv", "dailymotion.com", "kwai.com", "linkedin.com",
    "reddit.com", "threads.net", "bilibili.com", "soundcloud.com",
    "globoplay.globo.com", "rumble.com", "odysee.com",
)


def id_do_google_drive(url: str) -> str | None:
    """Extrai o identificador do arquivo num link do Google Drive."""
    for padrao in (r"/file/d/([A-Za-z0-9_-]{10,})",
                   r"[?&]id=([A-Za-z0-9_-]{10,})",
                   r"/d/([A-Za-z0-9_-]{10,})"):
        achou = re.search(padrao, url)
        if achou:
            return achou.group(1)
    return None


def normalizar_link(url: str) -> str:
    """Transforma links de compartilhamento em links de download direto."""
    url = url.strip()
    baixo = url.lower()

    if "drive.google.com" in baixo or "docs.google.com" in baixo:
        ident = id_do_google_drive(url)
        if ident:
            return ("https://drive.usercontent.google.com/download"
                    "?id=%s&export=download&confirm=t" % ident)

    if "dropbox.com" in baixo:
        base = url.split("?")[0]
        return base + "?dl=1"

    if "1drv.ms" in baixo or "onedrive.live.com" in baixo:
        return url

    return url


def _servidor(url: str) -> str:
    """Nome do servidor do endereco, em minusculas ('www.youtube.com')."""
    try:
        alvo = url if "://" in url else "http://" + url
        return (urllib.parse.urlparse(alvo).hostname or "").lower()
    except Exception:
        return ""


def _dominio_bate(servidor: str, dominios) -> bool:
    """True se o servidor for um dos dominios da lista (ou subdominio dele).

    Compara pelo NOME do servidor, e nao por "esta escrito no meio do
    endereco". Sem esse cuidado, 'dropbox.com' casava com 'x.com' (o site do
    Twitter) e o programa mandava um arquivo do Dropbox para o motor de
    video, que nao sabe o que fazer com ele.
    """
    return any(servidor == d or servidor.endswith("." + d) for d in dominios)


def parece_arquivo_direto(url: str) -> bool:
    """True quando o endereco aponta para um ARQUIVO que da para baixar direto."""
    if _dominio_bate(_servidor(url), DOMINIOS_ARQUIVO):
        return True
    caminho = urllib.parse.urlparse(url.lower()).path
    return os.path.splitext(caminho)[1] in EXTENSOES_MIDIA


def parece_site_video(url: str) -> bool:
    """True quando o endereco e de um site de video (YouTube, TikTok...)."""
    return _dominio_bate(_servidor(url), DOMINIOS_VIDEO)


def _nome_do_cabecalho(resposta, url: str) -> str:
    """Descobre o nome do arquivo pelo cabecalho ou pela propria URL."""
    disp = resposta.headers.get("Content-Disposition", "") or ""
    achou = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disp)
    if achou:
        nome = urllib.parse.unquote(achou.group(1)).strip()
        if nome:
            return os.path.basename(nome)

    caminho = urllib.parse.urlparse(url).path
    nome = os.path.basename(urllib.parse.unquote(caminho))
    if nome and "." in nome:
        return nome

    tipo = (resposta.headers.get("Content-Type", "") or "").split(";")[0].strip()
    ext = {
        "video/mp4": ".mp4", "video/quicktime": ".mov",
        "video/x-matroska": ".mkv", "video/webm": ".webm",
        "video/x-msvideo": ".avi", "video/mpeg": ".mpeg",
        "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/ogg": ".ogg",
        "audio/flac": ".flac",
    }.get(tipo, ".mp4")
    return "video-baixado" + ext


def _caminho_livre(pasta: str, nome: str) -> str:
    """Devolve um caminho que ainda nao existe dentro de `pasta`."""
    os.makedirs(pasta, exist_ok=True)
    nome = re.sub(r'[\\/:*?"<>|]', "-", nome).strip() or "arquivo"
    caminho = os.path.join(pasta, nome)
    base, ext = os.path.splitext(caminho)
    contador = 2
    while os.path.exists(caminho):
        caminho = "%s (%d)%s" % (base, contador, ext)
        contador += 1
    return caminho


def _gravar_resposta(resposta, cabeca: bytes, caminho: str, cancelou) -> None:
    """Grava o corpo da resposta em disco, em pedacos, olhando o Cancelar.

    Grava direto no arquivo (e nao na memoria) porque aqui os arquivos sao
    videos: guardar um filme inteiro na memoria antes de salvar derrubaria
    o programa.
    """
    with open(caminho, "wb") as arq:
        if cabeca:
            arq.write(cabeca)
        while True:
            if cancelou():
                raise InterruptedError
            pedaco = resposta.read(262144)
            if not pedaco:
                break
            arq.write(pedaco)


def baixar_arquivo_direto(url: str, destino_pasta: str, avisar, cancelou) -> str:
    """Baixa um arquivo de video/audio de um link e devolve o caminho salvo.

    Serve para Google Drive, Dropbox, OneDrive e qualquer endereco que aponte
    para o proprio arquivo. Nao serve para pagina de site de video: para isso
    existe `baixar_por_motor`.
    """
    direto = normalizar_link(url)
    contexto = motor_video._contexto_ssl()
    pedido = urllib.request.Request(direto, headers={
        "User-Agent": NAVEGADOR,
        "Accept": "video/*,audio/*,*/*;q=0.8",
    })

    with urllib.request.urlopen(pedido, timeout=60, context=contexto) as resp:
        tipo = (resp.headers.get("Content-Type", "") or "").lower()
        nome = _nome_do_cabecalho(resp, direto)
        cabeca = resp.read(65536)

        if "text/html" not in tipo:
            caminho = _caminho_livre(destino_pasta, nome)
            _gravar_resposta(resp, cabeca, caminho, cancelou)
            avisar("Baixado: %s" % os.path.basename(caminho))
            return caminho

        pagina = cabeca.decode("utf-8", "ignore")

    # Chegou HTML no lugar do arquivo. No Google Drive isso e a pagina de
    # confirmacao que aparece com arquivo grande: dali sai o link de verdade.
    if "drive.usercontent.google.com" in direto or "drive.google.com" in direto:
        achou = re.search(r'name="confirm"\s+value="([^"]+)"', pagina)
        uuid = re.search(r'name="uuid"\s+value="([^"]+)"', pagina)
        if achou or uuid:
            extra = direto
            if achou:
                extra = re.sub(r"confirm=[^&]*", "confirm=" + achou.group(1), extra)
            if uuid:
                extra += "&uuid=" + uuid.group(1)
            pedido2 = urllib.request.Request(
                extra, headers={"User-Agent": NAVEGADOR})
            with urllib.request.urlopen(pedido2, timeout=120,
                                        context=contexto) as resp2:
                nome = _nome_do_cabecalho(resp2, extra)
                caminho = _caminho_livre(destino_pasta, nome)
                _gravar_resposta(resp2, b"", caminho, cancelou)
            avisar("Baixado: %s" % os.path.basename(caminho))
            return caminho
        raise RuntimeError(
            "o link do Google Drive nao esta publico. Abra o arquivo no "
            "Drive, clique em Compartilhar e deixe como 'Qualquer pessoa "
            "com o link'.")

    raise RuntimeError("o link devolveu uma pagina, nao um arquivo de video.")


# Marcas usadas para separar, na saida do yt-dlp, o que e progresso e o que e
# o caminho do arquivo pronto. Mesma ideia da aba "Baixar".
MARCA_PROG = "@@P@@"
MARCA_ARQ = "@@F@@"


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class ExtrairAudioGUI:
    NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def __init__(self, pai, foco: str = "video") -> None:
        # `pai` e o quadro daquela aba. O resto do codigo continua chamando
        # `self.root`, para nao trocar o nome em todas as linhas.
        self.root = pai
        self.foco = foco

        self.fonte_base, self.fonte_peq = tema.fontes()

        # Estado
        self.arquivos: list[Path] = []
        self.links: list[str] = []
        self.pasta_saida = StringVar(value=pastas.pasta_downloads())
        self.formato = StringVar(value=FORMATO_MP3)
        self.bitrate = StringVar(value="192k")
        self.link_novo = StringVar(value="")

        self.fila: queue.Queue = queue.Queue()
        self.processo: subprocess.Popen | None = None
        self.cancelar = False
        self.rodando = False
        self.ultimo_destino: Path | None = None

        self.ffmpeg = find_ffmpeg()

        self._montar_ui()
        self._verificar_ffmpeg()
        self.root.after(100, self._processar_fila)

    # -------------------------------------------------------------- dialogos
    def _janela(self):
        """Janela de verdade por tras da aba, para ancorar os dialogos."""
        return self.root.winfo_toplevel()

    # ------------------------------------------------------------------ UI
    def _montar_ui(self) -> None:
        # Espacamento enxuto entre os quadros: a aba precisa caber inteira na
        # janela, sem barra de rolagem, mas ainda com respiro entre eles.
        pad = {"padx": 8, "pady": 3}

        # A ordem de empacotamento importa: tudo que e ancorado embaixo entra
        # PRIMEIRO, para nunca sair da tela quando a janela e baixa. Quem cede
        # espaco e a area de entrada (as listas), que vem por ultimo com
        # expand=True.

        # --- Progresso e log (bem no fundo da aba) ---
        frm_prog = ttk.LabelFrame(self.root, text=" Progresso ")
        frm_prog.pack(side="bottom", fill="x", **pad)

        self.lbl_atual = ttk.Label(frm_prog, text="Pronto.")
        self.lbl_atual.pack(fill="x", padx=6, pady=(6, 0))
        self.prog_arquivo = ttk.Progressbar(frm_prog, mode="determinate",
                                            style="Horizontal.TProgressbar",
                                            maximum=100)
        self.prog_arquivo.pack(fill="x", padx=6, pady=2)

        self.lbl_lote = ttk.Label(frm_prog, text="Lote: 0/0")
        self.lbl_lote.pack(fill="x", padx=6)
        self.prog_lote = ttk.Progressbar(frm_prog, mode="determinate",
                                         style="Horizontal.TProgressbar",
                                         maximum=100)
        self.prog_lote.pack(fill="x", padx=6, pady=2)

        # ScrolledText e Tk puro: a cor vai na mao, senao nasce branco.
        self.log = scrolledtext.ScrolledText(
            frm_prog, height=5, state=DISABLED,
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightcolor=COR_BORDA,
            relief="flat", borderwidth=0, wrap="word", font=self.fonte_peq)
        self.log.pack(fill="x", padx=6, pady=(4, 5))
        # A barra de rolagem do registro tambem e Tk puro.
        try:
            self.log.vbar.configure(bg=COR_BOTAO, troughcolor=COR_CAMPO,
                                    activebackground=COR_BOTAO_HOVER,
                                    highlightthickness=0, bd=0)
        except Exception:
            pass

        # --- Acao ---
        frm_acao = ttk.Frame(self.root)
        frm_acao.pack(side="bottom", fill="x", **pad)
        self.btn_extrair = ttk.Button(frm_acao, text="Extrair audio",
                                      style="Acao.TButton",
                                      command=self._iniciar)
        self.btn_extrair.pack(side="left")
        self.btn_cancelar = ttk.Button(frm_acao, text="Cancelar",
                                       command=self._cancelar, state=DISABLED)
        self.btn_cancelar.pack(side="left", padx=6)
        ttk.Button(frm_acao, text="Abrir pasta de destino",
                   command=self._abrir_pasta).pack(side="left", padx=6)

        # --- Destino ---
        frm_dest = ttk.LabelFrame(self.root, text=" Pasta de destino ")
        frm_dest.pack(side="bottom", fill="x", **pad)
        linha_d = ttk.Frame(frm_dest)
        linha_d.pack(fill="x", padx=6, pady=6)
        ttk.Entry(linha_d, textvariable=self.pasta_saida).pack(
            side="left", fill="x", expand=True)
        ttk.Button(linha_d, text="Escolher...",
                   command=self._escolher_destino).pack(side="left", padx=(6, 0))

        # --- Opcoes ---
        frm_opt = ttk.LabelFrame(self.root, text=" Formato de saida ")
        frm_opt.pack(side="bottom", fill="x", **pad)

        linha = ttk.Frame(frm_opt)
        linha.pack(fill="x", padx=6, pady=6)
        ttk.Label(linha, text="Formato:").pack(side="left")
        cb_fmt = ttk.Combobox(linha, textvariable=self.formato, values=FORMATOS,
                              state="readonly", width=22)
        cb_fmt.pack(side="left", padx=(4, 16))

        self.lbl_bitrate = ttk.Label(linha, text="Bitrate:")
        self.lbl_bitrate.pack(side="left")
        self.cb_bitrate = ttk.Combobox(linha, textvariable=self.bitrate, values=BITRATES,
                                       state="readonly", width=8)
        self.cb_bitrate.pack(side="left", padx=4)

        # A reacao fica presa na variavel, e nao no evento do combo: assim ela
        # dispara tambem quando o formato e trocado por codigo.
        self.formato.trace_add("write", lambda *a: self._on_formato())
        self._on_formato()

        # --- Entrada: videos do computador (esquerda) e links (direita) ---
        frm_ent = ttk.LabelFrame(self.root, text=" Videos de entrada ")
        frm_ent.pack(side="top", fill="both", expand=True, **pad)

        colunas = ttk.Frame(frm_ent)
        colunas.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        colunas.columnconfigure(0, weight=1, uniform="entrada")
        colunas.columnconfigure(1, weight=1, uniform="entrada")
        colunas.rowconfigure(0, weight=1)

        esq = ttk.Frame(colunas)
        esq.grid(row=0, column=0, sticky="nsew")
        dir_ = ttk.Frame(colunas)
        dir_.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._bloco_lista(esq)
        self._bloco_link(dir_)

    def _lista_pintada(self, pai, altura: int):
        """Cria uma Listbox com barra de rolagem, ja pintada na mao.

        Listbox e Scrollbar sao Tk puro: nao seguem o estilo ttk, entao cada
        cor precisa ser dita aqui, senao nascem brancas no modo escuro do Mac.
        """
        moldura = tk.Frame(pai, bg=COR_BORDA, bd=0, highlightthickness=0)
        moldura.pack(fill="both", expand=True, pady=(6, 0))
        lista = tk.Listbox(
            moldura, height=altura, activestyle="none", selectmode="extended",
            bg=COR_CAMPO, fg=COR_TEXTO, font=self.fonte_peq,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightthickness=0,
            relief="flat", bd=0)
        rolo = tk.Scrollbar(moldura, command=lista.yview,
                            bg=COR_BOTAO, troughcolor=COR_CAMPO,
                            activebackground=COR_BOTAO_HOVER,
                            highlightthickness=0, bd=0)
        lista.configure(yscrollcommand=rolo.set)
        rolo.pack(side="right", fill="y")
        lista.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        return lista

    def _bloco_lista(self, pai) -> None:
        """Coluna da esquerda: os videos que ja estao no computador."""
        cx = ttk.Labelframe(pai, text="Vídeos", padding=(8, 6))
        cx.pack(fill="both", expand=True)

        barra = ttk.Frame(cx)
        barra.pack(fill="x")
        ttk.Button(barra, text="Adicionar vídeos",
                   command=self._add_arquivos).pack(side="left")
        ttk.Button(barra, text="Adicionar pasta",
                   command=self._add_pasta).pack(side="left", padx=6)

        # Quatro linhas ja dao uma boa visao da fila, e a lista rola sozinha
        # quando tem mais. Assim a aba inteira cabe na janela.
        self.lista = self._lista_pintada(cx, altura=4)

        botoes = ttk.Frame(cx)
        botoes.pack(fill="x", pady=(6, 0))
        ttk.Button(botoes, text="Remover selecionado",
                   command=self._remover_selecionado).pack(side="left")
        ttk.Button(botoes, text="Limpar lista",
                   command=self._limpar).pack(side="left", padx=6)
        self.rotulo_lista = ttk.Label(botoes, text="Nenhum vídeo na fila.",
                                      style="Suave.TLabel")
        self.rotulo_lista.pack(side="right")

    def _bloco_link(self, pai) -> None:
        """Coluna da direita: os links a baixar antes de extrair o audio."""
        cx = ttk.Labelframe(pai, text="Links", padding=(8, 6))
        cx.pack(fill="both", expand=True)

        linha = ttk.Frame(cx)
        linha.pack(fill="x")
        self.campo_link = ttk.Entry(linha, textvariable=self.link_novo)
        self.campo_link.pack(side="left", fill="x", expand=True)
        self.campo_link.bind("<Return>", lambda e: self._add_link())
        ttk.Button(linha, text="+  Adicionar",
                   command=self._add_link).pack(side="left", padx=(6, 0))

        # Mesma altura da lista de videos, para as duas colunas ficarem iguais.
        self.lista_links = self._lista_pintada(cx, altura=4)

        botoes = ttk.Frame(cx)
        botoes.pack(fill="x", pady=(6, 0))
        ttk.Button(botoes, text="Remover selecionado",
                   command=self._remover_link).pack(side="left")
        ttk.Button(botoes, text="Limpar links",
                   command=self._limpar_links).pack(side="left", padx=6)
        self.rotulo_links = ttk.Label(botoes, text="Nenhum link na fila.",
                                      style="Suave.TLabel")
        self.rotulo_links.pack(side="right")

    # ------------------------------------------------------- ffmpeg check
    def _verificar_ffmpeg(self) -> None:
        if not self.ffmpeg:
            self._logar("AVISO: ffmpeg nao encontrado. No executavel final ele "
                        "vem embutido. Em desenvolvimento, instale o ffmpeg e "
                        "coloque-o no PATH.")
            self.btn_extrair.config(state=DISABLED)
        else:
            self._logar(f"ffmpeg: {self.ffmpeg}")

    # --------------------------------------------------------- callbacks
    def _on_formato(self) -> None:
        wav = self.formato.get() == FORMATO_WAV
        estado = DISABLED if wav else NORMAL
        self.cb_bitrate.config(state="disabled" if wav else "readonly")
        self.lbl_bitrate.config(state=estado)

    def _add_arquivos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecione os videos",
            filetypes=[("Videos", "*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm "
                                   "*.m4v *.mpg *.mpeg *.3gp *.ts *.m2ts"),
                       ("Todos os arquivos", "*.*")],
            parent=self._janela(),
        )
        for p in paths:
            self._adicionar(Path(p))

    def _add_pasta(self) -> None:
        d = filedialog.askdirectory(title="Selecione a pasta com videos",
                                    parent=self._janela())
        if not d:
            return
        encontrados = 0
        for p in sorted(Path(d).iterdir()):
            if p.is_file() and p.suffix.lower() in EXTENSOES_VIDEO:
                if self._adicionar(p):
                    encontrados += 1
        self._logar(f"Pasta varrida: {encontrados} video(s) adicionado(s).")

    def _adicionar(self, p: Path) -> bool:
        if p in self.arquivos:
            return False
        self.arquivos.append(p)
        self.lista.insert(END, p.name)
        self._atualizar_rotulo_lista()
        return True

    def _remover_selecionado(self) -> None:
        for i in sorted(self.lista.curselection(), reverse=True):
            self.lista.delete(i)
            del self.arquivos[i]
        self._atualizar_rotulo_lista()

    def _limpar(self) -> None:
        self.arquivos.clear()
        self.lista.delete(0, END)
        self._atualizar_rotulo_lista()

    def _atualizar_rotulo_lista(self) -> None:
        n = len(self.arquivos)
        if n == 0:
            texto = "Nenhum vídeo na fila."
        elif n == 1:
            texto = "1 vídeo na fila."
        else:
            texto = "%d vídeos na fila." % n
        self.rotulo_lista.configure(text=texto)

    # ------------------------------------------------------------- links
    def _add_link(self) -> None:
        """Coloca na fila o link (ou os links) escritos no campo."""
        texto = self.link_novo.get().strip()
        candidatos = [p for p in texto.replace(",", " ").split() if p]
        validos = [p for p in candidatos if p.lower().startswith("http")]
        if not validos:
            messagebox.showwarning(
                APP_NAME,
                "Cole um endereco que comece com http, por exemplo o link de "
                "um video do YouTube ou de um arquivo no Google Drive.",
                parent=self._janela())
            return
        for url in validos:
            if url not in self.links:
                self.links.append(url)
        self.link_novo.set("")
        self.campo_link.focus_set()
        self._redesenhar_links()

    def _remover_link(self) -> None:
        for i in sorted(self.lista_links.curselection(), reverse=True):
            del self.links[i]
        self._redesenhar_links()

    def _limpar_links(self) -> None:
        self.links = []
        self._redesenhar_links()

    def _redesenhar_links(self) -> None:
        self.lista_links.delete(0, END)
        for i, url in enumerate(self.links, start=1):
            self.lista_links.insert(END, "%d.  %s" % (i, url))
        n = len(self.links)
        if n == 0:
            texto = "Nenhum link na fila."
        elif n == 1:
            texto = "1 link na fila."
        else:
            texto = "%d links na fila." % n
        self.rotulo_links.configure(text=texto)

    def _escolher_destino(self) -> None:
        d = filedialog.askdirectory(title="Pasta de destino",
                                    parent=self._janela())
        if d:
            self.pasta_saida.set(d)

    # ------------------------------------------------------------ extrair
    def _iniciar(self) -> None:
        if self.rodando:
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado.",
                                 parent=self._janela())
            return

        # Se a pessoa digitou um link e clicou direto em Extrair, aproveita.
        if self.link_novo.get().strip():
            self._add_link()

        if not self.arquivos and not self.links:
            messagebox.showwarning(APP_NAME,
                                   "Adicione pelo menos um video ou um link.",
                                   parent=self._janela())
            return

        destino = Path(pastas.garantir(self.pasta_saida.get().strip()
                                       or pastas.pasta_downloads()))
        if not destino.is_dir():
            messagebox.showerror(APP_NAME,
                                 "Nao foi possivel criar a pasta de destino.",
                                 parent=self._janela())
            return

        self.ultimo_destino = destino
        self.cancelar = False
        self.rodando = True
        self.btn_extrair.config(state=DISABLED)
        self.btn_cancelar.config(state=NORMAL)
        self.prog_lote.config(value=0)
        self.prog_arquivo.config(value=0)

        t = threading.Thread(target=self._worker,
                             args=(list(self.arquivos), list(self.links),
                                   destino, self.formato.get(),
                                   self.bitrate.get()),
                             daemon=True)
        t.start()

    def _abrir_pasta(self) -> None:
        """Abre a pasta de destino no explorador de arquivos do sistema."""
        destino = self.ultimo_destino or Path(self.pasta_saida.get().strip() or ".")
        if not destino.exists():
            messagebox.showinfo(APP_NAME, "A pasta de destino ainda nao existe.",
                                parent=self._janela())
            return
        try:
            if os.name == "nt":
                os.startfile(str(destino))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(destino)])
            else:
                subprocess.Popen(["xdg-open", str(destino)])
        except Exception as e:
            messagebox.showwarning(APP_NAME, f"Nao foi possivel abrir a pasta:\n{e}",
                                   parent=self._janela())

    def _cancelar(self) -> None:
        self.cancelar = True
        if self.processo and self.processo.poll() is None:
            try:
                self.processo.terminate()
            except Exception:
                pass
        self.fila.put(("log", "Cancelando..."))

    def _comando(self, entrada: Path, saida: Path, formato: str, bitrate: str) -> list[str]:
        cmd = [self.ffmpeg, "-y", "-hide_banner", "-i", str(entrada), "-vn"]
        if formato == FORMATO_MP3:
            cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
        elif formato == FORMATO_WAV:
            cmd += ["-c:a", "pcm_s16le"]
        else:  # M4A / AAC
            cmd += ["-c:a", "aac", "-b:a", bitrate]
        cmd.append(str(saida))
        return cmd

    def _extensao(self, formato: str) -> str:
        return {FORMATO_MP3: ".mp3", FORMATO_WAV: ".wav", FORMATO_M4A: ".m4a"}[formato]

    # ------------------------------------------------------- baixar links
    def _cancelou(self) -> bool:
        return self.cancelar

    def _baixar_por_motor(self, url: str, destino_pasta: str) -> str:
        """Baixa so a faixa de audio de um site de video, com o yt-dlp.

        Pedir so o audio (`-f ba`) evita trazer o filme inteiro para depois
        jogar a imagem fora. O arquivo vem no formato original do site
        (m4a, webm...); quem converte para MP3/WAV/M4A e o ffmpeg, depois.
        """
        if not motor_video.motor_instalado():
            self.fila.put(("log", "Preparando o motor de download "
                                  "(primeira vez)..."))
            motor_video.baixar_motor()

        js = motor_video.localizar_js()
        if not js:
            try:
                motor_video.baixar_js()
                js = motor_video.localizar_js()
            except Exception as e:
                self.fila.put(("log", f"  Aviso: motor de JavaScript nao "
                                      f"instalado ({e})."))

        modelo = os.path.join(destino_pasta, "%(title).120s.%(ext)s")
        cmd = [
            motor_video.caminho_motor(),
            "--ignore-config", "--newline", "--no-colors", "--no-simulate",
            "--progress", "--no-playlist",
            "--retries", "5", "--fragment-retries", "5",
            "--progress-template",
            "download:" + MARCA_PROG + "%(progress._percent_str)s",
            "--print", "after_move:" + MARCA_ARQ + "%(filepath)s",
            "-f", "ba/bestaudio/best",
            "-o", modelo,
        ]

        ffmpeg_dir = motor_video.find_ffmpeg_dir()
        if ffmpeg_dir:
            cmd += ["--ffmpeg-location", ffmpeg_dir]
        if js:
            cmd += ["--js-runtimes", f"{js[0]}:{js[1]}"]
        cmd += ["--extractor-args", motor_video.CLIENTE_YOUTUBE]
        cmd.append(url)

        caminho = None
        linhas: list[str] = []
        self.processo = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, universal_newlines=True, encoding="utf-8",
            errors="replace", creationflags=self.NO_WINDOW,
        )
        for linha in self.processo.stdout:
            linha = linha.rstrip("\r\n")
            if not linha:
                continue
            if linha.startswith(MARCA_PROG):
                m = re.search(r"([\d.]+)%", linha)
                if m:
                    try:
                        self.fila.put(("arquivo", float(m.group(1))))
                    except ValueError:
                        pass
            elif linha.startswith(MARCA_ARQ):
                caminho = linha[len(MARCA_ARQ):].strip()
            else:
                linhas.append(linha)
                if len(linhas) > 12:
                    linhas.pop(0)

        self.processo.wait()
        codigo = self.processo.returncode
        self.processo = None

        if self.cancelar:
            raise InterruptedError
        if codigo != 0 or not caminho or not os.path.isfile(caminho):
            erros = [l for l in linhas if l.startswith("ERROR")]
            detalhe = erros[-1] if erros else (linhas[-1] if linhas
                                               else f"codigo {codigo}")
            raise RuntimeError(detalhe[:200])
        return caminho

    def _baixar_link(self, url: str, destino_pasta: str) -> str:
        """Baixa um link, escolhendo sozinho entre arquivo direto e motor.

        Quando nao da para decidir pelo endereco, tenta primeiro como arquivo
        direto e, se falhar, tenta de novo pelo motor de video.
        """
        avisar = lambda m: self.fila.put(("log", "  " + m))

        if parece_site_video(url):
            ordem = ("motor", "direto")
        elif parece_arquivo_direto(url):
            ordem = ("direto", "motor")
        else:
            ordem = ("direto", "motor")

        erro_primeiro = None
        for tentativa in ordem:
            if self.cancelar:
                raise InterruptedError
            try:
                if tentativa == "direto":
                    return baixar_arquivo_direto(url, destino_pasta, avisar,
                                                 self._cancelou)
                caminho = self._baixar_por_motor(url, destino_pasta)
                avisar("Baixado: %s" % os.path.basename(caminho))
                return caminho
            except InterruptedError:
                raise
            except Exception as e:
                if erro_primeiro is None:
                    erro_primeiro = e
                    self.fila.put(("log", f"  Primeira tentativa falhou ({e}). "
                                          f"Tentando pelo outro caminho..."))
                else:
                    raise RuntimeError(f"{erro_primeiro} / {e}")
        raise RuntimeError(str(erro_primeiro or "falha desconhecida"))

    # ----------------------------------------------------------- trabalho
    def _worker(self, arquivos: list[Path], links: list[str], destino: Path,
                formato: str, bitrate: str) -> None:
        temporaria = None
        baixados_ok: list[str] = []
        falhas_link = 0

        try:
            # ---- 1) Baixar os links, um a um, antes de processar ----
            if links and not self.cancelar:
                temporaria = tempfile.mkdtemp(prefix="estudio-audio-")
                total_links = len(links)
                self.fila.put(("lote", (0, total_links)))
                for i, url in enumerate(links, start=1):
                    if self.cancelar:
                        break
                    self.fila.put(("atual", f"Baixando {i} de {total_links}..."))
                    self.fila.put(("arquivo", 0))
                    self.fila.put(("log", f"Baixando: {url}"))
                    try:
                        caminho = self._baixar_link(url, temporaria)
                        arquivos.append(Path(caminho))
                        baixados_ok.append(url)
                    except InterruptedError:
                        break
                    except Exception as e:
                        # Um link ruim nao pode derrubar o lote inteiro.
                        falhas_link += 1
                        self.fila.put(("log", f"  FALHA no link: {e}"))
                    self.fila.put(("lote", (i, total_links)))

                if baixados_ok:
                    self.fila.put(("links_prontos", baixados_ok))

            # ---- 2) Extrair o audio de tudo que estiver na fila ----
            total = len(arquivos)
            ok = 0
            falhas = falhas_link
            ext = self._extensao(formato)

            if total:
                self.fila.put(("lote", (0, total)))

            for i, entrada in enumerate(arquivos, start=1):
                if self.cancelar:
                    break

                saida = destino / (entrada.stem + ext)
                n = 1
                while saida.exists():
                    saida = destino / f"{entrada.stem} ({n}){ext}"
                    n += 1

                self.fila.put(("atual", f"[{i}/{total}] {entrada.name}"))
                self.fila.put(("arquivo", 0))
                self.fila.put(("log", f"Extraindo: {entrada.name} -> {saida.name}"))

                try:
                    erro = self._rodar_ffmpeg(
                        self._comando(entrada, saida, formato, bitrate))
                except Exception as e:
                    erro = str(e)

                if self.cancelar:
                    if saida.exists():
                        try:
                            saida.unlink()
                        except OSError:
                            pass
                    break

                if erro is None:
                    ok += 1
                    self.fila.put(("log", f"  OK: {saida.name}"))
                else:
                    falhas += 1
                    self.fila.put(("log", f"  FALHA: {entrada.name} ({erro})"))

                self.fila.put(("lote", (i, total)))

            self.fila.put(("fim", (ok, falhas, self.cancelar)))
        finally:
            # Os arquivos baixados eram so materia-prima: o audio ja foi para
            # a pasta de destino, entao a pasta temporaria pode ir embora.
            if temporaria:
                shutil.rmtree(temporaria, ignore_errors=True)

    def _rodar_ffmpeg(self, cmd: list[str]) -> str | None:
        """Roda o ffmpeg, atualiza o progresso e retorna None se sucesso
        ou uma mensagem de erro curta em caso de falha."""
        self.processo = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            creationflags=self.NO_WINDOW,
        )

        duracao = None
        ultimas = []
        for linha in self.processo.stderr:
            ultimas.append(linha)
            if len(ultimas) > 12:
                ultimas.pop(0)

            if duracao is None:
                m = RE_DURACAO.search(linha)
                if m:
                    duracao = _hms_para_seg(*m.groups())

            m = RE_TEMPO.search(linha)
            if m and duracao:
                atual = _hms_para_seg(*m.groups())
                pct = max(0, min(100, atual / duracao * 100))
                self.fila.put(("arquivo", pct))

        self.processo.wait()
        codigo = self.processo.returncode
        self.processo = None

        if codigo == 0:
            self.fila.put(("arquivo", 100))
            return None

        if self.cancelar:
            return "cancelado"

        texto = "".join(ultimas).strip().replace("\n", " ")
        return texto[-160:] if texto else f"codigo {codigo}"

    # ------------------------------------------------------- fila / log
    def _processar_fila(self) -> None:
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "atual":
                    self.lbl_atual.config(text=dado)
                elif tipo == "arquivo":
                    self.prog_arquivo.config(value=dado)
                elif tipo == "lote":
                    i, total = dado
                    self.lbl_lote.config(text=f"Lote: {i}/{total}")
                    self.prog_lote.config(
                        value=(i / total * 100) if total else 0)
                elif tipo == "log":
                    self._logar(dado)
                elif tipo == "links_prontos":
                    # Sem isso o link continuaria na fila e o proximo clique
                    # baixaria tudo de novo, sem fim.
                    self.links = [u for u in self.links if u not in dado]
                    self._redesenhar_links()
                elif tipo == "fim":
                    self._finalizar(*dado)
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def _finalizar(self, ok: int, falhas: int, cancelado: bool) -> None:
        self.rodando = False
        self.btn_extrair.config(state=NORMAL)
        self.btn_cancelar.config(state=DISABLED)
        if cancelado:
            self.lbl_atual.config(text="Cancelado.")
            self._logar(f"Cancelado. Concluidos: {ok}, falhas: {falhas}.")
        else:
            self.lbl_atual.config(text="Concluido.")
            self.prog_arquivo.config(value=100)
            self.prog_lote.config(value=100)
            self._logar(f"Concluido. Sucesso: {ok}, falhas: {falhas}.")
            if ok > 0:
                self._abrir_pasta()
            messagebox.showinfo(APP_NAME,
                                f"Extracao concluida.\nSucesso: {ok}\nFalhas: {falhas}",
                                parent=self._janela())

    def _logar(self, msg: str) -> None:
        self.log.config(state=NORMAL)
        self.log.insert(END, msg + "\n")
        self.log.see(END)
        self.log.config(state=DISABLED)

    # -------------------------------------------------------- fechamento
    def ao_fechar(self) -> None:
        """Limpeza pedida pelo programa principal na hora de fechar.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se marca o cancelamento e
        se derruba o processo que ainda estiver rodando (ffmpeg ou motor de
        download), para nao ficar um processo orfao comendo a maquina.
        Nenhuma janela e destruida.
        """
        self.cancelar = True
        self.rodando = False
        p = self.processo
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


def montar(pai, foco="video"):
    """Desenha a aba de extrair audio dentro de `pai`.

    `foco` diz em qual estudio a aba esta ("video" ou "audio"). Ele nao muda o
    que a aba faz: ela sempre tira o audio de arquivos de video. Serve so para
    o dialogo de escolha de arquivo abrir com o filtro mais provavel na
    frente, poupando um clique.
    """
    return ExtrairAudioGUI(pai, foco=foco)
