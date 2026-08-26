"""
Cortar Audio e Video - interface grafica (Tkinter).

Duas coisas, num programa so:

Aba 1 - Cortar um trecho:
  - escolhe o comeco e o fim pela minutagem;
  - comeco vazio = do inicio do arquivo;
  - fim vazio = da minutagem de comeco ate o fim do arquivo;
  - aceita 1:30, 01:02:03, 90, 1h05m, 2min30s -- e mostra na hora o que
    entendeu, para nao haver duvida.

Aba 2 - Dividir em partes:
  - transforma um arquivo em 2, 3, 10 partes iguais;
  - ou em partes de X minutos cada.

Vale para audio e para video. O corte pode ser exato (recodifica, comeca no
ponto certo) ou rapido (nao recodifica, mas o video so pode ser cortado nos
pontos-chave e pode comecar um pouco antes do pedido).

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.
"""

import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from shutil import which
from tkinter import (
    Tk, StringVar, IntVar, END, DISABLED, NORMAL,
    filedialog, messagebox, ttk, scrolledtext,
)

import atualizador  # atualizacao automatica


APP_NAME = "Cortar Audio e Video"
APP_VERSION = "1.0.2"

EXTENSOES_MIDIA = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".aiff", ".aif", ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v",
    ".mpg", ".mpeg", ".ts", ".3gp", ".wmv",
}

MODO_EXATO = "Exato: comeca no ponto certo (recodifica, mais lento)"
MODO_RAPIDO = "Rapido: nao recodifica (o video pode comecar alguns segundos antes)"
MODOS = [MODO_EXATO, MODO_RAPIDO]

# Containers de video que aceitam H.264 sem trocar de extensao.
CONTAINERS_H264 = {".mp4", ".m4v", ".mov", ".mkv"}


# ---------------------------------------------------------------------------
# Localizacao do ffmpeg / ffprobe embutidos
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _achar_binario(nome: str):
    """Procura um binario embutido junto ao executavel, depois no PATH."""
    exe = f"{nome}.exe" if os.name == "nt" else nome
    for c in (resource_path(exe),
              resource_path(os.path.join("ffmpeg", exe)),
              resource_path(os.path.join("bin", exe))):
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    achado = which(nome)
    if achado:
        return achado

    # Aplicativo aberto por clique duplo costuma vir com PATH curto: procura
    # nos lugares mais comuns de instalacao no Mac e no Linux.
    for pasta in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/opt/local/bin"):
        c = os.path.join(pasta, exe)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def find_ffmpeg():
    return _achar_binario("ffmpeg")


def find_ffprobe():
    return _achar_binario("ffprobe")


def _sem_janela():
    """Impede o piscar do console preto no Windows."""
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ---------------------------------------------------------------------------
# Tempo: leitura do que o usuario digita e formatacao
# ---------------------------------------------------------------------------
RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")
RE_TEMPO = re.compile(r"time=\s*(\d+):(\d+):(\d+\.?\d*)")
RE_SUFIXO = re.compile(
    r"^(?:(\d+(?:[.,]\d+)?)\s*h)?\s*"
    r"(?:(\d+(?:[.,]\d+)?)\s*m(?:in)?)?\s*"
    r"(?:(\d+(?:[.,]\d+)?)\s*s(?:eg)?)?$",
    re.IGNORECASE,
)


def hms_para_seg(h, m, s) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def _num(txt):
    return float(str(txt).replace(",", "."))


def parse_tempo(texto: str):
    """Le a minutagem que o usuario digitou e devolve segundos.

    Devolve None quando o campo esta vazio (o programa trata isso como
    "do inicio" ou "ate o fim"). Levanta ValueError quando nao entende.

    Entende: 90 | 1:30 | 01:02:03 | 1:30,5 | 1h05m | 2min30s | 45s | 5m
    """
    t = (texto or "").strip()
    if not t:
        return None

    if ":" in t:
        partes = t.split(":")
        if len(partes) > 3 or any(p.strip() == "" for p in partes):
            raise ValueError(f"Nao entendi a minutagem '{texto}'.")
        try:
            partes = [_num(p) for p in partes]
        except ValueError:
            raise ValueError(f"Nao entendi a minutagem '{texto}'.")
        if len(partes) == 2:
            seg = partes[0] * 60 + partes[1]
        else:
            seg = partes[0] * 3600 + partes[1] * 60 + partes[2]
        if seg < 0:
            raise ValueError("A minutagem nao pode ser negativa.")
        return seg

    m = RE_SUFIXO.match(t)
    if m and any(m.groups()):
        h, mi, s = m.groups()
        return (_num(h) if h else 0) * 3600 + (_num(mi) if mi else 0) * 60 + (_num(s) if s else 0)

    try:
        seg = _num(t)
    except ValueError:
        raise ValueError(f"Nao entendi a minutagem '{texto}'.")
    if seg < 0:
        raise ValueError("A minutagem nao pode ser negativa.")
    return seg


def formatar_tempo(seg) -> str:
    if seg is None or seg < 0:
        return "--:--:--"
    total = int(round(seg))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def formatar_tempo_arquivo(seg) -> str:
    """Mesma coisa, mas com tracos, para virar nome de arquivo."""
    return formatar_tempo(seg).replace(":", "-")


def formatar_tamanho(bytes_) -> str:
    b = float(bytes_ or 0)
    for unidade in ("B", "KB", "MB", "GB"):
        if b < 1024 or unidade == "GB":
            return f"{b:.0f} {unidade}" if unidade == "B" else f"{b:.1f} {unidade}"
        b /= 1024.0
    return f"{b:.1f} GB"


# ---------------------------------------------------------------------------
# Leitura do arquivo
# ---------------------------------------------------------------------------
def ler_info_midia(ffmpeg: str, ffprobe, caminho: str) -> dict:
    """Duracao, se tem imagem, codecs, resolucao e tamanho do arquivo."""
    info = {
        "duracao": None, "tem_video": False, "codec_v": None, "codec_a": None,
        "largura": None, "altura": None, "bitrate_audio": None, "tamanho": None,
    }
    try:
        info["tamanho"] = os.path.getsize(caminho)
    except OSError:
        pass

    if ffprobe:
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_streams", "-show_format",
                 "-of", "json", caminho],
                capture_output=True, text=True, timeout=120, **_sem_janela()
            )
            dados = json.loads(proc.stdout or "{}")
            for fluxo in dados.get("streams") or []:
                tipo = fluxo.get("codec_type")
                if tipo == "video":
                    # Capa embutida (foto do album) nao conta como video.
                    if (fluxo.get("disposition") or {}).get("attached_pic") == 1:
                        continue
                    info["tem_video"] = True
                    info["codec_v"] = fluxo.get("codec_name")
                    info["largura"] = fluxo.get("width")
                    info["altura"] = fluxo.get("height")
                elif tipo == "audio" and not info["codec_a"]:
                    info["codec_a"] = fluxo.get("codec_name")
                    br = fluxo.get("bit_rate")
                    if br:
                        try:
                            info["bitrate_audio"] = int(br)
                        except ValueError:
                            pass
            dur = (dados.get("format") or {}).get("duration")
            if dur:
                info["duracao"] = float(dur)
        except Exception:
            pass

    if info["duracao"] is None:
        # Sem ffprobe: pega a duracao pelo cabecalho que o ffmpeg imprime.
        try:
            proc = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", caminho],
                capture_output=True, text=True, timeout=120, **_sem_janela()
            )
            saida = proc.stderr or ""
            m = RE_DURACAO.search(saida)
            if m:
                info["duracao"] = hms_para_seg(*m.groups())
            if re.search(r"Stream #\d+:\d+.*: Video:", saida):
                info["tem_video"] = True
        except Exception:
            pass

    return info


def ler_duracao(ffprobe, caminho):
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", caminho],
            capture_output=True, text=True, timeout=60, **_sem_janela()
        )
        return float((proc.stdout or "").strip())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Como codificar a saida
# ---------------------------------------------------------------------------
def opcoes_saida(info: dict, ext_original: str, modo: str):
    """Devolve (argumentos do ffmpeg, extensao de saida, aviso).

    No modo rapido a saida sai igual a entrada (copia os dados como estao).
    No modo exato o trecho e recodificado, para comecar exatamente no ponto
    pedido -- e ai a extensao pode mudar quando o formato original nao aceita
    o codec usado.
    """
    ext = (ext_original or "").lower()

    if modo == MODO_RAPIDO:
        return ["-c", "copy", "-avoid_negative_ts", "make_zero"], ext or ".mp4", ""

    if info.get("tem_video"):
        args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        if ext in CONTAINERS_H264:
            saida = ext
        else:
            saida = ".mp4"
        if saida in (".mp4", ".m4v", ".mov"):
            args += ["-movflags", "+faststart"]
        aviso = "" if saida == ext else f"O formato {ext} nao aceita corte exato: a saida vai sair em {saida}."
        return args, saida, aviso

    # Audio: mantem o formato quando da, com a mesma taxa do original.
    br = info.get("bitrate_audio") or 0
    kbps = 192
    if 48000 <= br <= 320000:
        kbps = int(round(br / 1000.0))

    if ext == ".wav":
        return ["-c:a", "pcm_s16le"], ".wav", ""
    if ext == ".flac":
        return ["-c:a", "flac"], ".flac", ""
    if ext in (".m4a", ".aac", ".mp4"):
        return ["-c:a", "aac", "-b:a", f"{kbps}k"], ".m4a" if ext != ".aac" else ".aac", ""
    if ext in (".ogg", ".opus"):
        return ["-c:a", "libopus", "-b:a", f"{min(kbps, 192)}k"], ext, ""
    if ext == ".mp3":
        return ["-c:a", "libmp3lame", "-b:a", f"{kbps}k"], ".mp3", ""
    return (["-c:a", "libmp3lame", "-b:a", f"{kbps}k"], ".mp3",
            f"O formato {ext} nao aceita corte exato: a saida vai sair em .mp3.")


def mapeamento(info: dict, modo: str):
    """Quais faixas entram na saida."""
    if info.get("tem_video"):
        return ["-map", "0:v:0", "-map", "0:a?"]
    return ["-map", "0:a:0", "-vn"]


# ---------------------------------------------------------------------------
# Corte
# ---------------------------------------------------------------------------
def cortar(ffmpeg, origem, destino, inicio, duracao, info, modo,
           log, progresso, cancelar, duracao_esperada=None):
    """Corta um trecho e grava em 'destino'.

    inicio None (ou 0) = desde o comeco do arquivo.
    duracao None = vai ate o fim do arquivo (nao entra '-t' no comando).
    duracao_esperada e so para a barra de progresso andar certo quando nao ha
    '-t' -- ela nao interfere no corte.
    """
    args_fmt, _, _ = opcoes_saida(info, Path(destino).suffix, modo)

    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    if inicio:
        cmd += ["-ss", f"{inicio:.3f}"]
    cmd += ["-i", origem]
    if duracao:
        cmd += ["-t", f"{duracao:.3f}"]
    cmd += mapeamento(info, modo) + args_fmt + [destino]

    referencia = duracao or duracao_esperada

    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **_sem_janela()
    )
    erros = []
    try:
        for linha in proc.stderr:
            if cancelar.is_set():
                proc.terminate()
                return False
            m = RE_TEMPO.search(linha)
            if m and referencia and progresso:
                progresso(min(100.0, hms_para_seg(*m.groups()) / referencia * 100.0))
            if "Error" in linha or "Invalid" in linha or "error" in linha:
                erros.append(linha.strip())
    finally:
        proc.wait()

    if proc.returncode != 0:
        for l in erros[-6:]:
            log(f"  {l}")
        raise RuntimeError("O ffmpeg nao conseguiu cortar esse arquivo. "
                           "Veja as linhas acima; tente o outro modo de corte.")
    return True


def nome_limpo(texto: str) -> str:
    limpo = re.sub(r"[^\w\-. ]+", "_", texto).strip(" _")
    return limpo or "arquivo"


def calcular_partes(duracao, criterio, n_partes, minutos):
    """Devolve a lista de (inicio, duracao) de cada parte."""
    if not duracao or duracao <= 0:
        return []
    if criterio == "partes":
        n = max(2, int(n_partes))
        passo = duracao / n
    else:
        passo = max(1, int(minutos)) * 60.0
        n = max(1, int(math.ceil(duracao / passo)))
    partes = []
    for i in range(n):
        inicio = round(i * passo, 3)
        if inicio >= duracao:
            break
        # A ultima parte vai ate o fim: sem duracao, o ffmpeg le o que sobrou.
        dur = None if i == n - 1 else round(min(passo, duracao - inicio), 3)
        partes.append((inicio, dur))
    return partes


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class Aplicativo:

    def __init__(self, raiz: Tk):
        self.raiz = raiz
        raiz.title(f"{APP_NAME} {APP_VERSION}")
        raiz.geometry("880x780")
        # O minimo tem de caber o miolo inteiro das abas: abaixo disso a caixa
        # "Onde salvar" era espremida ate sumir.
        raiz.minsize(760, 700)

        self.ffmpeg = find_ffmpeg()
        self.ffprobe = find_ffprobe()

        self.cancelar = threading.Event()
        self.trabalhando = False

        self.origem = ""
        self.info = {}
        self.destino_corte = ""
        self.pasta_partes = ""
        self.ultima_pasta = ""

        self._montar()

        if not self.ffmpeg:
            self.log("ATENCAO: ffmpeg nao encontrado nesta maquina. O programa nao vai "
                     "conseguir processar nada. No executavel publicado ele ja vem junto.")
        else:
            self.log("Pronto. Escolha um arquivo de audio ou video para comecar.")

    # -------------------------------------------------------------- montagem
    def _montar(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except Exception:
            pass

        # Rodape primeiro: empacotar por ultimo no 'bottom' e o que garante
        # que ele fique mesmo no fundo da janela.
        ttk.Label(
            self.raiz, text=f"{APP_NAME} • v{APP_VERSION}",
            foreground="#8b949e", font=("Segoe UI", 8), anchor="e",
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 4))

        self.txt = scrolledtext.ScrolledText(self.raiz, height=5, state=DISABLED, wrap="word")
        self.txt.pack(side="bottom", fill="both", expand=False, padx=10, pady=(0, 6))

        self.var_status = StringVar(value="Pronto.")
        ttk.Label(self.raiz, textvariable=self.var_status, foreground="#444").pack(
            side="bottom", anchor="w", padx=10, pady=(2, 4))

        self.prog = ttk.Progressbar(self.raiz, mode="determinate", maximum=100)
        self.prog.pack(side="bottom", fill="x", padx=10)

        topo = ttk.Frame(self.raiz, padding=(10, 10, 10, 0))
        topo.pack(side="top", fill="x")

        cx = ttk.LabelFrame(topo, text="1) Arquivo de audio ou video", padding=10)
        cx.pack(fill="x")
        linha = ttk.Frame(cx)
        linha.pack(fill="x")
        self.var_origem = StringVar(value="Nenhum arquivo escolhido")
        ttk.Label(linha, textvariable=self.var_origem, foreground="#333").pack(
            side="left", fill="x", expand=True)
        ttk.Button(linha, text="Escolher arquivo...", command=self.escolher_origem).pack(side="right")
        self.var_info = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_info, foreground="#666").pack(anchor="w", pady=(6, 0))

        cx2 = ttk.LabelFrame(topo, text="2) Como cortar", padding=10)
        cx2.pack(fill="x", pady=(8, 0))
        self.var_modo = StringVar(value=MODO_EXATO)
        for m in MODOS:
            ttk.Radiobutton(cx2, text=m, variable=self.var_modo, value=m,
                            command=self._modo_mudou).pack(anchor="w")

        cad = ttk.Notebook(self.raiz)
        cad.pack(side="top", fill="both", expand=True, padx=10, pady=10)
        self.aba_corte = ttk.Frame(cad, padding=10)
        self.aba_div = ttk.Frame(cad, padding=10)
        cad.add(self.aba_corte, text="  3) Cortar um trecho  ")
        cad.add(self.aba_div, text="  3) Dividir em partes  ")

        self._montar_aba_corte()
        self._montar_aba_dividir()

    # ----------------------------------------------------------- aba cortar
    def _montar_aba_corte(self):
        p = self.aba_corte

        # Os botoes sao empacotados primeiro, ancorados no fundo da aba. Assim
        # eles continuam na tela mesmo com a janela baixa -- antes o "Cortar"
        # era empurrado para fora e sumia.
        bt = ttk.Frame(p)
        bt.pack(side="bottom", fill="x", pady=(10, 0))
        self.bt_cortar = ttk.Button(bt, text="Cortar", command=self.iniciar_corte)
        self.bt_cortar.pack(side="left")
        self.bt_cancelar_c = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                        command=self.pedir_cancelamento)
        self.bt_cancelar_c.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta do resultado",
                   command=lambda: self.abrir_pasta(self.ultima_pasta)).pack(side="right")

        cx = ttk.LabelFrame(p, text="Trecho que voce quer guardar", padding=10)
        cx.pack(fill="x")

        grade = ttk.Frame(cx)
        grade.pack(fill="x")
        grade.columnconfigure(3, weight=1)

        ttk.Label(grade, text="Comeca em:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_ini = StringVar(value="")
        ttk.Entry(grade, textvariable=self.var_ini, width=14).grid(row=0, column=1, padx=6)
        self.var_ini_lido = StringVar(value="vazio = desde o inicio do arquivo")
        ttk.Label(grade, textvariable=self.var_ini_lido, foreground="#0a6").grid(
            row=0, column=2, columnspan=2, sticky="w")

        ttk.Label(grade, text="Termina em:").grid(row=1, column=0, sticky="w", pady=3)
        self.var_fim = StringVar(value="")
        ttk.Entry(grade, textvariable=self.var_fim, width=14).grid(row=1, column=1, padx=6)
        self.var_fim_lido = StringVar(value="vazio = ate o fim do arquivo")
        ttk.Label(grade, textvariable=self.var_fim_lido, foreground="#0a6").grid(
            row=1, column=2, columnspan=2, sticky="w")

        ttk.Label(
            cx,
            text="Escreva 1:30, 01:02:03, 90 (segundos), 5m ou 1h30m -- ao lado aparece o "
                 "que o programa entendeu.",
            foreground="#666", justify="left",
        ).pack(anchor="w", pady=(6, 0))

        self.var_resumo = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_resumo, foreground="#0a6",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 0))

        cx2 = ttk.LabelFrame(p, text="Onde salvar", padding=10)
        cx2.pack(fill="x", pady=(8, 0))
        l2 = ttk.Frame(cx2)
        l2.pack(fill="x")
        self.var_destino = StringVar(value="(ao lado do arquivo original)")
        ttk.Label(l2, textvariable=self.var_destino, foreground="#333").pack(
            side="left", fill="x", expand=True)
        ttk.Button(l2, text="Trocar...", command=self.escolher_destino).pack(side="right")

        self.var_ini.trace_add("write", lambda *_: self.atualizar_corte())
        self.var_fim.trace_add("write", lambda *_: self.atualizar_corte())

    # ---------------------------------------------------------- aba dividir
    def _montar_aba_dividir(self):
        p = self.aba_div

        bt = ttk.Frame(p)
        bt.pack(side="bottom", fill="x", pady=(10, 0))
        self.bt_dividir = ttk.Button(bt, text="Dividir", command=self.iniciar_divisao)
        self.bt_dividir.pack(side="left")
        self.bt_cancelar_d = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                        command=self.pedir_cancelamento)
        self.bt_cancelar_d.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta das partes",
                   command=lambda: self.abrir_pasta(self.ultima_pasta)).pack(side="right")

        cx = ttk.LabelFrame(p, text="Em quantos pedacos", padding=10)
        cx.pack(fill="x")

        self.var_criterio = StringVar(value="partes")
        l1 = ttk.Frame(cx)
        l1.pack(fill="x", pady=2)
        ttk.Radiobutton(l1, text="Dividir em quantas partes:", variable=self.var_criterio,
                        value="partes", command=self.atualizar_divisao).pack(side="left")
        self.var_n = IntVar(value=2)
        ttk.Spinbox(l1, from_=2, to=99, width=6, textvariable=self.var_n,
                    command=self.atualizar_divisao).pack(side="left", padx=8)

        l2 = ttk.Frame(cx)
        l2.pack(fill="x", pady=2)
        ttk.Radiobutton(l2, text="Ou partes de quantos minutos cada:", variable=self.var_criterio,
                        value="minutos", command=self.atualizar_divisao).pack(side="left")
        self.var_min = IntVar(value=10)
        ttk.Spinbox(l2, from_=1, to=600, width=6, textvariable=self.var_min,
                    command=self.atualizar_divisao).pack(side="left", padx=8)

        self.var_previa = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_previa, foreground="#0a6",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 0))

        cx2 = ttk.LabelFrame(p, text="Onde salvar as partes", padding=10)
        cx2.pack(fill="x", pady=(8, 0))
        l3 = ttk.Frame(cx2)
        l3.pack(fill="x")
        self.var_pasta = StringVar(value="(uma pasta ao lado do arquivo original)")
        ttk.Label(l3, textvariable=self.var_pasta, foreground="#333").pack(
            side="left", fill="x", expand=True)
        ttk.Button(l3, text="Trocar pasta...", command=self.escolher_pasta).pack(side="right")

        self.var_n.trace_add("write", lambda *_: self.atualizar_divisao())
        self.var_min.trace_add("write", lambda *_: self.atualizar_divisao())

    # ------------------------------------------------------------ mensagens
    def log(self, msg):
        def escrever():
            self.txt.configure(state=NORMAL)
            self.txt.insert(END, f"{time.strftime('%H:%M:%S')}  {msg}\n")
            self.txt.see(END)
            self.txt.configure(state=DISABLED)
        self.raiz.after(0, escrever)

    def status(self, msg):
        self.raiz.after(0, lambda: self.var_status.set(msg))

    def progresso(self, pct):
        self.raiz.after(0, lambda: self.prog.configure(value=pct))

    # -------------------------------------------------------------- arquivo
    def escolher_origem(self):
        caminho = filedialog.askopenfilename(
            title="Escolha o audio ou o video",
            filetypes=[("Audio e video", " ".join(f"*{e}" for e in sorted(EXTENSOES_MIDIA))),
                       ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado nesta maquina.")
            return
        self.origem = caminho
        self.var_origem.set(os.path.basename(caminho))
        self.var_info.set("Lendo o arquivo...")
        self.destino_corte = ""
        self.pasta_partes = str(Path(caminho).with_suffix("")) + " - partes"
        self.var_pasta.set(self.pasta_partes)
        threading.Thread(target=self._carregar_info, daemon=True).start()

    def _carregar_info(self):
        info = ler_info_midia(self.ffmpeg, self.ffprobe, self.origem)
        self.info = info
        pedacos = []
        if info.get("duracao"):
            pedacos.append(f"Duracao: {formatar_tempo(info['duracao'])}")
        pedacos.append("Video" if info.get("tem_video") else "So audio")
        if info.get("tem_video") and info.get("largura"):
            pedacos.append(f"{info['largura']}x{info['altura']}")
        if info.get("codec_v"):
            pedacos.append(f"imagem: {info['codec_v']}")
        if info.get("codec_a"):
            pedacos.append(f"som: {info['codec_a']}")
        if info.get("tamanho"):
            pedacos.append(formatar_tamanho(info["tamanho"]))
        texto = "   |   ".join(pedacos) if info.get("duracao") else \
            "Nao consegui ler esse arquivo. Ele pode estar corrompido ou nao ser audio/video."
        self.raiz.after(0, lambda: self.var_info.set(texto))
        self.raiz.after(0, self.atualizar_corte)
        self.raiz.after(0, self.atualizar_divisao)
        self.log(f"Arquivo carregado: {os.path.basename(self.origem)} "
                 f"({formatar_tempo(info.get('duracao'))}).")

    def _modo_mudou(self):
        self.atualizar_corte()
        if self.var_modo.get() == MODO_RAPIDO and self.info.get("tem_video"):
            self.log("Modo rapido: o corte de video so acontece nos pontos-chave da imagem, "
                     "entao o comeco pode sair alguns segundos antes do pedido.")

    # ------------------------------------------------- calculos da aba corte
    def _ler_campos(self):
        """Devolve (inicio, fim) em segundos. Levanta ValueError se nao entender."""
        return parse_tempo(self.var_ini.get()), parse_tempo(self.var_fim.get())

    def atualizar_corte(self):
        dur = self.info.get("duracao")

        try:
            ini = parse_tempo(self.var_ini.get())
            self.var_ini_lido.set("vazio = desde o inicio do arquivo" if ini is None
                                  else f"= {formatar_tempo(ini)}")
            erro_ini = False
        except ValueError as e:
            self.var_ini_lido.set(str(e))
            erro_ini = True

        try:
            fim = parse_tempo(self.var_fim.get())
            self.var_fim_lido.set("vazio = ate o fim do arquivo" if fim is None
                                  else f"= {formatar_tempo(fim)}")
            erro_fim = False
        except ValueError as e:
            self.var_fim_lido.set(str(e))
            erro_fim = True

        if erro_ini or erro_fim:
            self.var_resumo.set("")
            return
        if not dur:
            self.var_resumo.set("")
            return

        ini = ini or 0.0
        fim_real = dur if fim is None else min(fim, dur)
        if ini >= dur:
            self.var_resumo.set("O comeco esta depois do fim do arquivo.")
            return
        if fim is not None and fim <= ini:
            self.var_resumo.set("O fim precisa vir depois do comeco.")
            return

        tamanho = fim_real - ini
        aviso = ""
        if fim is not None and fim > dur:
            aviso = "  (o fim pedido passa do arquivo: vai ate o fim mesmo)"
        self.var_resumo.set(
            f"Vai gerar um arquivo de {formatar_tempo(tamanho)} "
            f"({formatar_tempo(ini)} ate {formatar_tempo(fim_real)}).{aviso}")

        if not self.destino_corte:
            self.var_destino.set(os.path.basename(self._destino_sugerido(ini, fim_real)))

    def _destino_sugerido(self, ini, fim):
        base = Path(self.origem)
        _, ext, _ = opcoes_saida(self.info, base.suffix.lower(), self.var_modo.get())
        nome = (f"{nome_limpo(base.stem)} - corte {formatar_tempo_arquivo(ini)} "
                f"a {formatar_tempo_arquivo(fim)}{ext}")
        return str(base.parent / nome)

    def escolher_destino(self):
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha primeiro o arquivo que voce quer cortar.")
            return
        try:
            ini, fim = self._ler_campos()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        dur = self.info.get("duracao") or 0
        sugerido = self._destino_sugerido(ini or 0, dur if fim is None else min(fim, dur))
        caminho = filedialog.asksaveasfilename(
            title="Salvar o trecho como",
            initialfile=os.path.basename(sugerido),
            initialdir=os.path.dirname(sugerido),
            defaultextension=Path(sugerido).suffix,
        )
        if caminho:
            self.destino_corte = caminho
            self.var_destino.set(caminho)

    # --------------------------------------------------- calculos da divisao
    def atualizar_divisao(self):
        dur = self.info.get("duracao")
        if not dur:
            self.var_previa.set("")
            return
        try:
            partes = calcular_partes(dur, self.var_criterio.get(),
                                     self.var_n.get(), self.var_min.get())
        except Exception:
            self.var_previa.set("")
            return
        if not partes:
            self.var_previa.set("")
            return

        n = len(partes)
        ultima = dur - partes[-1][0]
        if self.var_criterio.get() == "partes":
            self.var_previa.set(
                f"Vai gerar {n} partes de aproximadamente {formatar_tempo(dur / n)} cada.")
        elif n > 1 and abs(ultima - partes[0][1]) > 5:
            # A ultima parte quase sempre sobra menor: melhor dizer o tamanho dela.
            self.var_previa.set(
                f"Vai gerar {n} partes: {n - 1} de {formatar_tempo(partes[0][1])} "
                f"e a ultima de {formatar_tempo(ultima)}.")
        else:
            self.var_previa.set(
                f"Vai gerar {n} partes de aproximadamente {formatar_tempo(dur / n)} cada.")

    def escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Onde salvar as partes")
        if pasta:
            self.pasta_partes = pasta
            self.var_pasta.set(pasta)

    # ---------------------------------------------------------- acao: cortar
    def iniciar_corte(self):
        if self.trabalhando:
            return
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha primeiro o arquivo que voce quer cortar.")
            return
        dur = self.info.get("duracao")
        if not dur:
            messagebox.showerror(APP_NAME, "Nao consegui ler a duracao desse arquivo.")
            return
        try:
            ini, fim = self._ler_campos()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e))
            return

        ini = ini or 0.0
        if ini >= dur:
            messagebox.showerror(APP_NAME, "O comeco que voce escreveu esta depois do fim do arquivo.")
            return
        if fim is not None and fim <= ini:
            messagebox.showerror(APP_NAME, "O fim precisa vir depois do comeco.")
            return
        fim_real = dur if fim is None else min(fim, dur)
        duracao_trecho = fim_real - ini

        destino = self.destino_corte or self._destino_sugerido(ini, fim_real)
        if os.path.abspath(destino) == os.path.abspath(self.origem):
            messagebox.showerror(APP_NAME, "O arquivo de saida nao pode ser o mesmo da entrada.")
            return
        if os.path.exists(destino):
            if not messagebox.askyesno(APP_NAME, f"Ja existe um arquivo chamado\n"
                                                 f"{os.path.basename(destino)}\n\nSubstituir?"):
                return

        self._travar(True)
        self.cancelar.clear()
        # Tudo que vem da janela (modo, campos) e lido aqui, na thread da
        # interface. A thread de trabalho so recebe valores prontos: mexer em
        # variavel do Tkinter de outra thread da problema.
        threading.Thread(target=self._rodar_corte,
                         args=(ini, duracao_trecho if fim is not None else None,
                               fim_real, destino, self.var_modo.get()), daemon=True).start()

    def _rodar_corte(self, ini, duracao, fim_real, destino, modo):
        try:
            _, _, aviso = opcoes_saida(self.info, Path(self.origem).suffix.lower(), modo)
            self.log("=" * 60)
            self.log(f"Cortando de {formatar_tempo(ini)} ate {formatar_tempo(fim_real)} "
                     f"({formatar_tempo(fim_real - ini)}).")
            if aviso:
                self.log(aviso)
            self.status("Cortando...")
            self.progresso(0)

            os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
            ok = cortar(self.ffmpeg, self.origem, destino, ini, duracao,
                        self.info, modo, self.log, self.progresso, self.cancelar,
                        duracao_esperada=fim_real - ini)
            if not ok or self.cancelar.is_set():
                raise InterruptedError

            self.progresso(100)
            self.ultima_pasta = os.path.dirname(destino)
            saiu = ler_duracao(self.ffprobe, destino)
            tamanho = os.path.getsize(destino) if os.path.exists(destino) else 0
            self.log(f"Pronto: {os.path.basename(destino)} "
                     f"({formatar_tempo(saiu) if saiu else '?'}, {formatar_tamanho(tamanho)}).")
            if saiu and abs(saiu - (fim_real - ini)) > 1.5:
                self.log(f"Observacao: o trecho saiu com {formatar_tempo(saiu)} em vez de "
                         f"{formatar_tempo(fim_real - ini)}. No modo rapido isso e normal, "
                         f"porque o corte cai no ponto-chave mais proximo.")
            self.status("Corte concluido.")
            self.raiz.after(0, lambda: messagebox.showinfo(
                APP_NAME, f"Trecho salvo em:\n{destino}"))
        except InterruptedError:
            self.status("Cancelado.")
            self.log("Cancelado. O arquivo pela metade foi apagado.")
            try:
                if os.path.exists(destino):
                    os.remove(destino)
            except OSError:
                pass
        except Exception as e:
            self.status("Deu erro.")
            self.log(f"ERRO: {e}")
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    # --------------------------------------------------------- acao: dividir
    def iniciar_divisao(self):
        if self.trabalhando:
            return
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha primeiro o arquivo que voce quer dividir.")
            return
        dur = self.info.get("duracao")
        if not dur:
            messagebox.showerror(APP_NAME, "Nao consegui ler a duracao desse arquivo.")
            return
        partes = calcular_partes(dur, self.var_criterio.get(), self.var_n.get(), self.var_min.get())
        if len(partes) < 2:
            messagebox.showwarning(APP_NAME, "Do jeito que esta configurado sairia um arquivo so. "
                                             "Aumente o numero de partes ou diminua os minutos.")
            return
        os.makedirs(self.pasta_partes, exist_ok=True)
        self._travar(True)
        self.cancelar.clear()
        threading.Thread(target=self._rodar_divisao,
                         args=(partes, self.var_modo.get(), self.pasta_partes),
                         daemon=True).start()

    def _rodar_divisao(self, partes, modo, pasta_partes):
        try:
            ext_orig = Path(self.origem).suffix.lower()
            _, ext, aviso = opcoes_saida(self.info, ext_orig, modo)
            base = nome_limpo(Path(self.origem).stem)

            self.log("=" * 60)
            self.log(f"Dividindo em {len(partes)} partes.")
            if aviso:
                self.log(aviso)

            gerados = []
            total = len(partes)
            for i, (inicio, duracao) in enumerate(partes, start=1):
                if self.cancelar.is_set():
                    raise InterruptedError
                destino = os.path.join(pasta_partes, f"{i:02d}_{base}{ext}")
                self.status(f"Cortando a parte {i} de {total}...")
                self.log(f"  Parte {i}: de {formatar_tempo(inicio)} "
                         f"({formatar_tempo(duracao) if duracao else 'ate o fim'})")

                def prog_parcial(pct, i=i):
                    self.progresso(((i - 1) + pct / 100.0) / total * 100.0)

                ok = cortar(self.ffmpeg, self.origem, destino, inicio, duracao,
                            self.info, modo, self.log, prog_parcial, self.cancelar,
                            duracao_esperada=(self.info.get("duracao") or 0) - inicio)
                if not ok or self.cancelar.is_set():
                    raise InterruptedError
                gerados.append(destino)
                self.progresso(i / total * 100.0)

            self.progresso(100)
            self.ultima_pasta = pasta_partes
            soma = 0.0
            self.log("-" * 60)
            for caminho in gerados:
                d = ler_duracao(self.ffprobe, caminho)
                soma += d or 0
                tam = os.path.getsize(caminho) if os.path.exists(caminho) else 0
                self.log(f"  {os.path.basename(caminho)}  "
                         f"({formatar_tempo(d) if d else '?'}, {formatar_tamanho(tam)})")
            self.log("-" * 60)
            dur = self.info.get("duracao") or 0
            self.log(f"Soma das partes: {formatar_tempo(soma)}   |   "
                     f"Original: {formatar_tempo(dur)}   |   "
                     f"Diferenca: {abs(soma - dur):.2f}s")
            self.status(f"Pronto: {len(gerados)} partes geradas.")
            self.raiz.after(0, lambda: messagebox.showinfo(
                APP_NAME, f"{len(gerados)} partes geradas em:\n{pasta_partes}"))
        except InterruptedError:
            self.status("Cancelado.")
            self.log("Cancelado pelo usuario. As partes que ja tinham ficado prontas "
                     "continuam na pasta.")
        except Exception as e:
            self.status("Deu erro.")
            self.log(f"ERRO: {e}")
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    # ------------------------------------------------------------------ util
    def _travar(self, ligado):
        self.trabalhando = ligado
        acao = DISABLED if ligado else NORMAL
        cancel = NORMAL if ligado else DISABLED
        self.bt_cortar.configure(state=acao)
        self.bt_dividir.configure(state=acao)
        self.bt_cancelar_c.configure(state=cancel)
        self.bt_cancelar_d.configure(state=cancel)

    def pedir_cancelamento(self):
        self.cancelar.set()
        self.status("Cancelando...")

    def abrir_pasta(self, pasta):
        if not pasta or not os.path.isdir(pasta):
            messagebox.showinfo(APP_NAME, "Ainda nao ha pasta para abrir.")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            elif os.name == "nt":
                os.startfile(pasta)
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Nao consegui abrir a pasta.\n{e}")


def main():
    raiz = Tk()
    Aplicativo(raiz)
    atualizador.iniciar(raiz, "cortar-audio-video", APP_VERSION, "Cortar Audio e Video")
    raiz.mainloop()


if __name__ == "__main__":
    main()
