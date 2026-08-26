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
import ssl
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
APP_VERSION = "1.8.3"

# O motor de download (achar, instalar e atualizar o yt-dlp) mora em
# `compartilhado/motor_download.py`, porque a aba "Extrair audio" tambem
# precisa dele, nos dois estudios. Os nomes sao trazidos para ca para o resto
# deste arquivo continuar escrevendo `caminho_motor()` e afins, como sempre.
from compartilhado.motor_download import (      # noqa: F401
    YTDLP_BASE, DENO_BASE, CLIENTE_YOUTUBE, NAVEGADORES,
    resource_path, pasta_do_usuario, caminho_motor, url_motor,
    nome_zip_deno, caminho_js, localizar_js, find_ffmpeg_dir,
    find_ffmpeg_exe, _contexto_ssl, _sem_janela, motor_instalado,
    versao_motor, baixar_motor, baixar_js,
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
class App:
    def __init__(self, pai):
        self.raiz = pai

        self.fonte_base, self.fonte_peq = tema.fontes()

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

        self._montar_ui()
        self._verificar_ffmpeg()
        self.raiz.after(100, self._processar_fila)

        # Trava o botão até o motor de download estar pronto: clicar em
        # "Baixar" antes disso (primeira execução, ainda instalando o
        # yt-dlp) fazia o download tentar rodar um arquivo que ainda não
        # existe no disco.
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
            text="URL do vídeo ou playlist (YouTube, Instagram, TikTok, "
                 "Google Drive e outros):",
        ).pack(anchor="w")
        self.url_entry = ttk.Entry(topo)
        self.url_entry.pack(fill="x", pady=(2, 0))

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
            linha6, text="use se der erro de login",
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
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Cole a URL do vídeo.",
                                   parent=self._pai_dialogo())
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

        self.cancelar_flag.clear()
        self.btn_baixar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.barra.config(value=0)
        self.lbl_pct.config(text="0%")
        self._set_status("Iniciando…")
        self.rodando = True

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
                self.fila.put(("status", "Preparando o motor de download…"))
                self._preparar_motor()

            if not motor_instalado():
                raise RuntimeError(
                    "Não consegui preparar o motor de download (yt-dlp). "
                    "Verifique sua conexão com a internet e clique em "
                    "Baixar de novo. Se persistir, feche e abra o "
                    "programa."
                )

            codigo, saida = self._rodar(opc)

            # 403 e afins: tenta de novo por outro caminho, uma vez só.
            # Erro de cota/permissão do Google Drive não é bloqueio de robô
            # — tentar de novo por outro caminho não resolve, só perde tempo.
            if codigo != 0 and not self.cancelar_flag.is_set() \
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

            if self.cancelar_flag.is_set():
                self.fila.put(("status", "Cancelado pelo usuário."))
            elif codigo == 0:
                self.fila.put((
                    "download_ok",
                    ("Download concluído com sucesso!", opc["destino"]),
                ))
            else:
                self.fila.put(("erro", self._mensagem_erro(saida, opc["url"])))
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
    def _parece_erro_drive(url: str, saida: str) -> bool:
        """True se o erro veio de um link do Google Drive (não é bloqueio de
        robô: é cota de download excedida ou o arquivo não está
        compartilhado publicamente — tentar de novo não resolve)."""
        if "drive.google.com" not in url.lower():
            return False
        s = saida.lower()
        return any(t in s for t in (
            "429", "too many requests", "404", "not found",
            "confirmation code", "permission", "access",
        ))

    @staticmethod
    def _mensagem_erro(saida: str, url: str = "") -> str:
        erros = [l for l in saida.splitlines() if l.startswith("ERROR")]
        base = erros[-1] if erros else "O download falhou."
        s = saida.lower()
        if App._parece_erro_drive(url, saida):
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
                base += (
                    "\n\nNão consegui acessar esse arquivo do Google "
                    "Drive. Confira se ele está compartilhado como "
                    "\"Qualquer pessoa com o link\" (Visualizador). Se for "
                    "um arquivo restrito a contas específicas, marque "
                    "\"Usar cookies do navegador\" com o navegador em que "
                    "você está logado na conta que tem acesso."
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

    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se derruba o processo do
        yt-dlp que ainda estiver rodando, para nao ficar orfao.
        """
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
