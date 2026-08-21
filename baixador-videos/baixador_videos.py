#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baixador de Vídeos — interface gráfica (Tkinter) para baixar vídeos.

Recursos:
  - Seleção de qualidade (melhor, 1080p, 720p, 480p, 360p)
  - Nome do arquivo de saída personalizado (opcional; vazio = título do vídeo)
  - Download somente do áudio em MP3
  - Corte por tempo (início e/ou fim): baixa o vídeo completo e recorta o
    trecho pedido logo em seguida, sem recodificar
  - Suporte a playlists (baixar todos os vídeos da lista)
  - Remoção de TODOS os metadados do arquivo final (título, autor, capa,
    capítulos, data de gravação, tag de codificador, data do arquivo)
  - Limpeza de metadados de arquivos que já estão no computador
  - Cookies do navegador (resolve "403 Forbidden" e verificação de robô)
  - Motor de download (yt-dlp) instalado e atualizado sozinho, em segundo
    plano — o usuário não precisa ver nem mexer nisso
  - Notificação ao final do download, com opção de abrir a pasta de destino

Por que o motor fica fora do executável: os sites mudam com frequência e um
yt-dlp velho começa a dar "HTTP Error 403: Forbidden". Aqui o yt-dlp é um
programa à parte, guardado numa pasta do usuário. Quando um download falha
com 403, o programa atualiza o motor sozinho e tenta de novo, sem precisar
de nenhuma ação da pessoa que está usando.

O ffmpeg (junta vídeo+áudio, converte em MP3 e limpa metadados) é procurado
embutido no executável e, depois, no sistema.
"""

import os
import re
import sys
import stat
import shutil
import subprocess
import threading
import queue
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Baixador de Vídeos"
APP_VERSION = "1.6.0"

YTDLP_BASE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
DENO_BASE = "https://github.com/denoland/deno/releases/latest/download/"

# O YouTube passou a exigir um motor de JavaScript (para resolver o desafio
# "n") e a recusar o cliente que o yt-dlp escolhe sozinho. Sem as duas coisas
# o download morre em "HTTP Error 403: Forbidden".
CLIENTE_YOUTUBE = "youtube:player_client=web_embedded"

NAVEGADORES = ["chrome", "safari", "firefox", "edge", "brave", "opera", "vivaldi"]


# ---------------------------------------------------------------------------
# Caminhos e recursos
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def pasta_do_usuario() -> str:
    """Pasta gravável onde fica o motor de download."""
    if os.name == "nt":
        raiz = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        p = os.path.join(raiz, "BaixadorDeVideos")
    elif sys.platform == "darwin":
        p = os.path.expanduser(
            "~/Library/Application Support/BaixadorDeVideos"
        )
    else:
        p = os.path.expanduser("~/.baixador-de-videos")
    os.makedirs(p, exist_ok=True)
    return p


def caminho_motor() -> str:
    nome = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
    return os.path.join(pasta_do_usuario(), nome)


def url_motor() -> str:
    """Endereço do yt-dlp certo para este sistema e processador."""
    import platform
    arq = platform.machine().lower()
    if os.name == "nt":
        return YTDLP_BASE + "yt-dlp.exe"
    if sys.platform == "darwin":
        return YTDLP_BASE + "yt-dlp_macos"   # serve para Intel e Apple Silicon
    if arq in ("aarch64", "arm64"):
        return YTDLP_BASE + "yt-dlp_linux_aarch64"
    return YTDLP_BASE + "yt-dlp_linux"


def nome_zip_deno() -> str:
    import platform
    arq = platform.machine().lower()
    braco = arq in ("arm64", "aarch64")
    if os.name == "nt":
        return "deno-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return ("deno-aarch64-apple-darwin.zip" if braco
                else "deno-x86_64-apple-darwin.zip")
    return ("deno-aarch64-unknown-linux-gnu.zip" if braco
            else "deno-x86_64-unknown-linux-gnu.zip")


def caminho_js() -> str:
    nome = "deno.exe" if os.name == "nt" else "deno"
    return os.path.join(pasta_do_usuario(), nome)


def localizar_js():
    """Acha um motor de JavaScript utilizável. Devolve (nome, caminho) ou None.

    Ordem: a cópia do próprio programa, depois um deno ou node já instalados.
    """
    from shutil import which
    p = caminho_js()
    if os.path.isfile(p):
        return ("deno", p)
    for nome in ("deno", "node"):
        achado = which(nome)
        if achado:
            return (nome, achado)
    return None


def find_ffmpeg_dir():
    """Pasta que contém o ffmpeg (embutido ou do sistema), ou None."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"

    candidates = [
        resource_path(exe),
        resource_path(os.path.join("ffmpeg", exe)),
        resource_path(os.path.join("bin", exe)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), exe),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.dirname(c)

    from shutil import which
    found = which("ffmpeg")
    if found:
        return os.path.dirname(found)
    for c in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(c):
            return os.path.dirname(c)
    return None


def find_ffmpeg_exe():
    d = find_ffmpeg_dir()
    if not d:
        return None
    exe = os.path.join(d, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    return exe if os.path.isfile(exe) else None


def _sem_janela():
    """Evita abrir janela preta de console no Windows."""
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


# ---------------------------------------------------------------------------
# Motor de download (yt-dlp como programa à parte)
# ---------------------------------------------------------------------------
def motor_instalado() -> bool:
    return os.path.isfile(caminho_motor())


def versao_motor():
    """Devolve a versão do yt-dlp instalado, ou None."""
    if not motor_instalado():
        return None
    try:
        p = subprocess.run(
            [caminho_motor(), "--version"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=60, **_sem_janela()
        )
        return p.stdout.decode("utf-8", "replace").strip() or None
    except Exception:
        return None


def baixar_motor(aviso=None) -> str:
    """Baixa (ou atualiza) o yt-dlp. Devolve a versão instalada."""
    destino = caminho_motor()
    temp = destino + ".novo"
    if aviso:
        aviso("Baixando o motor de download (yt-dlp)…")
    req = urllib.request.Request(
        url_motor(), headers={"User-Agent": "BaixadorDeVideos"}
    )
    with urllib.request.urlopen(req, timeout=180) as r, open(temp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.chmod(temp, os.stat(temp).st_mode | stat.S_IEXEC | stat.S_IRUSR)
    shutil.move(temp, destino)
    if sys.platform == "darwin":
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", destino],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    v = versao_motor()
    if not v:
        raise RuntimeError(
            "O motor foi baixado mas não rodou nesta máquina."
        )
    return v


def baixar_js(aviso=None) -> str:
    """Baixa o Deno (motor de JavaScript) para a pasta do programa."""
    import zipfile
    import tempfile

    if aviso:
        aviso("Baixando o motor de JavaScript (uma vez só)…")
    destino = caminho_js()
    req = urllib.request.Request(
        DENO_BASE + nome_zip_deno(), headers={"User-Agent": "BaixadorDeVideos"}
    )
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "deno.zip")
        with urllib.request.urlopen(req, timeout=300) as r, \
                open(zip_path, "wb") as f:
            shutil.copyfileobj(r, f)
        with zipfile.ZipFile(zip_path) as z:
            alvo = next(
                (n for n in z.namelist()
                 if os.path.basename(n) in ("deno", "deno.exe")), None
            )
            if not alvo:
                raise RuntimeError("O pacote do Deno veio sem o programa.")
            z.extract(alvo, tmp)
            shutil.move(os.path.join(tmp, alvo), destino)

    os.chmod(destino, os.stat(destino).st_mode | stat.S_IEXEC | stat.S_IRUSR)
    if sys.platform == "darwin":
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", destino],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    return destino


# ---------------------------------------------------------------------------
# Limpeza de metadados
# ---------------------------------------------------------------------------
EXT_AUDIO = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".wav", ".flac"}


def limpar_metadados(caminho: str, ffmpeg: str) -> str:
    """Reescreve o arquivo sem nenhum metadado, sem recodificar.

    Remove tags globais e por faixa, capítulos, capa embutida (nos áudios), o
    nome do aparelho/handler e a marca do programa que gerou o arquivo.
    Levanta RuntimeError se o ffmpeg falhar.
    """
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado para limpar os metadados.")
    if not os.path.isfile(caminho):
        raise RuntimeError(f"Arquivo não encontrado: {caminho}")

    base, ext = os.path.splitext(caminho)
    ext_low = ext.lower()
    temp = base + ".semmeta" + ext

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", caminho]

    if ext_low in EXT_AUDIO:
        # Só a faixa de áudio: descarta capa embutida (que carrega metadado).
        cmd += ["-map", "0:a"]
    else:
        # Vídeo: mantém vídeo e áudio, descarta anexos e capítulos.
        cmd += ["-map", "0:v?", "-map", "0:a?"]

    cmd += [
        "-c", "copy",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-fflags", "+bitexact",
        "-flags:v", "+bitexact",
        "-flags:a", "+bitexact",
    ]

    if ext_low == ".mp3":
        cmd += ["-write_id3v1", "0", "-id3v2_version", "0"]
    if ext_low in (".mp4", ".m4a", ".mov"):
        # Apaga também o nome do "handler" de cada faixa, que o mp4 guarda.
        cmd += [
            "-movflags", "+faststart",
            "-metadata:s:v", "handler_name=",
            "-metadata:s:a", "handler_name=",
        ]

    cmd.append(temp)

    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_sem_janela()
    )
    if proc.returncode != 0 or not os.path.isfile(temp):
        if os.path.isfile(temp):
            try:
                os.remove(temp)
            except OSError:
                pass
        erro = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(erro[-1] if erro else "ffmpeg falhou.")

    shutil.move(temp, caminho)
    try:
        os.utime(caminho, None)  # zera a data original do arquivo
    except OSError:
        pass
    return f"Metadados removidos: {os.path.basename(caminho)}"


def cortar_video(caminho: str, ffmpeg: str, inicio: str, fim: str) -> str:
    """Corta o arquivo já baixado para o trecho entre `inicio` e `fim`
    (qualquer um dos dois pode vir vazio), sem recodificar.

    Importante: o corte usa "-ss"/"-to" DEPOIS do "-i" (corte de saída, no
    arquivo já em disco), não antes. Testado na prática: cortar direto na
    URL remota (antes do "-i", ou pelo recurso nativo do yt-dlp de baixar só
    o trecho) dá resultado ERRADO nos vídeos do YouTube — o arquivo final
    sai maior do que devia, sem respeitar o início pedido. Cortar depois do
    download, no arquivo local, é o único jeito confiável encontrado.
    """
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado para cortar o vídeo.")
    if not os.path.isfile(caminho):
        raise RuntimeError(f"Arquivo não encontrado: {caminho}")

    base, ext = os.path.splitext(caminho)
    temp = base + ".corte" + ext

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", caminho]
    if inicio:
        cmd += ["-ss", inicio]
    if fim:
        cmd += ["-to", fim]
    cmd += ["-c", "copy", temp]

    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_sem_janela()
    )
    if proc.returncode != 0 or not os.path.isfile(temp):
        if os.path.isfile(temp):
            try:
                os.remove(temp)
            except OSError:
                pass
        erro = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(erro[-1] if erro else "ffmpeg falhou ao cortar.")

    shutil.move(temp, caminho)
    return f"Vídeo cortado: {os.path.basename(caminho)}"


# ---------------------------------------------------------------------------
# Qualidade -> seletor de formato do yt-dlp
# ---------------------------------------------------------------------------
QUALIDADES = {
    "Melhor qualidade": "bv*+ba/b",
    "1080p (Full HD)": "bv*[height<=1080]+ba/b[height<=1080]",
    "720p (HD)": "bv*[height<=720]+ba/b[height<=720]",
    "480p": "bv*[height<=480]+ba/b[height<=480]",
    "360p": "bv*[height<=360]+ba/b[height<=360]",
}

MARCA_PROG = "@@P@@"
MARCA_ARQ = "@@F@@"

# Extensões que o usuário pode digitar por engano no nome de saída;
# a extensão certa é sempre decidida pelo download (mp4, mp3 etc.).
EXT_CONHECIDAS = {
    ".mp4", ".mp3", ".mkv", ".webm", ".m4a", ".mov", ".avi",
    ".wav", ".flac", ".ogg", ".opus", ".aac",
}


def nome_saida_seguro(nome: str) -> str:
    """Prepara o nome de arquivo digitado pelo usuário.

    Remove caracteres proibidos em nome de arquivo, tira uma extensão
    digitada por engano (a extensão certa vem do download) e devolve ""
    se não sobrar nada utilizável.
    """
    nome = (nome or "").strip()
    if not nome:
        return ""
    nome = re.sub(r'[\\/:*?"<>|]', "-", nome)
    base, ext = os.path.splitext(nome)
    if ext.lower() in EXT_CONHECIDAS:
        nome = base
    nome = nome.strip().strip(".")
    return nome.strip()


# ---------------------------------------------------------------------------
# Corte por tempo (início / fim)
# ---------------------------------------------------------------------------
# Aceita "SS", "MM:SS" ou "HH:MM:SS" (com ou sem casas decimais nos segundos).
TEMPO_RE = re.compile(r"^\d{1,3}(:\d{1,2}){0,2}(\.\d+)?$")


def tempo_valido(txt: str) -> bool:
    """True se o campo estiver vazio (sem corte nesse lado) ou for um
    tempo em formato hh:mm:ss / mm:ss / ss."""
    txt = (txt or "").strip()
    return txt == "" or bool(TEMPO_RE.match(txt))


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("720x660")
        self.minsize(660, 600)

        self.fila = queue.Queue()
        self.cancelar_flag = threading.Event()
        self.thread = None
        self.proc = None

        self.pasta_destino = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads")
        )
        self.qualidade = tk.StringVar(value="Melhor qualidade")
        self.nome_saida = tk.StringVar(value="")
        self.somente_audio = tk.BooleanVar(value=False)
        self.tempo_inicio = tk.StringVar(value="")
        self.tempo_fim = tk.StringVar(value="")
        self.baixar_playlist = tk.BooleanVar(value=False)
        self.remover_metadados = tk.BooleanVar(value=True)
        self.usar_cookies = tk.BooleanVar(value=False)
        self.navegador = tk.StringVar(value="chrome")

        self._montar_ui()
        self._verificar_ffmpeg()
        self.after(100, self._processar_fila)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        threading.Thread(target=self._preparar_motor, daemon=True).start()

    # ----- UI -----------------------------------------------------------
    def _montar_ui(self):
        pad = {"padx": 12, "pady": 6}

        # Rodapé primeiro, para ficar ancorado no fundo da janela.
        ttk.Label(
            self, text=f"{APP_NAME} • v{APP_VERSION}",
            anchor="e", foreground="#8b949e", font=("", 9),
        ).pack(side="bottom", fill="x", padx=12, pady=(0, 6))

        topo = ttk.Frame(self)
        topo.pack(fill="x", **pad)
        ttk.Label(topo, text="URL do vídeo ou playlist:").pack(anchor="w")
        self.url_entry = ttk.Entry(topo)
        self.url_entry.pack(fill="x", pady=(2, 0))

        # ---------------- Opções do download ----------------
        opc = ttk.LabelFrame(self, text="Opções do download")
        opc.pack(fill="x", **pad)

        linha1 = ttk.Frame(opc)
        linha1.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(linha1, text="Qualidade:").pack(side="left")
        self.combo_qual = ttk.Combobox(
            linha1, textvariable=self.qualidade,
            values=list(QUALIDADES.keys()), state="readonly", width=22,
        )
        self.combo_qual.pack(side="left", padx=(6, 20))

        ttk.Checkbutton(
            linha1, text="Somente áudio (MP3)",
            variable=self.somente_audio, command=self._toggle_audio,
        ).pack(side="left")

        ttk.Checkbutton(
            linha1, text="Baixar playlist inteira",
            variable=self.baixar_playlist,
        ).pack(side="left", padx=(20, 0))

        # Pasta de destino
        linha2 = ttk.Frame(opc)
        linha2.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(linha2, text="Salvar em:").pack(side="left")
        ttk.Entry(linha2, textvariable=self.pasta_destino).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(linha2, text="Escolher…",
                   command=self._escolher_pasta).pack(side="left")

        # Nome do arquivo de saída (opcional)
        linha3 = ttk.Frame(opc)
        linha3.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(linha3, text="Nome do arquivo (opcional):").pack(side="left")
        ttk.Entry(linha3, textvariable=self.nome_saida).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Label(
            linha3, text="vazio = título do vídeo",
            foreground="#8b949e", font=("", 9),
        ).pack(side="left")

        # Corte por tempo (opcional)
        linha4 = ttk.Frame(opc)
        linha4.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(linha4, text="Cortar vídeo — início:").pack(side="left")
        ttk.Entry(linha4, textvariable=self.tempo_inicio, width=10).pack(
            side="left", padx=(6, 16)
        )
        ttk.Label(linha4, text="fim:").pack(side="left")
        ttk.Entry(linha4, textvariable=self.tempo_fim, width=10).pack(
            side="left", padx=(6, 0)
        )

        ttk.Label(
            opc,
            text="Opcional. Formato hh:mm:ss (ex.: 1:23:45 ou 90). Deixe um "
                 "dos dois em branco para cortar só do início ou só até o "
                 "fim; deixe os dois em branco para baixar o vídeo inteiro. "
                 "O programa baixa o vídeo completo e corta em seguida (não "
                 "dá para baixar só o trecho direto do site).",
            foreground="#8b949e", font=("", 9), wraplength=660, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        # ---------------- Privacidade (metadados) ----------------
        priv = ttk.LabelFrame(self, text="Privacidade  ·  metadados")
        priv.pack(fill="x", **pad)

        linha_meta = ttk.Frame(priv)
        linha_meta.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Checkbutton(
            linha_meta,
            text="Remover TODOS os metadados do arquivo baixado",
            variable=self.remover_metadados,
        ).pack(side="left")
        ttk.Button(
            linha_meta, text="Limpar arquivos que já tenho…",
            command=self._limpar_existentes,
        ).pack(side="left", padx=(20, 0))

        ttk.Label(
            priv,
            text="Apaga título, autor, canal, descrição, capa, capítulos, "
                 "data de gravação, nome do aparelho e a data original do "
                 "arquivo. A imagem e o som não são recodificados.",
            foreground="#8b949e", font=("", 9), wraplength=660, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # ---------------- Acesso (discreto; só aparece se precisar) --------
        acesso = ttk.Frame(self)
        acesso.pack(fill="x", padx=12, pady=(0, 2))
        ttk.Checkbutton(
            acesso, text="Usar cookies do navegador",
            variable=self.usar_cookies, command=self._toggle_cookies,
        ).pack(side="left")
        self.combo_nav = ttk.Combobox(
            acesso, textvariable=self.navegador, values=NAVEGADORES,
            state="disabled", width=12,
        )
        self.combo_nav.pack(side="left", padx=(8, 8))
        ttk.Label(
            acesso, text="marque se der erro ao baixar (site exige login)",
            foreground="#8b949e", font=("", 9),
        ).pack(side="left")

        # ---------------- Ações ----------------
        acoes = ttk.Frame(self)
        acoes.pack(fill="x", **pad)
        self.btn_baixar = ttk.Button(acoes, text="⬇  Baixar",
                                     command=self._iniciar_download)
        self.btn_baixar.pack(side="left")
        self.btn_cancelar = ttk.Button(acoes, text="Cancelar",
                                       command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left", padx=8)

        # ---------------- Progresso ----------------
        prog = ttk.Frame(self)
        prog.pack(fill="x", **pad)
        barra_wrap = ttk.Frame(prog)
        barra_wrap.pack(fill="x")
        self.barra = ttk.Progressbar(barra_wrap, mode="determinate", maximum=100)
        self.barra.pack(fill="x", ipady=8)
        self.lbl_pct = ttk.Label(barra_wrap, text="0%", anchor="center")
        self.lbl_pct.place(relx=0.5, rely=0.5, anchor="center")
        self.status = ttk.Label(prog, text="Pronto.")
        self.status.pack(anchor="w", pady=(4, 0))

        # ---------------- Log ----------------
        logf = ttk.LabelFrame(self, text="Registro")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=9, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.log.config(yscrollcommand=sb.set)

    def _toggle_audio(self):
        self.combo_qual.config(
            state="disabled" if self.somente_audio.get() else "readonly"
        )

    def _toggle_cookies(self):
        self.combo_nav.config(
            state="readonly" if self.usar_cookies.get() else "disabled"
        )

    def _escolher_pasta(self):
        d = filedialog.askdirectory(initialdir=self.pasta_destino.get() or ".")
        if d:
            self.pasta_destino.set(d)

    def _verificar_ffmpeg(self):
        if find_ffmpeg_dir() is None:
            self._logar(
                "AVISO: ffmpeg não foi encontrado. Juntar vídeo+áudio, "
                "converter em MP3 e remover metadados podem falhar."
            )

    # ----- Motor (roda em segundo plano; não aparece para o usuário) ----
    def _preparar_motor(self, forcar=False):
        """Garante o yt-dlp e o motor de JavaScript exigido pelo YouTube."""
        try:
            v = None if forcar else versao_motor()
            if not v:
                self.fila.put(("status", "Preparando o programa (primeira vez)…"))
                v = baixar_motor()
                self.fila.put(("log", f"Motor de download instalado: {v}"))

            js = localizar_js()
            if not js:
                self.fila.put((
                    "status",
                    "Preparando o programa (primeira vez)…",
                ))
                baixar_js()
                localizar_js()
                self.fila.put(("log", "Motor de JavaScript instalado."))

            self.fila.put(("status", "Pronto."))
        except Exception as e:
            self.fila.put(("log", f"ERRO ao preparar o motor: {e}"))

    def _abrir_pasta(self, caminho):
        """Abre a pasta no Finder (Mac), Explorer (Windows) ou equivalente."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            elif os.name == "nt":
                os.startfile(caminho)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception as e:
            messagebox.showinfo(APP_NAME, f"A pasta é:\n{caminho}\n\n{e}")

    # ----- Limpeza de arquivos já existentes ----------------------------
    def _limpar_existentes(self):
        if self.thread and self.thread.is_alive():
            messagebox.showinfo(APP_NAME, "Aguarde a tarefa em andamento terminar.")
            return
        arquivos = filedialog.askopenfilenames(
            title="Escolha os arquivos para limpar os metadados",
            initialdir=self.pasta_destino.get() or ".",
        )
        if not arquivos:
            return
        self.btn_baixar.config(state="disabled")
        self._set_status("Limpando metadados…")
        self.thread = threading.Thread(
            target=self._worker_limpeza, args=(list(arquivos),), daemon=True
        )
        self.thread.start()

    def _worker_limpeza(self, arquivos):
        ffmpeg = find_ffmpeg_exe()
        total = len(arquivos)
        for i, caminho in enumerate(arquivos, start=1):
            self.fila.put(("status", f"Limpando {i} de {total}…"))
            self.fila.put(("progresso", (i - 1) * 100.0 / total))
            try:
                self.fila.put(("log", limpar_metadados(caminho, ffmpeg)))
            except Exception as e:
                self.fila.put(("log", f"ERRO em {os.path.basename(caminho)}: {e}"))
        self.fila.put(("progresso", 100.0))
        self.fila.put(("ok", f"Limpeza concluída ({total} arquivo(s))."))
        self.fila.put(("fim", None))

    # ----- Download -----------------------------------------------------
    def _iniciar_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Cole a URL do vídeo.")
            return
        destino = self.pasta_destino.get().strip()
        if not destino:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de destino.")
            return
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Não foi possível usar a pasta:\n{e}")
            return
        if self.remover_metadados.get() and find_ffmpeg_exe() is None:
            messagebox.showwarning(
                APP_NAME,
                "O ffmpeg não foi encontrado, então não dá para remover os "
                "metadados. Desmarque a opção ou instale o ffmpeg.",
            )
            return

        corte_inicio = self.tempo_inicio.get().strip()
        corte_fim = self.tempo_fim.get().strip()
        if not tempo_valido(corte_inicio) or not tempo_valido(corte_fim):
            messagebox.showwarning(
                APP_NAME,
                "Tempo de corte inválido. Use hh:mm:ss, mm:ss ou apenas "
                "segundos (ex.: 1:23:45, 12:30 ou 90).",
            )
            return
        if (corte_inicio or corte_fim) and find_ffmpeg_exe() is None:
            messagebox.showwarning(
                APP_NAME,
                "O ffmpeg não foi encontrado, então não dá para cortar o "
                "vídeo. Apague os campos de corte ou instale o ffmpeg.",
            )
            return

        self.cancelar_flag.clear()
        self.btn_baixar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.barra.config(value=0)
        self.lbl_pct.config(text="0%")
        self._set_status("Iniciando…")

        opcoes = {
            "url": url,
            "destino": destino,
            "nome_saida": nome_saida_seguro(self.nome_saida.get()),
            "format": QUALIDADES.get(self.qualidade.get(), "bv*+ba/b"),
            "somente_audio": self.somente_audio.get(),
            "corte_inicio": corte_inicio,
            "corte_fim": corte_fim,
            "playlist": self.baixar_playlist.get(),
            "remover_metadados": self.remover_metadados.get(),
            "cookies": self.navegador.get() if self.usar_cookies.get() else None,
        }
        self.thread = threading.Thread(target=self._worker, args=(opcoes,),
                                       daemon=True)
        self.thread.start()

    def _montar_comando(self, opc):
        nome = opc.get("nome_saida") or ""
        if nome:
            # O yt-dlp trata % como código de modelo; %% vira % literal.
            modelo = nome.replace("%", "%%")
            if opc["playlist"]:
                # Em playlist, um nome fixo sobrescreveria os arquivos;
                # numera cada item: "Nome - 1.mp4", "Nome - 2.mp4"…
                modelo += " - %(playlist_index)s"
            destino = os.path.join(opc["destino"], modelo + ".%(ext)s")
        else:
            destino = os.path.join(opc["destino"], "%(title)s.%(ext)s")
        cmd = [
            caminho_motor(),
            "--ignore-config",
            "--newline",
            "--no-colors",
            "--no-simulate",
            # --print deixa o yt-dlp calado; --progress traz a barra de volta.
            "--progress",
            "--retries", "10",
            "--fragment-retries", "10",
            "--progress-template",
            "download:" + MARCA_PROG +
            "%(progress._percent_str)s|%(progress._speed_str)s|"
            "%(progress._eta_str)s|%(info.title)s",
            "--print", "after_move:" + MARCA_ARQ + "%(filepath)s",
            "-o", destino,
        ]

        ffmpeg_dir = find_ffmpeg_dir()
        if ffmpeg_dir:
            cmd += ["--ffmpeg-location", ffmpeg_dir]

        js = localizar_js()
        if js:
            cmd += ["--js-runtimes", f"{js[0]}:{js[1]}"]

        if not opc.get("teimar"):
            # Primeira tentativa: o cliente do YouTube que hoje funciona.
            # Na segunda, sai do caminho e deixa o yt-dlp escolher sozinho,
            # caso um dia esse cliente pare de servir.
            cmd += ["--extractor-args", CLIENTE_YOUTUBE]

        cmd += ["--yes-playlist", "--ignore-errors"] if opc["playlist"] \
            else ["--no-playlist"]

        if opc["somente_audio"]:
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "192K"]
        else:
            cmd += ["-f", opc["format"], "--merge-output-format", "mp4"]

        # O corte por tempo NÃO usa --download-sections do yt-dlp: testado na
        # prática, esse recurso baixa o vídeo do YouTube errado (sai maior
        # do que devia, ignorando o início pedido). O corte é aplicado
        # depois, no arquivo já baixado (ver _rodar/cortar_video).

        if opc["remover_metadados"]:
            # Não carimba no arquivo a data de publicação (isso é metadado).
            cmd += ["--no-mtime", "--no-write-info-json", "--no-write-thumbnail"]

        if opc["cookies"]:
            cmd += ["--cookies-from-browser", opc["cookies"]]

        if opc.get("teimar"):
            # Segunda tentativa: sair por IPv4 costuma contornar bloqueios
            # que aparecem so em IPv6, e um tempo maior evita corte no meio.
            cmd += ["--force-ipv4", "--socket-timeout", "30"]

        cmd.append(opc["url"])
        return cmd

    def _worker(self, opc):
        """Roda em thread separada. Comunica-se com a GUI via self.fila."""
        try:
            if not motor_instalado() or not localizar_js():
                self._preparar_motor()

            codigo, saida = self._rodar(opc)

            # 403 e afins: tenta de novo por outro caminho, uma vez só.
            if codigo != 0 and not self.cancelar_flag.is_set() \
                    and self._parece_bloqueio(saida):
                self.fila.put((
                    "log",
                    "O site recusou o download. Tentando de novo por outro "
                    "caminho…",
                ))
                if "javascript runtime" in saida.lower():
                    try:
                        baixar_js()
                        self.fila.put(("log", "Motor de JavaScript instalado."))
                    except Exception as e:
                        self.fila.put(("log", f"Falha ao instalar o JS: {e}"))
                try:
                    baixar_motor()
                    self.fila.put(("log", "Motor de download atualizado."))
                except Exception as e:
                    self.fila.put(("log", f"Não consegui atualizar o motor: {e}"))
                opc = dict(opc, teimar=True)
                codigo, saida = self._rodar(opc)

            if self.cancelar_flag.is_set():
                self.fila.put(("status", "Cancelado pelo usuário."))
            elif codigo == 0:
                self.fila.put((
                    "download_ok",
                    ("Download concluído com sucesso!", opc["destino"]),
                ))
            else:
                self.fila.put(("erro", self._mensagem_erro(saida)))
        except Exception as e:
            self.fila.put(("erro", str(e)))
        finally:
            self.proc = None
            self.fila.put(("fim", None))

    def _rodar(self, opc):
        """Executa o yt-dlp e vai traduzindo a saída para a GUI."""
        ffmpeg = find_ffmpeg_exe()
        linhas = []
        self.proc = subprocess.Popen(
            self._montar_comando(opc),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, universal_newlines=True, encoding="utf-8",
            errors="replace", **_sem_janela()
        )
        for linha in self.proc.stdout:
            linha = linha.rstrip("\r\n")
            if not linha:
                continue
            linhas.append(linha)

            if linha.startswith(MARCA_PROG):
                self._linha_progresso(linha[len(MARCA_PROG):])
            elif linha.startswith(MARCA_ARQ):
                caminho = linha[len(MARCA_ARQ):].strip()
                self.fila.put(("log", f"Baixado: {os.path.basename(caminho)}"))
                corte_ini = opc.get("corte_inicio") or ""
                corte_fim = opc.get("corte_fim") or ""
                if corte_ini or corte_fim:
                    self.fila.put(("status", "Cortando o trecho pedido…"))
                    try:
                        self.fila.put((
                            "log", cortar_video(caminho, ffmpeg, corte_ini, corte_fim)
                        ))
                    except Exception as e:
                        self.fila.put(("log", f"ERRO ao cortar o vídeo: {e}"))
                if opc["remover_metadados"]:
                    self.fila.put(("status", "Removendo metadados…"))
                    try:
                        self.fila.put(("log", limpar_metadados(caminho, ffmpeg)))
                    except Exception as e:
                        self.fila.put(("log", f"ERRO ao remover metadados: {e}"))
            elif linha.startswith(("ERROR", "WARNING")):
                self.fila.put(("log", linha))
            elif "[Merger]" in linha or "[ExtractAudio]" in linha:
                self.fila.put(("status", "Processando (ffmpeg)…"))

        self.proc.wait()
        return self.proc.returncode, "\n".join(linhas)

    def _linha_progresso(self, dados):
        partes = dados.split("|")
        pct_txt = partes[0].strip() if partes else ""
        m = re.search(r"([\d.]+)%", pct_txt)
        if m:
            try:
                self.fila.put(("progresso", float(m.group(1))))
            except ValueError:
                pass
        vel = partes[1].strip() if len(partes) > 1 else ""
        eta = partes[2].strip() if len(partes) > 2 else ""
        titulo = partes[3].strip() if len(partes) > 3 else ""
        self.fila.put(("status", f"Baixando {titulo[:48]}  {vel}  ETA {eta}"))

    @staticmethod
    def _parece_bloqueio(saida: str) -> bool:
        s = saida.lower()
        return any(t in s for t in (
            "403", "forbidden", "sign in to confirm", "unable to extract",
            "please update", "nsig extraction failed", "not a bot",
        ))

    @staticmethod
    def _mensagem_erro(saida: str) -> str:
        erros = [l for l in saida.splitlines() if l.startswith("ERROR")]
        base = erros[-1] if erros else "O download falhou."
        s = saida.lower()
        if "javascript runtime" in s or "n challenge" in s:
            base += (
                "\n\nFalta o motor de JavaScript que o YouTube exige. Feche "
                "e abra o programa de novo para tentar instalar mais uma vez."
            )
        elif "403" in s or "forbidden" in s or "sign in to confirm" in s \
                or "not a bot" in s:
            base += (
                "\n\nO site recusou o acesso nas duas tentativas. Marque "
                "\"Usar cookies do navegador\" e escolha o navegador em que "
                "você está logado nesse site, depois tente de novo."
            )
        return base

    def _cancelar(self):
        self.cancelar_flag.set()
        self._set_status("Cancelando…")
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

    # ----- Comunicação thread -> GUI ------------------------------------
    def _processar_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "progresso":
                    self.barra.config(value=valor)
                    self.lbl_pct.config(text=f"{valor:.1f}%")
                elif tipo == "status":
                    self._set_status(valor)
                elif tipo == "log":
                    self._logar(valor)
                elif tipo == "ok":
                    self._set_status(valor)
                    self._logar(valor)
                elif tipo == "download_ok":
                    msg, pasta = valor
                    self._set_status(msg)
                    self._logar(msg)
                    if messagebox.askyesno(
                        APP_NAME,
                        "Download concluído!\n\n"
                        "Quer abrir a pasta onde o arquivo foi salvo?",
                    ):
                        self._abrir_pasta(pasta)
                elif tipo == "erro":
                    self._set_status("Erro.")
                    self._logar("ERRO: " + valor)
                    messagebox.showerror(APP_NAME, valor)
                elif tipo == "fim":
                    self.btn_baixar.config(state="normal")
                    self.btn_cancelar.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _set_status(self, txt):
        self.status.config(text=txt)

    def _logar(self, txt):
        self.log.config(state="normal")
        self.log.insert("end", txt + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _ao_fechar(self):
        if self.thread and self.thread.is_alive():
            if not messagebox.askyesno(
                APP_NAME, "Há uma tarefa em andamento. Fechar mesmo assim?"
            ):
                return
            self._cancelar()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
