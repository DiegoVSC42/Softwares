"""
Dividir e Juntar Audio - interface grafica (Tkinter).

Serve para quebrar um audio longo (uma entrevista de 2 horas, por exemplo) em
partes menores, levar essas partes para algum servico externo de tratamento
(transcricao, melhoria de voz, reducao de ruido) e depois juntar tudo de volta
num arquivo so, sem descompasso.

Aba 1 - Dividir:
  - escolhe o audio e diz em quantas partes (ou de quantos minutos cada);
  - corta exatamente no tempo OU procura o silencio mais proximo, para nao
    partir palavra no meio;
  - as partes saem numeradas (01_, 02_, ...) para nunca perder a ordem;
  - grava um manifesto .json com os tempos de corte e as duracoes.

Aba 2 - Juntar:
  - carrega o manifesto e acha as partes tratadas automaticamente;
  - confere a duracao de cada parte contra o original e avisa se o servico
    externo comeu ou esticou algum pedaco;
  - junta na ordem certa, normalizando formato quando as partes voltarem
    diferentes umas das outras.

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from shutil import which
from tkinter import (
    Tk, StringVar, IntVar, BooleanVar, END, DISABLED, NORMAL, SINGLE,
    Listbox, filedialog, messagebox, ttk, scrolledtext,
)

import atualizador  # atualizacao automatica


APP_NAME = "Dividir e Juntar Audio"
APP_VERSION = "1.1.1"

EXTENSOES_AUDIO = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".wma", ".aiff", ".aif", ".mp4", ".mkv", ".mov", ".webm",
}

# Formatos de saida das partes
FMT_ORIGINAL = "Manter o formato original (mais rapido, sem perda)"
FMT_MP3_192 = "MP3 192k (qualidade boa, arquivo menor)"
FMT_MP3_128 = "MP3 128k (arquivo menor ainda)"
FMT_MP3_64M = "MP3 64k mono (o menor de todos, bom para transcricao)"
FMT_WAV = "WAV 16-bit (sem perdas, arquivo grande)"
FORMATOS_PARTES = [FMT_ORIGINAL, FMT_MP3_192, FMT_MP3_128, FMT_MP3_64M, FMT_WAV]

# Formatos de saida da juncao
JUN_AUTO = "Automatico (recomendado)"
JUN_WAV = "WAV 16-bit (sem perdas)"
JUN_MP3 = "MP3 192k"
JUN_M4A = "M4A / AAC 192k"
FORMATOS_JUNCAO = [JUN_AUTO, JUN_WAV, JUN_MP3, JUN_M4A]

MODO_EXATO = "Corte exato no tempo"
MODO_SILENCIO = "Procurar o silencio mais proximo (nao parte palavra)"
MODOS_CORTE = [MODO_EXATO, MODO_SILENCIO]

# Tolerancia (em segundos) para considerar que uma parte voltou com a
# duracao errada do servico externo.
TOLERANCIA_DURACAO = 1.0


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
    candidatos = [
        resource_path(exe),
        resource_path(os.path.join("ffmpeg", exe)),
        resource_path(os.path.join("bin", exe)),
    ]
    for c in candidatos:
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
    """ffprobe pode nao estar embutido; nesse caso o ffmpeg cobre o basico."""
    return _achar_binario("ffprobe")


def _sem_janela():
    """Impede o piscar do console preto no Windows."""
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ---------------------------------------------------------------------------
# Leitura de informacoes do audio
# ---------------------------------------------------------------------------
RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")
RE_TEMPO = re.compile(r"time=\s*(\d+):(\d+):(\d+\.?\d*)")
RE_SIL_INI = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
RE_SIL_FIM = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")


def hms_para_seg(h, m, s) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def formatar_tempo(seg: float) -> str:
    if seg is None or seg < 0:
        return "--:--:--"
    seg = int(round(seg))
    return f"{seg // 3600:02d}:{(seg % 3600) // 60:02d}:{seg % 60:02d}"


def formatar_tamanho(bytes_: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024 or unidade == "GB":
            return f"{bytes_:.0f} {unidade}" if unidade == "B" else f"{bytes_:.1f} {unidade}"
        bytes_ /= 1024.0
    return f"{bytes_:.1f} GB"


def ler_info_audio(ffmpeg: str, ffprobe, caminho: str) -> dict:
    """Retorna duracao, codec, taxa de amostragem e canais do arquivo."""
    info = {
        "duracao": None, "codec": None, "sample_rate": None,
        "canais": None, "tamanho": None,
    }
    try:
        info["tamanho"] = os.path.getsize(caminho)
    except OSError:
        pass

    if ffprobe:
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "a:0",
                 "-show_entries",
                 "stream=codec_name,sample_rate,channels:format=duration",
                 "-of", "json", caminho],
                capture_output=True, text=True, timeout=120, **_sem_janela()
            )
            dados = json.loads(proc.stdout or "{}")
            fluxos = dados.get("streams") or []
            if fluxos:
                info["codec"] = fluxos[0].get("codec_name")
                sr = fluxos[0].get("sample_rate")
                info["sample_rate"] = int(sr) if sr else None
                info["canais"] = fluxos[0].get("channels")
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
            m = RE_DURACAO.search(proc.stderr or "")
            if m:
                info["duracao"] = hms_para_seg(*m.groups())
        except Exception:
            pass

    return info


# ---------------------------------------------------------------------------
# Deteccao de silencio
# ---------------------------------------------------------------------------
def detectar_silencios(ffmpeg, caminho, ruido_db, dur_min, log, cancelar, progresso=None,
                       duracao_total=None):
    """Devolve a lista de trechos de silencio como pares (inicio, fim)."""
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-i", caminho,
        "-af", f"silencedetect=noise={ruido_db}dB:d={dur_min}",
        "-f", "null", "-",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **_sem_janela()
    )
    silencios, inicio = [], None
    try:
        for linha in proc.stderr:
            if cancelar.is_set():
                proc.terminate()
                return []
            mi = RE_SIL_INI.search(linha)
            if mi:
                inicio = float(mi.group(1))
            mf = RE_SIL_FIM.search(linha)
            if mf and inicio is not None:
                silencios.append((inicio, float(mf.group(1))))
                inicio = None
            if progresso and duracao_total:
                mt = RE_TEMPO.search(linha)
                if mt:
                    progresso(min(100.0, hms_para_seg(*mt.groups()) / duracao_total * 100.0))
    finally:
        proc.wait()

    log(f"Silencios encontrados: {len(silencios)}")
    return silencios


def ajustar_para_silencio(alvo, silencios, janela):
    """Move o ponto de corte para o meio do silencio mais proximo do alvo.

    Devolve (novo_ponto, achou). Se nao houver silencio dentro da janela,
    devolve o proprio alvo.
    """
    melhor, menor_dist = None, None
    for ini, fim in silencios:
        meio = (ini + fim) / 2.0
        dist = abs(meio - alvo)
        if dist <= janela and (menor_dist is None or dist < menor_dist):
            melhor, menor_dist = meio, dist
    if melhor is None:
        return alvo, False
    return melhor, True


# ---------------------------------------------------------------------------
# Divisao
# ---------------------------------------------------------------------------
def opcoes_formato_partes(formato, ext_original):
    """Devolve (lista de argumentos do ffmpeg, extensao de saida)."""
    if formato == FMT_ORIGINAL:
        return ["-c", "copy"], ext_original
    if formato == FMT_MP3_192:
        return ["-c:a", "libmp3lame", "-b:a", "192k"], ".mp3"
    if formato == FMT_MP3_128:
        return ["-c:a", "libmp3lame", "-b:a", "128k"], ".mp3"
    if formato == FMT_MP3_64M:
        return ["-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1", "-ar", "22050"], ".mp3"
    if formato == FMT_WAV:
        return ["-c:a", "pcm_s16le"], ".wav"
    return ["-c", "copy"], ext_original


def dividir_audio(ffmpeg, ffprobe, origem, pasta_saida, pontos, formato,
                  info_origem, modo_corte, log, progresso, cancelar):
    """Corta o audio nos pontos indicados, numa passada so, sem sobra nem falta.

    Usa o muxer 'segment' do ffmpeg, que garante que o fim de uma parte e o
    comeco da seguinte sao exatamente o mesmo instante.
    """
    base = Path(origem).stem
    ext_original = Path(origem).suffix or ".mp3"
    args_fmt, ext_saida = opcoes_formato_partes(formato, ext_original)

    # Nome limpo, sem caracteres que atrapalhem servicos externos.
    base_limpa = re.sub(r"[^\w\-.]+", "_", base).strip("_") or "audio"
    padrao = os.path.join(pasta_saida, f"%02d_{base_limpa}{ext_saida}")

    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", origem,
        "-vn", "-map", "0:a:0",
        *args_fmt,
        "-f", "segment",
        "-segment_times", ",".join(f"{p:.3f}" for p in pontos),
        "-segment_start_number", "1",
        "-reset_timestamps", "1",
        padrao,
    ]

    log("Cortando...")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **_sem_janela()
    )
    dur = info_origem.get("duracao") or 0
    erro_final = []
    try:
        for linha in proc.stderr:
            if cancelar.is_set():
                proc.terminate()
                return None
            mt = RE_TEMPO.search(linha)
            if mt and dur:
                progresso(min(100.0, hms_para_seg(*mt.groups()) / dur * 100.0))
            if "Error" in linha or "Invalid" in linha:
                erro_final.append(linha.strip())
    finally:
        proc.wait()

    if proc.returncode != 0:
        for l in erro_final[-5:]:
            log(f"  {l}")
        raise RuntimeError("O ffmpeg nao conseguiu dividir o arquivo.")

    # Monta o manifesto com o que realmente saiu.
    limites = [0.0] + list(pontos) + [dur]
    partes = []
    for i in range(len(limites) - 1):
        nome = f"{i + 1:02d}_{base_limpa}{ext_saida}"
        caminho = os.path.join(pasta_saida, nome)
        if not os.path.isfile(caminho):
            continue
        info_p = ler_info_audio(ffmpeg, ffprobe, caminho)
        partes.append({
            "ordem": i + 1,
            "arquivo": nome,
            "inicio_seg": round(limites[i], 3),
            "fim_seg": round(limites[i + 1], 3),
            "duracao_seg": round(info_p.get("duracao") or (limites[i + 1] - limites[i]), 3),
            "tamanho_bytes": info_p.get("tamanho"),
        })

    manifesto = {
        "programa": APP_NAME,
        "versao": APP_VERSION,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "origem": {
            "arquivo": os.path.basename(origem),
            "caminho": origem,
            "duracao_seg": round(dur, 3),
            "codec": info_origem.get("codec"),
            "sample_rate": info_origem.get("sample_rate"),
            "canais": info_origem.get("canais"),
        },
        "modo_corte": modo_corte,
        "formato_partes": formato,
        "partes": partes,
    }
    caminho_manifesto = os.path.join(pasta_saida, f"manifesto_{base_limpa}.json")
    with open(caminho_manifesto, "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)

    return manifesto, caminho_manifesto


# ---------------------------------------------------------------------------
# Juncao
# ---------------------------------------------------------------------------
def opcoes_formato_juncao(formato, infos):
    """Devolve (lista de argumentos, extensao) para o arquivo juntado."""
    if formato == JUN_WAV:
        return ["-c:a", "pcm_s16le"], ".wav"
    if formato == JUN_MP3:
        return ["-c:a", "libmp3lame", "-b:a", "192k"], ".mp3"
    if formato == JUN_M4A:
        return ["-c:a", "aac", "-b:a", "192k"], ".m4a"

    # Automatico: segue o codec das partes quando todas sao iguais.
    codecs = {i.get("codec") for i in infos if i.get("codec")}
    if len(codecs) == 1:
        codec = codecs.pop()
        if codec in ("pcm_s16le", "pcm_s24le", "pcm_f32le"):
            return ["-c:a", "pcm_s16le"], ".wav"
        if codec == "mp3":
            return ["-c:a", "libmp3lame", "-b:a", "192k"], ".mp3"
        if codec in ("aac", "alac"):
            return ["-c:a", "aac", "-b:a", "192k"], ".m4a"
        if codec == "flac":
            return ["-c:a", "flac"], ".flac"
    return ["-c:a", "pcm_s16le"], ".wav"


def partes_sao_identicas(infos):
    """Diz se todas as partes tem exatamente o mesmo formato tecnico."""
    if len(infos) < 2:
        return True
    chave = lambda i: (i.get("codec"), i.get("sample_rate"), i.get("canais"))
    return len({chave(i) for i in infos}) == 1


def juntar_audios(ffmpeg, arquivos, infos, saida, formato, copia_direta,
                  log, progresso, cancelar):
    """Junta as partes na ordem recebida.

    Dois caminhos:
      - copia direta (concat demuxer + -c copy): so quando as partes sao
        tecnicamente identicas e o usuario pediu Automatico. Nao recomprime.
      - filtro concat: normaliza formatos diferentes. E o caminho seguro
        quando as partes voltaram tratadas de um servico externo.
    """
    total = sum(i.get("duracao") or 0 for i in infos) or 1

    if copia_direta:
        log("Todas as partes tem o mesmo formato: juntando por copia direta, sem recomprimir.")
        lista = saida + ".lista.txt"
        with open(lista, "w", encoding="utf-8") as f:
            for a in arquivos:
                f.write("file '" + os.path.abspath(a).replace("'", "'\\''") + "'\n")
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-f", "concat",
               "-safe", "0", "-i", lista, "-c", "copy", saida]
    else:
        log("Juntando com normalizacao de formato (caminho seguro para partes tratadas).")
        args_fmt, _ = opcoes_formato_juncao(formato, infos)
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
        for a in arquivos:
            cmd += ["-i", a]
        n = len(arquivos)
        filtro = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[saida]"
        cmd += ["-filter_complex", filtro, "-map", "[saida]", *args_fmt, saida]
        lista = None

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
            mt = RE_TEMPO.search(linha)
            if mt:
                progresso(min(100.0, hms_para_seg(*mt.groups()) / total * 100.0))
            if "Error" in linha or "Invalid" in linha:
                erros.append(linha.strip())
    finally:
        proc.wait()
        if lista and os.path.isfile(lista):
            try:
                os.remove(lista)
            except OSError:
                pass

    if proc.returncode != 0:
        for l in erros[-5:]:
            log(f"  {l}")
        raise RuntimeError("O ffmpeg nao conseguiu juntar as partes.")
    return True


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class Aplicativo:

    def __init__(self, raiz: Tk):
        self.raiz = raiz
        raiz.title(f"{APP_NAME} {APP_VERSION}")
        raiz.geometry("880x760")
        raiz.minsize(820, 700)

        self.ffmpeg = find_ffmpeg()
        self.ffprobe = find_ffprobe()

        self.cancelar = threading.Event()
        self.trabalhando = False

        # Estado da divisao
        self.origem = ""
        self.info_origem = {}
        self.pasta_saida_div = ""

        # Estado da juncao
        self.partes = []            # caminhos, na ordem
        self.manifesto = None
        self.pasta_saida_jun = ""

        self._montar()

        if not self.ffmpeg:
            self.log_div("ATENCAO: ffmpeg nao encontrado. O programa nao vai conseguir "
                         "processar audio. No executavel publicado o ffmpeg ja vem junto.")

    # -------------------------------------------------------------- montagem
    def _montar(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except Exception:
            pass

        ttk.Label(
            self.raiz, text=f"{APP_NAME} • v{APP_VERSION}",
            foreground="#8b949e", font=("Segoe UI", 8), anchor="e",
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 4))

        cad = ttk.Notebook(self.raiz)
        cad.pack(fill="both", expand=True, padx=10, pady=10)

        self.aba_div = ttk.Frame(cad, padding=12)
        self.aba_jun = ttk.Frame(cad, padding=12)
        cad.add(self.aba_div, text="  1. Dividir  ")
        cad.add(self.aba_jun, text="  2. Juntar  ")

        self._montar_aba_dividir()
        self._montar_aba_juntar()

    # ------------------------------------------------------------ aba dividir
    def _montar_aba_dividir(self):
        p = self.aba_div

        # --- arquivo de origem
        cx = ttk.LabelFrame(p, text="Audio que voce quer dividir", padding=10)
        cx.pack(fill="x", pady=(0, 8))
        linha = ttk.Frame(cx)
        linha.pack(fill="x")
        self.var_origem = StringVar(value="Nenhum arquivo escolhido")
        ttk.Label(linha, textvariable=self.var_origem, foreground="#333").pack(
            side="left", fill="x", expand=True)
        ttk.Button(linha, text="Escolher audio...", command=self.escolher_origem).pack(side="right")
        self.var_info = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_info, foreground="#666").pack(anchor="w", pady=(6, 0))

        # --- como dividir
        cx2 = ttk.LabelFrame(p, text="Como dividir", padding=10)
        cx2.pack(fill="x", pady=(0, 8))

        self.var_criterio = StringVar(value="partes")
        l1 = ttk.Frame(cx2)
        l1.pack(fill="x", pady=2)
        ttk.Radiobutton(l1, text="Em quantas partes:", variable=self.var_criterio,
                        value="partes", command=self.atualizar_previa).pack(side="left")
        self.var_num_partes = IntVar(value=4)
        ttk.Spinbox(l1, from_=2, to=60, width=6, textvariable=self.var_num_partes,
                    command=self.atualizar_previa).pack(side="left", padx=8)

        l2 = ttk.Frame(cx2)
        l2.pack(fill="x", pady=2)
        ttk.Radiobutton(l2, text="Partes de quantos minutos:", variable=self.var_criterio,
                        value="minutos", command=self.atualizar_previa).pack(side="left")
        self.var_minutos = IntVar(value=30)
        ttk.Spinbox(l2, from_=1, to=600, width=6, textvariable=self.var_minutos,
                    command=self.atualizar_previa).pack(side="left", padx=8)

        self.var_previa = StringVar(value="")
        ttk.Label(cx2, textvariable=self.var_previa, foreground="#0a6").pack(anchor="w", pady=(6, 0))

        # --- onde cortar
        cx3 = ttk.LabelFrame(p, text="Onde cortar", padding=10)
        cx3.pack(fill="x", pady=(0, 8))
        self.var_modo = StringVar(value=MODO_SILENCIO)
        for m in MODOS_CORTE:
            ttk.Radiobutton(cx3, text=m, variable=self.var_modo, value=m,
                            command=self._alternar_silencio).pack(anchor="w")
        self.linha_sil = ttk.Frame(cx3)
        self.linha_sil.pack(fill="x", pady=(6, 0))
        ttk.Label(self.linha_sil, text="    Procurar silencio ate").pack(side="left")
        self.var_janela = IntVar(value=45)
        ttk.Spinbox(self.linha_sil, from_=5, to=300, width=5,
                    textvariable=self.var_janela).pack(side="left", padx=4)
        ttk.Label(self.linha_sil, text="segundos antes ou depois do ponto ideal.").pack(side="left")

        # --- formato das partes
        cx4 = ttk.LabelFrame(p, text="Formato das partes", padding=10)
        cx4.pack(fill="x", pady=(0, 8))
        self.var_formato = StringVar(value=FMT_ORIGINAL)
        ttk.Combobox(cx4, textvariable=self.var_formato, values=FORMATOS_PARTES,
                     state="readonly").pack(fill="x")

        # --- destino
        cx5 = ttk.LabelFrame(p, text="Onde salvar as partes", padding=10)
        cx5.pack(fill="x", pady=(0, 8))
        l5 = ttk.Frame(cx5)
        l5.pack(fill="x")
        self.var_destino_div = StringVar(value="(uma pasta ao lado do arquivo original)")
        ttk.Label(l5, textvariable=self.var_destino_div, foreground="#333").pack(
            side="left", fill="x", expand=True)
        ttk.Button(l5, text="Trocar pasta...", command=self.escolher_destino_div).pack(side="right")

        # --- botoes
        bt = ttk.Frame(p)
        bt.pack(fill="x", pady=(4, 8))
        self.bt_dividir = ttk.Button(bt, text="Dividir", command=self.iniciar_divisao)
        self.bt_dividir.pack(side="left")
        self.bt_cancelar_div = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                          command=self.pedir_cancelamento)
        self.bt_cancelar_div.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta das partes",
                   command=lambda: self.abrir_pasta(self.pasta_saida_div)).pack(side="right")

        self.prog_div = ttk.Progressbar(p, mode="determinate", maximum=100)
        self.prog_div.pack(fill="x")
        self.var_status_div = StringVar(value="Pronto.")
        ttk.Label(p, textvariable=self.var_status_div, foreground="#444").pack(
            anchor="w", pady=(4, 6))

        self.txt_div = scrolledtext.ScrolledText(p, height=10, state=DISABLED, wrap="word")
        self.txt_div.pack(fill="both", expand=True)

    def _alternar_silencio(self):
        estado = NORMAL if self.var_modo.get() == MODO_SILENCIO else DISABLED
        for w in self.linha_sil.winfo_children():
            try:
                w.configure(state=estado)
            except Exception:
                pass

    # ------------------------------------------------------------- aba juntar
    def _montar_aba_juntar(self):
        p = self.aba_jun

        cx = ttk.LabelFrame(p, text="Partes tratadas, na ordem em que serao juntadas", padding=10)
        cx.pack(fill="both", expand=True, pady=(0, 8))

        topo = ttk.Frame(cx)
        topo.pack(fill="x", pady=(0, 6))
        ttk.Button(topo, text="Carregar manifesto (recomendado)...",
                   command=self.carregar_manifesto).pack(side="left")
        ttk.Button(topo, text="Adicionar arquivos...",
                   command=self.adicionar_partes).pack(side="left", padx=6)
        ttk.Button(topo, text="Limpar lista", command=self.limpar_partes).pack(side="left")

        meio = ttk.Frame(cx)
        meio.pack(fill="both", expand=True)
        self.lista = Listbox(meio, selectmode=SINGLE, activestyle="none")
        self.lista.pack(side="left", fill="both", expand=True)
        barra = ttk.Scrollbar(meio, orient="vertical", command=self.lista.yview)
        barra.pack(side="left", fill="y")
        self.lista.configure(yscrollcommand=barra.set)

        lado = ttk.Frame(meio, padding=(8, 0))
        lado.pack(side="left", fill="y")
        ttk.Button(lado, text="Subir", width=10, command=lambda: self.mover(-1)).pack(pady=2)
        ttk.Button(lado, text="Descer", width=10, command=lambda: self.mover(1)).pack(pady=2)
        ttk.Button(lado, text="Remover", width=10, command=self.remover_parte).pack(pady=2)

        cx2 = ttk.LabelFrame(p, text="Formato do arquivo final", padding=10)
        cx2.pack(fill="x", pady=(0, 8))
        self.var_formato_jun = StringVar(value=JUN_AUTO)
        ttk.Combobox(cx2, textvariable=self.var_formato_jun, values=FORMATOS_JUNCAO,
                     state="readonly").pack(fill="x")

        bt = ttk.Frame(p)
        bt.pack(fill="x", pady=(4, 8))
        self.bt_juntar = ttk.Button(bt, text="Juntar e salvar...", command=self.iniciar_juncao)
        self.bt_juntar.pack(side="left")
        self.bt_cancelar_jun = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                          command=self.pedir_cancelamento)
        self.bt_cancelar_jun.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta do resultado",
                   command=lambda: self.abrir_pasta(self.pasta_saida_jun)).pack(side="right")

        self.prog_jun = ttk.Progressbar(p, mode="determinate", maximum=100)
        self.prog_jun.pack(fill="x")
        self.var_status_jun = StringVar(value="Pronto.")
        ttk.Label(p, textvariable=self.var_status_jun, foreground="#444").pack(
            anchor="w", pady=(4, 6))

        self.txt_jun = scrolledtext.ScrolledText(p, height=10, state=DISABLED, wrap="word")
        self.txt_jun.pack(fill="both", expand=True)

    # ------------------------------------------------------------------- log
    def _log(self, widget, msg):
        def escrever():
            widget.configure(state=NORMAL)
            widget.insert(END, f"{time.strftime('%H:%M:%S')}  {msg}\n")
            widget.see(END)
            widget.configure(state=DISABLED)
        self.raiz.after(0, escrever)

    def log_div(self, msg):
        self._log(self.txt_div, msg)

    def log_jun(self, msg):
        self._log(self.txt_jun, msg)

    def status_div(self, msg):
        self.raiz.after(0, lambda: self.var_status_div.set(msg))

    def status_jun(self, msg):
        self.raiz.after(0, lambda: self.var_status_jun.set(msg))

    def progresso_div(self, pct):
        self.raiz.after(0, lambda: self.prog_div.configure(value=pct))

    def progresso_jun(self, pct):
        self.raiz.after(0, lambda: self.prog_jun.configure(value=pct))

    # -------------------------------------------------------- acoes dividir
    def escolher_origem(self):
        caminho = filedialog.askopenfilename(
            title="Escolha o audio",
            filetypes=[("Audio e video", " ".join(f"*{e}" for e in sorted(EXTENSOES_AUDIO))),
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
        self.pasta_saida_div = str(Path(caminho).with_suffix("")) + " - partes"
        self.var_destino_div.set(self.pasta_saida_div)
        threading.Thread(target=self._carregar_info_origem, daemon=True).start()

    def _carregar_info_origem(self):
        info = ler_info_audio(self.ffmpeg, self.ffprobe, self.origem)
        self.info_origem = info
        partes_txt = []
        if info.get("duracao"):
            partes_txt.append(f"Duracao: {formatar_tempo(info['duracao'])}")
        if info.get("codec"):
            partes_txt.append(f"Formato: {info['codec']}")
        if info.get("sample_rate"):
            partes_txt.append(f"{info['sample_rate']} Hz")
        if info.get("canais"):
            partes_txt.append("mono" if info["canais"] == 1 else f"{info['canais']} canais")
        if info.get("tamanho"):
            partes_txt.append(formatar_tamanho(info["tamanho"]))
        self.raiz.after(0, lambda: self.var_info.set("   |   ".join(partes_txt) or "Nao consegui ler o arquivo."))
        self.raiz.after(0, self.atualizar_previa)
        self.log_div(f"Arquivo carregado: {os.path.basename(self.origem)}")

    def calcular_pontos(self):
        """Devolve a lista de instantes (em segundos) onde o audio sera cortado."""
        dur = self.info_origem.get("duracao")
        if not dur:
            return []
        if self.var_criterio.get() == "partes":
            n = max(2, int(self.var_num_partes.get()))
            passo = dur / n
        else:
            passo = max(1, int(self.var_minutos.get())) * 60
            n = max(1, int(dur / passo + 0.999999))
        pontos = []
        t = passo
        while t < dur - 1.0:
            pontos.append(round(t, 3))
            t += passo
        return pontos

    def atualizar_previa(self):
        dur = self.info_origem.get("duracao")
        if not dur:
            self.var_previa.set("")
            return
        pontos = self.calcular_pontos()
        n = len(pontos) + 1
        media = dur / n
        self.var_previa.set(
            f"Vai gerar {n} partes de aproximadamente {formatar_tempo(media)} cada."
        )

    def escolher_destino_div(self):
        pasta = filedialog.askdirectory(title="Onde salvar as partes")
        if pasta:
            self.pasta_saida_div = pasta
            self.var_destino_div.set(pasta)

    def iniciar_divisao(self):
        if self.trabalhando:
            return
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha primeiro o audio que voce quer dividir.")
            return
        if not self.info_origem.get("duracao"):
            messagebox.showerror(APP_NAME, "Nao consegui ler a duracao desse arquivo.")
            return
        pontos = self.calcular_pontos()
        if not pontos:
            messagebox.showwarning(APP_NAME, "Do jeito que esta configurado, nao ha o que dividir.")
            return
        os.makedirs(self.pasta_saida_div, exist_ok=True)
        self._travar(True)
        self.cancelar.clear()
        threading.Thread(target=self._rodar_divisao, args=(pontos,), daemon=True).start()

    def _rodar_divisao(self, pontos):
        try:
            modo = self.var_modo.get()
            self.log_div("=" * 60)
            self.log_div(f"Dividindo em {len(pontos) + 1} partes.")

            if modo == MODO_SILENCIO:
                self.status_div("Procurando os silencios do audio...")
                self.log_div("Procurando silencios (essa varredura le o audio inteiro).")
                silencios = detectar_silencios(
                    self.ffmpeg, self.origem, -35, 0.45, self.log_div, self.cancelar,
                    self.progresso_div, self.info_origem.get("duracao"))
                if self.cancelar.is_set():
                    raise InterruptedError
                janela = int(self.var_janela.get())
                novos, achados = [], 0
                for alvo in pontos:
                    novo, achou = ajustar_para_silencio(alvo, silencios, janela)
                    novos.append(round(novo, 3))
                    achados += 1 if achou else 0
                    if achou:
                        self.log_div(f"  Corte previsto em {formatar_tempo(alvo)} movido para "
                                     f"{formatar_tempo(novo)} (silencio).")
                    else:
                        self.log_div(f"  Sem silencio perto de {formatar_tempo(alvo)}: "
                                     f"cortando no tempo exato.")
                # Os pontos precisam continuar em ordem crescente.
                novos = sorted(set(novos))
                pontos = novos
                self.log_div(f"{achados} de {len(pontos)} cortes cairam em silencio.")
                self.progresso_div(0)

            self.status_div("Cortando o audio...")
            resultado = dividir_audio(
                self.ffmpeg, self.ffprobe, self.origem, self.pasta_saida_div, pontos,
                self.var_formato.get(), self.info_origem, modo,
                self.log_div, self.progresso_div, self.cancelar)
            if self.cancelar.is_set() or resultado is None:
                raise InterruptedError

            manifesto, caminho_manifesto = resultado
            self.progresso_div(100)
            self.log_div("-" * 60)
            for parte in manifesto["partes"]:
                self.log_div(
                    f"  {parte['arquivo']}  ({formatar_tempo(parte['duracao_seg'])}, "
                    f"{formatar_tamanho(parte['tamanho_bytes'] or 0)})")
            soma = sum(p["duracao_seg"] for p in manifesto["partes"])
            dif = abs(soma - (self.info_origem.get("duracao") or soma))
            self.log_div("-" * 60)
            self.log_div(f"Soma das partes: {formatar_tempo(soma)}  |  "
                         f"Original: {formatar_tempo(self.info_origem.get('duracao'))}  |  "
                         f"Diferenca: {dif:.2f}s")
            if dif > TOLERANCIA_DURACAO:
                self.log_div("ATENCAO: a soma das partes ficou diferente do original.")
            else:
                self.log_div("Conferido: as partes somam o audio inteiro, sem sobra nem falta.")
            self.log_div(f"Manifesto salvo em: {os.path.basename(caminho_manifesto)}")
            self.log_div("Leve as partes para o servico de tratamento. Depois volte na aba "
                         "'2. Juntar' e clique em 'Carregar manifesto'.")
            self.status_div(f"Pronto: {len(manifesto['partes'])} partes geradas.")
            self.manifesto = manifesto
            self.raiz.after(0, lambda: messagebox.showinfo(
                APP_NAME,
                f"{len(manifesto['partes'])} partes geradas em:\n{self.pasta_saida_div}"))
        except InterruptedError:
            self.status_div("Cancelado.")
            self.log_div("Cancelado pelo usuario.")
        except Exception as e:
            self.status_div("Deu erro.")
            self.log_div(f"ERRO: {e}")
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    # --------------------------------------------------------- acoes juntar
    def carregar_manifesto(self):
        caminho = filedialog.askopenfilename(
            title="Escolha o manifesto gerado na divisao",
            filetypes=[("Manifesto", "manifesto_*.json"), ("JSON", "*.json")],
        )
        if not caminho:
            return
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                manifesto = json.load(f)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Nao consegui ler esse manifesto.\n{e}")
            return

        pasta = filedialog.askdirectory(
            title="Onde estao as partes ja tratadas?",
            initialdir=os.path.dirname(caminho))
        if not pasta:
            return

        self.manifesto = manifesto
        self.partes = []
        self.lista.delete(0, END)
        self.log_jun("=" * 60)
        self.log_jun(f"Manifesto de: {manifesto['origem']['arquivo']}  "
                     f"({formatar_tempo(manifesto['origem']['duracao_seg'])}, "
                     f"{len(manifesto['partes'])} partes)")

        faltando = []
        for parte in manifesto["partes"]:
            achado = self._achar_parte(pasta, parte["ordem"])
            if achado:
                self.partes.append(achado)
                self.lista.insert(END, f"{parte['ordem']:02d}.  {os.path.basename(achado)}")
            else:
                faltando.append(parte["ordem"])

        if faltando:
            self.log_jun(f"ATENCAO: nao achei as partes de numero {faltando} nessa pasta.")
            messagebox.showwarning(
                APP_NAME,
                "Nao encontrei todas as partes nessa pasta.\n"
                f"Faltaram: {faltando}\n\n"
                "Adicione os arquivos que faltam na mao, pelo botao 'Adicionar arquivos'.")
        else:
            self.log_jun("Todas as partes foram encontradas e colocadas na ordem certa.")

        self.pasta_saida_jun = pasta
        threading.Thread(target=self._conferir_partes, daemon=True).start()

    def _achar_parte(self, pasta, ordem):
        """Acha o arquivo cujo nome comeca pelo numero da parte.

        Aceita sufixos que servicos externos costumam colar no nome, tipo
        '01_entrevista_enhanced.wav'.
        """
        prefixos = (f"{ordem:02d}_", f"{ordem:02d}-", f"{ordem:02d}.", f"{ordem}_")
        candidatos = []
        for nome in sorted(os.listdir(pasta)):
            caminho = os.path.join(pasta, nome)
            if not os.path.isfile(caminho):
                continue
            if Path(nome).suffix.lower() not in EXTENSOES_AUDIO:
                continue
            if nome.startswith(prefixos):
                candidatos.append(caminho)
        if not candidatos:
            return None
        # Se houver mais de um, fica com o modificado por ultimo (o tratado).
        return max(candidatos, key=lambda c: os.path.getmtime(c))

    def _conferir_partes(self):
        """Compara a duracao de cada parte com o que o manifesto esperava."""
        if not self.manifesto or not self.partes:
            return
        self.status_jun("Conferindo as partes...")
        self.log_jun("-" * 60)
        esperado = {p["ordem"]: p["duracao_seg"] for p in self.manifesto["partes"]}
        soma = 0.0
        alertas = 0
        for i, caminho in enumerate(self.partes, start=1):
            info = ler_info_audio(self.ffmpeg, self.ffprobe, caminho)
            dur = info.get("duracao") or 0
            soma += dur
            alvo = esperado.get(i)
            marca = ""
            if alvo is not None and abs(dur - alvo) > TOLERANCIA_DURACAO:
                marca = f"  <-- ATENCAO: esperava {formatar_tempo(alvo)}"
                alertas += 1
            self.log_jun(f"  {os.path.basename(caminho)}: {formatar_tempo(dur)}{marca}")
        total_orig = self.manifesto["origem"]["duracao_seg"]
        self.log_jun("-" * 60)
        self.log_jun(f"Soma das partes: {formatar_tempo(soma)}  |  "
                     f"Original: {formatar_tempo(total_orig)}  |  "
                     f"Diferenca: {abs(soma - total_orig):.2f}s")
        if alertas:
            self.log_jun(f"ATENCAO: {alertas} parte(s) voltaram com duracao diferente do original. "
                         "Isso normalmente quer dizer que o servico de tratamento cortou silencio "
                         "ou aparou as pontas. Da para juntar assim mesmo, mas o arquivo final "
                         "vai ficar mais curto que o original.")
        else:
            self.log_jun("Conferido: todas as partes voltaram com a duracao esperada.")
        self.status_jun("Partes conferidas. Pode juntar.")

    def adicionar_partes(self):
        caminhos = filedialog.askopenfilenames(
            title="Escolha as partes (na duvida, selecione todas de uma vez)",
            filetypes=[("Audio", " ".join(f"*{e}" for e in sorted(EXTENSOES_AUDIO))),
                       ("Todos os arquivos", "*.*")],
        )
        if not caminhos:
            return
        # Ordena pelo numero do comeco do nome, quando existir.
        def chave(c):
            m = re.match(r"(\d+)", os.path.basename(c))
            return (0, int(m.group(1))) if m else (1, os.path.basename(c).lower())
        for c in sorted(caminhos, key=chave):
            if c not in self.partes:
                self.partes.append(c)
                self.lista.insert(END, f"{len(self.partes):02d}.  {os.path.basename(c)}")
        if not self.pasta_saida_jun and self.partes:
            self.pasta_saida_jun = os.path.dirname(self.partes[0])
        self.log_jun(f"{len(caminhos)} arquivo(s) adicionados. Total na lista: {len(self.partes)}.")

    def limpar_partes(self):
        self.partes = []
        self.manifesto = None
        self.lista.delete(0, END)
        self.log_jun("Lista limpa.")

    def remover_parte(self):
        sel = self.lista.curselection()
        if not sel:
            return
        i = sel[0]
        self.partes.pop(i)
        self._redesenhar_lista()

    def mover(self, direcao):
        sel = self.lista.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + direcao
        if j < 0 or j >= len(self.partes):
            return
        self.partes[i], self.partes[j] = self.partes[j], self.partes[i]
        self._redesenhar_lista()
        self.lista.selection_set(j)

    def _redesenhar_lista(self):
        self.lista.delete(0, END)
        for i, c in enumerate(self.partes, start=1):
            self.lista.insert(END, f"{i:02d}.  {os.path.basename(c)}")

    def iniciar_juncao(self):
        if self.trabalhando:
            return
        if len(self.partes) < 2:
            messagebox.showwarning(APP_NAME, "Coloque pelo menos duas partes na lista.")
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado nesta maquina.")
            return

        infos = [ler_info_audio(self.ffmpeg, self.ffprobe, c) for c in self.partes]
        formato = self.var_formato_jun.get()
        _, ext = opcoes_formato_juncao(formato, infos)

        sugestao = "audio-juntado" + ext
        if self.manifesto:
            base = Path(self.manifesto["origem"]["arquivo"]).stem
            sugestao = f"{base} - juntado{ext}"

        saida = filedialog.asksaveasfilename(
            title="Salvar o audio juntado como",
            initialfile=sugestao,
            initialdir=self.pasta_saida_jun or None,
            defaultextension=ext,
        )
        if not saida:
            return

        self.pasta_saida_jun = os.path.dirname(saida)
        self._travar(True)
        self.cancelar.clear()
        threading.Thread(target=self._rodar_juncao, args=(saida, infos, formato),
                         daemon=True).start()

    def _rodar_juncao(self, saida, infos, formato):
        try:
            self.log_jun("=" * 60)
            self.log_jun(f"Juntando {len(self.partes)} partes.")
            self.status_jun("Juntando...")

            iguais = partes_sao_identicas(infos)
            copia_direta = iguais and formato == JUN_AUTO and \
                len({Path(c).suffix.lower() for c in self.partes}) == 1
            if not iguais:
                self.log_jun("As partes voltaram com formatos diferentes entre si. "
                             "Vou normalizar tudo na juncao.")

            ok = juntar_audios(self.ffmpeg, self.partes, infos, saida, formato,
                               copia_direta, self.log_jun, self.progresso_jun, self.cancelar)
            if not ok or self.cancelar.is_set():
                raise InterruptedError

            self.progresso_jun(100)
            info_final = ler_info_audio(self.ffmpeg, self.ffprobe, saida)
            esperado = sum(i.get("duracao") or 0 for i in infos)
            obtido = info_final.get("duracao") or 0
            self.log_jun("-" * 60)
            self.log_jun(f"Arquivo final: {os.path.basename(saida)}  "
                         f"({formatar_tempo(obtido)}, {formatar_tamanho(info_final.get('tamanho') or 0)})")
            self.log_jun(f"Esperado pela soma das partes: {formatar_tempo(esperado)}  |  "
                         f"Diferenca: {abs(obtido - esperado):.2f}s")
            if abs(obtido - esperado) > TOLERANCIA_DURACAO:
                self.log_jun("ATENCAO: o arquivo final ficou com duracao diferente da soma "
                             "das partes. Confira o resultado antes de usar.")
            else:
                self.log_jun("Conferido: o arquivo final tem exatamente a duracao das partes somadas.")
            self.status_jun("Pronto.")
            self.raiz.after(0, lambda: messagebox.showinfo(
                APP_NAME, f"Audio juntado com sucesso:\n{saida}"))
        except InterruptedError:
            self.status_jun("Cancelado.")
            self.log_jun("Cancelado pelo usuario.")
        except Exception as e:
            self.status_jun("Deu erro.")
            self.log_jun(f"ERRO: {e}")
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    # ------------------------------------------------------------------ util
    def _travar(self, ligado):
        self.trabalhando = ligado
        estado_acao = DISABLED if ligado else NORMAL
        estado_cancel = NORMAL if ligado else DISABLED
        self.bt_dividir.configure(state=estado_acao)
        self.bt_juntar.configure(state=estado_acao)
        self.bt_cancelar_div.configure(state=estado_cancel)
        self.bt_cancelar_jun.configure(state=estado_cancel)

    def pedir_cancelamento(self):
        self.cancelar.set()
        self.status_div("Cancelando...")
        self.status_jun("Cancelando...")

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
    app = Aplicativo(raiz)
    app._alternar_silencio()
    atualizador.iniciar(raiz, "dividir-juntar-audio", APP_VERSION, "Dividir e Juntar Audio")
    raiz.mainloop()


if __name__ == "__main__":
    main()
