#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baixar — aba do Estúdio de Vídeo para baixar vídeos.

Recursos:
  - Seleção de qualidade (melhor, 1080p, 720p, 480p, 360p)
  - Nome do arquivo de saída personalizado (opcional; vazio = título do vídeo)
  - Download somente do áudio em MP3
  - Corte por tempo (início e/ou fim): baixa o vídeo completo e recorta o
    trecho pedido logo em seguida, sem recodificar
  - Fila de links: cola-se vários links de uma vez (um por linha) e o
    programa baixa um depois do outro, sem parar no primeiro que falhar
  - Suporte a playlists (baixar todos os vídeos da lista)
  - Remoção de TODOS os metadados do arquivo final (título, autor, capa,
    capítulos, data de gravação, tag de codificador, data do arquivo)
  - Limpeza de metadados de arquivos que já estão no computador
  - Cookies do navegador (resolve "403 Forbidden" e verificação de robô).
    Em site que exige conta — como o g1 e o Globoplay, que desde 2026 pedem
    a Conta Globo até para vídeo aberto de telejornal — o programa procura
    sozinho, entre os navegadores instalados, um que já esteja logado, e só
    avisa a pessoa se nenhum servir
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
import ssl
import json
import sys
import stat
import shutil
import subprocess
import threading
import queue
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# O import fica no nivel do modulo (e nao dentro de funcao) de proposito: o
# PyInstaller precisa "ver" este import estaticamente para embutir sozinho o
# arquivo de certificados do certifi (cacert.pem) dentro do executavel. Sem
# isso, o app empacotado falha ao baixar o motor com
# "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate".
# Mesmo assim ele e tolerante: rodando pelo codigo-fonte numa maquina sem o
# certifi instalado, a aba continua abrindo e o SSL cai no pacote de
# certificados do proprio sistema.
try:
    import certifi
except ImportError:
    certifi = None

import pastas
import tema
from tema import COR_CAMPO, COR_TEXTO, COR_BORDA, COR_DESTAQUE

APP_NAME = "Baixador de Vídeos"
APP_VERSION = "1.12.0"

# O motor de download (achar, instalar e atualizar o yt-dlp) mora em
# `compartilhado/motor_download.py`, porque a aba "Extrair audio" tambem
# precisa dele, nos dois estudios. Os nomes sao trazidos para ca para o resto
# deste arquivo continuar escrevendo `caminho_motor()` e afins, como sempre.
from compartilhado.motor_download import (      # noqa: F401
    YTDLP_BASE, DENO_BASE, CLIENTE_YOUTUBE, NAVEGADORES,
    resource_path, pasta_do_usuario, caminho_motor, url_motor,
    nome_zip_deno, caminho_js, localizar_js, find_ffmpeg_dir,
    find_ffmpeg_exe, _contexto_ssl, _sem_janela, motor_instalado,
    versao_motor, baixar_motor, baixar_js, EXT_AUDIO,
)


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


def segundos_de(txt: str):
    """Converte "SS", "MM:SS" ou "HH:MM:SS" em segundos. Vazio devolve None."""
    txt = (txt or "").strip()
    if not txt:
        return None
    total = 0.0
    for parte in txt.split(":"):
        total = total * 60 + float(parte or 0)
    return total


def achar_ffprobe(ffmpeg: str):
    """ffprobe costuma morar ao lado do ffmpeg. Devolve o caminho, ou None."""
    if not ffmpeg:
        return None
    nome = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    perto = os.path.join(os.path.dirname(ffmpeg), nome)
    if os.path.isfile(perto):
        return perto
    return shutil.which(nome)


def duracao_de(caminho: str, ffmpeg: str):
    """Duração do arquivo em segundos, ou None se não der para saber."""
    ffprobe = achar_ffprobe(ffmpeg)
    if not ffprobe or not os.path.isfile(caminho):
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", caminho],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=60, **_sem_janela()
        )
        return float(proc.stdout.decode("utf-8", "replace").strip())
    except Exception:
        return None


def tem_video(caminho: str, ffmpeg: str):
    """True/False se o arquivo tem faixa de imagem. None se não der para saber."""
    ffprobe = achar_ffprobe(ffmpeg)
    if not ffprobe or not os.path.isfile(caminho):
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", caminho],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=60, **_sem_janela()
        )
        return bool(proc.stdout.decode("utf-8", "replace").strip())
    except Exception:
        return None


VIDEO_COMPATIVEL = {"h264", "hevc"}
AUDIO_COMPATIVEL = {"aac", "mp3", "alac"}


def _codec_de(caminho: str, ffprobe: str, tipo: str) -> str:
    """Nome do codec da primeira faixa do tipo pedido ('v' ou 'a'), ou ''."""
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", f"{tipo}:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", caminho],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=60, **_sem_janela()
    )
    return proc.stdout.decode("utf-8", "replace").strip().lower()


def garantir_compativel(caminho: str, ffmpeg: str) -> str:
    """Converte para H.264 + AAC quando o arquivo veio num formato que o Mac
    nao abre (VP9 ou AV1 no video, Opus no audio). Devolve a mensagem para o
    registro, ou "" quando nao havia nada a fazer.

    Caso real: o Instagram entrega o video em VP9. O arquivo baixa inteiro, o
    ffprobe le sem reclamar, e o QuickTime diz que nao consegue abrir.
    """
    if not ffmpeg or not caminho.lower().endswith((".mp4", ".mov", ".m4v")):
        return ""
    ffprobe = achar_ffprobe(ffmpeg)
    if not ffprobe or not os.path.isfile(caminho):
        return ""
    try:
        v = _codec_de(caminho, ffprobe, "v")
        a = _codec_de(caminho, ffprobe, "a")
    except Exception:
        return ""
    mexer_video = bool(v) and v not in VIDEO_COMPATIVEL
    mexer_audio = bool(a) and a not in AUDIO_COMPATIVEL
    if not (mexer_video or mexer_audio):
        return ""

    base, ext = os.path.splitext(caminho)
    temp = base + ".convertendo" + ext
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", caminho,
           "-map", "0:v:0?", "-map", "0:a:0?", "-map_metadata", "0"]
    if mexer_video:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "copy"]
    if mexer_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]
    cmd += ["-movflags", "+faststart", temp]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          **_sem_janela())
    if proc.returncode == 0 and os.path.isfile(temp) \
            and os.path.getsize(temp) > 0 and duracao_de(temp, ffmpeg):
        # O original so e substituido depois que a conversao deu certo.
        shutil.move(temp, caminho)
        return (f"Convertido para um formato que abre no Mac e no Windows "
                f"(de {v or a} para H.264): {os.path.basename(caminho)}")
    if os.path.isfile(temp):
        try:
            os.remove(temp)
        except OSError:
            pass
    linhas = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    raise RuntimeError(linhas[-1] if linhas else "ffmpeg falhou ao converter.")


def _relogio(seg: float) -> str:
    seg = max(0, int(seg))
    h, m, s = seg // 3600, (seg % 3600) // 60, seg % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _corte_serve(temp: str, original: str, ffmpeg: str) -> bool:
    """Confere se o arquivo recém-cortado presta, ANTES de apagar o original.

    O ffmpeg pode sair com sucesso e ainda assim gravar um arquivo sem
    imagem nenhuma. Trocar o vídeo baixado por um arquivo desses é perder o
    trabalho inteiro, então a troca só acontece depois desta conferência.
    """
    dur = duracao_de(temp, ffmpeg)
    if dur is not None and dur < 0.05:
        return False
    tem = tem_video(temp, ffmpeg)
    if tem is False and tem_video(original, ffmpeg) is not False:
        return False
    if dur is None and tem is None:
        # Sem ffprobe na maquina: sobra o tamanho. Arquivo de video vazio
        # fica na casa das centenas de bytes; qualquer trecho de verdade
        # passa MUITO disso.
        return os.path.getsize(temp) > 20000
    return True


def cortar_video(caminho: str, ffmpeg: str, inicio: str, fim: str) -> str:
    """Corta o arquivo já baixado para o trecho entre `inicio` e `fim`
    (qualquer um dos dois pode vir vazio).

    O corte é RECODIFICADO, e não copiado, sempre que houver um tempo de
    início. Essa decisão custou um arquivo que não abria, então vale
    registrar o porquê.

    Vídeo comprimido não pode ser cortado em qualquer ponto: só existem
    alguns quadros completos (os "quadros-chave"), e todos os outros são
    descritos a partir deles. Copiando os dados sem recodificar, o corte
    começa no meio dessa dependência, e o arquivo sai com o relógio interno
    começando fora do zero e sem o quadro completo de referência. Medido
    aqui: cortando de 52s a 70s por cópia, o arquivo dizia durar 18s mas só
    tinha 352 dos 540 quadros, e o primeiro instante marcava 6,3s em vez de
    0. O QuickTime recusa arquivo assim, e foi exatamente o "não abre".

    Recodificando, o trecho sai exato no segundo pedido, com o primeiro
    quadro completo e o relógio começando do zero. Custa alguns segundos de
    processamento, o que é barato perto de um arquivo inútil.

    Corte só com fim (começando do zero) não tem esse problema e continua
    sendo cópia pura, que é instantânea.
    """
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado para cortar o vídeo.")
    if not os.path.isfile(caminho):
        raise RuntimeError(f"Arquivo não encontrado: {caminho}")

    ini = segundos_de(inicio)
    fin = segundos_de(fim)
    if ini is not None and fin is not None and fin <= ini:
        raise RuntimeError(
            "O fim do corte precisa vir depois do começo."
        )

    # Pedir um trecho que não existe no vídeo é a armadilha silenciosa deste
    # passo: o ffmpeg NÃO reclama, devolve sucesso e grava um arquivo vazio
    # de duzentos e poucos bytes. O programa dizia "cortado com sucesso" e a
    # pessoa ficava com um arquivo que não abre. Então se confere antes.
    dur = duracao_de(caminho, ffmpeg)
    if dur and ini is not None and ini >= dur:
        raise RuntimeError(
            f"O vídeo tem {_relogio(dur)} e você pediu para começar o corte "
            f"em {_relogio(ini)}, que é depois do fim. Confira a minutagem: "
            f"o começo precisa estar dentro do vídeo."
        )
    if dur and fin is not None and fin > dur + 1:
        # Passar do fim não é erro: o trecho simplesmente termina onde o
        # vídeo termina. Mas o pedido é ajustado, para a conta de duração
        # bater com o que sai.
        fin = dur

    base, ext = os.path.splitext(caminho)
    temp = base + ".corte" + ext

    def montar(recodificar: bool):
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        if ini:
            # Antes do "-i": o ffmpeg salta direto para o ponto, em vez de
            # ler o arquivo inteiro ate la.
            cmd += ["-ss", f"{ini:.3f}"]
        cmd += ["-i", caminho]
        if fin is not None:
            # Duracao, e nao instante final: com o salto acima, o relogio ja
            # foi reiniciado, e "-to" seria medido do lugar errado.
            cmd += ["-t", f"{fin - (ini or 0):.3f}"]
        if recodificar:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-c", "copy"]
        # Zera o relogio interno do arquivo: sem isto ele comeca no minuto
        # em que o trecho foi cortado, e varios tocadores nao abrem.
        cmd += ["-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
                temp]
        return cmd

    # Com inicio, recodifica (exato e sempre abre). Só com fim, copia.
    tentativas = [True, False] if ini else [False]
    erro = ""
    for recodificar in tentativas:
        proc = subprocess.run(
            montar(recodificar), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, **_sem_janela()
        )
        if proc.returncode == 0 and os.path.isfile(temp) \
                and os.path.getsize(temp) > 0 \
                and _corte_serve(temp, caminho, ffmpeg):
            shutil.move(temp, caminho)
            return f"Vídeo cortado: {os.path.basename(caminho)}"
        if os.path.isfile(temp):
            try:
                os.remove(temp)
            except OSError:
                pass
        linhas = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        erro = linhas[-1] if linhas else "ffmpeg falhou ao cortar."
        # Se a recodificacao falhar (ffmpeg sem o codificador de video, por
        # exemplo), ainda tenta a copia: trecho com comeco impreciso e melhor
        # do que trecho nenhum.

    raise RuntimeError(erro)


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

def conferir_arquivo(caminho, ffmpeg):
    """Diz o que ha de errado com o arquivo baixado, ou nada se estiver bom.

    Usa o ffprobe (que vem junto com o ffmpeg) so para ABRIR o arquivo e ler a
    duracao. Se ele nao conseguir, o arquivo nao vai tocar em lugar nenhum.
    """
    try:
        if not os.path.exists(caminho):
            return "o arquivo nao esta onde deveria: " + caminho
        if os.path.getsize(caminho) < 10000:
            return ("o arquivo saiu praticamente vazio (%d bytes). Tente baixar "
                    "de novo." % os.path.getsize(caminho))
        ffprobe = None
        if ffmpeg:
            cand = os.path.join(os.path.dirname(ffmpeg),
                                "ffprobe.exe" if os.name == "nt" else "ffprobe")
            if os.path.isfile(cand):
                ffprobe = cand
        if not ffprobe:
            return ""          # sem ffprobe nao da para conferir; segue a vida
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", caminho],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        saida = (r.stdout or b"").decode("utf-8", "ignore").strip()
        if r.returncode != 0 or not saida:
            return ("o arquivo baixado nao abre (pode ter vindo pela metade). "
                    "Apague ele e baixe de novo: " + os.path.basename(caminho))
        try:
            if float(saida) < 0.3:
                return "o arquivo baixado esta sem conteudo (duracao zero)."
        except ValueError:
            pass
    except Exception:
        pass                   # conferir nunca pode atrapalhar o download
    return ""


class App:
    def __init__(self, pai):
        self.raiz = pai

        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self.fila = queue.Queue()
        self.cancelar_flag = threading.Event()
        self.thread = None
        self.proc = None

        # O Estudio olha este atributo antes de fechar a janela.
        self.rodando = False

        # Regra da casa: toda aba comeca salvando na pasta de Downloads.
        self.pasta_destino = tk.StringVar(value=pastas.pasta_downloads())
        self.qualidade = tk.StringVar(value="Melhor qualidade")
        self.nome_saida = tk.StringVar(value="")
        self.somente_audio = tk.BooleanVar(value=False)
        self.tempo_inicio = tk.StringVar(value="")
        self.tempo_fim = tk.StringVar(value="")
        self.baixar_playlist = tk.BooleanVar(value=False)
        self.remover_metadados = tk.BooleanVar(value=True)
        self.usar_cookies = tk.BooleanVar(value=False)
        self.navegador = tk.StringVar(value="chrome")

        # Navegador cuja sessão já resolveu um link desta fila. Guardado para
        # os links seguintes saírem direto com ele, sem repetir a procura.
        self._cookies_descobertos = None
        # "Link 3 de 12: " na frente do progresso, quando a fila tem mais de
        # um link. Vazio quando é um link só.
        self._prefixo_fila = ""
        # Enquanto o programa varre os navegadores atrás de uma sessão
        # logada, os erros crus do yt-dlp não vão para a tela: viram uma
        # linha em português por navegador.
        self._silenciar_erros = False
        # Marcado quando algum navegador ficou de fora porque o macOS barrou
        # a leitura dos cookies. Vira instrução no fim da mensagem de erro.
        self._pedir_acesso_disco = False

        self._montar_ui()
        # Repoe as escolhas da ultima vez ANTES de qualquer conferencia,
        # para a tela ja nascer do jeito que a pessoa deixou.
        self._carregar_prefs()
        self._toggle_audio()
        self._toggle_cookies()
        self._verificar_ffmpeg()
        self.raiz.after(100, self._processar_fila)

        # Motor de download: só trava o botão e fala em "primeira vez"
        # quando é MESMO a primeira vez, ou seja, quando o arquivo do motor
        # ainda não existe no disco (conferência instantânea).
        #
        # Antes, toda abertura chamava `yt-dlp --version`, que é um programa
        # empacotado e leva vários segundos para responder no Mac. Nesse
        # tempo o botão ficava travado e a tela dizia "Preparando o programa
        # (primeira vez)…", então TODA abertura parecia a primeira. A
        # conferência continua existindo, mas agora corre em segundo plano,
        # sem atrapalhar quem já quer colar um link e baixar.
        if motor_instalado():
            self._set_status("Pronto.")
            threading.Thread(target=self._conferir_motor, daemon=True).start()
        else:
            self.btn_baixar.config(state="disabled")
            self._set_status("Preparando o programa (primeira vez)…")
            threading.Thread(target=self._preparar_motor, daemon=True).start()

    # ----- UI -----------------------------------------------------------
    def _montar_ui(self):
        pad = {"padx": 12, "pady": 4}

        # A tela e enxuta de proposito: cada texto de apoio cabe na propria
        # linha do campo, para a aba inteira caber sem barra de rolagem.
        topo = ttk.Frame(self.raiz)
        topo.pack(fill="x", **pad)
        ttk.Label(
            topo,
            text="URLs dos vídeos ou playlists (YouTube, Instagram, TikTok, "
                 "Google Drive e outros):",
        ).pack(anchor="w")

        # Caixa de várias linhas, e não um campo de uma linha só: dá para
        # colar uma lista inteira de links de uma vez, que o programa baixa
        # um atrás do outro. Um link por linha.
        caixa = ttk.Frame(topo)
        caixa.pack(fill="x", pady=(2, 0))
        self.url_texto = tk.Text(
            caixa, height=4, wrap="none",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightthickness=1,
            relief="flat", padx=6, pady=4,
        )
        self.url_texto.pack(side="left", fill="both", expand=True)
        sb_url = ttk.Scrollbar(caixa, command=self.url_texto.yview)
        sb_url.pack(side="right", fill="y")
        self.url_texto.config(yscrollcommand=sb_url.set)

        # Enter em caixa de texto quebra linha, que é justamente o que se
        # quer aqui (um link por linha). Quem quiser disparar pelo teclado
        # usa Cmd+Enter (Mac) ou Ctrl+Enter (Windows).
        self.url_texto.bind("<Command-Return>", self._atalho_baixar)
        self.url_texto.bind("<Control-Return>", self._atalho_baixar)

        self.lbl_links = ttk.Label(topo, text="", style="Suave.TLabel")
        self.lbl_links.pack(anchor="w", pady=(2, 0))
        self.url_texto.bind("<<Modified>>", self._contar_links)

        # ---------------- Opções ----------------
        opc = ttk.LabelFrame(self.raiz, text="Opções ")
        opc.pack(fill="x", **pad)

        linha1 = ttk.Frame(opc)
        linha1.pack(fill="x", padx=10, pady=(6, 3))
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
        linha2.pack(fill="x", padx=10, pady=(0, 3))
        ttk.Label(linha2, text="Salvar em:").pack(side="left")
        ttk.Entry(linha2, textvariable=self.pasta_destino).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(linha2, text="Escolher...",
                   command=self._escolher_pasta).pack(side="left")

        # Nome do arquivo de saída (opcional)
        linha3 = ttk.Frame(opc)
        linha3.pack(fill="x", padx=10, pady=(0, 3))
        ttk.Label(linha3, text="Nome do arquivo:").pack(side="left")
        ttk.Entry(linha3, textvariable=self.nome_saida).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Label(
            linha3, text="vazio = título do vídeo", style="Suave.TLabel",
        ).pack(side="left")

        # Corte por tempo (opcional), com a dica na propria linha
        linha4 = ttk.Frame(opc)
        linha4.pack(fill="x", padx=10, pady=(0, 3))
        ttk.Label(linha4, text="Cortar - início:").pack(side="left")
        ttk.Entry(linha4, textvariable=self.tempo_inicio, width=9).pack(
            side="left", padx=(6, 14)
        )
        ttk.Label(linha4, text="fim:").pack(side="left")
        ttk.Entry(linha4, textvariable=self.tempo_fim, width=9).pack(
            side="left", padx=(6, 12)
        )
        ttk.Label(
            linha4,
            text="vazio = vídeo inteiro. Ex.: 1:23:45 ou 90",
            style="Suave.TLabel",
        ).pack(side="left")

        # Privacidade: virou mais uma linha das Opções, sem quadro proprio.
        linha5 = ttk.Frame(opc)
        linha5.pack(fill="x", padx=10, pady=(0, 3))
        ttk.Checkbutton(
            linha5,
            text="Remover TODOS os metadados (título, autor, capa, data)",
            variable=self.remover_metadados,
        ).pack(side="left")
        ttk.Button(
            linha5, text="Limpar arquivos que já tenho...",
            command=self._limpar_existentes,
        ).pack(side="left", padx=(16, 0))

        # Acesso: cookies, na ultima linha das Opções.
        linha6 = ttk.Frame(opc)
        linha6.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Checkbutton(
            linha6, text="Usar cookies do navegador",
            variable=self.usar_cookies, command=self._toggle_cookies,
        ).pack(side="left")
        self.combo_nav = ttk.Combobox(
            linha6, textvariable=self.navegador, values=NAVEGADORES,
            state="disabled", width=12,
        )
        self.combo_nav.pack(side="left", padx=(8, 8))
        ttk.Label(
            linha6,
            text="sites que pedem conta (g1, Globoplay): deixe desmarcado "
                 "que o programa procura sozinho",
            style="Suave.TLabel",
        ).pack(side="left")

        # ---------------- Ações ----------------
        acoes = ttk.Frame(self.raiz)
        acoes.pack(fill="x", **pad)
        self.btn_baixar = ttk.Button(acoes, text="Baixar",
                                     style="Acao.TButton",
                                     command=self._iniciar_download)
        self.btn_baixar.pack(side="left")
        self.btn_cancelar = ttk.Button(acoes, text="Cancelar",
                                       command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left", padx=8)

        # ---------------- Progresso ----------------
        prog = ttk.Frame(self.raiz)
        prog.pack(fill="x", **pad)
        barra_wrap = ttk.Frame(prog)
        barra_wrap.pack(fill="x")
        self.barra = ttk.Progressbar(barra_wrap, mode="determinate", maximum=100)
        self.barra.pack(fill="x", ipady=6)
        self.lbl_pct = ttk.Label(barra_wrap, text="0%", anchor="center")
        self.lbl_pct.place(relx=0.5, rely=0.5, anchor="center")
        self.status = ttk.Label(prog, text="Pronto.")
        self.status.pack(anchor="w", pady=(3, 0))

        # ---------------- Log ----------------
        logf = ttk.LabelFrame(self.raiz, text="Registro ")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(
            logf, height=5, wrap="word", state="disabled",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, relief="flat",
        )
        self.log.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y", pady=6, padx=(0, 8))
        self.log.config(yscrollcommand=sb.set)

    def _pai_dialogo(self):
        """Janela a que as caixas de diálogo devem se prender.

        Sem isso a caixa pode nascer atrás da janela do Estúdio.
        """
        return self.raiz.winfo_toplevel()

    def _urls(self):
        """Lista de links da caixa, na ordem, sem repetição e sem lixo.

        Aceita um link por linha, mas também tolera a lista colada com
        espaço, vírgula ou ponto e vírgula separando: é assim que os links
        costumam vir de um WhatsApp ou de uma planilha.
        """
        bruto = self.url_texto.get("1.0", "end")
        for sep in (",", ";", "\t"):
            bruto = bruto.replace(sep, "\n")
        vistos, saida = set(), []
        for pedaco in bruto.split():
            link = pedaco.strip().strip("<>\"'")
            if not link or link in vistos:
                continue
            vistos.add(link)
            saida.append(link)
        return saida

    def _contar_links(self, _evento=None):
        """Mostra quantos links estão na caixa, para não haver surpresa."""
        # A marca precisa ser zerada, senão o evento <<Modified>> dispara
        # uma vez só e o contador congela.
        self.url_texto.edit_modified(False)
        n = len(self._urls())
        if n == 0:
            self.lbl_links.config(text="Um link por linha.")
        elif n == 1:
            self.lbl_links.config(text="1 link na fila.")
        else:
            self.lbl_links.config(
                text=f"{n} links na fila, baixados um depois do outro."
            )

    def _atalho_baixar(self, _evento=None):
        if str(self.btn_baixar["state"]) != "disabled":
            self._iniciar_download()
        return "break"      # impede a quebra de linha do próprio atalho

    def _toggle_audio(self):
        self.combo_qual.config(
            state="disabled" if self.somente_audio.get() else "readonly"
        )

    def _toggle_cookies(self):
        self.combo_nav.config(
            state="readonly" if self.usar_cookies.get() else "disabled"
        )

    def _escolher_pasta(self):
        d = filedialog.askdirectory(initialdir=self.pasta_destino.get() or ".",
                                    parent=self._pai_dialogo())
        if d:
            self.pasta_destino.set(d)

    def _verificar_ffmpeg(self):
        if find_ffmpeg_dir() is None:
            self._logar(
                "AVISO: ffmpeg não foi encontrado. Juntar vídeo+áudio, "
                "converter em MP3 e remover metadados podem falhar."
            )

    # ----- Motor (roda em segundo plano; não aparece para o usuário) ----
    def _conferir_motor(self):
        """Confere em silêncio, com o programa já liberado, se o motor roda.

        O arquivo existir não garante que ele funcione: pode ter vindo pela
        metade de um download interrompido, ou ter perdido a permissão de
        execução. Só que essa conferência é lenta, então ela acontece com a
        pessoa já podendo usar a tela, e não travando a abertura.

        Se estiver quebrado, o motor é reinstalado na hora. E o motor de
        JavaScript, quando falta, é buscado aqui também, para o YouTube não
        falhar no primeiro clique.
        """
        try:
            if not versao_motor():
                # Achado raro, mas é o único caso em que o botão precisa
                # travar depois de já ter sido liberado: baixar com um motor
                # quebrado só produziria erro sem explicação.
                self.fila.put(("motor_ocupado", None))
                self.fila.put((
                    "status", "Consertando o motor de download…",
                ))
                self._preparar_motor(forcar=True)
                return
            if not localizar_js():
                baixar_js()
                self.fila.put(("log", "Motor de JavaScript instalado."))
        except Exception as e:
            # Nunca atrapalha: o download tentará de novo, e lá existe a
            # rotina de atualizar o motor quando algo dá errado.
            self.fila.put(("log", f"Aviso ao conferir o motor: {e}"))

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
            self.fila.put(("motor_ok", None))
        except Exception as e:
            self.fila.put(("log", f"ERRO ao preparar o motor: {e}"))
            self.fila.put(("motor_erro", str(e)))

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
            messagebox.showinfo(APP_NAME, f"A pasta é:\n{caminho}\n\n{e}",
                                parent=self._pai_dialogo())

    # ----- Limpeza de arquivos já existentes ----------------------------
    def _limpar_existentes(self):
        if self.thread and self.thread.is_alive():
            messagebox.showinfo(APP_NAME, "Aguarde a tarefa em andamento terminar.",
                                parent=self._pai_dialogo())
            return
        arquivos = filedialog.askopenfilenames(
            title="Escolha os arquivos para limpar os metadados",
            initialdir=self.pasta_destino.get() or ".",
            parent=self._pai_dialogo(),
        )
        if not arquivos:
            return
        self.btn_baixar.config(state="disabled")
        self._set_status("Limpando metadados…")
        self.rodando = True
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
        urls = self._urls()
        if not urls:
            messagebox.showwarning(
                APP_NAME,
                "Cole pelo menos um link na caixa de cima. Se for mais de "
                "um, coloque um por linha.",
                parent=self._pai_dialogo(),
            )
            return
        destino = self.pasta_destino.get().strip()
        if not destino:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de destino.",
                                   parent=self._pai_dialogo())
            return
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Não foi possível usar a pasta:\n{e}",
                                 parent=self._pai_dialogo())
            return
        if self.remover_metadados.get() and find_ffmpeg_exe() is None:
            messagebox.showwarning(
                APP_NAME,
                "O ffmpeg não foi encontrado, então não dá para remover os "
                "metadados. Desmarque a opção ou instale o ffmpeg.",
                parent=self._pai_dialogo(),
            )
            return

        corte_inicio = self.tempo_inicio.get().strip()
        corte_fim = self.tempo_fim.get().strip()
        if not tempo_valido(corte_inicio) or not tempo_valido(corte_fim):
            messagebox.showwarning(
                APP_NAME,
                "Tempo de corte inválido. Use hh:mm:ss, mm:ss ou apenas "
                "segundos (ex.: 1:23:45, 12:30 ou 90).",
                parent=self._pai_dialogo(),
            )
            return
        if (corte_inicio or corte_fim) and find_ffmpeg_exe() is None:
            messagebox.showwarning(
                APP_NAME,
                "O ffmpeg não foi encontrado, então não dá para cortar o "
                "vídeo. Apague os campos de corte ou instale o ffmpeg.",
                parent=self._pai_dialogo(),
            )
            return

        # Corte por tempo só faz sentido para um vídeo: o mesmo "de 2:00 a
        # 5:00" aplicado a uma lista inteira quase nunca é o que a pessoa
        # quis. Pergunta antes em vez de estragar a fila em silêncio.
        if len(urls) > 1 and (corte_inicio or corte_fim):
            if not messagebox.askyesno(
                APP_NAME,
                f"Você pediu o mesmo corte de tempo para os {len(urls)} "
                "links da fila.\n\nO trecho será recortado igual em todos "
                "eles. Quer continuar assim?",
                parent=self._pai_dialogo(),
            ):
                return

        self.cancelar_flag.clear()
        self.btn_baixar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.barra.config(value=0)
        self.lbl_pct.config(text="0%")
        self._set_status("Iniciando…")
        self.rodando = True

        opcoes = {
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
        # Guarda as escolhas agora, e nao so no fechamento: se o programa
        # for encerrado a forca, o que ele estava usando nao se perde.
        self._salvar_prefs()

        self.thread = threading.Thread(target=self._worker,
                                       args=(opcoes, urls), daemon=True)
        self.thread.start()

    def _montar_comando(self, opc):
        nome = opc.get("nome_saida") or ""
        if nome:
            # O yt-dlp trata % como código de modelo; %% vira % literal.
            modelo = nome.replace("%", "%%")
            if opc.get("total", 1) > 1:
                # Nome fixo com vários links sobrescreveria tudo no mesmo
                # arquivo: numera na ordem em que os links foram colados.
                modelo += f" - {opc.get('indice', 1)}"
            if opc["playlist"]:
                # Em playlist, um nome fixo sobrescreveria os arquivos;
                # numera cada item: "Nome - 1.mp4", "Nome - 2.mp4"…
                modelo += " - %(playlist_index)s"
            destino = os.path.join(opc["destino"], modelo + ".%(ext)s")
        else:
            # O identificador do post entra no nome DE PROPOSITO. Sem ele,
            # dois links do mesmo perfil (no Instagram e no TikTok o titulo e
            # sempre "Video by fulano") viram o MESMO nome de arquivo: o
            # segundo download passa por cima do primeiro, e voce fica com um
            # arquivo so - as vezes ate corrompido, quando a sobrescrita pega
            # o arquivo no meio da juncao de video e audio. Com o id, cada
            # link tem o seu arquivo, e baixar de novo nunca destroi o que ja
            # estava na pasta.
            destino = os.path.join(opc["destino"], "%(title)s [%(id)s].%(ext)s")
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
            # Entre versoes de MESMA resolucao, prefere H.264 + AAC, que abrem
            # em qualquer lugar (QuickTime, Premiere, WhatsApp). Sem isto o
            # Instagram entrega VP9, que o Mac nao abre. Quando so existe VP9
            # ou AV1 na resolucao maior, o arquivo e convertido depois
            # (ver garantir_compativel), sem perder qualidade.
            cmd += ["-S", "res,vcodec:h264,acodec:aac"]

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

    def _worker(self, opcoes, urls):
        """Roda em thread separada e baixa a fila de links, um por vez.

        Sequencial de propósito, e não vários ao mesmo tempo: baixar em
        paralelo divide a mesma internet, deixa a barra de progresso sem
        sentido e é o jeito mais rápido de o site tratar o programa como
        robô e bloquear tudo.

        Comunica-se com a GUI via self.fila.
        """
        try:
            if not motor_instalado() or not localizar_js():
                self.fila.put(("status", "Preparando o motor de download…"))
                self._preparar_motor()

            if not motor_instalado():
                raise RuntimeError(
                    "Não consegui preparar o motor de download (yt-dlp). "
                    "Verifique sua conexão com a internet e clique em "
                    "Baixar de novo. Se persistir, feche e abra o "
                    "programa."
                )

            total = len(urls)
            prontos, falhas = 0, []
            # Zera a cada fila: aviso de Acesso Total ao Disco de uma sessão
            # anterior não pode aparecer num erro que nada tem a ver.
            self._pedir_acesso_disco = False

            for indice, url in enumerate(urls, 1):
                if self.cancelar_flag.is_set():
                    break

                opc = dict(opcoes, url=url, indice=indice, total=total)
                # Se um link anterior da fila só funcionou com a sessão de
                # um navegador, os próximos já saem com ela: não faz sentido
                # redescobrir a mesma coisa link a link.
                if not opc.get("cookies") and self._cookies_descobertos:
                    opc["cookies"] = self._cookies_descobertos

                self._prefixo_fila = (
                    f"Link {indice} de {total}: " if total > 1 else ""
                )
                if total > 1:
                    self.fila.put(("progresso", 0))
                    self.fila.put((
                        "log", f"[{indice} de {total}] {url}",
                    ))
                    self.fila.put((
                        "status", f"Link {indice} de {total}: começando…",
                    ))

                codigo, saida = self._baixar_um(opc)

                if codigo == 0:
                    # Conta ANTES de olhar o cancelamento: se a pessoa
                    # clicou em Cancelar logo depois de este link terminar,
                    # ele terminou mesmo, e some do placar se a ordem for a
                    # inversa.
                    prontos += 1
                    if total > 1:
                        self.fila.put((
                            "log", f"[{indice} de {total}] concluído.",
                        ))
                elif self.cancelar_flag.is_set():
                    # Interrompido no meio: não é falha do link, é escolha
                    # de quem estava usando. Não entra na lista de erros.
                    break
                else:
                    falhas.append((url, self._explicar_falha(saida, url)))
                    if total > 1:
                        # A fila não para no primeiro tropeço: um link
                        # morto no meio não pode impedir os outros nove.
                        self.fila.put((
                            "log",
                            f"[{indice} de {total}] falhou, seguindo para o "
                            f"próximo.",
                        ))

                if self.cancelar_flag.is_set():
                    break

            self._resumo_fila(opcoes["destino"], total, prontos, falhas)
        except FileNotFoundError:
            self.fila.put((
                "erro",
                "O motor de download (yt-dlp) sumiu do disco no meio da "
                "tarefa. Feche e abra o programa de novo para reinstalá-lo.",
            ))
        except Exception as e:
            self.fila.put(("erro", str(e)))
        finally:
            self.proc = None
            self.fila.put(("fim", None))

    def _resumo_fila(self, destino, total, prontos, falhas):
        """Fecha a conta da fila: o que baixou, o que não baixou e por quê."""
        if self.cancelar_flag.is_set():
            if total > 1 and prontos:
                self.fila.put((
                    "status",
                    f"Cancelado. {prontos} de {total} já tinham baixado.",
                ))
            else:
                self.fila.put(("status", "Cancelado pelo usuário."))
            return

        if total == 1:
            # Link único: continua como sempre foi, com a caixa de "abrir a
            # pasta" ou a mensagem de erro inteira.
            if prontos:
                self.fila.put((
                    "download_ok",
                    ("Download concluído com sucesso!", destino),
                ))
            else:
                self.fila.put(("erro", falhas[0][1]))
            return

        # Fila: cada erro vai para o registro, e a caixa final resume.
        for url, msg in falhas:
            self.fila.put(("log", f"ERRO em {url}\n{msg}"))

        if not falhas:
            self.fila.put((
                "download_ok",
                (f"Os {total} links foram baixados.", destino),
            ))
        elif prontos:
            self.fila.put((
                "download_parcial",
                (
                    f"{prontos} de {total} links baixados.\n\n"
                    f"{len(falhas)} não deram certo. O motivo de cada um "
                    "está no Registro, aqui embaixo.",
                    destino,
                ),
            ))
        else:
            self.fila.put((
                "erro",
                f"Nenhum dos {total} links baixou.\n\n" + falhas[0][1],
            ))

    def _baixar_um(self, opc):
        """Baixa UM link, com as tentativas de contorno.

        Devolve (código, saída) e NÃO fala com a GUI sobre sucesso ou
        fracasso: quem fecha a conta é `_resumo_fila`, no fim da fila
        inteira. Aqui só saem mensagens de andamento.
        """
        codigo, saida = self._rodar(opc)

        # Sites que exigem conta (Globo, Globoplay e afins) devolvem
        # "login-required" / 401. Atualizar o motor nao resolve: o que
        # falta e a sessao do usuario. Entao aqui o programa procura
        # sozinho, entre os navegadores instalados, um que ja esteja
        # logado nesse site — e so avisa se nenhum servir.
        if codigo != 0 and not self.cancelar_flag.is_set() \
                and not opc.get("cookies") \
                and self._parece_login(saida):
            codigo, saida = self._tentar_com_cookies(opc, codigo, saida)

        # 403 e afins: tenta de novo por outro caminho, uma vez só.
        # Erro de cota/permissão do Google Drive não é bloqueio de robô
        # — tentar de novo por outro caminho não resolve, só perde tempo.
        if codigo != 0 and not self.cancelar_flag.is_set() \
                and not self._parece_login(saida) \
                and self._parece_bloqueio(saida) \
                and not self._parece_erro_drive(opc["url"], saida):
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

        return codigo, saida

    def _tentar_com_cookies(self, opc, codigo, saida):
        """Repete o download pegando a sessão de cada navegador instalado.

        Sites como o Globo/Globoplay passaram a exigir conta até para vídeo
        aberto de telejornal: sem a sessão, a API de reprodução responde
        "login-required" e nada é baixado. Como o usuário não tem por que
        saber o que é um cookie, o programa tenta sozinho — na ordem dos
        navegadores mais comuns — e para no primeiro que funcionar.

        Só é chamado quando a caixa "Usar cookies do navegador" está
        desmarcada; se ela já estiver marcada, o navegador escolhido pelo
        usuário é respeitado e não se sai testando os outros.
        """
        # O escolhido no menu vai na frente, mesmo com a caixa desmarcada:
        # é o palpite mais provável de onde a pessoa está logada.
        preferido = self.navegador.get()
        ordem = [preferido] + [n for n in NAVEGADORES if n != preferido]

        self.fila.put((
            "log",
            "Esse site pede conta. Vou procurar, nos navegadores deste "
            "computador, um que já esteja logado nele.",
        ))
        avisou_chaveiro = False

        # Enquanto varre os navegadores, o erro cru de cada tentativa não vai
        # para a tela: são mensagens de encanamento ("Operation not
        # permitted", "no key found") que assustam e não ajudam em nada. O
        # que a pessoa vê é uma linha em português por navegador.
        self._silenciar_erros = True
        try:
            for nav in ordem:
                if self.cancelar_flag.is_set():
                    break

                if sys.platform == "darwin" and nav in ("chrome", "brave",
                                                        "edge", "opera",
                                                        "vivaldi") \
                        and not avisou_chaveiro:
                    # O macOS guarda a sessão desses navegadores no Chaveiro
                    # e pede a senha do Mac para liberá-la. Sem o aviso, a
                    # janelinha aparece do nada e parece golpe. Uma vez só.
                    avisou_chaveiro = True
                    self.fila.put((
                        "log",
                        "Se o Mac pedir sua senha para liberar o Chaveiro, é "
                        "normal: é assim que ele entrega a sessão do "
                        "navegador.",
                    ))

                self.fila.put((
                    "log", f"Tentando com o {nav.capitalize()}…",
                ))
                tentativa = dict(opc, cookies=nav)
                novo_codigo, nova_saida = self._rodar(tentativa)

                if novo_codigo == 0:
                    self.fila.put((
                        "log",
                        f"Consegui usando a sua conta aberta no "
                        f"{nav.capitalize()}.",
                    ))
                    self._cookies_descobertos = nav
                    self.fila.put(("cookies_ok", nav))
                    return novo_codigo, nova_saida

                # Problema no NAVEGADOR (não instalado, sessão protegida pelo
                # macOS, banco travado): o site nem chegou a ser consultado,
                # então isso não é resposta nenhuma. Vai para o próximo.
                motivo = self._motivo_navegador(nav, nova_saida)
                if motivo:
                    self.fila.put(("log", f"  {motivo}"))
                    if "Acesso Total ao Disco" in motivo:
                        self._pedir_acesso_disco = True
                    continue

                # O site respondeu, e continua pedindo conta: é sessão não
                # logada nesse navegador. Segue tentando.
                if self._parece_login(nova_saida):
                    self.fila.put((
                        "log",
                        f"  Você não está logado nesse site pelo "
                        f"{nav.capitalize()}.",
                    ))
                    continue

                # Erro real do site (rede, formato, DRM, vídeo apagado): é a
                # resposta de verdade, não adianta rodar os outros
                # navegadores só para ouvir a mesma coisa.
                return novo_codigo, nova_saida
        finally:
            self._silenciar_erros = False

        # Nenhum navegador serviu: devolve o erro ORIGINAL do site, e não o
        # da última tentativa. O que interessa à pessoa é "esse site pede
        # conta", não "falhou ao ler os cookies do Vivaldi".
        return codigo, saida

    def _explicar_falha(self, saida, url):
        """Mensagem de erro final, mais o que só a busca por sessão sabe.

        `_mensagem_erro` é estática e não enxerga o que aconteceu durante a
        varredura dos navegadores. Quando o macOS barrou a leitura de algum
        deles, a instrução de Acesso Total ao Disco entra aqui: pode ter sido
        exatamente o navegador em que a pessoa está logada.
        """
        msg = self._mensagem_erro(saida, url)
        if self._pedir_acesso_disco and self._parece_login(saida):
            msg += (
                "\n\nUm detalhe do Mac: o macOS não deixou o programa ler a "
                "sessão de pelo menos um navegador (o Safari é o caso mais "
                "comum). Se é nele que você está logado, libere assim:"
                "\n1. Menu Apple > Ajustes do Sistema."
                "\n2. Privacidade e Segurança > Acesso Total ao Disco."
                "\n3. Clique em + , escolha o Media Studio na pasta "
                "Aplicativos e deixe a chavinha ligada."
                "\n4. Feche e abra o Media Studio."
                "\n\nSe preferir não mexer nisso, entre na sua conta pelo "
                "Chrome, que não precisa dessa liberação."
            )
        return msg

    @staticmethod
    def _motivo_navegador(nav, saida):
        """Explica, em português, por que um navegador não pôde ser usado.

        Devolve a frase, ou None quando o problema NÃO foi o navegador (aí a
        resposta veio do site e precisa ser tratada como tal).

        Existe porque a lista de erros de encanamento do yt-dlp é grande e
        muda: navegador ausente, banco de cookies travado, chave de
        criptografia não encontrada, e — o caso que motivou esta função — o
        macOS barrando a leitura dos cookies do Safari com
        "Operation not permitted", que antes derrubava a busca inteira.
        """
        s = saida.lower()
        nome = nav.capitalize()

        if "operation not permitted" in s or "errno 1" in s \
                or "binarycookies" in s:
            return (
                f"O macOS protege os cookies do {nome} e não deixou o "
                f"programa lê-los. Para usar o {nome}, é preciso dar "
                f"Acesso Total ao Disco (explico no fim). Seguindo."
            )
        if any(t in s for t in ("could not find", "not installed",
                                "no such file", "unsupported browser",
                                "does not support")):
            return f"O {nome} não está instalado neste computador. Seguindo."
        if any(t in s for t in ("permission denied", "errno 13",
                                "could not copy", "database is locked")):
            return (
                f"Não consegui ler a sessão do {nome} agora (arquivo em uso "
                f"ou sem permissão). Seguindo."
            )
        if any(t in s for t in ("no key found", "failed to decrypt",
                               "unable to decrypt", "failed to load cookies",
                               "find-generic-password failed",
                               "failed to read networkwallet",
                               "without sqlite3", "no cookies")):
            return (
                f"A sessão do {nome} existe, mas veio embaralhada (o Mac não "
                f"liberou a chave). Seguindo."
            )
        return None

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
                # Confere se o arquivo abre de verdade. Um download que termina
                # sem erro mas entrega arquivo quebrado e o pior dos casos: a
                # pessoa so descobre horas depois, na hora de usar.
                problema = conferir_arquivo(caminho, ffmpeg)
                if problema:
                    self.fila.put(("log", "ATENCAO: " + problema))
                elif not opc["somente_audio"]:
                    self.fila.put(("status", "Conferindo se o vídeo abre no Mac…"))
                    try:
                        msg = garantir_compativel(caminho, ffmpeg)
                        if msg:
                            self.fila.put(("log", msg))
                    except Exception as e:
                        self.fila.put(("log", f"ERRO ao converter o vídeo: {e}"))
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
                if not self._silenciar_erros:
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
        self.fila.put((
            "status",
            f"{self._prefixo_fila}Baixando {titulo[:48]}  {vel}  ETA {eta}",
        ))

    @staticmethod
    def _parece_bloqueio(saida: str) -> bool:
        s = saida.lower()
        return any(t in s for t in (
            "403", "forbidden", "sign in to confirm", "unable to extract",
            "please update", "nsig extraction failed", "not a bot",
        ))

    @staticmethod
    def _parece_login(saida: str) -> bool:
        """True quando o site respondeu pedindo conta, e não bloqueando robô.

        A diferença importa: bloqueio de robô às vezes some atualizando o
        motor ou saindo por outro caminho; pedido de conta, nunca. A única
        saída é entrar com a sessão de um navegador logado.
        """
        s = saida.lower()
        return any(t in s for t in (
            "login-required", "login required", "http error 401",
            "unauthorized", "conta globo", "assinante",
            "only available for registered users",
            "requires a subscription", "requires authentication",
            "use --cookies",
        )) and "not a bot" not in s

    @staticmethod
    def _parece_drm(saida: str) -> bool:
        s = saida.lower()
        return "drm" in s

    @staticmethod
    def _parece_erro_drive(url: str, saida: str = "") -> bool:
        """True se o link é do Google Drive (drive.google.com ou
        docs.google.com). Qualquer falha nesses links NÃO é bloqueio de
        robô, mesmo que o texto do erro pareça um ("403", "Forbidden"): é
        cota de download excedida, arquivo não compartilhado publicamente,
        ou (mais raro) link de PASTA em vez de arquivo. Tentar de novo por
        "outro caminho" (atualizar o motor e repetir) nunca resolve nenhum
        desses casos, só perde tempo -- por isso o motivo não entra mais na
        conta, só o dominio do link.
        """
        u = url.lower()
        return "drive.google.com" in u or "docs.google.com" in u

    @staticmethod
    def _eh_pasta_do_drive(url: str) -> bool:
        """True quando o link aponta para uma PASTA do Drive, não um
        arquivo. Isso não tem conserto tentando de novo, com cookies ou sem:
        nenhum baixador de vídeo consegue abrir uma pasta, só um arquivo por
        vez, pelo link direto dele."""
        u = url.lower()
        return "drive.google.com" in u and "/folders/" in u

    @staticmethod
    def _mensagem_erro(saida: str, url: str = "") -> str:
        erros = [l for l in saida.splitlines() if l.startswith("ERROR")]
        base = erros[-1] if erros else "O download falhou."
        s = saida.lower()

        # O link de PASTA vem primeiro, e sozinho: nenhuma outra explicação
        # de Drive (cota, permissão) faz sentido aqui, porque o problema não
        # é o arquivo -- é que uma pasta inteira nunca é baixável, com ou
        # sem sessão, com ou sem cota livre.
        if App._eh_pasta_do_drive(url):
            base += (
                "\n\nEsse link é de uma PASTA do Google Drive, não de um "
                "vídeo. Baixadores de vídeo (este incluído) só conseguem "
                "baixar um arquivo de cada vez, pelo link direto do "
                "arquivo -- nunca pelo link de uma pasta inteira."
                "\n\nO que fazer: abra essa pasta no Drive, entre no "
                "vídeo específico que você quer, clique em "
                "\"Compartilhar\" (ou nos três pontinhos do arquivo) e "
                "copie o link DAQUELE arquivo. Cole esse link aqui, não "
                "o da pasta."
            )
        elif App._parece_erro_drive(url, saida):
            if "429" in s or "too many requests" in s:
                base += (
                    "\n\nO Google Drive tem uma cota diária de downloads "
                    "para arquivos com link público, e ela parece ter "
                    "estourado (muita gente baixando esse mesmo arquivo). "
                    "Tente de novo mais tarde ou marque \"Usar cookies do "
                    "navegador\" logado na conta dona do arquivo — a cota "
                    "do dono é bem maior."
                )
            else:
                # Cobre os outros jeitos de o Drive recusar um arquivo:
                # "403 Forbidden" na hora de ler os metadados, "404",
                # "permission", "confirmation code" -- o texto exato muda
                # conforme o motivo, mas as causas prováveis são sempre as
                # mesmas três, então a explicação cobre as três de uma vez
                # em vez de tentar adivinhar qual bateu pelo texto do erro.
                base += (
                    "\n\nNão consegui baixar esse arquivo do Google "
                    "Drive. As causas mais prováveis:"
                    "\n\n• Ele não está compartilhado como \"Qualquer "
                    "pessoa com o link\" -- só quem tem acesso na conta "
                    "específica consegue abrir."
                    "\n• O Google barrou o download automático desse "
                    "arquivo (comum em arquivo grande ou muito baixado: "
                    "ele passa a exigir uma confirmação manual, que só "
                    "aparece abrindo pelo navegador)."
                    "\n• A cota diária de downloads públicos desse "
                    "arquivo estourou (muita gente baixando o mesmo "
                    "arquivo hoje)."
                    "\n\nO que fazer: abra o link direto do arquivo (não "
                    "o da pasta) no seu navegador e confirme que ele "
                    "toca normalmente ali. Se tocar, marque \"Usar "
                    "cookies do navegador\" aqui, escolha esse navegador "
                    "e tente de novo. Se nem no navegador abrir, o "
                    "problema é a permissão ou a cota do arquivo, e o "
                    "jeito é pedir pro dono compartilhar como \"Qualquer "
                    "pessoa com o link\" ou baixar direto pelo navegador."
                )
        elif App._parece_drm(saida):
            base += (
                "\n\nEsse vídeo é protegido contra cópia (DRM) pelo próprio "
                "site. Nenhum programa consegue baixá-lo, nem com a sua "
                "conta: só dá para assistir dentro do site ou do aplicativo "
                "oficial."
            )
        elif App._parece_login(saida):
            eh_globo = "globo.com" in url.lower()
            base += (
                "\n\nEsse site só entrega o vídeo para quem está com a "
                "conta aberta, e eu tentei todos os navegadores instalados "
                "sem achar uma sessão que servisse."
            )
            if eh_globo:
                base += (
                    "\n\nO Globo passou a exigir a Conta Globo até em vídeo "
                    "aberto de telejornal (o g1 mostra \"não foi possível "
                    "reproduzir o vídeo\" para quem não está logado). "
                    "A conta é gratuita."
                )
            base += (
                "\n\nO que fazer:"
                "\n1. Abra o site no seu navegador e entre na sua conta "
                "(no Globo: botão \"Entrar com Conta Globo\")."
                "\n2. Abra o vídeo e confirme que ele toca ali."
                "\n3. Deixe esse navegador aberto, volte aqui, marque "
                "\"Usar cookies do navegador\", escolha esse navegador na "
                "listinha ao lado e clique em Baixar de novo."
            )
        elif "javascript runtime" in s or "n challenge" in s:
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
                elif tipo == "cookies_ok":
                    # Deu certo com a sessão de um navegador: deixa a caixa
                    # marcada nele, para o próximo download desse site já
                    # sair de primeira, sem passar pela busca de novo.
                    self.navegador.set(valor)
                    self.usar_cookies.set(True)
                    self._toggle_cookies()
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
                        parent=self._pai_dialogo(),
                    ):
                        self._abrir_pasta(pasta)
                elif tipo == "download_parcial":
                    # Parte da fila deu certo: não é festa nem é erro. A
                    # caixa conta o placar e o Registro guarda o porquê de
                    # cada falha, para a pessoa decidir o que refazer.
                    msg, pasta = valor
                    self._set_status(msg.splitlines()[0])
                    self._logar(msg.splitlines()[0])
                    if messagebox.askyesno(
                        APP_NAME,
                        msg + "\n\nQuer abrir a pasta com o que baixou?",
                        parent=self._pai_dialogo(),
                    ):
                        self._abrir_pasta(pasta)
                elif tipo == "erro":
                    self._set_status("Erro.")
                    self._logar("ERRO: " + valor)
                    messagebox.showerror(APP_NAME, valor,
                                         parent=self._pai_dialogo())
                elif tipo == "fim":
                    self.rodando = False
                    self.btn_baixar.config(state="normal")
                    self.btn_cancelar.config(state="disabled")
                elif tipo == "motor_ok":
                    self.btn_baixar.config(state="normal")
                elif tipo == "motor_ocupado":
                    self.btn_baixar.config(state="disabled")
                elif tipo == "motor_erro":
                    self._set_status("Falha ao preparar o motor de download.")
                    self._logar(
                        "Não consegui preparar o motor de download na "
                        "primeira execução. Verifique sua conexão com a "
                        "internet; o programa tenta de novo automaticamente "
                        "quando você clicar em Baixar."
                    )
                    # Libera o botão mesmo assim: o clique dispara uma nova
                    # tentativa de instalar o motor (ver _worker), e se
                    # falhar de novo o erro agora sai claro, não um crash.
                    self.btn_baixar.config(state="normal")
        except queue.Empty:
            pass
        self.raiz.after(100, self._processar_fila)

    def _set_status(self, txt):
        self.status.config(text=txt)

    def _logar(self, txt):
        self.log.config(state="normal")
        self.log.insert("end", txt + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ----- Memória das escolhas ----------------------------------------
    def _arquivo_prefs(self):
        return os.path.join(pasta_do_usuario(), "preferencias-baixar.json")

    def _carregar_prefs(self):
        """Repõe as escolhas da última vez.

        Sem isso, toda abertura começava do zero: pasta de Downloads,
        "Melhor qualidade", tudo desmarcado. Quem usa o programa todo dia
        tinha de reconfigurar sempre, e o programa parecia recém-instalado.

        A leitura é tolerante de propósito: arquivo corrompido, campo que
        não existe mais ou pasta que foi apagada não podem impedir a aba de
        abrir. Na dúvida, fica o padrão.
        """
        try:
            with open(self._arquivo_prefs(), encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            return

        pasta = p.get("pasta_destino")
        if isinstance(pasta, str) and os.path.isdir(pasta):
            self.pasta_destino.set(pasta)

        qual = p.get("qualidade")
        if qual in QUALIDADES:
            self.qualidade.set(qual)

        nav = p.get("navegador")
        if nav in NAVEGADORES:
            self.navegador.set(nav)

        for chave, var in (
            ("somente_audio", self.somente_audio),
            ("baixar_playlist", self.baixar_playlist),
            ("remover_metadados", self.remover_metadados),
            ("usar_cookies", self.usar_cookies),
        ):
            if isinstance(p.get(chave), bool):
                var.set(p[chave])

    def _salvar_prefs(self):
        """Grava as escolhas atuais. Falhar aqui nunca atrapalha o usuário."""
        try:
            dados = {
                "pasta_destino": self.pasta_destino.get(),
                "qualidade": self.qualidade.get(),
                "somente_audio": self.somente_audio.get(),
                "baixar_playlist": self.baixar_playlist.get(),
                "remover_metadados": self.remover_metadados.get(),
                "usar_cookies": self.usar_cookies.get(),
                "navegador": self.navegador.get(),
            }
            with open(self._arquivo_prefs(), "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se derruba o processo do
        yt-dlp que ainda estiver rodando, para nao ficar orfao.
        """
        self._salvar_prefs()
        self.cancelar_flag.set()
        self.rodando = False
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


def montar(pai):
    """Desenha a aba de baixar dentro de `pai` e devolve o aplicativo."""
    return App(pai)
