# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/cortar_dividir.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

"""
Cortar e dividir - aba compartilhada pelo Video Studio e pelo Audio Studio.

Tres coisas, numa aba so:

Aba interna 1 - Tirar um trecho:
  - escolhe o comeco e o fim pela minutagem;
  - comeco vazio = do inicio do arquivo;
  - fim vazio = da minutagem de comeco ate o fim do arquivo;
  - aceita 1:30, 01:02:03, 90, 1h05m, 2min30s -- e mostra na hora o que
    entendeu, para nao haver duvida;
  - o nome do arquivo que vai sair e montado por Nome + Sufixo, com previa.

Aba interna 2 - Dividir em partes:
  - transforma um arquivo em 2, 3, 10 partes iguais, ou em partes de X minutos;
  - pode cortar no silencio mais proximo, para nao partir palavra no meio;
  - as partes saem numeradas (01_, 02_, ...), e a numeracao vem no COMECO do
    nome de proposito: servico externo cola sufixo no fim ("_enhanced"), nunca
    no comeco, entao a ordem sobrevive a ida e volta;
  - grava um manifesto .json com os tempos, que a aba de juntar le depois.

Aba interna 3 - Juntar de volta:
  - recebe os pedacos (inclusive os que voltaram de um servico externo com
    sufixo colado no nome), coloca na ordem pela numeracao e junta num
    arquivo so, sem descompasso;
  - confere a duracao de cada pedaco contra o manifesto e avisa se o servico
    externo comeu ou esticou algum.

Vale para audio e para video nas tres abas. O parametro `foco` do `montar()`
so muda a ORDEM dos filtros do dialogo de arquivo (e um texto ou outro), para
a pessoa nao ter que trocar o filtro toda vez: o que a aba faz e sempre o
mesmo nos dois estudios.

O corte pode ser exato (recodifica, comeca no ponto certo) ou rapido (nao
recodifica, mas o video so pode ser cortado nos pontos-chave e pode comecar um
pouco antes do pedido).

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.

Esta tela nao cria janela nem define estilo: a janela e o estilo sao do
programa principal do estudio (`tema.py`).
"""

import json
import math
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
    StringVar, IntVar, BooleanVar, END, DISABLED, NORMAL, SINGLE,
    Listbox, filedialog, messagebox, ttk, scrolledtext,
)

import pastas
import tema
from tema import COR_CAMPO, COR_TEXTO, COR_BORDA, COR_DESTAQUE


APP_NAME = "Cortar e dividir"
APP_VERSION = "1.1.0"

EXTENSOES_AUDIO = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".aiff", ".aif",
}
EXTENSOES_VIDEO = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mpg", ".mpeg",
    ".ts", ".3gp", ".wmv",
}
EXTENSOES_MIDIA = EXTENSOES_AUDIO | EXTENSOES_VIDEO

MODO_EXATO = "Exato (recodifica, mais lento)"
MODO_RAPIDO = "Rapido (pode comecar antes)"
MODOS = [MODO_EXATO, MODO_RAPIDO]

# Containers de video que aceitam H.264 sem trocar de extensao.
CONTAINERS_H264 = {".mp4", ".m4v", ".mov", ".mkv"}

# Formatos de saida da juncao.
JUN_AUTO = "Automatico (recomendado)"
JUN_WAV = "WAV 16-bit (sem perdas)"
JUN_MP3 = "MP3 192k"
JUN_M4A = "M4A / AAC 192k"
FORMATOS_JUNCAO = [JUN_AUTO, JUN_WAV, JUN_MP3, JUN_M4A]

# Diferenca (em segundos) a partir da qual a duracao de um pedaco e
# considerada errada -- normalmente porque o servico externo aparou as pontas.
TOLERANCIA_DURACAO = 1.0

# Parametros da busca por silencio. Sao fixos porque funcionam para voz
# gravada, que e o caso real: -35 dB pega respiracao de estudio sem confundir
# ruido de sala com fala, e 0,45 s e a menor pausa que ainda e uma pausa.
SILENCIO_DB = -35
SILENCIO_DURACAO = 0.45


# ---------------------------------------------------------------------------
# Localizacao do ffmpeg / ffprobe embutidos
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir).

    O `_MEIPASS` so existe no executavel empacotado. Rodando pelo codigo, a
    referencia e a pasta do estudio (duas acima deste arquivo, porque ele mora
    em `<estudio>/compartilhado/`), que e onde o ffmpeg baixado costuma ficar.
    """
    aqui = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(aqui)), rel)


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
    for pasta in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin",
                  "/opt/local/bin"):
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
RE_SIL_INI = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
RE_SIL_FIM = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")
RE_SUFIXO = re.compile(
    r"^(?:(\d+(?:[.,]\d+)?)\s*h)?\s*"
    r"(?:(\d+(?:[.,]\d+)?)\s*m(?:in)?)?\s*"
    r"(?:(\d+(?:[.,]\d+)?)\s*s(?:eg)?)?$",
    re.IGNORECASE,
)
# Numero no COMECO do nome do arquivo, que e como as partes sao identificadas
# na volta. Precisa de um separador depois para nao confundir com um nome que
# simplesmente comeca com numero ("2024 entrevista.wav").
RE_NUMERO_PARTE = re.compile(r"^(\d{1,3})[_\-. ]")


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
        return ((_num(h) if h else 0) * 3600 + (_num(mi) if mi else 0) * 60
                + (_num(s) if s else 0))

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
    """Duracao, se tem imagem, codecs, resolucao, som e tamanho do arquivo.

    Traz tambem taxa de amostragem e numero de canais porque a aba de juntar
    precisa saber se os pedacos voltaram todos com o mesmo formato tecnico.
    """
    info = {
        "duracao": None, "tem_video": False, "codec_v": None, "codec_a": None,
        "largura": None, "altura": None, "bitrate_audio": None,
        "sample_rate": None, "canais": None, "tamanho": None,
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
                    sr = fluxo.get("sample_rate")
                    if sr:
                        try:
                            info["sample_rate"] = int(sr)
                        except ValueError:
                            pass
                    info["canais"] = fluxo.get("channels")
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
        saida = ext if ext in CONTAINERS_H264 else ".mp4"
        if saida in (".mp4", ".m4v", ".mov"):
            args += ["-movflags", "+faststart"]
        aviso = "" if saida == ext else (
            f"O formato {ext} nao aceita corte exato: a saida vai sair em {saida}.")
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
        return (["-c:a", "aac", "-b:a", f"{kbps}k"],
                ".m4a" if ext != ".aac" else ".aac", "")
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
           log, progresso, cancelar, duracao_esperada=None, guardar_proc=None):
    """Corta um trecho e grava em 'destino'.

    inicio None (ou 0) = desde o comeco do arquivo.
    duracao None = vai ate o fim do arquivo (nao entra '-t' no comando).
    duracao_esperada e so para a barra de progresso andar certo quando nao ha
    '-t' -- ela nao interfere no corte.
    guardar_proc, quando passado, recebe o processo do ffmpeg assim que ele
    nasce (e None quando ele termina), para que a aba consiga derruba-lo se o
    estudio for fechado no meio do trabalho.
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
    if guardar_proc:
        guardar_proc(proc)
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
        if guardar_proc:
            guardar_proc(None)

    if proc.returncode != 0:
        for l in erros[-6:]:
            log(f"  {l}")
        raise RuntimeError("O ffmpeg nao conseguiu cortar esse arquivo. "
                           "Veja as linhas acima; tente o outro modo de corte.")
    return True


def nome_limpo(texto: str) -> str:
    limpo = re.sub(r"[^\w\-. ]+", "_", texto).strip(" _")
    return limpo or "arquivo"


def nome_sem_espaco(texto: str) -> str:
    """Nome de arquivo para as PARTES: sem espaco, sem acento perdido.

    As partes viajam para servicos externos (transcricao, melhoria de voz) e
    voltam. Espaco em nome de arquivo e o que mais quebra formulario de envio
    e linha de comando alheia, entao aqui ele vira sublinhado.
    """
    limpo = re.sub(r"[^\w\-.]+", "_", texto).strip("_")
    return limpo or "arquivo"


# ---------------------------------------------------------------------------
# Divisao: onde cortar
# ---------------------------------------------------------------------------
def calcular_pontos(duracao, criterio, n_partes, minutos):
    """Instantes (em segundos) onde o arquivo sera cortado.

    Sao so os pontos DE DENTRO: o comeco (0) e o fim nao entram na lista.
    """
    if not duracao or duracao <= 0:
        return []
    if criterio == "partes":
        n = max(2, int(n_partes))
        passo = duracao / n
        pontos = [round(passo * i, 3) for i in range(1, n)]
    else:
        passo = max(1, int(minutos)) * 60.0
        n = max(1, int(math.ceil(duracao / passo)))
        pontos = [round(passo * i, 3) for i in range(1, n)]
    # Um corte a menos de um segundo do fim geraria um pedaco vazio.
    return [p for p in pontos if 0.0 < p < duracao - 1.0]


def pontos_para_partes(duracao, pontos):
    """Transforma os pontos de corte em pares (inicio, duracao).

    A ultima parte fica com duracao None de proposito: assim o ffmpeg le o que
    sobrou do arquivo e nada se perde por arredondamento no fim.
    """
    limites = [0.0] + list(pontos) + [float(duracao)]
    partes = []
    for i in range(len(limites) - 1):
        inicio = round(limites[i], 3)
        dur = None if i == len(limites) - 2 else round(limites[i + 1] - inicio, 3)
        partes.append((inicio, dur))
    return partes


def detectar_silencios(ffmpeg, caminho, ruido_db, dur_min, log, cancelar,
                       progresso=None, duracao_total=None, guardar_proc=None):
    """Devolve a lista de trechos de silencio como pares (inicio, fim).

    Esta varredura le o arquivo inteiro uma vez -- e o preco de nao partir
    palavra no meio.
    """
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-i", caminho,
        "-af", f"silencedetect=noise={ruido_db}dB:d={dur_min}",
        "-f", "null", "-",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **_sem_janela()
    )
    if guardar_proc:
        guardar_proc(proc)
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
                    progresso(min(100.0, hms_para_seg(*mt.groups())
                                  / duracao_total * 100.0))
    finally:
        proc.wait()
        if guardar_proc:
            guardar_proc(None)

    log(f"Silencios encontrados: {len(silencios)}")
    return silencios


def ajustar_para_silencio(alvo, silencios, janela):
    """Move o ponto de corte para o meio do silencio mais proximo do alvo.

    Devolve (novo_ponto, achou). Se nao houver silencio dentro da janela,
    devolve o proprio alvo -- e o corte sai no tempo exato mesmo.
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
# Juncao
# ---------------------------------------------------------------------------
def listar_partes_da_pasta(pasta):
    """Pedacos da pasta, na ordem do numero que abre o nome do arquivo.

    E aqui que a numeracao no comeco do nome paga o investimento: o servico
    externo devolve '01_entrevista_enhanced.wav', com sufixo colado no fim, e
    a ordem continua legivel. Quando ha mais de um arquivo com o mesmo numero
    (o original e o tratado, lado a lado), fica com o modificado por ultimo,
    que e sempre o que voltou do tratamento.
    """
    achados = {}
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return []
    for nome in nomes:
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            continue
        if Path(nome).suffix.lower() not in EXTENSOES_MIDIA:
            continue
        m = RE_NUMERO_PARTE.match(nome)
        if not m:
            continue
        n = int(m.group(1))
        anterior = achados.get(n)
        if anterior is None or os.path.getmtime(caminho) > os.path.getmtime(anterior):
            achados[n] = caminho
    return [achados[k] for k in sorted(achados)]


def partes_sao_identicas(infos):
    """Diz se todos os pedacos tem exatamente o mesmo formato tecnico."""
    if len(infos) < 2:
        return True
    chave = lambda i: (i.get("codec_a"), i.get("sample_rate"), i.get("canais"),
                       i.get("tem_video"), i.get("codec_v"))
    return len({chave(i) for i in infos}) == 1


def opcoes_formato_juncao(formato, infos):
    """Devolve (lista de argumentos, extensao) para o arquivo juntado."""
    # Pedaco com imagem manda no formato: nao adianta pedir MP3 para video.
    if infos and all(i.get("tem_video") for i in infos):
        return (["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart"], ".mp4")

    if formato == JUN_WAV:
        return ["-c:a", "pcm_s16le"], ".wav"
    if formato == JUN_MP3:
        return ["-c:a", "libmp3lame", "-b:a", "192k"], ".mp3"
    if formato == JUN_M4A:
        return ["-c:a", "aac", "-b:a", "192k"], ".m4a"

    # Automatico: segue o codec dos pedacos quando todos sao iguais.
    codecs = {i.get("codec_a") for i in infos if i.get("codec_a")}
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


def juntar(ffmpeg, arquivos, infos, saida, formato, copia_direta,
           log, progresso, cancelar, guardar_proc=None):
    """Junta os pedacos na ordem recebida.

    Dois caminhos:
      - copia direta (concat demuxer + '-c copy'): so quando os pedacos sao
        tecnicamente identicos e o usuario pediu Automatico. Nao recomprime.
      - filtro concat: normaliza formatos diferentes. E o caminho seguro
        quando os pedacos voltaram tratados de um servico externo, cada um com
        a sua taxa de amostragem.
    """
    total = sum(i.get("duracao") or 0 for i in infos) or 1
    tem_video = bool(infos) and all(i.get("tem_video") for i in infos)
    lista = None

    if copia_direta:
        log("Todos os pedacos tem o mesmo formato: juntando por copia direta, "
            "sem recomprimir.")
        lista = saida + ".lista.txt"
        with open(lista, "w", encoding="utf-8") as f:
            for a in arquivos:
                f.write("file '" + os.path.abspath(a).replace("'", "'\\''") + "'\n")
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-f", "concat",
               "-safe", "0", "-i", lista, "-c", "copy", saida]
    else:
        log("Juntando com normalizacao de formato (caminho seguro para "
            "pedacos tratados).")
        args_fmt, _ = opcoes_formato_juncao(formato, infos)
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
        for a in arquivos:
            cmd += ["-i", a]
        n = len(arquivos)
        if tem_video:
            filtro = ("".join(f"[{i}:v][{i}:a]" for i in range(n))
                      + f"concat=n={n}:v=1:a=1[v][a]")
            cmd += ["-filter_complex", filtro, "-map", "[v]", "-map", "[a]"]
        else:
            filtro = ("".join(f"[{i}:a]" for i in range(n))
                      + f"concat=n={n}:v=0:a=1[a]")
            cmd += ["-filter_complex", filtro, "-map", "[a]"]
        cmd += args_fmt + [saida]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **_sem_janela()
    )
    if guardar_proc:
        guardar_proc(proc)
    erros = []
    try:
        for linha in proc.stderr:
            if cancelar.is_set():
                proc.terminate()
                return False
            mt = RE_TEMPO.search(linha)
            if mt and progresso:
                progresso(min(100.0, hms_para_seg(*mt.groups()) / total * 100.0))
            if "Error" in linha or "Invalid" in linha:
                erros.append(linha.strip())
    finally:
        proc.wait()
        if guardar_proc:
            guardar_proc(None)
        if lista and os.path.isfile(lista):
            try:
                os.remove(lista)
            except OSError:
                pass

    if proc.returncode != 0:
        for l in erros[-6:]:
            log(f"  {l}")
        raise RuntimeError("O ffmpeg nao conseguiu juntar os pedacos.")
    return True


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class Aplicativo:

    def __init__(self, pai, foco="video"):
        self.raiz = pai
        # `foco` nao muda o que a aba faz: so a ordem dos filtros do dialogo
        # de arquivo e um texto ou outro.
        self.foco = "audio" if str(foco).lower().startswith("a") else "video"

        # `tema.fontes()` devolve DUAS fontes nos estudios antigos e TRES no
        # Media Studio (que herdou o tema do Transcript Studio, com a fonte
        # mini). Esta tela roda nos dois, entao pega so as duas primeiras, em
        # vez de exigir um numero exato. Sem isso, a aba morre no Media Studio
        # com "too many values to unpack".
        self.fonte_base, self.fonte_peq = tema.fontes()[:2]

        self.ffmpeg = find_ffmpeg()
        self.ffprobe = find_ffprobe()

        self.cancelar = threading.Event()
        self.trabalhando = False
        # O programa principal olha `rodando` antes de fechar a janela.
        self.rodando = False
        self.proc = None

        self.origem = ""
        self.info = {}
        self.destino_corte = ""
        # Regra da casa: comeca sempre na pasta de Downloads.
        self.pasta_destino = pastas.pasta_downloads()
        # Ultimo sufixo que o PROGRAMA escreveu. Serve para saber se a pessoa
        # editou o campo a mao: se editou, o programa para de reescrever.
        self._sufixo_auto = ""
        self.pasta_partes = ""
        self.ultima_pasta = ""

        # Estado da aba de juntar.
        self.pedacos = []          # caminhos, na ordem em que serao juntados
        self.manifesto = None
        self.pasta_juncao = ""

        self._montar()

        if not self.ffmpeg:
            self.log("ATENCAO: ffmpeg nao encontrado nesta maquina. O programa nao vai "
                     "conseguir processar nada. No executavel publicado ele ja vem junto.")
        else:
            tipo = "audio ou video" if self.foco == "audio" else "video ou audio"
            self.log(f"Pronto. Escolha um arquivo de {tipo} para comecar.")

    # ---------------------------------------------------- janela para dialogos
    def _janela(self):
        """A janela de verdade, para os dialogos nascerem em cima dela."""
        return self.raiz.winfo_toplevel()

    def _filtros(self):
        """Filtros do dialogo de arquivo, com o do estudio atual na frente."""
        aud = ("Audio", " ".join(f"*{e}" for e in sorted(EXTENSOES_AUDIO)))
        vid = ("Video", " ".join(f"*{e}" for e in sorted(EXTENSOES_VIDEO)))
        todos = ("Todos os arquivos", "*.*")
        return [aud, vid, todos] if self.foco == "audio" else [vid, aud, todos]

    # -------------------------------------------------------------- montagem
    def _montar(self):
        # O registro, o status e a barra sao empacotados PRIMEIRO, ancorados no
        # fundo: quem vai para "bottom" antes fica mais embaixo, e assim eles
        # nunca sao empurrados para fora numa janela baixa.
        self.txt = scrolledtext.ScrolledText(
            self.raiz, height=3, state=DISABLED, wrap="word",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, relief="flat", font=self.fonte_peq,
        )
        self.txt.pack(side="bottom", fill="both", expand=False, padx=10, pady=(0, 6))

        self.var_status = StringVar(value="Pronto.")
        ttk.Label(self.raiz, textvariable=self.var_status,
                  style="Suave.TLabel").pack(side="bottom", anchor="w",
                                             padx=10, pady=(2, 4))

        self.prog = ttk.Progressbar(self.raiz, mode="determinate", maximum=100,
                                    style="Horizontal.TProgressbar")
        self.prog.pack(side="bottom", fill="x", padx=10)

        topo = ttk.Frame(self.raiz, padding=(10, 8, 10, 0))
        topo.pack(side="top", fill="x")

        rotulo = (" Arquivo de audio ou video " if self.foco == "audio"
                  else " Arquivo de video ou audio ")
        cx = ttk.LabelFrame(topo, text=rotulo, padding=8)
        cx.pack(fill="x")
        linha = ttk.Frame(cx)
        linha.pack(fill="x")
        self.var_origem = StringVar(value="Nenhum arquivo escolhido")
        ttk.Label(linha, textvariable=self.var_origem).pack(
            side="left", fill="x", expand=True)
        ttk.Button(linha, text="Escolher arquivo...",
                   command=self.escolher_origem).pack(side="right")
        self.var_info = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_info, style="Suave.TLabel").pack(
            anchor="w", pady=(4, 0))

        # O modo de corte cabe numa linha so, dentro deste mesmo quadro: um
        # LabelFrame proprio custava altura demais para duas opcoes.
        lm = ttk.Frame(cx)
        lm.pack(fill="x", pady=(4, 0))
        ttk.Label(lm, text="Corte:").pack(side="left")
        self.var_modo = StringVar(value=MODO_EXATO)
        for m in MODOS:
            ttk.Radiobutton(lm, text=m, variable=self.var_modo,
                            value=m).pack(side="left", padx=(10, 0))
        # A reacao fica presa a variavel, e nao ao `command` do radio: assim ela
        # tambem acontece quando o modo e trocado por codigo.
        self.var_modo.trace_add("write", lambda *_: self._modo_mudou())

        cad = ttk.Notebook(self.raiz, style="Interna.TNotebook")
        cad.pack(side="top", fill="both", expand=True, padx=10, pady=(8, 6))
        self.aba_corte = ttk.Frame(cad, padding=8)
        self.aba_div = ttk.Frame(cad, padding=8)
        self.aba_jun = ttk.Frame(cad, padding=8)
        cad.add(self.aba_corte, text="  Tirar um trecho  ")
        cad.add(self.aba_div, text="  Dividir em partes  ")
        cad.add(self.aba_jun, text="  Juntar de volta  ")

        self._montar_aba_corte()
        self._montar_aba_dividir()
        self._montar_aba_juntar()

    # ----------------------------------------------------------- aba cortar
    def _montar_aba_corte(self):
        p = self.aba_corte

        # Os botoes sao empacotados primeiro, ancorados no fundo da aba. Assim
        # eles continuam na tela mesmo com a janela baixa -- antes o "Cortar"
        # era empurrado para fora e sumia.
        bt = ttk.Frame(p)
        bt.pack(side="bottom", fill="x", pady=(8, 0))
        self.bt_cortar = ttk.Button(bt, text="Cortar", style="Acao.TButton",
                                    command=self.iniciar_corte)
        self.bt_cortar.pack(side="left")
        self.bt_cancelar_c = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                        command=self.pedir_cancelamento)
        self.bt_cancelar_c.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta do resultado",
                   command=lambda: self.abrir_pasta(self.ultima_pasta)).pack(side="right")

        cx = ttk.LabelFrame(p, text=" Trecho que voce quer guardar ", padding=8)
        cx.pack(fill="x")

        grade = ttk.Frame(cx)
        grade.pack(fill="x")
        grade.columnconfigure(3, weight=1)

        ttk.Label(grade, text="Comeca em:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_ini = StringVar(value="")
        ttk.Entry(grade, textvariable=self.var_ini, width=14).grid(row=0, column=1, padx=6)
        self.var_ini_lido = StringVar(
            value="vazio = do inicio  •  ex.: 1:30, 90, 5m, 1h30m")
        ttk.Label(grade, textvariable=self.var_ini_lido, style="Ok.TLabel").grid(
            row=0, column=2, columnspan=2, sticky="w")

        ttk.Label(grade, text="Termina em:").grid(row=1, column=0, sticky="w", pady=2)
        self.var_fim = StringVar(value="")
        ttk.Entry(grade, textvariable=self.var_fim, width=14).grid(row=1, column=1, padx=6)
        self.var_fim_lido = StringVar(value="vazio = ate o fim")
        ttk.Label(grade, textvariable=self.var_fim_lido, style="Ok.TLabel").grid(
            row=1, column=2, columnspan=2, sticky="w")

        self.var_resumo = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_resumo, style="Ok.TLabel",
                  font=(self.fonte_base[0], self.fonte_base[1], "bold")).pack(
            anchor="w", pady=(6, 0))

        # ------------------------------------------- arquivo que vai sair
        # Nome, sufixo e pasta ficam no MESMO quadro. Eram dois quadros
        # separados, e na janela no tamanho minimo o segundo era empurrado
        # para tras dos botoes e sumia.
        cx2 = ttk.LabelFrame(p, text=" Arquivo que vai sair ", padding=8)
        cx2.pack(fill="x", pady=(6, 0))

        gn = ttk.Frame(cx2)
        gn.pack(fill="x")
        gn.columnconfigure(1, weight=3)
        gn.columnconfigure(3, weight=2)

        ttk.Label(gn, text="Nome:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_nome = StringVar(value="")
        ttk.Entry(gn, textvariable=self.var_nome).grid(
            row=0, column=1, sticky="ew", padx=(6, 12))

        ttk.Label(gn, text="Sufixo:").grid(row=0, column=2, sticky="w", pady=2)
        self.var_sufixo = StringVar(value="")
        ttk.Entry(gn, textvariable=self.var_sufixo).grid(
            row=0, column=3, sticky="ew", padx=6)
        ttk.Button(gn, text="Voltar ao padrao",
                   command=self.restaurar_sufixo).grid(row=0, column=4,
                                                       sticky="ew", padx=(6, 0))

        # A explicacao longa do sufixo saiu: o campo ja mostra o valor, a previa
        # mostra o resultado e o botao "Voltar ao padrao" desfaz a edicao.
        ttk.Label(gn, text="Pasta:").grid(row=1, column=0, sticky="w", pady=2)
        self.var_destino = StringVar(value=self.pasta_destino)
        ttk.Label(gn, textvariable=self.var_destino,
                  style="Suave.TLabel").grid(row=1, column=1, columnspan=3,
                                             sticky="w", padx=6)
        ttk.Button(gn, text="Trocar...",
                   command=self.escolher_destino).grid(row=1, column=4,
                                                       sticky="ew", padx=(6, 0),
                                                       pady=(2, 0))

        # A previa fica DENTRO do mesmo grid: como Label solto no LabelFrame
        # ela era a ultima a ser empacotada e, na janela no tamanho minimo,
        # ficava de fora.
        self.var_previa_nome = StringVar(value="")
        ttk.Label(gn, textvariable=self.var_previa_nome,
                  style="Destaque.TLabel").grid(row=2, column=0, columnspan=5,
                                                sticky="w", pady=(4, 0))

        self.var_ini.trace_add("write", lambda *_: self.atualizar_corte())
        self.var_fim.trace_add("write", lambda *_: self.atualizar_corte())
        # A previa reage a QUALQUER mudanca nos dois campos, inclusive quando
        # o valor e trocado por codigo (ao abrir outro arquivo, ao clicar em
        # "Voltar ao padrao"). Por isso a reacao fica presa na variavel.
        self.var_nome.trace_add("write", lambda *_: self.atualizar_previa_nome())
        self.var_sufixo.trace_add("write", lambda *_: self.atualizar_previa_nome())

    # ---------------------------------------------------------- aba dividir
    def _montar_aba_dividir(self):
        p = self.aba_div

        bt = ttk.Frame(p)
        bt.pack(side="bottom", fill="x", pady=(8, 0))
        self.bt_dividir = ttk.Button(bt, text="Dividir", style="Acao.TButton",
                                     command=self.iniciar_divisao)
        self.bt_dividir.pack(side="left")
        self.bt_cancelar_d = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                        command=self.pedir_cancelamento)
        self.bt_cancelar_d.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta das partes",
                   command=lambda: self.abrir_pasta(self.ultima_pasta)).pack(side="right")

        cx = ttk.LabelFrame(p, text=" Em quantos pedacos ", padding=8)
        cx.pack(fill="x")

        # As duas opcoes cabem na mesma linha, cada uma com o seu numero ao lado.
        self.var_criterio = StringVar(value="partes")
        l1 = ttk.Frame(cx)
        l1.pack(fill="x", pady=1)
        ttk.Radiobutton(l1, text="Quantas partes:", variable=self.var_criterio,
                        value="partes").pack(side="left")
        self.var_n = IntVar(value=2)
        ttk.Spinbox(l1, from_=2, to=99, width=6,
                    textvariable=self.var_n).pack(side="left", padx=8)
        ttk.Radiobutton(l1, text="Ou partes de quantos minutos:",
                        variable=self.var_criterio,
                        value="minutos").pack(side="left", padx=(20, 0))
        self.var_min = IntVar(value=10)
        ttk.Spinbox(l1, from_=1, to=600, width=6,
                    textvariable=self.var_min).pack(side="left", padx=8)

        # Corte no silencio: uma linha so, com a janela de busca ao lado.
        l2 = ttk.Frame(cx)
        l2.pack(fill="x", pady=(3, 0))
        self.var_silencio = BooleanVar(value=False)
        ttk.Checkbutton(l2, text="Cortar no silencio mais proximo (nao parte palavra)",
                        variable=self.var_silencio).pack(side="left")
        self.lbl_janela = ttk.Label(l2, text="ate", style="Suave.TLabel")
        self.lbl_janela.pack(side="left", padx=(10, 4))
        self.var_janela = IntVar(value=45)
        self.sp_janela = ttk.Spinbox(l2, from_=5, to=300, width=5,
                                     textvariable=self.var_janela)
        self.sp_janela.pack(side="left")
        self.lbl_janela2 = ttk.Label(l2, text="s do ponto ideal",
                                     style="Suave.TLabel")
        self.lbl_janela2.pack(side="left", padx=(4, 0))

        self.var_previa = StringVar(value="")
        ttk.Label(cx, textvariable=self.var_previa, style="Ok.TLabel",
                  font=(self.fonte_base[0], self.fonte_base[1], "bold")).pack(
            anchor="w", pady=(6, 0))

        cx2 = ttk.LabelFrame(p, text=" Onde salvar as partes ", padding=8)
        cx2.pack(fill="x", pady=(6, 0))
        l3 = ttk.Frame(cx2)
        l3.pack(fill="x")
        self.var_pasta = StringVar(value="(escolha um arquivo primeiro)")
        ttk.Label(l3, textvariable=self.var_pasta).pack(
            side="left", fill="x", expand=True)
        ttk.Button(l3, text="Trocar pasta...",
                   command=self.escolher_pasta).pack(side="right")

        # Tudo que muda a previa fica preso a variavel, nunca ao `command` do
        # radio, do spinbox ou da caixa de marcar: assim a previa tambem reage
        # quando o valor e trocado por codigo.
        self.var_criterio.trace_add("write", lambda *_: self.atualizar_divisao())
        self.var_n.trace_add("write", lambda *_: self.atualizar_divisao())
        self.var_min.trace_add("write", lambda *_: self.atualizar_divisao())
        self.var_silencio.trace_add("write", lambda *_: self._silencio_mudou())
        self._silencio_mudou()

    def _silencio_mudou(self):
        """Liga e desliga o campo da janela de busca junto com a caixa."""
        estado = NORMAL if self.var_silencio.get() else DISABLED
        for w in (self.sp_janela,):
            try:
                w.configure(state=estado)
            except Exception:
                pass
        estilo = "Suave.TLabel" if self.var_silencio.get() else "Apagado.TLabel"
        for w in (self.lbl_janela, self.lbl_janela2):
            try:
                w.configure(style=estilo)
            except Exception:
                pass

    # ----------------------------------------------------------- aba juntar
    def _montar_aba_juntar(self):
        p = self.aba_jun

        bt = ttk.Frame(p)
        bt.pack(side="bottom", fill="x", pady=(8, 0))
        self.bt_juntar = ttk.Button(bt, text="Juntar e salvar...",
                                    style="Acao.TButton",
                                    command=self.iniciar_juncao)
        self.bt_juntar.pack(side="left")
        self.bt_cancelar_j = ttk.Button(bt, text="Cancelar", state=DISABLED,
                                        command=self.pedir_cancelamento)
        self.bt_cancelar_j.pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir pasta do resultado",
                   command=lambda: self.abrir_pasta(self.ultima_pasta)).pack(side="right")

        lf = ttk.Frame(p)
        lf.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Label(lf, text="Formato final:").pack(side="left")
        self.var_formato_jun = StringVar(value=JUN_AUTO)
        ttk.Combobox(lf, textvariable=self.var_formato_jun,
                     values=FORMATOS_JUNCAO, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        cx = ttk.LabelFrame(p, text=" Pedacos, na ordem em que serao juntados ",
                            padding=8)
        cx.pack(fill="both", expand=True)

        topo = ttk.Frame(cx)
        topo.pack(fill="x", pady=(0, 4))
        ttk.Button(topo, text="Escolher a pasta dos pedacos...",
                   command=self.carregar_pasta_pedacos).pack(side="left")
        ttk.Button(topo, text="Adicionar arquivos...",
                   command=self.adicionar_pedacos).pack(side="left", padx=6)
        ttk.Button(topo, text="Limpar", command=self.limpar_pedacos).pack(side="left")

        meio = ttk.Frame(cx)
        meio.pack(fill="both", expand=True)
        # Listbox e Tk puro: a cor vai na mao, senao no Mac escuro sai letra
        # clara em fundo claro.
        self.lista = Listbox(
            meio, selectmode=SINGLE, activestyle="none", height=4,
            bg=COR_CAMPO, fg=COR_TEXTO, selectbackground=COR_DESTAQUE,
            selectforeground="#1a1a1a", highlightbackground=COR_BORDA,
            highlightcolor=COR_BORDA, relief="flat", font=self.fonte_peq,
        )
        self.lista.pack(side="left", fill="both", expand=True)
        barra = ttk.Scrollbar(meio, orient="vertical", command=self.lista.yview)
        barra.pack(side="left", fill="y")
        self.lista.configure(yscrollcommand=barra.set)

        lado = ttk.Frame(meio, padding=(8, 0))
        lado.pack(side="left", fill="y")
        ttk.Button(lado, text="Subir", width=9,
                   command=lambda: self.mover(-1)).pack(pady=1)
        ttk.Button(lado, text="Descer", width=9,
                   command=lambda: self.mover(1)).pack(pady=1)
        ttk.Button(lado, text="Remover", width=9,
                   command=self.remover_pedaco).pack(pady=1)

        ttk.Label(cx, text="A ordem vem do numero no comeco do nome, mesmo que o "
                           "servico externo tenha colado sufixo no fim.",
                  style="Apagado.TLabel").pack(anchor="w", pady=(4, 0))

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
            title="Escolha o arquivo",
            filetypes=self._filtros(),
            parent=self._janela(),
        )
        if not caminho:
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado nesta maquina.",
                                 parent=self._janela())
            return
        self.origem = caminho
        self.var_origem.set(os.path.basename(caminho))
        self.var_info.set("Lendo o arquivo...")
        self.destino_corte = ""
        # Arquivo novo: o nome volta a ser o do original e o sufixo volta a
        # ser automatico, mesmo que a pessoa tivesse editado o do anterior.
        # A pasta escolhida NAO se perde: se a pessoa ja tinha trocado, ela
        # continua valendo para o proximo arquivo.
        self.var_nome.set(nome_limpo(Path(caminho).stem))
        self._sufixo_auto = ""
        self.var_sufixo.set("")
        self.pasta_partes = str(Path(pastas.pasta_downloads()) /
                                (Path(caminho).stem + " - partes"))
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
            self.var_ini_lido.set("vazio = do inicio" if ini is None
                                  else f"= {formatar_tempo(ini)}")
            erro_ini = False
        except ValueError as e:
            self.var_ini_lido.set(str(e))
            erro_ini = True

        try:
            fim = parse_tempo(self.var_fim.get())
            self.var_fim_lido.set("vazio = ate o fim" if fim is None
                                  else f"= {formatar_tempo(fim)}")
            erro_fim = False
        except ValueError as e:
            self.var_fim_lido.set(str(e))
            erro_fim = True

        if erro_ini or erro_fim or not dur:
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

        self._propor_sufixo(ini, fim_real)

    # ------------------------------------------------------- nome de saida
    def _sufixo_padrao(self, ini, fim) -> str:
        """Minutagem do trecho no formato HH-MM-SS_HH-MM-SS.

        Os dois-pontos do relogio viram traco porque o Windows proibe ":" em
        nome de arquivo e o Finder do Mac o converte em barra. O separador
        entre os dois horarios e "_" para que de para ler onde um termina e o
        outro comeca, ja que dentro de cada um o traco esta ocupado.
        """
        return f"{formatar_tempo_arquivo(ini)}_{formatar_tempo_arquivo(fim)}"

    def _propor_sufixo(self, ini, fim):
        """Reescreve o sufixo com a minutagem nova, se a pessoa nao o editou.

        A regra e simples: o programa so mexe no campo enquanto o que estiver
        la for exatamente o ultimo padrao que ele mesmo escreveu. Assim que a
        pessoa digita qualquer coisa diferente, o campo passa a ser dela.
        """
        novo = self._sufixo_padrao(ini, fim)
        if self.var_sufixo.get().strip() in ("", self._sufixo_auto):
            self._sufixo_auto = novo
            self.var_sufixo.set(novo)
        else:
            # Guarda o padrao atual mesmo sem aplicar, para o botao
            # "Voltar ao padrao" ter sempre a minutagem em dia.
            self._sufixo_auto = novo
        self.atualizar_previa_nome()

    def restaurar_sufixo(self):
        """Devolve ao sufixo a minutagem do trecho escolhido agora."""
        if not self.origem:
            return
        try:
            ini, fim = self._ler_campos()
        except ValueError:
            return
        dur = self.info.get("duracao") or 0
        ini = ini or 0.0
        fim_real = dur if fim is None else min(fim, dur)
        self._sufixo_auto = self._sufixo_padrao(ini, fim_real)
        self.var_sufixo.set(self._sufixo_auto)

    def _nome_de_saida(self) -> str:
        """Monta o nome do arquivo (sem pasta), ja limpo e com a extensao."""
        base = Path(self.origem)
        _, ext, _ = opcoes_saida(self.info, base.suffix.lower(),
                                 self.var_modo.get())

        nome = nome_limpo(self.var_nome.get().strip())
        if not nome:
            nome = nome_limpo(base.stem)
        sufixo = nome_limpo(self.var_sufixo.get().strip())

        return f"{nome} - {sufixo}{ext}" if sufixo else f"{nome}{ext}"

    def atualizar_previa_nome(self):
        if not self.origem:
            self.var_previa_nome.set("")
            return
        self.var_previa_nome.set(f"Vai salvar como:  {self._nome_de_saida()}")

    def _destino_sugerido(self, ini=None, fim=None):
        """Caminho completo do arquivo de saida.

        Os parametros `ini` e `fim` nao sao mais usados para montar o nome
        (quem manda agora sao os campos Nome e Sufixo), mas continuam na
        assinatura porque o resto do codigo chama com eles.
        """
        pasta = self.pasta_destino or pastas.pasta_downloads()
        return str(Path(pasta) / self._nome_de_saida())

    def escolher_destino(self):
        if not self.origem:
            messagebox.showwarning(APP_NAME,
                                   "Escolha primeiro o arquivo que voce quer cortar.",
                                   parent=self._janela())
            return
        pasta = filedialog.askdirectory(
            title="Escolha a pasta onde salvar o trecho",
            initialdir=self.pasta_destino or pastas.pasta_downloads(),
            parent=self._janela(),
        )
        if pasta:
            self.pasta_destino = pasta
            self.var_destino.set(pasta)

    # --------------------------------------------------- calculos da divisao
    def atualizar_divisao(self):
        dur = self.info.get("duracao")
        if not dur:
            self.var_previa.set("")
            return
        try:
            pontos = calcular_pontos(dur, self.var_criterio.get(),
                                     self.var_n.get(), self.var_min.get())
        except Exception:
            self.var_previa.set("")
            return
        if not pontos:
            self.var_previa.set("Do jeito que esta sairia um arquivo so.")
            return

        partes = pontos_para_partes(dur, pontos)
        n = len(partes)
        ultima = dur - partes[-1][0]
        if self.var_criterio.get() == "partes":
            self.var_previa.set(
                f"Vai gerar {n} partes de aproximadamente "
                f"{formatar_tempo(dur / n)} cada.")
        elif n > 1 and abs(ultima - (partes[0][1] or 0)) > 5:
            # A ultima parte quase sempre sobra menor: melhor dizer o tamanho dela.
            self.var_previa.set(
                f"Vai gerar {n} partes: {n - 1} de {formatar_tempo(partes[0][1])} "
                f"e a ultima de {formatar_tempo(ultima)}.")
        else:
            self.var_previa.set(
                f"Vai gerar {n} partes de aproximadamente "
                f"{formatar_tempo(dur / n)} cada.")

    def escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Onde salvar as partes",
                                        initialdir=self.pasta_partes or
                                        pastas.pasta_downloads(),
                                        parent=self._janela())
        if pasta:
            self.pasta_partes = pasta
            self.var_pasta.set(pasta)

    # ---------------------------------------------------------- acao: cortar
    def iniciar_corte(self):
        if self.trabalhando:
            return
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha primeiro o arquivo que voce quer cortar.",
                                   parent=self._janela())
            return
        dur = self.info.get("duracao")
        if not dur:
            messagebox.showerror(APP_NAME, "Nao consegui ler a duracao desse arquivo.",
                                 parent=self._janela())
            return
        try:
            ini, fim = self._ler_campos()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e), parent=self._janela())
            return

        ini = ini or 0.0
        if ini >= dur:
            messagebox.showerror(APP_NAME, "O comeco que voce escreveu esta depois do fim do arquivo.",
                                 parent=self._janela())
            return
        if fim is not None and fim <= ini:
            messagebox.showerror(APP_NAME, "O fim precisa vir depois do comeco.",
                                 parent=self._janela())
            return
        fim_real = dur if fim is None else min(fim, dur)
        duracao_trecho = fim_real - ini

        destino = self.destino_corte or self._destino_sugerido(ini, fim_real)
        if os.path.abspath(destino) == os.path.abspath(self.origem):
            messagebox.showerror(APP_NAME, "O arquivo de saida nao pode ser o mesmo da entrada.",
                                 parent=self._janela())
            return
        if os.path.exists(destino):
            if not messagebox.askyesno(APP_NAME, f"Ja existe um arquivo chamado\n"
                                                 f"{os.path.basename(destino)}\n\nSubstituir?",
                                       parent=self._janela()):
                return

        self._travar(True)
        self.cancelar.clear()
        # Tudo que vem da janela (modo, campos) e lido aqui, na thread da
        # interface. A thread de trabalho so recebe valores prontos: mexer em
        # variavel do Tkinter de outra thread da problema.
        threading.Thread(target=self._rodar_corte,
                         args=(ini, duracao_trecho if fim is not None else None,
                               fim_real, destino, self.var_modo.get()),
                         daemon=True).start()

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
                        duracao_esperada=fim_real - ini,
                        guardar_proc=self._guardar_proc)
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
                APP_NAME, f"Trecho salvo em:\n{destino}", parent=self._janela()))
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
            # O texto e guardado numa variavel a parte porque o Python apaga o
            # 'e' assim que o except termina, e este aviso so aparece depois.
            recado = str(e)
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, recado,
                                                            parent=self._janela()))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    # --------------------------------------------------------- acao: dividir
    def iniciar_divisao(self):
        if self.trabalhando:
            return
        if not self.origem:
            messagebox.showwarning(APP_NAME, "Escolha primeiro o arquivo que voce quer dividir.",
                                   parent=self._janela())
            return
        dur = self.info.get("duracao")
        if not dur:
            messagebox.showerror(APP_NAME, "Nao consegui ler a duracao desse arquivo.",
                                 parent=self._janela())
            return
        pontos = calcular_pontos(dur, self.var_criterio.get(),
                                 self.var_n.get(), self.var_min.get())
        if not pontos:
            messagebox.showwarning(APP_NAME, "Do jeito que esta configurado sairia um arquivo so. "
                                             "Aumente o numero de partes ou diminua os minutos.",
                                   parent=self._janela())
            return
        pastas.garantir(self.pasta_partes)
        self._travar(True)
        self.cancelar.clear()
        threading.Thread(
            target=self._rodar_divisao,
            args=(pontos, self.var_modo.get(), self.pasta_partes,
                  bool(self.var_silencio.get()), int(self.var_janela.get())),
            daemon=True).start()

    def _rodar_divisao(self, pontos, modo, pasta_partes, usar_silencio, janela):
        try:
            dur = self.info.get("duracao") or 0
            ext_orig = Path(self.origem).suffix.lower()
            _, ext, aviso = opcoes_saida(self.info, ext_orig, modo)
            # Nome sem espaco: as partes viajam para servicos externos.
            base = nome_sem_espaco(Path(self.origem).stem)

            self.log("=" * 60)
            self.log(f"Dividindo em {len(pontos) + 1} partes.")
            if aviso:
                self.log(aviso)

            if usar_silencio:
                self.status("Procurando os silencios...")
                self.log("Procurando silencios (essa varredura le o arquivo inteiro).")
                silencios = detectar_silencios(
                    self.ffmpeg, self.origem, SILENCIO_DB, SILENCIO_DURACAO,
                    self.log, self.cancelar, self.progresso, dur,
                    guardar_proc=self._guardar_proc)
                if self.cancelar.is_set():
                    raise InterruptedError
                novos, achados = [], 0
                for alvo in pontos:
                    novo, achou = ajustar_para_silencio(alvo, silencios, janela)
                    novos.append(round(novo, 3))
                    achados += 1 if achou else 0
                # Os pontos precisam continuar em ordem crescente e sem repetir:
                # dois alvos vizinhos podem cair no mesmo silencio.
                pontos = sorted(set(novos))
                self.log(f"{achados} de {len(pontos)} cortes cairam em silencio.")
                self.progresso(0)

            partes = pontos_para_partes(dur, pontos)
            gerados = []
            total = len(partes)
            for i, (inicio, duracao) in enumerate(partes, start=1):
                if self.cancelar.is_set():
                    raise InterruptedError
                # O numero vem no COMECO do nome: e o que sobrevive ao sufixo
                # que servico externo cola no fim.
                destino = os.path.join(pasta_partes, f"{i:02d}_{base}{ext}")
                self.status(f"Cortando a parte {i} de {total}...")
                self.log(f"  Parte {i}: de {formatar_tempo(inicio)} "
                         f"({formatar_tempo(duracao) if duracao else 'ate o fim'})")

                def prog_parcial(pct, i=i):
                    self.progresso(((i - 1) + pct / 100.0) / total * 100.0)

                ok = cortar(self.ffmpeg, self.origem, destino, inicio, duracao,
                            self.info, modo, self.log, prog_parcial, self.cancelar,
                            duracao_esperada=dur - inicio,
                            guardar_proc=self._guardar_proc)
                if not ok or self.cancelar.is_set():
                    raise InterruptedError
                gerados.append(destino)
                self.progresso(i / total * 100.0)

            self.progresso(100)
            self.ultima_pasta = pasta_partes
            soma = 0.0
            registro = []
            self.log("-" * 60)
            for ordem, caminho in enumerate(gerados, start=1):
                d = ler_duracao(self.ffprobe, caminho)
                soma += d or 0
                tam = os.path.getsize(caminho) if os.path.exists(caminho) else 0
                registro.append({
                    "ordem": ordem,
                    "arquivo": os.path.basename(caminho),
                    "inicio_seg": round(partes[ordem - 1][0], 3),
                    "duracao_seg": round(d or 0, 3),
                    "tamanho_bytes": tam,
                })
                self.log(f"  {os.path.basename(caminho)}  "
                         f"({formatar_tempo(d) if d else '?'}, {formatar_tamanho(tam)})")
            self.log("-" * 60)
            self.log(f"Soma das partes: {formatar_tempo(soma)}   |   "
                     f"Original: {formatar_tempo(dur)}   |   "
                     f"Diferenca: {abs(soma - dur):.2f}s")
            if abs(soma - dur) > TOLERANCIA_DURACAO:
                self.log("ATENCAO: a soma das partes ficou diferente do original.")

            caminho_manifesto = self._gravar_manifesto(pasta_partes, base, dur,
                                                       registro, modo,
                                                       usar_silencio)
            if caminho_manifesto:
                self.log(f"Manifesto salvo: {os.path.basename(caminho_manifesto)}. "
                         "A aba 'Juntar de volta' usa ele para conferir as duracoes.")

            self.status(f"Pronto: {len(gerados)} partes geradas.")
            self.raiz.after(0, lambda: messagebox.showinfo(
                APP_NAME, f"{len(gerados)} partes geradas em:\n{pasta_partes}",
                parent=self._janela()))
        except InterruptedError:
            self.status("Cancelado.")
            self.log("Cancelado pelo usuario. As partes que ja tinham ficado prontas "
                     "continuam na pasta.")
        except Exception as e:
            self.status("Deu erro.")
            self.log(f"ERRO: {e}")
            # Mesmo motivo do corte: o 'e' some no fim do except.
            recado = str(e)
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, recado,
                                                            parent=self._janela()))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    def _gravar_manifesto(self, pasta, base, dur, registro, modo, usar_silencio):
        """Grava o .json com os tempos de corte, ao lado das partes.

        E um arquivo minusculo e serve a uma coisa so: quando as partes
        voltarem do servico externo, dizer qual era a duracao esperada de cada
        uma, para o programa avisar se alguma foi aparada. Se nao der para
        gravar, o trabalho ja esta feito e nao vale interromper por isso.
        """
        try:
            manifesto = {
                "programa": APP_NAME,
                "versao": APP_VERSION,
                "criado_em": datetime.now().isoformat(timespec="seconds"),
                "origem": {
                    "arquivo": os.path.basename(self.origem),
                    "duracao_seg": round(dur, 3),
                },
                "modo_corte": modo,
                "corte_no_silencio": bool(usar_silencio),
                "partes": registro,
            }
            caminho = os.path.join(pasta, f"manifesto_{base}.json")
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(manifesto, f, ensure_ascii=False, indent=2)
            return caminho
        except Exception:
            return None

    # ---------------------------------------------------------- acao: juntar
    def carregar_pasta_pedacos(self):
        """Le uma pasta inteira e monta a lista na ordem da numeracao."""
        pasta = filedialog.askdirectory(
            title="Onde estao os pedacos (ja tratados, se for o caso)?",
            initialdir=self.pasta_partes or pastas.pasta_downloads(),
            parent=self._janela(),
        )
        if not pasta:
            return

        achados = listar_partes_da_pasta(pasta)
        if not achados:
            messagebox.showwarning(
                APP_NAME,
                "Nao achei nessa pasta nenhum arquivo numerado no comeco do nome "
                "(01_, 02_...).\n\nUse 'Adicionar arquivos...' e ponha na ordem "
                "com os botoes Subir e Descer.",
                parent=self._janela())
            return

        self.pedacos = achados
        self.pasta_juncao = pasta
        self._redesenhar_lista()
        self.log("=" * 60)
        self.log(f"{len(achados)} pedacos encontrados em {pasta}.")

        # O manifesto e opcional: sem ele a juncao funciona igual, so nao da
        # para avisar se algum pedaco voltou com a duracao errada.
        self.manifesto = None
        try:
            candidatos = [n for n in sorted(os.listdir(pasta))
                          if n.startswith("manifesto_") and n.endswith(".json")]
            if candidatos:
                with open(os.path.join(pasta, candidatos[0]), "r",
                          encoding="utf-8") as f:
                    self.manifesto = json.load(f)
                self.log(f"Manifesto encontrado: {candidatos[0]}.")
        except Exception:
            self.manifesto = None

        threading.Thread(target=self._conferir_pedacos, daemon=True).start()

    def _conferir_pedacos(self):
        """Compara a duracao de cada pedaco com o que o manifesto esperava."""
        if not self.pedacos:
            return
        self.status("Conferindo os pedacos...")
        esperado = {}
        total_orig = None
        if self.manifesto:
            esperado = {p["ordem"]: p["duracao_seg"]
                        for p in self.manifesto.get("partes", [])}
            total_orig = (self.manifesto.get("origem") or {}).get("duracao_seg")

        soma, alertas = 0.0, 0
        self.log("-" * 60)
        for i, caminho in enumerate(list(self.pedacos), start=1):
            info = ler_info_midia(self.ffmpeg, self.ffprobe, caminho)
            d = info.get("duracao") or 0
            soma += d
            alvo = esperado.get(i)
            marca = ""
            if alvo is not None and abs(d - alvo) > TOLERANCIA_DURACAO:
                marca = f"  <-- ATENCAO: esperava {formatar_tempo(alvo)}"
                alertas += 1
            self.log(f"  {os.path.basename(caminho)}: {formatar_tempo(d)}{marca}")
        self.log("-" * 60)
        if total_orig:
            self.log(f"Soma dos pedacos: {formatar_tempo(soma)}   |   "
                     f"Original: {formatar_tempo(total_orig)}   |   "
                     f"Diferenca: {abs(soma - total_orig):.2f}s")
        else:
            self.log(f"Soma dos pedacos: {formatar_tempo(soma)}.")
        if alertas:
            self.log(f"ATENCAO: {alertas} pedaco(s) voltaram com duracao diferente. "
                     "Isso normalmente quer dizer que o servico de tratamento cortou "
                     "silencio ou aparou as pontas. Da para juntar assim mesmo, mas o "
                     "arquivo final vai ficar mais curto que o original.")
        elif esperado:
            self.log("Conferido: todos os pedacos voltaram com a duracao esperada.")
        self.status("Pedacos conferidos. Pode juntar.")

    def adicionar_pedacos(self):
        caminhos = filedialog.askopenfilenames(
            title="Escolha os pedacos (na duvida, selecione todos de uma vez)",
            filetypes=self._filtros(),
            parent=self._janela(),
        )
        if not caminhos:
            return

        # Ordena pelo numero do comeco do nome, quando existir; quem nao tiver
        # numero vai para o fim, em ordem alfabetica.
        def chave(c):
            m = RE_NUMERO_PARTE.match(os.path.basename(c))
            return (0, int(m.group(1)), "") if m else (1, 0, os.path.basename(c).lower())

        novos = 0
        for c in sorted(caminhos, key=chave):
            if c not in self.pedacos:
                self.pedacos.append(c)
                novos += 1
        if not self.pasta_juncao and self.pedacos:
            self.pasta_juncao = os.path.dirname(self.pedacos[0])
        self._redesenhar_lista()
        self.log(f"{novos} arquivo(s) adicionados. Total na lista: {len(self.pedacos)}.")

    def limpar_pedacos(self):
        self.pedacos = []
        self.manifesto = None
        self._redesenhar_lista()
        self.log("Lista de pedacos limpa.")

    def remover_pedaco(self):
        sel = self.lista.curselection()
        if not sel:
            return
        self.pedacos.pop(sel[0])
        # Tirar um pedaco do meio invalida a conferencia contra o manifesto,
        # porque a ordem esperada deixa de bater com a lista.
        self.manifesto = None
        self._redesenhar_lista()

    def mover(self, direcao):
        sel = self.lista.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + direcao
        if j < 0 or j >= len(self.pedacos):
            return
        self.pedacos[i], self.pedacos[j] = self.pedacos[j], self.pedacos[i]
        self.manifesto = None
        self._redesenhar_lista()
        self.lista.selection_set(j)

    def _redesenhar_lista(self):
        self.lista.delete(0, END)
        for i, c in enumerate(self.pedacos, start=1):
            self.lista.insert(END, f"{i:02d}.  {os.path.basename(c)}")

    def iniciar_juncao(self):
        if self.trabalhando:
            return
        if len(self.pedacos) < 2:
            messagebox.showwarning(APP_NAME, "Coloque pelo menos dois pedacos na lista.",
                                   parent=self._janela())
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado nesta maquina.",
                                 parent=self._janela())
            return

        infos = [ler_info_midia(self.ffmpeg, self.ffprobe, c) for c in self.pedacos]
        formato = self.var_formato_jun.get()

        # A copia direta so vale quando nada precisa ser normalizado: mesmo
        # codec, mesma taxa, mesmos canais e mesma extensao.
        exts = {Path(c).suffix.lower() for c in self.pedacos}
        copia_direta = (partes_sao_identicas(infos) and formato == JUN_AUTO
                        and len(exts) == 1)
        ext = list(exts)[0] if copia_direta else opcoes_formato_juncao(formato, infos)[1]

        base = "juntado"
        if self.manifesto:
            base = Path((self.manifesto.get("origem") or {}).get("arquivo")
                        or "juntado").stem
        else:
            # Sem manifesto, tira o numero do comeco do primeiro pedaco para
            # sugerir um nome que lembre o material.
            primeiro = os.path.basename(self.pedacos[0])
            base = Path(RE_NUMERO_PARTE.sub("", primeiro)).stem or "juntado"

        saida = filedialog.asksaveasfilename(
            title="Salvar o arquivo juntado como",
            initialfile=f"{nome_limpo(base)} - juntado{ext}",
            initialdir=self.pasta_juncao or pastas.pasta_downloads(),
            defaultextension=ext,
            parent=self._janela(),
        )
        if not saida:
            return
        if os.path.abspath(saida) in {os.path.abspath(c) for c in self.pedacos}:
            messagebox.showerror(APP_NAME, "O arquivo final nao pode ser um dos pedacos.",
                                 parent=self._janela())
            return

        self.pasta_juncao = os.path.dirname(saida)
        self._travar(True)
        self.cancelar.clear()
        threading.Thread(target=self._rodar_juncao,
                         args=(list(self.pedacos), saida, infos, formato,
                               copia_direta),
                         daemon=True).start()

    def _rodar_juncao(self, arquivos, saida, infos, formato, copia_direta):
        try:
            self.log("=" * 60)
            self.log(f"Juntando {len(arquivos)} pedacos.")
            self.status("Juntando...")
            self.progresso(0)

            if not partes_sao_identicas(infos):
                self.log("Os pedacos voltaram com formatos diferentes entre si. "
                         "Vou normalizar tudo na juncao.")

            ok = juntar(self.ffmpeg, arquivos, infos, saida, formato, copia_direta,
                        self.log, self.progresso, self.cancelar,
                        guardar_proc=self._guardar_proc)
            if not ok or self.cancelar.is_set():
                raise InterruptedError

            self.progresso(100)
            self.ultima_pasta = os.path.dirname(saida)
            obtido = ler_duracao(self.ffprobe, saida) or 0
            esperado = sum(i.get("duracao") or 0 for i in infos)
            tam = os.path.getsize(saida) if os.path.exists(saida) else 0
            self.log("-" * 60)
            self.log(f"Arquivo final: {os.path.basename(saida)}  "
                     f"({formatar_tempo(obtido)}, {formatar_tamanho(tam)})")
            self.log(f"Esperado pela soma dos pedacos: {formatar_tempo(esperado)}   |   "
                     f"Diferenca: {abs(obtido - esperado):.2f}s")
            if abs(obtido - esperado) > TOLERANCIA_DURACAO:
                self.log("ATENCAO: o arquivo final ficou com duracao diferente da soma "
                         "dos pedacos. Confira o resultado antes de usar.")
            else:
                self.log("Conferido: o arquivo final tem exatamente a duracao dos "
                         "pedacos somados.")
            self.status("Juncao concluida.")
            self.raiz.after(0, lambda: messagebox.showinfo(
                APP_NAME, f"Arquivo juntado:\n{saida}", parent=self._janela()))
        except InterruptedError:
            self.status("Cancelado.")
            self.log("Cancelado. O arquivo pela metade foi apagado.")
            try:
                if os.path.exists(saida):
                    os.remove(saida)
            except OSError:
                pass
        except Exception as e:
            self.status("Deu erro.")
            self.log(f"ERRO: {e}")
            recado = str(e)
            self.raiz.after(0, lambda: messagebox.showerror(APP_NAME, recado,
                                                            parent=self._janela()))
        finally:
            self.raiz.after(0, lambda: self._travar(False))

    # ------------------------------------------------------------------ util
    def _guardar_proc(self, proc):
        """Guarda o ffmpeg da vez, para poder derruba-lo no fechamento."""
        self.proc = proc

    def _travar(self, ligado):
        self.trabalhando = ligado
        # Espelha o mesmo estado no nome que o estudio consulta antes de fechar.
        self.rodando = ligado
        acao = DISABLED if ligado else NORMAL
        cancel = NORMAL if ligado else DISABLED
        for b in (self.bt_cortar, self.bt_dividir, self.bt_juntar):
            b.configure(state=acao)
        for b in (self.bt_cancelar_c, self.bt_cancelar_d, self.bt_cancelar_j):
            b.configure(state=cancel)

    def pedir_cancelamento(self):
        self.cancelar.set()
        self.status("Cancelando...")

    def abrir_pasta(self, pasta):
        if not pasta or not os.path.isdir(pasta):
            messagebox.showinfo(APP_NAME, "Ainda nao ha pasta para abrir.",
                                parent=self._janela())
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            elif os.name == "nt":
                os.startfile(pasta)
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Nao consegui abrir a pasta.\n{e}",
                                 parent=self._janela())

    # ------------------------------------------------------------ fechamento
    def ao_fechar(self):
        """Limpeza no fechamento do estudio: nao destroi janela nenhuma.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se avisa a thread para
        parar e se derruba o ffmpeg que ainda estiver rodando, para nao ficar
        um processo orfao comendo a maquina.
        """
        self.cancelar.set()
        self.rodando = False
        self.trabalhando = False
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


def montar(pai, foco="video"):
    """Desenha a aba dentro de `pai`.

    `foco` diz em qual estudio a aba esta: "video" ou "audio". Ele NAO muda o
    que a aba faz (ela sempre trata os dois), so a ordem em que os tipos de
    arquivo aparecem no dialogo de escolha, para a pessoa nao ter que trocar
    o filtro toda vez.
    """
    return Aplicativo(pai, foco=foco)
