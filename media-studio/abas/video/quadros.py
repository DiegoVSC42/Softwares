"""
Extrair Quadros - aba do Estudio de Video.

Para que serve:
  - abre um video (normalmente vertical, de celular);
  - deixa escolher o trecho (comeco e fim) e quantos quadros por segundo;
  - mostra o quadro na tela com uma moldura que se arrasta e se redimensiona,
    na proporcao escolhida (16:9, 9:16, 1:1, 4:5 e outras), para escolher
    exatamente a area que vai ser aproveitada;
  - salva os quadros ja cortados, em PNG ou JPG, no tamanho pedido.

Notas de interface (macOS no modo escuro):
  - as cores vem todas de `tema.py`, que e quem pinta a janela inteira do
    Estudio; esta aba nao define estilo nenhum, so usa a paleta;
  - o canvas NAO usa "stipple" para escurecer area nenhuma: o Tk do Mac nao
    desenha stipple e a area sai preta solida, escondendo a imagem.

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.
"""

import os
import re
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from shutil import which
from tkinter import (
    Canvas, StringVar, DoubleVar, BooleanVar, END, DISABLED, NORMAL,
    PhotoImage, filedialog, messagebox, ttk, scrolledtext,
)

import pastas
import tema
from tema import (COR_FUNDO, COR_PAINEL, COR_CAMPO, COR_BOTAO,
                  COR_BOTAO_HOVER, COR_BORDA, COR_TEXTO, COR_SUAVE,
                  COR_APAGADO, COR_MOLDURA)

APP_NAME = "Extrair Quadros"
APP_VERSION = "1.7.0"

EXTENSOES_VIDEO = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v",
    ".mpg", ".mpeg", ".ts", ".3gp", ".wmv", ".flv",
}

PREVIEW_MAX_W = 460
# Altura de referencia do preview. Ela e o teto: `_limite_preview()` ainda
# reduz mais quando a janela esta baixa. Foi baixada de 430 para 320 para a
# aba inteira caber na tela sem barra de rolagem.
PREVIEW_MAX_H = 320

# Quadros por segundo da reproducao no preview. Nao e para ver filme: e para
# achar o ponto certo. 15 ja da a sensacao de video correndo e nao pesa a
# maquina, porque cada quadro passa cru (sem compressao) por um cano.
PLAY_FPS = 15.0

# Proporcoes disponiveis: rotulo, largura, altura. (0, 0) = a do proprio video.
PROPORCOES = [
    ("16:9  deitado (YouTube, TV, slide)", 16, 9),
    ("9:16  em pe (Reels, Stories, TikTok)", 9, 16),
    ("1:1  quadrado (feed)", 1, 1),
    ("4:5  retrato (feed do Instagram)", 4, 5),
    ("5:4  paisagem curta", 5, 4),
    ("4:3  classico", 4, 3),
    ("3:4  retrato classico", 3, 4),
    ("3:2  foto de camera", 3, 2),
    ("2:3  foto de camera em pe", 2, 3),
    ("21:9  cinema (bem largo)", 21, 9),
    ("2:1  banner largo", 2, 1),
    ("Livre  o quadro inteiro do video", 0, 0),
]

# Barra de ajuste fino: rotulo e quanto ela cobre para cada lado, em segundos.
# O rotulo mostra o trecho inteiro (os dois lados somados), que e o que a
# pessoa ve na tela.
ALCANCES = [
    ("trecho de 1 s", 0.5),
    ("trecho de 4 s", 2.0),
    ("trecho de 20 s", 10.0),
    ("trecho de 2 min", 60.0),
]

# Tamanho de saida: rotulo, largura final em pixels (0 = nao redimensiona).
TAMANHOS = [
    ("Do recorte (nao mexe no tamanho)", 0),
    ("Largura 3840 px (4K)", 3840),
    ("Largura 2560 px", 2560),
    ("Largura 1920 px (Full HD)", 1920),
    ("Largura 1440 px", 1440),
    ("Largura 1280 px (HD)", 1280),
    ("Largura 1080 px", 1080),
    ("Largura 720 px", 720),
    ("Largura 500 px", 500),
]


# ---------------------------------------------------------------------------
# Localizacao do ffmpeg / ffprobe
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def _achar_binario(nome: str):
    exe = f"{nome}.exe" if os.name == "nt" else nome
    for c in (resource_path(exe),
              resource_path(os.path.join("ffmpeg", exe)),
              resource_path(os.path.join("bin", exe))):
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    achado = which(nome)
    if achado:
        return achado

    extras = [
        "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
        "/opt/local/bin", str(Path.home() / "bin"),
    ]
    for pasta in extras:
        cand = os.path.join(pasta, exe)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def find_ffmpeg():
    return _achar_binario("ffmpeg")


def find_ffprobe():
    return _achar_binario("ffprobe")


def _sem_console():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si,
                "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _ler_ppm(fluxo):
    """Le UM quadro cru (PPM binario) do cano do ffmpeg.

    O PPM e o unico formato de imagem que o Tk le direto da memoria, sem
    biblioteca nenhuma: e por isso que a reproducao usa ele. O cabecalho e
    texto ("P6", largura, altura, valor maximo), separado por espaco ou quebra
    de linha, e comentario comeca com "#". Depois vem largura x altura x 3
    bytes de pixel.

    Devolve os bytes do quadro inteiro (cabecalho junto, que e como o Tk quer)
    ou None quando o video acabou.
    """
    def prox_campo():
        campo = b""
        while True:
            c = fluxo.read(1)
            if not c:
                return None
            if c == b"#":                      # comentario ate o fim da linha
                while c and c not in b"\r\n":
                    c = fluxo.read(1)
                continue
            if c.isspace():
                if campo:
                    return campo
                continue                       # espaco antes do campo
            campo += c

    cabecalho = b""
    magico = prox_campo()
    if magico != b"P6":
        return None
    cabecalho += magico + b"\n"

    numeros = []
    for _ in range(3):                         # largura, altura, valor maximo
        campo = prox_campo()
        if campo is None:
            return None
        numeros.append(campo)
    cabecalho += b" ".join(numeros) + b"\n"

    try:
        larg, alt = int(numeros[0]), int(numeros[1])
    except ValueError:
        return None

    faltando = larg * alt * 3
    corpo = b""
    while faltando > 0:
        pedaco = fluxo.read(faltando)
        if not pedaco:
            return None                        # cano fechou no meio do quadro
        corpo += pedaco
        faltando -= len(pedaco)
    return cabecalho + corpo


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------
def texto_para_segundos(txt: str):
    """Aceita 90, 1:30, 01:02:03, 1h05m, 2min30s. Devolve None se nao entender."""
    if txt is None:
        return None
    t = txt.strip().lower().replace(",", ".")
    if not t:
        return None

    if ":" in t:
        partes = t.split(":")
        if len(partes) > 3:
            return None
        try:
            valores = [float(p) if p.strip() else 0.0 for p in partes]
        except ValueError:
            return None
        total = 0.0
        for v in valores:
            total = total * 60 + v
        return total

    m = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*(?:min|m))?"
        r"\s*(?:(\d+(?:\.\d+)?)\s*(?:seg|s))?", t)
    if m and any(m.groups()):
        h = float(m.group(1) or 0)
        mi = float(m.group(2) or 0)
        s = float(m.group(3) or 0)
        return h * 3600 + mi * 60 + s

    try:
        return float(t)
    except ValueError:
        return None


def segundos_para_texto(seg: float) -> str:
    seg = max(0.0, float(seg))
    h = int(seg // 3600)
    m = int((seg % 3600) // 60)
    s = seg % 60
    if h:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m}:{s:05.2f}"


# ---------------------------------------------------------------------------
# Informacoes do video
# ---------------------------------------------------------------------------
def ler_info_video(ffmpeg, ffprobe, caminho):
    """Devolve dict com largura, altura, duracao, fps e se o video e HDR."""
    info = {"largura": 0, "altura": 0, "duracao": 0.0, "fps": 0.0,
            "transfer": "", "codec": ""}

    if ffprobe:
        try:
            saida = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries",
                 "stream=width,height,r_frame_rate,color_transfer,codec_name"
                 ":format=duration",
                 "-of", "default=noprint_wrappers=1", caminho],
                capture_output=True, text=True, timeout=60, **_sem_console()
            ).stdout
            for linha in saida.splitlines():
                if "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                chave, valor = chave.strip(), valor.strip()
                if chave == "width":
                    info["largura"] = int(float(valor))
                elif chave == "height":
                    info["altura"] = int(float(valor))
                elif chave == "duration" and valor not in ("N/A", ""):
                    info["duracao"] = float(valor)
                elif chave == "r_frame_rate" and "/" in valor:
                    a, b = valor.split("/", 1)
                    if float(b) > 0:
                        info["fps"] = float(a) / float(b)
                elif chave == "color_transfer":
                    info["transfer"] = valor
                elif chave == "codec_name":
                    info["codec"] = valor
        except Exception:
            pass

    if (not info["largura"] or not info["duracao"]) and ffmpeg:
        try:
            texto = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", caminho],
                capture_output=True, text=True, timeout=60, **_sem_console()
            ).stderr
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", texto)
            if m and not info["duracao"]:
                info["duracao"] = (int(m.group(1)) * 3600 +
                                   int(m.group(2)) * 60 + float(m.group(3)))
            m = re.search(r",\s*(\d{2,5})x(\d{2,5})", texto)
            if m and not info["largura"]:
                info["largura"] = int(m.group(1))
                info["altura"] = int(m.group(2))
            m = re.search(r"(\d+(?:\.\d+)?)\s*fps", texto)
            if m and not info["fps"]:
                info["fps"] = float(m.group(1))
        except Exception:
            pass

    return info


def medir_quadro(ffmpeg, caminho, pasta_tmp, momento=0.0):
    """Extrai um quadro e le a largura/altura do PNG gerado.

    Isso e mais confiavel do que o ffprobe quando o video vem de celular:
    videos gravados de lado guardam a rotacao nos metadados, e o quadro que
    o filtro de corte enxerga ja vem girado. Medindo o quadro de verdade, o
    corte cai sempre no lugar certo.
    """
    destino = os.path.join(pasta_tmp, "_medida.png")
    try:
        subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
             "-ss", f"{max(0.0, momento):.3f}", "-i", caminho,
             "-frames:v", "1", "-y", destino],
            capture_output=True, timeout=120, **_sem_console())
        with open(destino, "rb") as f:
            dados = f.read(32)
        if dados[:8] == b"\x89PNG\r\n\x1a\n":
            largura = int.from_bytes(dados[16:20], "big")
            altura = int.from_bytes(dados[20:24], "big")
            if largura > 0 and altura > 0:
                return largura, altura
    except Exception:
        pass
    finally:
        try:
            os.remove(destino)
        except Exception:
            pass
    return 0, 0


def tem_filtro(ffmpeg, nome) -> bool:
    """Diz se este ffmpeg foi compilado com um filtro (ex.: zscale)."""
    try:
        saida = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                               capture_output=True, text=True, timeout=30,
                               **_sem_console()).stdout
        return any(linha.split()[1] == nome
                   for linha in saida.splitlines()
                   if len(linha.split()) > 1)
    except Exception:
        return False


def e_hdr(info) -> bool:
    """HDR de celular e de camera moderna: PQ (smpte2084) ou HLG."""
    return info.get("transfer", "") in ("smpte2084", "arib-std-b67")


def par(n) -> int:
    n = int(round(n))
    return n if n % 2 == 0 else n - 1


# ---------------------------------------------------------------------------
# Aplicativo
# ---------------------------------------------------------------------------
class App:
    def __init__(self, pai):
        self.raiz = pai
        self.raiz.configure(bg=COR_FUNDO)

        self.ffmpeg = find_ffmpeg()
        self.ffprobe = find_ffprobe()
        self._tem_zscale = tem_filtro(self.ffmpeg, "zscale") if self.ffmpeg else False
        self._ultimo_erro_prev = ""

        self.origem = ""
        self.info = {"largura": 0, "altura": 0, "duracao": 0.0, "fps": 0.0}
        self.escala = 1.0          # video -> preview
        self.prev_w = 0
        self.prev_h = 0
        self.imagem = None         # PhotoImage viva
        self.tmpdir = tempfile.mkdtemp(prefix="extrair_quadros_")

        # Preview ao vivo: uma unica thread trabalhadora, que ao terminar um
        # quadro pega sempre o pedido MAIS RECENTE e joga fora os do meio.
        # Assim a imagem corre junto com o arrasto do slider, sem formar fila
        # de quadros atrasados e sem disparar dez ffmpeg ao mesmo tempo.
        self.preview_seq = 0
        self._prev_exibido = 0
        self._prev_pedido = None
        self._prev_evento = threading.Event()
        self._prev_proc = None
        self._prev_lock = threading.Lock()
        self._prev_fim = False
        self._prev_thread = threading.Thread(target=self._worker_preview,
                                             daemon=True)
        self._prev_thread.start()

        # Reproducao (botao Assistir). O ffmpeg despeja os quadros crus num
        # cano, uma thread le e a janela troca a imagem no compasso. A
        # "geracao" e o que invalida thread e temporizador de uma tocada
        # anterior: sem ela, pausar e tocar de novo depressa deixaria dois
        # players brigando pela mesma tela.
        self._tocando = False
        self._play_geracao = 0
        self._play_proc = None
        # Fila COM LIMITE e com espera: e ela que segura o ffmpeg no ritmo do
        # video. Sem limite (ou descartando quadro para caber mais), o ffmpeg
        # decodifica o video inteiro em segundos e a tela recebe quadros
        # salteados, o que faz o video passar voando.
        self._play_fila = queue.Queue(maxsize=8)
        self._play_id = None
        self._play_pos = 0.0
        self._play_inicio = 0.0
        self._play_fps = PLAY_FPS
        self._play_t0 = 0.0          # relogio de parede do inicio da tocada
        self._play_proximo = None    # quadro ja tirado da fila, esperando a hora
        self._avisou_ppm = False

        # Espera antes de refazer o quadro quando a janela muda de tamanho.
        self._redimensionar_id = None

        # Ajuste fino: o slider fino desloca em torno desta base.
        # Trecho do video coberto pela barra de ajuste fino.
        self.jan_ini = 0.0
        self.jan_fim = 1.0

        # Recorte em coordenadas do VIDEO
        self.crop_w = 0
        self.crop_h = 0
        self.crop_x = 0
        self.crop_y = 0
        self._arrastando = False
        self._ax = 0
        self._ay = 0

        self.processo = None
        self.cancelar = False
        self.rodando = False

        # O estilo e global, aplicado uma vez pelo Estudio; aqui so se pegam
        # as fontes para os widgets Tk puros (canvas e caixa de mensagens).
        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self._montar()
        if not self.ffmpeg:
            self.log("ATENCAO: ffmpeg nao encontrado nesta maquina. "
                     "O programa nao vai conseguir ler nem cortar video.")

    # -------------------------------------------------- interface
    def _montar(self):
        topo = ttk.Frame(self.raiz)
        topo.pack(fill="x", padx=14, pady=(8, 4))
        ttk.Button(topo, text="Escolher video...",
                   command=self.escolher_video).pack(side="left")
        self.lbl_arquivo = ttk.Label(topo, text="Nenhum video escolhido.",
                                     style="Suave.TLabel")
        self.lbl_arquivo.pack(side="left", padx=10)

        corpo = ttk.Frame(self.raiz)
        corpo.pack(fill="both", expand=True, padx=14, pady=4)

        # ---------- esquerda: preview
        esq = ttk.LabelFrame(corpo, text="Preview e enquadramento ")
        esq.pack(side="left", fill="y", padx=(0, 14))
        self.frm_esq = esq

        # Os controles vao num quadro proprio, ancorado no FUNDO e empacotado
        # ANTES do canvas. No Tk, quando falta altura, quem foi empacotado por
        # ultimo e cortado primeiro -- e antes o cortado era justamente a
        # barra de posicao e os botoes de avanco, que sumiam embaixo. Assim a
        # imagem e que cede espaco, e os controles ficam sempre na tela.
        controles = ttk.Frame(esq)
        controles.pack(side="bottom", fill="x")
        self.frm_controles = controles

        # Trava a largura da coluna. Sem isto, um video bem em pe (9:16) deixa
        # o canvas estreito, a coluna encolhe junto e os quatro botoes de
        # avanco ficam espremidos um sobre o outro.
        ttk.Frame(controles, width=PREVIEW_MAX_W + 4, height=1).pack(side="top")

        self.canvas = Canvas(esq, width=PREVIEW_MAX_W, height=PREVIEW_MAX_H,
                             bg="#000000", highlightthickness=0)
        self.canvas.pack(padx=8, pady=(6, 8), fill="both", expand=True)
        self.canvas.bind("<Configure>", self._reajustar_preview)
        self.canvas.bind("<ButtonPress-1>", self._mouse_desce)
        self.canvas.bind("<B1-Motion>", self._mouse_arrasta)
        self.canvas.bind("<ButtonRelease-1>", self._mouse_sobe)

        # ----- posicao: digitar o tempo
        linha = ttk.Frame(controles)
        linha.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(linha, text="Ir para:", style="Suave.TLabel").pack(side="left")
        self.var_tempo = StringVar(value="0:00.00")
        ent = ttk.Entry(linha, textvariable=self.var_tempo, width=10,
                        justify="center")
        ent.pack(side="left", padx=6)
        ent.bind("<Return>", self._ir_para)
        ent.bind("<KP_Enter>", self._ir_para)
        ttk.Button(linha, text="Ir", width=4,
                   command=self._ir_para).pack(side="left")
        self.lbl_pos = ttk.Label(linha, text="quadro 0", style="Destaque.TLabel")
        self.lbl_pos.pack(side="right")

        # ----- posicao: percorrer o video inteiro
        ttk.Label(controles, text="Percorrer o video inteiro:",
                  style="Suave.TLabel").pack(anchor="w", padx=10)
        self.var_pos = DoubleVar(value=0.0)
        self.sld_pos = ttk.Scale(controles, from_=0, to=100, variable=self.var_pos)
        self.sld_pos.pack(fill="x", padx=10, pady=(0, 4))
        self.sld_pos.bind("<ButtonRelease-1>", self._geral_solto)
        # Observador na variavel, e nao "command" do Scale: o command so
        # dispara quando a pessoa mexe naquele widget, entao mudanca vinda do
        # ajuste fino, do campo de tempo ou dos botoes passaria despercebida.
        self.var_pos.trace_add("write", lambda *a: self._pos_mudou())

        # ----- posicao: ajuste fino (a mesma posicao, num trecho curto)
        linha = ttk.Frame(controles)
        linha.pack(fill="x", padx=10)
        ttk.Label(linha, text="Ajuste fino:",
                  style="Suave.TLabel").pack(side="left")
        self.var_alcance = StringVar(value=ALCANCES[1][0])
        cba = ttk.Combobox(linha, textvariable=self.var_alcance, width=14,
                           state="readonly", values=[a[0] for a in ALCANCES])
        cba.pack(side="right")
        cba.bind("<<ComboboxSelected>>", lambda e: self._recentrar_janela())
        ttk.Button(linha, text="Recentrar", width=10,
                   command=self._recentrar_janela).pack(side="right", padx=6)

        # A barra fina mexe na MESMA posicao da barra de cima; a diferenca e
        # que ela cobre so um trecho curto, entao cada pixel vale bem menos
        # tempo. Nao volta ao centro: onde ela esta e onde o video esta.
        self.sld_fino = ttk.Scale(controles, from_=0.0, to=1.0, variable=self.var_pos)
        self.sld_fino.pack(fill="x", padx=10, pady=(0, 2))

        pontas = ttk.Frame(controles)
        pontas.pack(fill="x", padx=10)
        self.lbl_jan_ini = ttk.Label(pontas, text="0:00.00", style="Suave.TLabel")
        self.lbl_jan_ini.pack(side="left")
        self.lbl_jan_fim = ttk.Label(pontas, text="0:00.00", style="Suave.TLabel")
        self.lbl_jan_fim.pack(side="right")

        # ----- assistir ao video ate o ponto certo
        # Vale a pena ter: achar o quadro arrastando barrinha e chutando
        # minutagem e trabalhoso. Assistindo, a pessoa pausa exatamente onde
        # quer e o recorte comeca dali.
        play = ttk.Frame(controles)
        play.pack(padx=10, pady=(6, 0))
        self.btn_play = ttk.Button(play, text="▶  Assistir", width=12,
                                   command=self._play_pause, state=DISABLED)
        self.btn_play.pack(side="left", padx=2)
        ttk.Label(play, text="pausa onde voce quiser (sem som)",
                  style="Suave.TLabel").pack(side="left", padx=(8, 0))

        nav = ttk.Frame(controles)
        nav.pack(padx=10, pady=(6, 4))
        ttk.Button(nav, text="<< 1s", width=6,
                   command=lambda: self._pular(-1)).pack(side="left", padx=2)
        ttk.Button(nav, text="< quadro", width=9,
                   command=lambda: self._pular(-1, quadro=True)).pack(side="left", padx=2)
        ttk.Button(nav, text="quadro >", width=9,
                   command=lambda: self._pular(1, quadro=True)).pack(side="left", padx=2)
        ttk.Button(nav, text="1s >>", width=6,
                   command=lambda: self._pular(1)).pack(side="left", padx=2)

        # A dica de arrastar a moldura saiu daqui: ocupava uma linha inteira e
        # o gesto se descobre na hora, arrastando a moldura no proprio preview.
        zf = ttk.Frame(controles)
        zf.pack(fill="x", padx=10, pady=(2, 0))
        ttk.Label(zf, text="Tamanho da moldura:",
                  style="Suave.TLabel").pack(side="left")
        self.lbl_zoom = ttk.Label(zf, text="100%", style="Destaque.TLabel")
        self.lbl_zoom.pack(side="right")
        self.var_zoom = DoubleVar(value=100.0)
        # A reacao fica presa na VARIAVEL, nao no `command=` do Scale: o
        # `command` so dispara quando a pessoa arrasta este widget, e o zoom
        # tambem muda por codigo (ao trocar de proporcao, ao abrir outro
        # video). Com o trace, a moldura reage nos dois casos.
        ttk.Scale(controles, from_=15, to=100,
                  variable=self.var_zoom).pack(fill="x", padx=10, pady=(0, 6))
        self.var_zoom.trace_add("write", lambda *a: self._zoom_mudou())

        # ---------- direita: controles
        dir_ = ttk.Frame(corpo)
        dir_.pack(side="left", fill="both", expand=True)

        # --- video e enquadramento (um quadro so)
        # Antes eram dois quadros pequenos, um debaixo do outro. Cada quadro
        # cobra borda, titulo e espaco em volta; juntos, sobra altura para a
        # aba caber na tela sem barra de rolagem.
        enq = ttk.LabelFrame(dir_, text="Video e enquadramento ")
        enq.pack(fill="x")

        self.lbl_info = ttk.Label(enq, text="-", style="Suave.TLabel")
        self.lbl_info.pack(anchor="w", padx=12, pady=(6, 2))

        linha = ttk.Frame(enq)
        linha.pack(fill="x", padx=12, pady=2)
        ttk.Label(linha, text="Proporcao:", width=11).pack(side="left")
        self.var_prop = StringVar(value=PROPORCOES[0][0])
        cb = ttk.Combobox(linha, textvariable=self.var_prop, width=34,
                          state="readonly",
                          values=[p[0] for p in PROPORCOES])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._proporcao_mudou)

        self.lbl_recorte = ttk.Label(enq, text="-", style="Suave.TLabel")
        self.lbl_recorte.pack(anchor="w", padx=12, pady=(2, 6))

        # --- trecho
        trecho = ttk.LabelFrame(dir_, text="Trecho e quantidade ")
        trecho.pack(fill="x", pady=(6, 0))

        linha = ttk.Frame(trecho)
        linha.pack(fill="x", padx=12, pady=(6, 2))
        ttk.Label(linha, text="Comeco:", width=11).pack(side="left")
        self.var_ini = StringVar()
        ttk.Entry(linha, textvariable=self.var_ini, width=11).pack(side="left")
        ttk.Button(linha, text="posicao atual",
                   command=lambda: self._marcar("ini")).pack(side="left", padx=8)
        ttk.Label(linha, text="vazio = inicio",
                  style="Suave.TLabel").pack(side="left")

        linha = ttk.Frame(trecho)
        linha.pack(fill="x", padx=12, pady=2)
        ttk.Label(linha, text="Fim:", width=11).pack(side="left")
        self.var_fim = StringVar()
        entrada_fim = ttk.Entry(linha, textvariable=self.var_fim, width=11)
        entrada_fim.pack(side="left")
        entrada_fim.bind("<Key>", self._fim_editado_a_mao)
        ttk.Button(linha, text="posicao atual",
                   command=lambda: self._marcar("fim")).pack(side="left", padx=8)
        ttk.Label(linha, text="vazio = ate o fim",
                  style="Suave.TLabel").pack(side="left")

        linha = ttk.Frame(trecho)
        linha.pack(fill="x", padx=12, pady=2)
        ttk.Label(linha, text="Duracao:", width=11).pack(side="left")
        self.var_duracao = StringVar()
        ttk.Entry(linha, textvariable=self.var_duracao, width=11).pack(side="left")
        ttk.Label(linha, text="preencha para o Fim se ajustar sozinho "
                  "(Comeco + Duracao)",
                  style="Suave.TLabel").pack(side="left", padx=8)

        linha = ttk.Frame(trecho)
        linha.pack(fill="x", padx=12, pady=2)
        ttk.Label(linha, text="Quadros/s:", width=11).pack(side="left")
        self.var_fps = StringVar(value="1")
        ttk.Combobox(linha, textvariable=self.var_fps, width=8,
                     values=["0.2", "0.5", "1", "2", "4", "5", "10", "todos"]
                     ).pack(side="left")
        ttk.Label(linha, text="1 = um por segundo",
                  style="Suave.TLabel").pack(side="left", padx=8)

        for v in (self.var_ini, self.var_fim, self.var_fps):
            v.trace_add("write", lambda *a: self._estimar())
        # A Duracao reage ao Comeco tambem: se ele mudar (digitando, no
        # "posicao atual" ou nas setinhas) com uma duracao preenchida, o
        # Fim anda junto, mantendo o mesmo tamanho de trecho.
        self.var_ini.trace_add("write", self._duracao_mudou)
        self.var_duracao.trace_add("write", self._duracao_mudou)

        self.lbl_estimativa = ttk.Label(trecho, text="-", style="Suave.TLabel")
        self.lbl_estimativa.pack(anchor="w", padx=12, pady=(2, 6))

        # --- saida
        saida = ttk.LabelFrame(dir_, text="Saida ")
        saida.pack(fill="x", pady=(6, 0))

        linha = ttk.Frame(saida)
        linha.pack(fill="x", padx=12, pady=(6, 2))
        ttk.Label(linha, text="Formato:", width=11).pack(side="left")
        self.var_formato = StringVar(value="JPG (bem menor, otimo para a maioria)")
        ttk.Combobox(linha, textvariable=self.var_formato, width=34,
                     state="readonly",
                     values=["JPG (bem menor, otimo para a maioria)",
                             "PNG (sem perda, arquivo maior)"]).pack(side="left")

        linha = ttk.Frame(saida)
        linha.pack(fill="x", padx=12, pady=2)
        ttk.Label(linha, text="Tamanho:", width=11).pack(side="left")
        self.var_tamanho = StringVar(value=TAMANHOS[0][0])
        cbt = ttk.Combobox(linha, textvariable=self.var_tamanho, width=34,
                           state="readonly", values=[t[0] for t in TAMANHOS])
        cbt.pack(side="left")
        cbt.bind("<<ComboboxSelected>>", lambda e: self._estimar())

        linha = ttk.Frame(saida)
        linha.pack(fill="x", padx=12, pady=(2, 0))
        ttk.Label(linha, text="Pasta:", width=11).pack(side="left")
        self.var_pasta = StringVar()
        # Verdadeiro enquanto a pasta na tela e so uma SUGESTAO nossa (do
        # nome do video), nunca uma escolha da pessoa. So nesse estado a
        # troca de video pode atualizar a pasta sozinha; assim que a pessoa
        # digita ou usa "Escolher...", a pasta passa a ser dela, e videos
        # seguintes nao pisam mais em cima.
        self._pasta_automatica = True
        entrada_pasta = ttk.Entry(linha, textvariable=self.var_pasta)
        entrada_pasta.pack(side="left", fill="x", expand=True)
        entrada_pasta.bind("<Key>", self._marcar_pasta_manual)
        ttk.Button(linha, text="Escolher...",
                   command=self.escolher_pasta).pack(side="left", padx=(8, 0))

        linha = ttk.Frame(saida)
        linha.pack(fill="x", padx=12, pady=(2, 6))
        # Os arquivos continuam soltos na pasta, do jeito de sempre; o zip e
        # so uma copia extra, compactada, com o mesmo nome dela, para quem
        # precisa mandar tudo junto (WhatsApp, e-mail, upload).
        self.var_zip = BooleanVar(value=False)
        ttk.Checkbutton(linha, text="Tambem gerar um .zip da pasta "
                        "(mesmo nome dela)",
                        variable=self.var_zip).pack(side="left")

        acao = ttk.Frame(dir_)
        acao.pack(fill="x", pady=(10, 0))
        self.btn_extrair = ttk.Button(acao, text="Extrair quadros",
                                      style="Acao.TButton",
                                      command=self.iniciar)
        self.btn_extrair.pack(side="left")
        self.btn_cancelar = ttk.Button(acao, text="Cancelar",
                                       command=self.pedir_cancelar,
                                       state=DISABLED)
        self.btn_cancelar.pack(side="left", padx=8)
        self.btn_abrir = ttk.Button(acao, text="Abrir pasta",
                                    command=self.abrir_pasta, state=DISABLED)
        self.btn_abrir.pack(side="left")

        self.barra = ttk.Progressbar(dir_, mode="determinate", maximum=100)
        self.barra.pack(fill="x", pady=(8, 2))
        self.lbl_status = ttk.Label(dir_, text="Pronto.", style="Suave.TLabel")
        self.lbl_status.pack(anchor="w")

        self.txt = scrolledtext.ScrolledText(
            dir_, height=3, bg=COR_PAINEL, fg=COR_TEXTO,
            insertbackground=COR_TEXTO, selectbackground=COR_MOLDURA,
            selectforeground="#1a1a1a", relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=COR_BORDA,
            font=self.fonte_peq)
        self.txt.pack(fill="both", expand=True, pady=(4, 0))
        self.txt.configure(state=DISABLED)

    # -------------------------------------------------- utilidades
    def log(self, msg):
        self.txt.configure(state=NORMAL)
        self.txt.insert(END, msg + "\n")
        self.txt.see(END)
        self.txt.configure(state=DISABLED)

    def status(self, msg):
        self.lbl_status.configure(text=msg)

    # -------------------------------------------------- abrir video
    def escolher_video(self):
        if self.rodando:
            return
        caminho = filedialog.askopenfilename(
            title="Escolha o video",
            filetypes=[("Videos", " ".join(f"*{e}" for e in sorted(EXTENSOES_VIDEO))),
                       ("Todos os arquivos", "*.*")],
            parent=self.raiz.winfo_toplevel())
        if not caminho:
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado nesta maquina.",
                                 parent=self.raiz.winfo_toplevel())
            return

        self.origem = caminho
        self.lbl_arquivo.configure(text=os.path.basename(caminho))
        self.status("Lendo o video...")
        self.raiz.update_idletasks()

        self.info = ler_info_video(self.ffmpeg, self.ffprobe, caminho)

        # Dimensoes reais do quadro decodificado (respeita video girado).
        rw, rh = medir_quadro(self.ffmpeg, caminho, self.tmpdir,
                              min(1.0, self.info["duracao"] / 2 or 0.0))
        if rw and rh:
            if (rw, rh) != (self.info["largura"], self.info["altura"]):
                self.log(f"Video girado nos metadados: usando {rw} x {rh} "
                         f"(o cabecalho dizia {self.info['largura']} x "
                         f"{self.info['altura']}).")
            self.info["largura"], self.info["altura"] = rw, rh

        vw, vh, dur = self.info["largura"], self.info["altura"], self.info["duracao"]
        if not vw or not vh:
            messagebox.showerror(APP_NAME,
                                 "Nao consegui ler as dimensoes desse video.",
                                 parent=self.raiz.winfo_toplevel())
            self.status("Pronto.")
            return

        if e_hdr(self.info):
            self.log("Video HDR (" + self.info.get("transfer", "") + "): "
                     "convertendo a cor para a faixa normal" +
                     ("" if self._tem_zscale else
                      " -- este ffmpeg nao tem o filtro zscale, a cor pode "
                      "ficar diferente da do celular"))

        fps = self.info["fps"]
        texto = f"{vw} x {vh}  •  {segundos_para_texto(dur)}"
        if fps:
            texto += f"  •  {fps:.2f} quadros/s"
        self.lbl_info.configure(text=texto)

        lim_w, lim_h = self._limite_preview()
        self.escala = min(lim_w / vw, lim_h / vh)
        self.prev_w = max(1, int(vw * self.escala))
        self.prev_h = max(1, int(vh * self.escala))
        self.canvas.configure(width=self.prev_w, height=self.prev_h)

        self.sld_pos.configure(to=max(dur, 0.1))
        self._prev_exibido = 0
        self.var_pos.set(0.0)
        self.var_tempo.set("0:00.00")
        self.lbl_pos.configure(text="quadro 0")
        self._recentrar_janela()
        self.var_zoom.set(100.0)
        self.lbl_zoom.configure(text="100%")

        if not self.var_pasta.get() or self._pasta_automatica:
            # Regra da casa: a saida padrao fica na pasta de Downloads,
            # numa subpasta com o nome do video, para os quadros de cada
            # video nao se misturarem. So mexe aqui enquanto a pasta na
            # tela ainda for a nossa sugestao (ver `_pasta_automatica`);
            # uma pasta que a pessoa escolheu nunca e trocada sozinha.
            self.var_pasta.set(str(Path(pastas.pasta_downloads()) /
                                   (Path(caminho).stem + " - quadros")))
            self._pasta_automatica = True

        self._recalcular_crop(manter_centro=False)
        self.atualizar_preview()
        self._estimar()
        self.btn_play.configure(state=NORMAL)
        self.status("Pronto.")
        self.log(f"Video carregado: {os.path.basename(caminho)}")

    def escolher_pasta(self):
        pasta = filedialog.askdirectory(
            title="Onde salvar os quadros",
            initialdir=self.var_pasta.get() or pastas.pasta_downloads(),
            parent=self.raiz.winfo_toplevel())
        if pasta:
            self._pasta_automatica = False
            self.var_pasta.set(pasta)

    def _marcar_pasta_manual(self, _evento=None):
        self._pasta_automatica = False

    def _limite_preview(self):
        """Maior imagem que cabe na area do preview AGORA.

        Nao basta usar PREVIEW_MAX_W/H fixos: a janela pode estar menor ou
        MUITO maior, e a fonte do Mac e maior que a do Windows, entao os
        controles ocupam alturas diferentes em cada maquina.

        Antes esta funcao devolvia a largura fixa de PREVIEW_MAX_W e limitava
        a altura ao PREVIEW_MAX_H. Como o canvas e empacotado com
        `fill="both", expand=True`, ele cresce com a janela, mas a imagem
        continuava pequena: sobrava muito preto em volta, sobretudo em video
        em pe (9:16). Agora a medida vem do proprio canvas, que e onde a
        imagem realmente cabe, e os valores fixos passam a ser so o ponto de
        partida de antes de a tela existir.
        """
        larg, alt = PREVIEW_MAX_W, PREVIEW_MAX_H
        try:
            self.canvas.update_idletasks()
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            # winfo_* devolve 1 enquanto o widget ainda nao foi desenhado;
            # nesse caso ficamos com os valores de referencia.
            if cw > 80:
                larg = cw
            if ch > 80:
                alt = ch
            else:
                # Canvas ainda sem altura: calcula pelo espaco que sobra na
                # coluna depois dos controles, como era feito antes.
                self.frm_esq.update_idletasks()
                disp_h = (self.frm_esq.winfo_height()
                          - self.frm_controles.winfo_height() - 28)
                if disp_h > 80:
                    alt = disp_h
        except Exception:
            pass
        return max(120, larg), max(120, alt)

    def _reajustar_preview(self, _evento=None):
        """Recalcula o tamanho da imagem quando a area do preview muda.

        Sem isto, esticar a janela so aumentava a area preta: a escala era
        decidida uma vez, ao abrir o video, e nunca mais. O pedido de quadro
        novo sai com um respiro para nao disparar dezenas de ffmpeg enquanto
        a pessoa ainda esta arrastando a borda da janela.
        """
        if not self.origem or self._tocando:
            # Tocando, o tamanho da imagem esta combinado com o ffmpeg que
            # esta no ar: mudar agora quebraria o quadro no meio do caminho.
            return
        vw = self.info.get("largura") or 0
        vh = self.info.get("altura") or 0
        if not vw or not vh:
            return

        lim_w, lim_h = self._limite_preview()
        nova = min(lim_w / vw, lim_h / vh)
        # Mudanca insignificante nao vale um quadro novo.
        if abs(nova - self.escala) < 0.005:
            return

        self.escala = nova
        self.prev_w = max(1, int(vw * nova))
        self.prev_h = max(1, int(vh * nova))

        if self._redimensionar_id is not None:
            try:
                self.raiz.after_cancel(self._redimensionar_id)
            except Exception:
                pass
        self._redimensionar_id = self.raiz.after(250, self._apos_redimensionar)

    def _apos_redimensionar(self):
        self._redimensionar_id = None
        self._desenhar_moldura()
        self.atualizar_preview()

    def _centro_imagem(self):
        """Canto superior esquerdo da imagem dentro do canvas.

        O canvas ocupa a coluna inteira, e a imagem quase nunca tem a mesma
        forma: sobra espaco de um lado ou do outro. Desenhar a imagem no
        canto (0, 0) jogava tudo para cima e para a esquerda, com o preto
        todo junto embaixo e a direita. Centralizando, a sobra fica dividida
        e o preview parece o que e: uma tela de video.
        """
        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
        except Exception:
            cw = ch = 0
        if cw < 2 or ch < 2:
            return 0, 0
        return max(0, (cw - self.prev_w) // 2), max(0, (ch - self.prev_h) // 2)

    # -------------------------------------------------- recorte
    def _proporcao_atual(self):
        """Devolve a razao largura/altura pedida (a do video, se for Livre)."""
        rotulo = self.var_prop.get()
        for nome, a, b in PROPORCOES:
            if nome == rotulo:
                if a and b:
                    return a / b
                break
        vw, vh = self.info["largura"], self.info["altura"]
        return (vw / vh) if (vw and vh) else 16 / 9

    def _crop_max(self):
        vw, vh = self.info["largura"], self.info["altura"]
        if not vw or not vh:
            return 0, 0
        razao = self._proporcao_atual()
        cw = vw
        ch = cw / razao
        if ch > vh:
            ch = vh
            cw = ch * razao
        return par(cw), par(ch)

    def _recalcular_crop(self, manter_centro=True):
        maxw, maxh = self._crop_max()
        if not maxw:
            return
        cx_ant = self.crop_x + self.crop_w / 2 if self.crop_w else None
        cy_ant = self.crop_y + self.crop_h / 2 if self.crop_h else None

        razao = self._proporcao_atual()
        fator = max(0.05, min(1.0, self.var_zoom.get() / 100.0))
        self.crop_w = max(16, par(maxw * fator))
        self.crop_h = max(16, par(self.crop_w / razao))
        if self.crop_h > maxh:
            self.crop_h = maxh
            self.crop_w = max(16, par(self.crop_h * razao))

        vw, vh = self.info["largura"], self.info["altura"]
        if manter_centro and cx_ant is not None:
            self.crop_x = int(cx_ant - self.crop_w / 2)
            self.crop_y = int(cy_ant - self.crop_h / 2)
        else:
            self.crop_x = int((vw - self.crop_w) / 2)
            self.crop_y = int((vh - self.crop_h) / 2)
        self._limitar_crop()

    def _limitar_crop(self):
        vw, vh = self.info["largura"], self.info["altura"]
        self.crop_x = max(0, min(int(self.crop_x), vw - self.crop_w))
        self.crop_y = max(0, min(int(self.crop_y), vh - self.crop_h))

    def _proporcao_mudou(self, _=None):
        if not self.origem:
            return
        self._recalcular_crop(manter_centro=True)
        self._desenhar_moldura()
        self._estimar()

    def _zoom_mudou(self, _=None):
        if not self.origem:
            return
        self.lbl_zoom.configure(text=f"{int(self.var_zoom.get())}%")
        self._recalcular_crop(manter_centro=True)
        self._desenhar_moldura()
        self._estimar()

    def _mouse_desce(self, ev):
        if not self.origem:
            return
        ox, oy = self._centro_imagem()
        x = (ev.x - ox) / self.escala
        y = (ev.y - oy) / self.escala
        if (self.crop_x <= x <= self.crop_x + self.crop_w and
                self.crop_y <= y <= self.crop_y + self.crop_h):
            self._ax = x - self.crop_x
            self._ay = y - self.crop_y
        else:
            self.crop_x = int(x - self.crop_w / 2)
            self.crop_y = int(y - self.crop_h / 2)
            self._limitar_crop()
            self._ax = self.crop_w / 2
            self._ay = self.crop_h / 2
            self._desenhar_moldura()
        self._arrastando = True

    def _mouse_arrasta(self, ev):
        if not self._arrastando:
            return
        ox, oy = self._centro_imagem()
        self.crop_x = int((ev.x - ox) / self.escala - self._ax)
        self.crop_y = int((ev.y - oy) / self.escala - self._ay)
        self._limitar_crop()
        self._desenhar_moldura()

    def _mouse_sobe(self, _):
        self._arrastando = False

    def _desenhar_moldura(self):
        """Desenha so a moldura, sem escurecer nada.

        O Tk do macOS ignora o parametro 'stipple' do canvas: qualquer
        retangulo "meio transparente" sairia preto solido e taparia a imagem.
        Por isso a area de fora fica normal e a marcacao e feita com linhas.
        """
        self.canvas.delete("moldura")
        if not self.origem or not self.crop_w:
            return
        e = self.escala
        # A moldura e desenhada sobre a imagem, que esta centralizada no
        # canvas: sem somar o deslocamento, ela apareceria deslocada dela.
        ox, oy = self._centro_imagem()
        x1, y1 = ox + self.crop_x * e, oy + self.crop_y * e
        x2, y2 = (ox + (self.crop_x + self.crop_w) * e,
                  oy + (self.crop_y + self.crop_h) * e)

        # Contorno escuro por baixo, para a moldura aparecer em cena clara.
        self.canvas.create_rectangle(x1 - 2, y1 - 2, x2 + 2, y2 + 2,
                                     outline="#000000", width=3, tags="moldura")
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=COR_MOLDURA,
                                     width=3, tags="moldura")

        # Linhas dos tercos, para ajudar a compor.
        for i in (1, 2):
            xt = x1 + (x2 - x1) * i / 3
            yt = y1 + (y2 - y1) * i / 3
            self.canvas.create_line(xt, y1, xt, y2, fill=COR_MOLDURA,
                                    width=1, dash=(3, 5), tags="moldura")
            self.canvas.create_line(x1, yt, x2, yt, fill=COR_MOLDURA,
                                    width=1, dash=(3, 5), tags="moldura")

        # Cantos reforcados.
        L = max(10, min(28, (x2 - x1) / 6))
        for px, py, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1),
                               (x1, y2, 1, -1), (x2, y2, -1, -1)):
            self.canvas.create_line(px, py, px + dx * L, py, fill="#ffffff",
                                    width=4, tags="moldura")
            self.canvas.create_line(px, py, px, py + dy * L, fill="#ffffff",
                                    width=4, tags="moldura")

        rotulo = f"{self.crop_w} x {self.crop_h}"
        ty = y1 - 12 if y1 > 20 else y1 + 14
        self.canvas.create_text((x1 + x2) / 2 + 1, ty + 1, text=rotulo,
                                fill="#000000", font=(self.fonte_peq[0], 11, "bold"),
                                tags="moldura")
        self.canvas.create_text((x1 + x2) / 2, ty, text=rotulo,
                                fill=COR_MOLDURA,
                                font=(self.fonte_peq[0], 11, "bold"),
                                tags="moldura")

    # -------------------------------------------------- posicao
    def _alcance_atual(self):
        for nome, seg in ALCANCES:
            if nome == self.var_alcance.get():
                return seg
        return 2.0

    def _quadro_de(self, seg):
        fps = self.info.get("fps") or 0.0
        return int(round(seg * fps)) if fps else 0

    def _pos_mudou(self, _=None):
        """Chamado sempre que a posicao muda, no arrasto ou por codigo."""
        if not self.origem:
            return
        # Durante a reproducao a posicao so muda por vontade da pessoa (a
        # reproducao mexe nos rotulos, nao nesta variavel). Entao mexer na
        # barra, nos botoes de avanco ou no campo de tempo pausa o video e
        # manda nele.
        if self._tocando:
            self._parar_play()
            self.status("Pausado.")
        try:
            pos = self.var_pos.get()
        except Exception:
            return
        self.var_tempo.set(segundos_para_texto(pos))
        if self.info.get("fps"):
            self.lbl_pos.configure(text=f"quadro {self._quadro_de(pos)}")
        # Se a posicao saiu do trecho coberto pela barra fina, o trecho anda
        # junto: assim ela nunca fica encostada na ponta, sem serventia.
        if pos < self.jan_ini or pos > self.jan_fim:
            self._recentrar_janela()
        self.atualizar_preview()

    def _ir_para(self, _=None):
        if not self.origem:
            return
        seg = texto_para_segundos(self.var_tempo.get())
        if seg is None:
            messagebox.showwarning(
                APP_NAME,
                "Nao entendi esse tempo.\n\nEscreva assim: 1:30 (um minuto e "
                "meio), 90 (noventa segundos), 1:02:03 (uma hora, dois minutos "
                "e tres segundos) ou 2min30s.",
                parent=self.raiz.winfo_toplevel())
            return
        self._posicionar(seg)

    def _posicionar(self, seg):
        """Leva a posicao para um ponto do video."""
        dur = self.info.get("duracao") or 0.0
        seg = max(0.0, min(seg, dur) if dur else max(0.0, seg))
        self.var_pos.set(seg)    # dispara _pos_mudou: rotulos + quadro novo

    def _geral_solto(self, _=None):
        """Soltou a barra grande: o trecho fino se muda para perto daqui."""
        self._recentrar_janela()

    def _recentrar_janela(self, _=None):
        """Reposiciona o trecho que a barra fina cobre, em torno da posicao.

        A barra fina compartilha a posicao com a barra de cima; o que muda
        aqui e so o comeco e o fim do que ela cobre.
        """
        if not self.origem:
            return
        dur = self.info.get("duracao") or 0.0
        meio = self.var_pos.get()
        raio = self._alcance_atual()

        ini = meio - raio
        fim = meio + raio
        if ini < 0:                       # encostou no comeco do video
            ini, fim = 0.0, min(dur, 2 * raio)
        if fim > dur:                     # encostou no fim
            fim, ini = dur, max(0.0, dur - 2 * raio)
        if fim - ini < 0.05:              # video curtissimo
            fim = ini + 0.05

        self.jan_ini, self.jan_fim = ini, fim
        self.sld_fino.configure(from_=ini, to=fim)
        self.lbl_jan_ini.configure(text=segundos_para_texto(ini))
        self.lbl_jan_fim.configure(text=segundos_para_texto(fim))

    def _pular(self, direcao, quadro=False):
        if not self.origem:
            return
        passo = 1.0
        if quadro:
            fps = self.info.get("fps") or 30.0
            passo = 1.0 / max(fps, 1.0)
        self._posicionar(self.var_pos.get() + direcao * passo)

    def _marcar(self, qual):
        if not self.origem:
            return
        if qual == "fim":
            # Marcar o Fim aqui, pelo botao, e uma escolha tao manual quanto
            # digitar: desarma a Duracao, senao na proxima vez que o Comeco
            # mudasse ela pisaria em cima do que a pessoa acabou de marcar.
            self.var_duracao.set("")
        txt = segundos_para_texto(self.var_pos.get())
        (self.var_ini if qual == "ini" else self.var_fim).set(txt)

    def _fim_editado_a_mao(self, _evento=None):
        """Digitar direto no campo Fim desarma a Duracao, para nao brigarem."""
        if self.var_duracao.get():
            self.var_duracao.set("")

    def _duracao_mudou(self, *_a):
        """Com a Duracao preenchida, o Fim se ajusta sozinho: Comeco + Duracao.

        E para isto: marcar so onde comeca e por quanto tempo, sem parar
        para calcular em que segundo o trecho termina. Se o Comeco mudar
        depois -- digitando, no "posicao atual" ou nas setinhas -- o Fim
        acompanha, mantendo a mesma duracao. Editar o Fim na mao (ou marcar
        a posicao atual nele) desarma isto, ver `_fim_editado_a_mao` e
        `_marcar`.
        """
        seg = texto_para_segundos(self.var_duracao.get())
        if seg is None or seg <= 0:
            return
        ini = texto_para_segundos(self.var_ini.get())
        if ini is None:
            ini = 0.0
        fim = ini + seg
        dur_video = self.info.get("duracao") or 0.0
        if dur_video:
            fim = min(fim, dur_video)
        self.var_fim.set(segundos_para_texto(fim))

    # -------------------------------------------------- preview ao vivo
    def atualizar_preview(self):
        """Pede um quadro novo. O pedido mais recente sempre vence."""
        if not self.origem or not self.ffmpeg:
            return
        with self._prev_lock:
            self.preview_seq += 1
            self._prev_pedido = (self.var_pos.get(), self.preview_seq)
        self._prev_evento.set()

    def _worker_preview(self):
        while True:
            self._prev_evento.wait()
            self._prev_evento.clear()
            if self._prev_fim:
                return
            with self._prev_lock:
                pedido = self._prev_pedido
                self._prev_pedido = None
            if not pedido:
                continue

            pos, seq = pedido
            destino = os.path.join(self.tmpdir, f"prev_{seq % 8}.png")
            cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error"]
            # No Mac o VideoToolbox decodifica 4K bem mais rapido. Em outros
            # sistemas nao vale a pena tentar: o ffmpeg gasta tempo procurando
            # placa e cai para software do mesmo jeito.
            if sys.platform == "darwin":
                cmd += ["-hwaccel", "videotoolbox"]
            filtros = self._filtros_cor() + [f"scale={self.prev_w}:{self.prev_h}",
                                             "format=rgb24"]
            cmd += ["-ss", f"{max(0.0, pos):.3f}", "-i", self.origem,
                    "-frames:v", "1", "-vf", ",".join(filtros),
                    "-y", destino]
            erro = ""
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, text=True,
                                        **_sem_console())
                with self._prev_lock:
                    self._prev_proc = proc
                _, erro = proc.communicate(timeout=120)
            except Exception as e:
                erro = str(e)
                continue
            finally:
                with self._prev_lock:
                    self._prev_proc = None

            if self._prev_fim:
                return
            if proc.returncode == 0:
                self.raiz.after(0, lambda c=destino, s=seq:
                                self._mostrar_preview(c, s))
            else:
                self.raiz.after(0, lambda m=(erro or "").strip():
                                self._falhou_preview(m))

    def _filtros_cor(self):
        """Conversao de cor que precisa vir ANTES de cortar ou redimensionar.

        Video de celular novo costuma ser HDR. Jogado direto para PNG ou JPG,
        ele sai com a cor errada, muitas vezes escuro a ponto de parecer tela
        preta. Aqui ele e trazido para a faixa normal (SDR/bt709).
        """
        if not e_hdr(self.info):
            return []
        if self._tem_zscale:
            return ["zscale=t=linear:npl=100",
                    "format=gbrpf32le",
                    "tonemap=tonemap=hable:desat=0",
                    "zscale=p=bt709:t=bt709:m=bt709:r=tv"]
        # ffmpeg sem zscale: pelo menos tira o excesso de bits e normaliza.
        return ["format=yuv420p"]

    def _falhou_preview(self, msg):
        """Diz na tela e no log por que o quadro nao apareceu."""
        self.canvas.delete("quadro")
        self.canvas.delete("aviso")
        lim_w, lim_h = self._limite_preview()
        larg = lim_w
        alt = lim_h
        self.canvas.create_text(
            larg / 2, alt / 2, width=max(120, larg - 40), justify="center",
            text="Nao consegui montar a imagem deste ponto do video.\n"
                 "O motivo esta no quadro de mensagens, a direita.",
            fill=COR_SUAVE, font=self.fonte_peq, tags="aviso")
        if msg and msg != self._ultimo_erro_prev:
            self._ultimo_erro_prev = msg
            self.log("Falha ao mostrar o quadro: " + msg[:400])

    # -------------------------------------------------- assistir (play/pause)
    def _play_pause(self):
        if self._tocando:
            self._pausar()
        else:
            self._tocar()

    def _tocar(self):
        """Roda o video a partir da posicao atual, na propria area do preview.

        Nao existe player de video no Tkinter, entao a reproducao e feita com
        o proprio ffmpeg: ele decodifica a partir do ponto atual e despeja os
        quadros crus (formato PPM, que o Tk le nativamente) num cano. Uma
        thread le esse cano e a janela vai trocando a imagem no compasso.

        E sem som de proposito: o Tk nao toca audio, e aqui o que interessa e
        achar o quadro certo, nao assistir ao filme.
        """
        if not self.origem or not self.ffmpeg or self._tocando:
            return

        self._tocando = True
        self._play_geracao += 1
        geracao = self._play_geracao
        self._play_inicio = self.var_pos.get()
        self._play_pos = self._play_inicio
        # Uma taxa so, guardada, para o ffmpeg e o relogio da tela nunca
        # discordarem: se um deles usar 15 e o outro 30, o video sai na
        # metade ou no dobro da velocidade.
        self._play_fps = min(PLAY_FPS, self.info.get("fps") or PLAY_FPS)
        self._play_proximo = None
        self._play_t0 = time.monotonic()
        while True:                       # esvazia sobra de uma tocada antiga
            try:
                self._play_fila.get_nowait()
            except queue.Empty:
                break

        self.btn_play.configure(text="❚❚  Pausar")
        self.status("Assistindo... clique em Pausar no ponto que quiser.")

        threading.Thread(target=self._worker_play, args=(geracao,),
                         daemon=True).start()
        self._agendar_quadro_play(geracao)

    def _pausar(self):
        """Para a reproducao e deixa a posicao exatamente onde a imagem parou."""
        if not self._tocando:
            return
        self._parar_play()
        # A posicao vai para onde a imagem parou, e o quadro e refeito em
        # qualidade cheia: e nesse ponto que o recorte vai valer.
        self._posicionar(self._play_pos)
        self.status("Pausado. O recorte comeca neste ponto.")

    def _parar_play(self):
        """Desliga a reproducao sem mexer na posicao.

        Existe separado de `_pausar` porque, quando a pessoa arrasta a barra
        durante a reproducao, quem manda e a barra: voltar para onde o video
        estava tocando seria desfazer o que ela acabou de fazer.
        """
        if not self._tocando:
            return
        self._tocando = False
        self._play_geracao += 1          # invalida a thread e o temporizador
        self.btn_play.configure(text="▶  Assistir")

        p = self._play_proc
        self._play_proc = None
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

        if self._play_id is not None:
            try:
                self.raiz.after_cancel(self._play_id)
            except Exception:
                pass
            self._play_id = None

        self._play_proximo = None
        while True:
            try:
                self._play_fila.get_nowait()
            except queue.Empty:
                break

    def _worker_play(self, geracao):
        """Le os quadros crus que o ffmpeg despeja no cano.

        Esta thread NAO tem pressa: quando a fila enche, ela espera. Isso
        segura o ffmpeg, que trava ao escrever num cano cheio, e e o que
        mantem a decodificacao no ritmo do video. Antes ela descartava quadro
        para caber mais, e o ffmpeg saia decodificando o filme inteiro em
        segundos, entregando quadros salteados: o video passava voando.
        """
        fps = self._play_fps
        filtros = self._filtros_cor() + [
            f"fps={fps:.4f}",
            f"scale={self.prev_w}:{self.prev_h}",
            "format=rgb24",
        ]
        cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error"]
        if sys.platform == "darwin":
            cmd += ["-hwaccel", "videotoolbox"]
        cmd += ["-ss", f"{max(0.0, self._play_inicio):.3f}", "-i", self.origem,
                "-an", "-vf", ",".join(filtros),
                "-f", "image2pipe", "-vcodec", "ppm", "-"]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    **_sem_console())
        except Exception as e:
            self.raiz.after(0, lambda m=str(e): self._falhou_play(m))
            return
        self._play_proc = proc

        indice = 0
        try:
            while geracao == self._play_geracao:
                quadro = _ler_ppm(proc.stdout)
                if quadro is None:
                    break            # fim do video
                indice += 1
                segundos = self._play_inicio + indice / fps
                # Espera com prazo curto, em vez de esperar para sempre: e o
                # que permite notar que a pessoa apertou Pausar e sair.
                while geracao == self._play_geracao:
                    try:
                        self._play_fila.put((quadro, segundos), timeout=0.2)
                        break
                    except queue.Full:
                        continue
        except Exception:
            pass
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

        if geracao == self._play_geracao:
            self.raiz.after(0, self._fim_do_video)

    def _agendar_quadro_play(self, geracao):
        """Mostra cada quadro na HORA dele, medida por relogio de parede.

        Cada quadro sabe a que segundo do video pertence. A conta e simples:
        o quadro do segundo 3,2 aparece 3,2 segundos depois de a reproducao
        ter comecado. Assim a velocidade nao depende de quao rapido a maquina
        decodifica nem de quanto tempo o desenho na tela levou.

        A versao anterior fazia diferente: mostrava um quadro a cada 66
        milissegundos, fosse qual fosse. Somado ao ffmpeg correndo solto, o
        video passava rapido demais.
        """
        if geracao != self._play_geracao or not self._tocando:
            return

        def de_novo(ms):
            self._play_id = self.raiz.after(
                max(1, int(ms)), lambda: self._agendar_quadro_play(geracao))

        intervalo = 1.0 / max(self._play_fps, 1.0)

        while True:
            if self._play_proximo is None:
                try:
                    self._play_proximo = self._play_fila.get_nowait()
                except queue.Empty:
                    de_novo(15)      # ainda decodificando; espia de novo
                    return

            _dados, segundos = self._play_proximo
            decorrido = time.monotonic() - self._play_t0
            devido = segundos - self._play_inicio
            adianto = devido - decorrido

            if adianto > 0.004:
                # Ainda nao e a hora deste quadro: dorme ate ela chegar.
                de_novo(min(adianto * 1000, 250))
                return

            if adianto < -intervalo * 1.5:
                # Muito atrasado (a maquina engasgou): PULA sem desenhar. Se
                # desenhasse, a tela correria depressa para "recuperar" o
                # atraso, que e justamente o efeito de video acelerado.
                self._play_proximo = None
                continue

            break

        dados, segundos = self._play_proximo
        self._play_proximo = None
        try:
            img = PhotoImage(data=dados)
            self.imagem = img
            self._play_pos = segundos
            self.canvas.delete("quadro")
            self.canvas.delete("aviso")
            ox, oy = self._centro_imagem()
            self.canvas.create_image(ox, oy, anchor="nw", image=img,
                                     tags="quadro")
            self.canvas.tag_lower("quadro")
            self._desenhar_moldura()
            self.var_tempo.set(segundos_para_texto(segundos))
            if self.info.get("fps"):
                self.lbl_pos.configure(
                    text=f"quadro {self._quadro_de(segundos)}")
        except Exception as e:
            if not self._avisou_ppm:
                self._avisou_ppm = True
                self.log("Aviso ao exibir o quadro em movimento: "
                         + str(e)[:200])

        de_novo(4)

    def _fim_do_video(self):
        if not self._tocando:
            return
        self._pausar()
        self.status("Chegou ao fim do video.")

    def _falhou_play(self, msg):
        self._tocando = False
        self.btn_play.configure(text="▶  Assistir")
        self.status("Nao consegui rodar o video.")
        self.log("Falha ao assistir: " + str(msg)[:300])

    def _mostrar_preview(self, caminho, seq):
        # Mostra todo quadro que chegar, contanto que nao seja mais antigo do
        # que o ultimo ja exibido. E o que faz a imagem correr junto com o
        # arrasto, em vez de so aparecer no fim.
        if seq <= self._prev_exibido or not os.path.isfile(caminho):
            return
        try:
            img = PhotoImage(file=caminho)
        except Exception as erro:
            self._falhou_preview(f"o Tk nao conseguiu abrir a imagem gerada "
                                 f"({erro})")
            return
        self._prev_exibido = seq
        self.imagem = img
        self.canvas.delete("quadro")
        self.canvas.delete("aviso")
        ox, oy = self._centro_imagem()
        self.canvas.create_image(ox, oy, anchor="nw", image=img, tags="quadro")
        self.canvas.tag_lower("quadro")
        self._desenhar_moldura()

    # -------------------------------------------------- estimativa
    def _valores_trecho(self):
        dur = self.info.get("duracao", 0.0)
        ini = texto_para_segundos(self.var_ini.get())
        fim = texto_para_segundos(self.var_fim.get())
        if ini is None:
            ini = 0.0
        if fim is None:
            fim = dur
        ini = max(0.0, min(ini, dur if dur else ini))
        fim = max(0.0, min(fim, dur if dur else fim))
        return ini, fim

    def _fps_escolhido(self):
        t = self.var_fps.get().strip().lower().replace(",", ".")
        if t in ("todos", "tudo", "all"):
            return None
        try:
            v = float(t)
            return v if v > 0 else 1.0
        except ValueError:
            return 1.0

    def _largura_saida(self):
        rotulo = self.var_tamanho.get()
        for nome, larg in TAMANHOS:
            if nome == rotulo:
                return larg
        return 0

    def _tamanho_final(self):
        """Tamanho do arquivo que sai.

        Quando ha redimensionamento, a altura vem da proporcao ESCOLHIDA, e
        nao da do recorte: assim 16:9 com largura 1920 sai exatamente
        1920 x 1080, sem sobrar aquele pixel de arredondamento do corte.
        """
        larg = self._largura_saida()
        if not larg or not self.crop_w:
            return self.crop_w, self.crop_h
        alt = par(larg / self._proporcao_atual())
        return par(larg), max(2, alt)

    def _estimar(self):
        if not self.origem:
            return
        fw, fh = self._tamanho_final()
        aviso = ""
        if fw > self.crop_w:
            aviso = "  (maior que o recorte: a imagem sera esticada)"
        self.lbl_recorte.configure(
            text=f"Recorte de {self.crop_w} x {self.crop_h} px "
                 f"na posicao ({self.crop_x}, {self.crop_y}) do video")

        ini, fim = self._valores_trecho()
        if fim <= ini:
            self.lbl_estimativa.configure(
                text="O fim precisa ser depois do comeco.")
            return
        dur = fim - ini
        fps = self._fps_escolhido()
        taxa = fps if fps else (self.info.get("fps") or 30.0)
        n = int(dur * taxa) + 1
        self.lbl_estimativa.configure(
            text=f"Trecho de {segundos_para_texto(dur)} • cerca de {n} "
                 f"imagem(ns) de {fw} x {fh} px{aviso}")

    # -------------------------------------------------- extracao
    def iniciar(self):
        if self.rodando:
            return
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha um video primeiro.",
                                   parent=self.raiz.winfo_toplevel())
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado nesta maquina.",
                                 parent=self.raiz.winfo_toplevel())
            return

        ini, fim = self._valores_trecho()
        if fim <= ini:
            messagebox.showwarning(APP_NAME,
                                   "O fim precisa ser depois do comeco.",
                                   parent=self.raiz.winfo_toplevel())
            return

        pasta = self.var_pasta.get().strip()
        if not pasta:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de saida.",
                                   parent=self.raiz.winfo_toplevel())
            return
        try:
            Path(pasta).mkdir(parents=True, exist_ok=True)
        except Exception as erro:
            messagebox.showerror(APP_NAME, f"Nao consegui criar a pasta:\n{erro}",
                                 parent=self.raiz.winfo_toplevel())
            return

        self.rodando = True
        self.cancelar = False
        self.btn_extrair.configure(state=DISABLED)
        self.btn_cancelar.configure(state=NORMAL)
        self.btn_abrir.configure(state=DISABLED)
        self.barra.configure(value=0)

        threading.Thread(target=self._extrair, args=(ini, fim, pasta),
                         daemon=True).start()

    def _extrair(self, ini, fim, pasta):
        dur = fim - ini
        fps = self._fps_escolhido()
        jpg = self.var_formato.get().startswith("JPG")
        ext = "jpg" if jpg else "png"

        filtros = [f"crop={self.crop_w}:{self.crop_h}:{self.crop_x}:{self.crop_y}"]
        for f in reversed(self._filtros_cor()):   # conversao de cor vem antes
            filtros.insert(0, f)
        if fps:
            filtros.insert(0, f"fps={fps}")
        fw, fh = self._tamanho_final()
        if self._largura_saida():
            filtros.append(f"scale={fw}:{fh}:flags=lanczos")

        # O nome carrega o trecho, para uma extracao nao apagar a anterior.
        nome = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(self.origem).stem)[:40] or "quadro"
        marca = f"{int(ini // 60):02d}m{int(ini % 60):02d}s"
        base = f"{nome}_{marca}"
        padrao = os.path.join(pasta, f"{base}_%04d.{ext}")

        cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
               "-ss", f"{ini:.3f}", "-i", self.origem, "-t", f"{dur:.3f}",
               "-vf", ",".join(filtros), "-vsync", "0"]
        if jpg:
            cmd += ["-q:v", "2"]
        cmd += ["-progress", "pipe:1", "-nostats", "-y", padrao]

        taxa = fps if fps else (self.info.get("fps") or 30.0)
        total = max(1, int(dur * taxa))

        self.raiz.after(0, lambda: self.status("Extraindo quadros..."))
        self.raiz.after(0, lambda: self.log(
            f"Trecho {segundos_para_texto(ini)} ate {segundos_para_texto(fim)} "
            f"• recorte {self.crop_w}x{self.crop_h} em ({self.crop_x},"
            f"{self.crop_y}) • saida {fw}x{fh} {ext.upper()}"))

        feitos = 0
        erro_txt = ""
        try:
            self.processo = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, **_sem_console())
            for linha in self.processo.stdout:
                if self.cancelar:
                    break
                linha = linha.strip()
                if linha.startswith("frame="):
                    try:
                        feitos = int(linha.split("=", 1)[1])
                    except ValueError:
                        pass
                    pct = min(100, feitos * 100 / total)
                    self.raiz.after(0, lambda p=pct, f=feitos:
                                    (self.barra.configure(value=p),
                                     self.status(f"Extraindo... {f} imagem(ns)")))
            if self.cancelar and self.processo.poll() is None:
                self.processo.terminate()
            self.processo.wait(timeout=30)
            if self.processo.returncode not in (0, None) and not self.cancelar:
                erro_txt = (self.processo.stderr.read() or "").strip()[:400]
        except Exception as e:
            erro_txt = str(e)
        finally:
            self.processo = None

        try:
            gerados = len([p for p in os.listdir(pasta)
                           if p.startswith(base + "_") and p.endswith("." + ext)])
        except Exception:
            gerados = feitos
        if not gerados:
            gerados = feitos

        # O zip so entra se a extracao deu certo: cancelada ou com erro, nao
        # ha por que compactar imagem incompleta.
        zip_caminho = None
        zip_erro = ""
        if not self.cancelar and not erro_txt and self.var_zip.get() and gerados:
            self.raiz.after(0, lambda: self.status("Gerando o arquivo .zip..."))
            try:
                zip_caminho = self._gerar_zip(pasta)
            except Exception as e:
                zip_erro = str(e)

        def terminar():
            self.rodando = False
            self.btn_extrair.configure(state=NORMAL)
            self.btn_cancelar.configure(state=DISABLED)
            self.btn_abrir.configure(state=NORMAL)
            if self.cancelar:
                self.status("Cancelado.")
                self.log(f"Cancelado. {gerados} imagem(ns) ja tinham sido salvas.")
            elif erro_txt:
                self.barra.configure(value=0)
                self.status("Deu erro.")
                self.log("ERRO: " + erro_txt)
                messagebox.showerror(APP_NAME,
                                     "Nao consegui extrair os quadros.\n\n" + erro_txt,
                                     parent=self.raiz.winfo_toplevel())
            else:
                self.barra.configure(value=100)
                if zip_caminho:
                    self.status(f"Pronto: {gerados} imagem(ns) salvas, "
                                f"e o zip {zip_caminho.name}.")
                elif zip_erro:
                    self.status(f"Pronto: {gerados} imagem(ns) salvas "
                                "(mas o zip falhou, veja o registro).")
                else:
                    self.status(f"Pronto: {gerados} imagem(ns) salvas.")
                self.log(f"Concluido: {gerados} arquivo(s) em {pasta}")
                if zip_caminho:
                    self.log(f"Zip criado: {zip_caminho}")
                elif zip_erro:
                    self.log("ERRO ao gerar o zip: " + zip_erro)

        self.raiz.after(0, terminar)

    def _gerar_zip(self, pasta):
        """Compacta a pasta de saida inteira num .zip ao lado dela.

        O zip nasce com o MESMO NOME da pasta (nunca dentro dela, senao
        entraria zipando a si mesmo). Os arquivos soltos continuam na
        pasta do jeito de sempre: o zip e so uma copia extra, compactada,
        para quem precisa mandar tudo junto de uma vez.
        """
        pasta_p = Path(pasta)
        destino = pasta_p.parent / (pasta_p.name + ".zip")
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in sorted(pasta_p.iterdir()):
                if arquivo.is_file():
                    zf.write(arquivo, arcname=arquivo.name)
        return destino

    def pedir_cancelar(self):
        self.cancelar = True
        self.status("Cancelando...")
        p = self.processo
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

    def abrir_pasta(self):
        pasta = self.var_pasta.get().strip()
        if not pasta or not os.path.isdir(pasta):
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            elif os.name == "nt":
                os.startfile(pasta)  # noqa
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception:
            pass

    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        Para a thread de preview, derruba os processos de ffmpeg que ainda
        estiverem rodando e apaga a pasta temporaria. Quem fecha a janela e o
        programa principal.
        """
        self.cancelar = True
        self._prev_fim = True
        self._tocando = False
        self._play_geracao += 1
        self._prev_evento.set()
        for p in (self.processo, self._prev_proc, self._play_proc):
            if p and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)


def montar(pai):
    """Desenha a aba de extrair quadros dentro de `pai` e devolve o aplicativo."""
    return App(pai)
