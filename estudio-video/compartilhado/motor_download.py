# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/motor_download.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

"""Motor de download (yt-dlp), compartilhado pelos estudios.

Este arquivo NAO tem interface: sao so as funcoes que acham, instalam e
atualizam o yt-dlp e o motor de JavaScript que o YouTube passou a exigir, mais
a localizacao do ffmpeg.

Ele existe porque duas telas precisam da mesma coisa: a aba "Baixar" do Video
Studio, que baixa o video inteiro, e a aba "Extrair audio", que aparece nos
dois estudios e usa o mesmo motor para pegar so a faixa de som de um link.

Por que o motor fica FORA do executavel: os sites mudam com frequencia e um
yt-dlp velho comeca a dar "HTTP Error 403: Forbidden". Aqui ele e um programa
a parte, guardado numa pasta do usuario e atualizado sozinho quando um
download falha.
"""

import os
import re
import ssl
import sys
import stat
import shutil
import subprocess
import urllib.request

# O import fica no nivel do modulo de proposito: o PyInstaller precisa "ver"
# este import estaticamente para embutir os certificados do certifi no
# executavel. Sem isso, o app empacotado falha ao baixar o motor com
# "CERTIFICATE_VERIFY_FAILED", mesmo com a internet normal. Ainda assim ele e
# tolerante, para o programa abrir numa maquina sem o certifi instalado.
try:
    import certifi
except ImportError:
    certifi = None


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
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), exe),
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


def _contexto_ssl():
    """Contexto SSL usando o pacote de certificados do certifi.

    Sem isso, o programa empacotado (PyInstaller) pode falhar ao baixar o
    motor com "CERTIFICATE_VERIFY_FAILED: unable to get local issuer
    certificate": o Python embutido no executável não enxerga a mesma
    cadeia de certificados raiz que o sistema operacional usa, mesmo com a
    internet funcionando normalmente.
    """
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


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
    with urllib.request.urlopen(req, timeout=180, context=_contexto_ssl()) as r, \
            open(temp, "wb") as f:
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
        with urllib.request.urlopen(req, timeout=300, context=_contexto_ssl()) as r, \
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
