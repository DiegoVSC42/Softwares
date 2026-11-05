#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aba "Converter e comprimir" do Audio Studio.

Duas coisas que na pratica sao a mesma: trocar o tipo do arquivo de som
(WAV vira MP3, M4A vira WAV, e assim por diante) e deixa-lo mais leve sem
mudar de tipo (um MP3 de 320 kbps virando um de 128 kbps).

Por isso as duas moram na mesma tela: quem escolhe "MP3" e uma qualidade
esta convertendo; quem escolhe "Manter o formato" e uma qualidade menor
esta so comprimindo. O caminho na tela e o mesmo, e a pessoa nao precisa
saber em qual dos dois casos ela esta.

Aceita um arquivo, varios arquivos ou uma pasta inteira. Cada arquivo e
processado pelo ffmpeg em thread separada, com barra de progresso do
arquivo, barra do lote e botao de cancelar.

O ffmpeg vem embutido no executavel final (PyInstaller --add-binary). Ao
rodar pelo codigo-fonte, usa o que estiver na pasta do projeto ou no PATH.
"""

import os
import sys
import queue
import shutil
import threading
import subprocess
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pastas
from tema import (COR_CAMPO, COR_BORDA, COR_TEXTO, COR_DESTAQUE)

APP_NAME = "Converter e comprimir"
APP_VERSION = "1.0.0"

# Extensoes que a aba reconhece como som ao varrer uma pasta. O ffmpeg le
# muito mais que isso, mas numa pasta ele nao deve sair convertendo video.
EXT_AUDIO = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus",
             ".aiff", ".aif", ".wma", ".amr", ".mp2", ".ac3", ".caf",
             ".mka", ".oga", ".alac", ".m4b")

MANTER = "Manter o formato original"

# Rotulo mostrado -> (extensao, codec, e_com_perda)
# "com perda" e o que decide se a caixa de qualidade (kbps) faz sentido:
# em WAV, FLAC e AIFF nao existe kbps para escolher.
FORMATOS = {
    "MP3":                 (".mp3",  "libmp3lame", True),
    "M4A (AAC)":           (".m4a",  "aac",        True),
    "OGG (Opus)":          (".ogg",  "libopus",    True),
    "WAV (sem perda)":     (".wav",  "pcm",        False),
    "FLAC (sem perda)":    (".flac", "flac",       False),
    "AIFF (sem perda)":    (".aiff", "pcm_be",     False),
    MANTER:                (None,    None,         None),
}

ORDEM_FORMATOS = ["MP3", "M4A (AAC)", "OGG (Opus)", "WAV (sem perda)",
                  "FLAC (sem perda)", "AIFF (sem perda)", MANTER]

# Rotulo mostrado -> valor passado ao ffmpeg. O texto explica o peso em
# linguagem de gente, porque "192k" nao diz nada a quem nunca mexeu nisso.
QUALIDADES = [
    ("Maxima (320 kbps) - quase o original", "320k"),
    ("Alta (256 kbps)",                      "256k"),
    ("Boa (192 kbps) - equilibrio",          "192k"),
    ("Media (128 kbps) - arquivo leve",      "128k"),
    ("Leve (96 kbps)",                       "96k"),
    ("Voz (64 kbps) - fala, bem leve",       "64k"),
    ("Voz minima (32 kbps)",                 "32k"),
]
QUALIDADE_PADRAO = "Boa (192 kbps) - equilibrio"

TAXAS = [("Manter", None), ("48.000 Hz (video)", "48000"),
         ("44.100 Hz (musica)", "44100"), ("32.000 Hz", "32000"),
         ("22.050 Hz", "22050"), ("16.000 Hz (voz)", "16000")]

CANAIS = [("Manter", None), ("Mono (1 canal)", "1"),
          ("Estereo (2 canais)", "2")]

BITS = [("Manter", None), ("16 bits (padrao)", "16"), ("24 bits", "24")]

RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
RE_TEMPO = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


# --------------------------------------------------------------------------- #
#  Ajudantes sem interface
# --------------------------------------------------------------------------- #
def resource_path(rel: str) -> str:
    """Caminho de um arquivo que viaja junto com o programa empacotado."""
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def find_ffmpeg():
    """Caminho do ffmpeg, ou None. Procura o embutido antes do sistema."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for cand in (resource_path(exe),
                 resource_path(os.path.join("ffmpeg", exe)),
                 resource_path(os.path.join("bin", exe))):
        if os.path.isfile(cand):
            return cand
    return shutil.which("ffmpeg")


def _hms_para_seg(h, m, s) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def tamanho_legivel(bytes_) -> str:
    """1536000 -> '1,5 MB'. Com virgula, que e como se escreve em portugues."""
    valor = float(bytes_)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            texto = ("%.0f" % valor) if unidade == "B" else ("%.1f" % valor)
            return texto.replace(".", ",") + " " + unidade
        valor /= 1024
    return ""


def listar_audios(pasta):
    """Lista os arquivos de som de uma pasta, sem entrar em subpastas."""
    achados = []
    for nome in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, nome)
        if os.path.isfile(caminho) and nome.lower().endswith(EXT_AUDIO):
            achados.append(caminho)
    return achados


def abrir_pasta(pasta):
    if not pasta or not os.path.isdir(pasta):
        return
    if sys.platform.startswith("win"):
        os.startfile(pasta)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", pasta])
    else:
        subprocess.Popen(["xdg-open", pasta])


# --------------------------------------------------------------------------- #
#  A tela
# --------------------------------------------------------------------------- #
class Aplicativo:
    NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def __init__(self, pai):
        self.raiz = pai
        self.ffmpeg = find_ffmpeg()

        self.entradas = []
        self.cancelar = False
        self.processo = None
        self.thread = None
        self.pastas_geradas = []

        # O Estudio olha este atributo antes de fechar a janela.
        self.rodando = False
        self._vivo = True
        self.fila = queue.Queue()

        self.formato = tk.StringVar(value="MP3")
        self.qualidade = tk.StringVar(value=QUALIDADE_PADRAO)
        self.taxa = tk.StringVar(value=TAXAS[0][0])
        self.canais = tk.StringVar(value=CANAIS[0][0])
        self.bits = tk.StringVar(value=BITS[0][0])
        self.normalizar = tk.BooleanVar(value=False)
        self.salvar_mesma_pasta = tk.BooleanVar(value=False)
        # Regra da casa: toda aba comeca salvando na pasta de Downloads.
        self.pasta_saida = tk.StringVar(value=pastas.pasta_downloads())

        self._montar_widgets()

        # A reacao mora na variavel, nunca no `command` do widget: assim ela
        # dispara tambem quando o valor muda por codigo.
        self.formato.trace_add("write", lambda *a: self._formato_mudou())
        self.salvar_mesma_pasta.trace_add("write",
                                          lambda *a: self._toggle_saida())
        self._formato_mudou()
        self._toggle_saida()

        if not self.ffmpeg:
            self._logar("AVISO: nao achei o motor de audio (ffmpeg). No "
                        "programa instalado ele vem embutido.")

        self.raiz.after(100, self._processar_fila)

    # ----- interface ------------------------------------------------------- #
    def _montar_widgets(self):
        pad = {"padx": 12, "pady": 5}

        # Botoes e progresso primeiro, ancorados embaixo: quem e empacotado
        # antes em "bottom" fica mais no fundo da tela.
        acao = ttk.Frame(self.raiz)
        acao.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        self.btn_converter = ttk.Button(acao, text="Converter",
                                        style="Acao.TButton",
                                        command=self.iniciar)
        self.btn_converter.pack(side="left")
        self.btn_cancelar = ttk.Button(acao, text="Cancelar",
                                       command=self.pedir_cancelar,
                                       state="disabled")
        self.btn_cancelar.pack(side="left", padx=8)
        self.btn_abrir = ttk.Button(acao, text="Abrir pasta de saida",
                                    command=self.abrir_saida, state="disabled")
        self.btn_abrir.pack(side="left")

        prog = ttk.Frame(self.raiz)
        prog.pack(side="bottom", fill="x", padx=12)
        self.prog_arquivo = ttk.Progressbar(prog, mode="determinate",
                                            maximum=100,
                                            style="Horizontal.TProgressbar")
        self.prog_arquivo.pack(fill="x", ipady=3)
        self.prog_lote = ttk.Progressbar(prog, mode="determinate", maximum=100,
                                         style="Horizontal.TProgressbar")
        self.prog_lote.pack(fill="x", pady=(3, 0))
        self.lbl_status = ttk.Label(prog, text="Pronto.")
        self.lbl_status.pack(anchor="w", pady=(3, 0))

        # ---------------- 1. O que converter ----------------
        topo = ttk.LabelFrame(self.raiz, text="1. O que converter ")
        topo.pack(fill="x", **pad)

        linha = ttk.Frame(topo)
        linha.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Button(linha, text="Escolher arquivos...",
                   command=self.selecionar_arquivos).pack(side="left")
        ttk.Button(linha, text="Escolher pasta (todos os audios)...",
                   command=self.selecionar_pasta).pack(side="left", padx=8)
        ttk.Button(linha, text="Limpar lista",
                   command=self.limpar).pack(side="left")

        self.lbl_selecao = ttk.Label(topo, text="Nada escolhido ainda.",
                                     style="Suave.TLabel")
        self.lbl_selecao.pack(anchor="w", padx=10, pady=(0, 7))

        # ---------------- 2. Para qual formato ----------------
        fmt = ttk.LabelFrame(self.raiz, text="2. Para qual formato ")
        fmt.pack(fill="x", **pad)

        linha_f = ttk.Frame(fmt)
        linha_f.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(linha_f, text="Formato:").pack(side="left")
        self.cb_formato = ttk.Combobox(linha_f, textvariable=self.formato,
                                       values=ORDEM_FORMATOS, state="readonly",
                                       width=26)
        self.cb_formato.pack(side="left", padx=6)
        ttk.Label(linha_f, text="Qualidade:").pack(side="left", padx=(14, 0))
        self.cb_qualidade = ttk.Combobox(
            linha_f, textvariable=self.qualidade,
            values=[r for r, _ in QUALIDADES], state="readonly", width=32)
        self.cb_qualidade.pack(side="left", padx=6)

        self.lbl_dica_fmt = ttk.Label(fmt, text="", style="Suave.TLabel")
        self.lbl_dica_fmt.pack(anchor="w", padx=10, pady=(0, 7))

        # ---------------- 3. Ajustes ----------------
        aj = ttk.LabelFrame(self.raiz, text="3. Ajustes (opcionais) ")
        aj.pack(fill="x", **pad)

        linha_a = ttk.Frame(aj)
        linha_a.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(linha_a, text="Taxa de amostragem:").pack(side="left")
        ttk.Combobox(linha_a, textvariable=self.taxa,
                     values=[r for r, _ in TAXAS], state="readonly",
                     width=18).pack(side="left", padx=6)
        ttk.Label(linha_a, text="Canais:").pack(side="left", padx=(14, 0))
        ttk.Combobox(linha_a, textvariable=self.canais,
                     values=[r for r, _ in CANAIS], state="readonly",
                     width=18).pack(side="left", padx=6)

        linha_b = ttk.Frame(aj)
        linha_b.pack(fill="x", padx=10, pady=(2, 2))
        ttk.Label(linha_b, text="Bits por amostra:").pack(side="left")
        self.cb_bits = ttk.Combobox(linha_b, textvariable=self.bits,
                                    values=[r for r, _ in BITS],
                                    state="readonly", width=18)
        self.cb_bits.pack(side="left", padx=6)
        ttk.Label(linha_b, text="(so vale para WAV, FLAC e AIFF)",
                  style="Suave.TLabel").pack(side="left")

        ttk.Checkbutton(aj, text="Emparelhar o volume dos arquivos "
                                 "(demora mais, bom para lote de gravacoes)",
                        variable=self.normalizar).pack(anchor="w", padx=10,
                                                       pady=(2, 7))

        # ---------------- 4. Onde salvar ----------------
        saida = ttk.LabelFrame(self.raiz, text="4. Onde salvar ")
        saida.pack(fill="x", **pad)

        linha_s = ttk.Frame(saida)
        linha_s.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(linha_s, text="Salvar em:").pack(side="left")
        self.campo_saida = ttk.Entry(linha_s, textvariable=self.pasta_saida)
        self.campo_saida.pack(side="left", fill="x", expand=True, padx=6)
        self.btn_pasta_saida = ttk.Button(linha_s, text="Escolher...",
                                          command=self.escolher_pasta_saida)
        self.btn_pasta_saida.pack(side="left")

        ttk.Checkbutton(saida,
                        text="Salvar na mesma pasta dos arquivos de origem",
                        variable=self.salvar_mesma_pasta).pack(
                            anchor="w", padx=10, pady=(0, 7))

        # ---------------- Registro ----------------
        reg = ttk.LabelFrame(self.raiz, text="Registro ")
        reg.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(
            reg, height=7, wrap="word", state="disabled",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, relief="flat",
        )
        self.log.pack(side="left", fill="both", expand=True,
                      padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(reg, command=self.log.yview)
        sb.pack(side="right", fill="y", pady=6, padx=(0, 8))
        self.log.config(yscrollcommand=sb.set)

    # ----- ajudantes de tela ----------------------------------------------- #
    def _pai_dialogo(self):
        """Janela a que as caixas de dialogo se prendem.

        Sem isso a caixa pode nascer atras da janela do Estudio.
        """
        return self.raiz.winfo_toplevel()

    def _formato_mudou(self):
        """Liga e desliga o que faz sentido para o formato escolhido."""
        nome = self.formato.get()
        _ext, _codec, com_perda = FORMATOS.get(nome, (None, None, True))

        if nome == MANTER:
            self.cb_qualidade.config(state="readonly")
            self.cb_bits.config(state="readonly")
            self.lbl_dica_fmt.config(
                text="Cada arquivo sai no mesmo formato em que entrou. Serve "
                     "para so deixar mais leve: escolha uma qualidade menor "
                     "que a atual.")
            return

        if com_perda:
            self.cb_qualidade.config(state="readonly")
            self.cb_bits.config(state="disabled")
            self.lbl_dica_fmt.config(
                text="Formato compacto: o arquivo fica bem menor. Quanto mais "
                     "baixa a qualidade, menor o arquivo.")
        else:
            self.cb_qualidade.config(state="disabled")
            self.cb_bits.config(state="readonly")
            self.lbl_dica_fmt.config(
                text="Formato sem perda: guarda o som inteiro, e o arquivo "
                     "fica grande. Aqui a qualidade em kbps nao se aplica.")

    def _toggle_saida(self):
        estado = "disabled" if self.salvar_mesma_pasta.get() else "normal"
        self.campo_saida.config(state=estado)
        self.btn_pasta_saida.config(state=estado)

    # ----- escolha ---------------------------------------------------------- #
    def selecionar_arquivos(self):
        caminhos = filedialog.askopenfilenames(
            title="Escolha os arquivos de audio",
            filetypes=[("Arquivos de audio",
                        " ".join("*" + e for e in EXT_AUDIO)),
                       ("Todos os arquivos", "*.*")],
            initialdir=self.pasta_saida.get() or ".",
            parent=self._pai_dialogo(),
        )
        if not caminhos:
            return
        novos = [c for c in caminhos if c not in self.entradas]
        self.entradas.extend(novos)
        self._atualizar_selecao()
        for c in novos:
            self._logar("Na fila: %s" % os.path.basename(c))

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(
            title="Escolha a pasta com os audios",
            initialdir=self.pasta_saida.get() or ".",
            parent=self._pai_dialogo(),
        )
        if not pasta:
            return
        achados = listar_audios(pasta)
        if not achados:
            messagebox.showwarning(
                "Nenhum audio",
                "Nao encontrei arquivos de audio nessa pasta.",
                parent=self._pai_dialogo())
            return
        novos = [c for c in achados if c not in self.entradas]
        self.entradas.extend(novos)
        self._atualizar_selecao()
        self._logar("Na fila: %d arquivo(s) da pasta %s."
                    % (len(novos), pasta))

    def limpar(self):
        self.entradas = []
        self._atualizar_selecao()

    def _atualizar_selecao(self):
        if not self.entradas:
            self.lbl_selecao.config(text="Nada escolhido ainda.")
            return
        total = sum(os.path.getsize(c) for c in self.entradas
                    if os.path.isfile(c))
        if len(self.entradas) == 1:
            texto = "1 arquivo: %s  (%s)" % (
                os.path.basename(self.entradas[0]), tamanho_legivel(total))
        else:
            texto = "%d arquivos escolhidos  (%s no total)" % (
                len(self.entradas), tamanho_legivel(total))
        self.lbl_selecao.config(text=texto)

    def escolher_pasta_saida(self):
        pasta = filedialog.askdirectory(
            title="Pasta de saida", initialdir=self.pasta_saida.get() or ".",
            parent=self._pai_dialogo())
        if pasta:
            self.pasta_saida.set(pasta)

    def abrir_saida(self):
        for pasta in self.pastas_geradas:
            abrir_pasta(pasta)

    # ----- execucao --------------------------------------------------------- #
    def iniciar(self):
        if not self.ffmpeg:
            messagebox.showerror(
                "Falta o motor de audio",
                "Nao encontrei o ffmpeg, que e quem converte os arquivos.\n\n"
                "No programa instalado ele vem embutido. Rodando pelo "
                "codigo-fonte, abra pelo \"abrir-audio-studio.command\".",
                parent=self._pai_dialogo())
            return
        if not self.entradas:
            messagebox.showinfo("Escolha algo",
                                "Escolha os arquivos ou uma pasta primeiro.",
                                parent=self._pai_dialogo())
            return
        if (not self.salvar_mesma_pasta.get()
                and not self.pasta_saida.get().strip()):
            messagebox.showinfo("Pasta de saida",
                                "Escolha a pasta de saida ou marque "
                                "'salvar na mesma pasta'.",
                                parent=self._pai_dialogo())
            return

        self.cancelar = False
        self.pastas_geradas = []
        self.rodando = True
        self.btn_converter.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.btn_abrir.config(state="disabled")
        self.prog_arquivo.config(value=0)
        self.prog_lote.config(value=0)

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def pedir_cancelar(self):
        self.cancelar = True
        self.fila.put(("status", "Cancelando..."))
        proc = self.processo
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _worker(self):
        """Roda em thread separada. So fala com a tela pela fila."""
        total = len(self.entradas)
        ok = 0
        erros = []
        entrou = 0
        saiu = 0

        try:
            for i, origem in enumerate(self.entradas, start=1):
                if self.cancelar:
                    break
                nome = os.path.basename(origem)
                self.fila.put(("status", "Convertendo %d/%d: %s"
                               % (i, total, nome)))
                self.fila.put(("arquivo", 0))
                try:
                    if self._sem_ganho(origem):
                        self.fila.put(("log",
                                       "Aviso: %s e um formato sem perda; "
                                       "manter o formato nao deixa o arquivo "
                                       "mais leve. Para comprimir, escolha "
                                       "MP3 ou M4A." % nome))
                    destino = self._caminho_destino(origem)
                    pastas.garantir(os.path.dirname(destino))
                    erro = self._rodar_ffmpeg(self._comando(origem, destino))
                    if erro == "cancelado":
                        # Arquivo pela metade nao serve para nada e ainda
                        # engana quem for procurar o resultado depois.
                        self._apagar(destino)
                        break
                    if erro:
                        erros.append("%s: %s" % (nome, erro))
                        self.fila.put(("log", "ERRO em %s: %s" % (nome, erro)))
                        self._apagar(destino)
                    else:
                        ok += 1
                        tam_e = os.path.getsize(origem)
                        tam_s = os.path.getsize(destino)
                        entrou += tam_e
                        saiu += tam_s
                        pasta = os.path.dirname(destino)
                        if pasta not in self.pastas_geradas:
                            self.pastas_geradas.append(pasta)
                        self.fila.put(("log", "Pronto: %s (%s) -> %s (%s)%s"
                                       % (nome, tamanho_legivel(tam_e),
                                          os.path.basename(destino),
                                          tamanho_legivel(tam_s),
                                          self._diferenca(tam_e, tam_s))))
                except Exception as e:  # noqa: BLE001
                    erros.append("%s: %s" % (nome, e))
                    self.fila.put(("log", "ERRO em %s: %s" % (nome, e)))
                self.fila.put(("lote", (i, total)))
        finally:
            self.fila.put(("fim", (ok, erros, entrou, saiu)))

    def _sem_ganho(self, origem):
        """True quando 'manter o formato' nao vai comprimir coisa nenhuma.

        Em WAV, AIFF e FLAC nao existe kbps: a qualidade escolhida na tela e
        simplesmente ignorada pelo motor, e o arquivo sai do mesmo tamanho.
        Melhor dizer isso no registro do que a pessoa achar que o programa
        falhou.
        """
        if self.formato.get() != MANTER:
            return False
        return os.path.splitext(origem)[1].lower() in (
            ".wav", ".aiff", ".aif", ".flac", ".alac", ".caf")

    def _diferenca(self, antes, depois):
        """Texto curto dizendo o quanto o arquivo encolheu (ou cresceu)."""
        if antes <= 0:
            return ""
        variacao = (depois - antes) / antes * 100
        if variacao <= -1:
            return "  [%d%% menor]" % round(-variacao)
        if variacao >= 1:
            return "  [%d%% maior]" % round(variacao)
        return ""

    def _apagar(self, caminho):
        try:
            if caminho and os.path.isfile(caminho):
                os.remove(caminho)
        except Exception:
            pass

    def _caminho_destino(self, origem):
        """Onde o arquivo convertido vai parar, sem passar por cima do original.

        Quando o resultado cairia exatamente sobre o arquivo de entrada (mesma
        pasta e mesma extensao, que e o caso de so comprimir), o nome ganha um
        "_convertido" no fim, e depois numeros (_convertido_2, _convertido_3)
        ate sobrar um nome livre. Sem isso, comprimir um MP3 na propria pasta
        destruiria o original enquanto ele ainda esta sendo lido.
        """
        base = os.path.splitext(os.path.basename(origem))[0]
        ext_origem = os.path.splitext(origem)[1]

        nome_fmt = self.formato.get()
        ext = FORMATOS.get(nome_fmt, (None,))[0] or ext_origem

        if self.salvar_mesma_pasta.get():
            pasta = os.path.dirname(origem)
        else:
            pasta = self.pasta_saida.get().strip()

        alvo = os.path.join(pasta, base + ext)
        if os.path.abspath(alvo) != os.path.abspath(origem):
            return alvo

        alvo = os.path.join(pasta, base + "_convertido" + ext)
        contador = 2
        while os.path.exists(alvo):
            alvo = os.path.join(pasta, "%s_convertido_%d%s"
                                % (base, contador, ext))
            contador += 1
        return alvo

    def _comando(self, origem, destino):
        """Monta a linha do ffmpeg para um arquivo."""
        cmd = [self.ffmpeg, "-y", "-hide_banner", "-i", origem, "-vn"]

        if self.normalizar.get():
            cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]

        taxa = dict(TAXAS).get(self.taxa.get())
        if taxa:
            cmd += ["-ar", taxa]
        canais = dict(CANAIS).get(self.canais.get())
        if canais:
            cmd += ["-ac", canais]

        nome_fmt = self.formato.get()
        if nome_fmt == MANTER:
            # Sem formato novo: o ffmpeg decide o codec pela extensao do
            # arquivo de saida, que aqui e a mesma da entrada. A qualidade
            # escolhida entra do mesmo jeito, e e ela que comprime.
            cmd += ["-b:a", dict(QUALIDADES).get(self.qualidade.get(), "192k")]
            cmd += [destino]
            return cmd

        _ext, codec, com_perda = FORMATOS[nome_fmt]
        bits = dict(BITS).get(self.bits.get())

        if codec == "pcm":
            cmd += ["-c:a", "pcm_s24le" if bits == "24" else "pcm_s16le"]
        elif codec == "pcm_be":
            cmd += ["-c:a", "pcm_s24be" if bits == "24" else "pcm_s16be"]
        elif codec == "flac":
            cmd += ["-c:a", "flac"]
            if bits:
                cmd += ["-sample_fmt", "s32" if bits == "24" else "s16"]
        else:
            cmd += ["-c:a", codec,
                    "-b:a", dict(QUALIDADES).get(self.qualidade.get(), "192k")]

        # Metadados (titulo, artista) seguem junto quando o formato de destino
        # sabe guarda-los; quando nao sabe, o ffmpeg simplesmente ignora.
        cmd += ["-map_metadata", "0", destino]
        return cmd

    def _rodar_ffmpeg(self, cmd):
        """Roda o ffmpeg, atualiza a barra e devolve None quando deu certo."""
        self.processo = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            universal_newlines=True, encoding="utf-8", errors="replace",
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
                self.fila.put(("arquivo",
                               max(0, min(100, atual / duracao * 100))))

        self.processo.wait()
        codigo = self.processo.returncode
        self.processo = None

        if self.cancelar:
            return "cancelado"
        if codigo == 0:
            self.fila.put(("arquivo", 100))
            return None
        texto = "".join(ultimas).strip().replace("\n", " ")
        return texto[-160:] if texto else "codigo %s" % codigo

    # ----- conversa entre a thread e a tela --------------------------------- #
    def _processar_fila(self):
        """Le a fila e mexe na tela. So este metodo toca em widget."""
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "status":
                    self.lbl_status.config(text=dado)
                elif tipo == "arquivo":
                    self.prog_arquivo.config(value=dado)
                elif tipo == "lote":
                    i, total = dado
                    self.prog_lote.config(value=(i / total * 100) if total else 0)
                elif tipo == "log":
                    self._logar(dado)
                elif tipo == "fim":
                    self._concluir(*dado)
        except queue.Empty:
            pass
        if self._vivo:
            self.raiz.after(100, self._processar_fila)

    def _concluir(self, ok, erros, entrou, saiu):
        self.rodando = False
        self.btn_converter.config(state="normal")
        self.btn_cancelar.config(state="disabled")
        if self.pastas_geradas:
            self.btn_abrir.config(state="normal")

        if self.cancelar:
            self.lbl_status.config(text="Cancelado. %d arquivo(s) prontos." % ok)
            return

        resumo = "Concluido. %d arquivo(s) convertidos." % ok
        if ok and entrou:
            resumo += "  %s -> %s%s" % (tamanho_legivel(entrou),
                                        tamanho_legivel(saiu),
                                        self._diferenca(entrou, saiu))
        self.lbl_status.config(text=resumo)
        self._logar(resumo)

        if erros:
            messagebox.showwarning(
                "Concluido com avisos",
                "Convertidos: %d\nFalhas: %d\n\n%s"
                % (ok, len(erros), "\n".join(erros[:8])),
                parent=self._pai_dialogo())
        elif ok:
            messagebox.showinfo("Concluido", resumo,
                                parent=self._pai_dialogo())

    def _logar(self, texto):
        self.log.config(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ----- fechamento ------------------------------------------------------- #
    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma."""
        self.cancelar = True
        self.rodando = False
        self._vivo = False
        proc = self.processo
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass


def montar(pai):
    """Desenha a aba de converter e comprimir dentro de `pai`."""
    return Aplicativo(pai)
