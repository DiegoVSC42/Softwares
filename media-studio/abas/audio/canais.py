#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aba "Separar canais" do Audio Studio.

Pega uma gravacao com duas vozes em canais separados (o caso tipico e uma
ligacao ou entrevista gravada em estereo, com cada pessoa num canal) e separa
em dois arquivos, um por voz:

    nome_esquerda.wav   -> so o que tocava no canal esquerdo (L)
    nome_direita.wav    -> so o que tocava no canal direito (R)

Cada arquivo de saida pode sair de dois jeitos (escolha na tela):

    - Mono (1 canal): arquivo com um unico canal, so a voz isolada.
    - Estereo centralizado: arquivo estereo com a mesma voz nos dois lados.

Da para processar um arquivo so ou uma pasta inteira de .wav.

O nucleo (separar_wav) veio do programa "Separar Canais WAV", que abria a
propria janela; aqui ele e o mesmo, sem nenhuma mudanca de comportamento. O
que mudou foi so a moldura: a classe virou uma tela desenhada dentro do quadro
da aba, com a paleta escura do estudio.

Le WAV PCM de 8, 16, 24 e 32 bits. O processamento usa numpy.
"""

import os
import sys
import wave
import queue
import threading
import traceback
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import numpy as np
except ImportError:  # mensagem amigavel se numpy faltar ao rodar o .py
    np = None

import pastas
import tema
from tema import (COR_FUNDO, COR_PAINEL, COR_CAMPO, COR_BOTAO, COR_BORDA,
                  COR_TEXTO, COR_SUAVE, COR_APAGADO, COR_DESTAQUE, COR_OK,
                  COR_ERRO)

APP_NAME = "Separar Canais"
APP_VERSION = "1.1.0"

# Recado unico para quando a pessoa aponta para um arquivo que nao e WAV.
AVISO_FORMATO = ("Este separador le arquivos WAV. Converta antes, ou use a "
                 "aba Cortar e dividir.")


# --------------------------------------------------------------------------- #
#  Nucleo de processamento (sem dependencia de GUI)
# --------------------------------------------------------------------------- #

def separar_wav(caminho_entrada, pasta_saida, modo_saida="mono"):
    """
    Separa um WAV estereo em dois arquivos (esquerda e direita).

    modo_saida:
        "mono"            -> 1 canal por arquivo
        "estereo"         -> estereo com o canal duplicado nos dois lados

    Retorna a lista de caminhos gerados.
    Lanca ValueError se o arquivo nao for estereo (2 canais).
    """
    with wave.open(caminho_entrada, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)

    if nchannels != 2:
        raise ValueError(
            "O arquivo nao e estereo (tem %d canal(is)). "
            "So da para separar L/R de arquivos com 2 canais." % nchannels
        )

    # Trata os bytes como matriz (nframes, canais, bytes_por_amostra).
    # Assim funciona para qualquer profundidade (8/16/24/32 bits) sem
    # precisar interpretar o tipo numerico da amostra.
    raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, nchannels, sampwidth)

    nome_base = os.path.splitext(os.path.basename(caminho_entrada))[0]
    os.makedirs(pasta_saida, exist_ok=True)

    gerados = []
    for indice_canal, sufixo in ((0, "esquerda"), (1, "direita")):
        canal = raw[:, indice_canal, :]  # (nframes, sampwidth)

        if modo_saida == "estereo":
            dados = np.empty((canal.shape[0], 2, sampwidth), dtype=np.uint8)
            dados[:, 0, :] = canal
            dados[:, 1, :] = canal
            canais_saida = 2
            bytes_saida = dados.tobytes()
        else:  # mono
            canais_saida = 1
            bytes_saida = canal.tobytes()

        caminho_saida = os.path.join(pasta_saida, "%s_%s.wav" % (nome_base, sufixo))
        with wave.open(caminho_saida, "wb") as wout:
            wout.setnchannels(canais_saida)
            wout.setsampwidth(sampwidth)
            wout.setframerate(framerate)
            wout.writeframes(bytes_saida)
        gerados.append(caminho_saida)

    return gerados


def abrir_pasta(pasta):
    """Abre a pasta no gerenciador de arquivos do sistema."""
    if not pasta or not os.path.isdir(pasta):
        return
    if sys.platform.startswith("win"):
        os.startfile(pasta)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", pasta])
    else:
        subprocess.Popen(["xdg-open", pasta])


def listar_wavs(pasta):
    """Lista todos os .wav de uma pasta (sem recursao)."""
    arquivos = []
    for nome in sorted(os.listdir(pasta)):
        if nome.lower().endswith(".wav"):
            caminho = os.path.join(pasta, nome)
            if os.path.isfile(caminho):
                arquivos.append(caminho)
    return arquivos


# --------------------------------------------------------------------------- #
#  A tela (desenhada dentro do quadro da aba)
# --------------------------------------------------------------------------- #

class Aplicativo:
    def __init__(self, pai):
        self.raiz = pai

        self.entradas = []          # lista de caminhos de WAV a processar
        self.pasta_origem = None    # pasta de referencia para saida
        self.cancelar = False
        self.thread = None
        self.pastas_geradas = []    # pastas onde os arquivos foram salvos

        # O Estudio olha este atributo antes de fechar a janela.
        self.rodando = False

        # Enquanto for True, a fila continua sendo lida. `ao_fechar` desliga.
        self._vivo = True
        self.fila = queue.Queue()

        self.modo_saida = tk.StringVar(value="mono")
        self.salvar_mesma_pasta = tk.BooleanVar(value=False)
        # Regra da casa: toda aba comeca salvando na pasta de Downloads.
        self.pasta_saida = tk.StringVar(value=pastas.pasta_downloads())

        self._montar_widgets()

        # A reacao mora na variavel, e nao no `command` do Checkbutton: assim
        # ela dispara tambem quando o valor muda por codigo.
        self.salvar_mesma_pasta.trace_add("write",
                                          lambda *a: self._toggle_saida())
        self._toggle_saida()

        self.raiz.after(100, self._processar_fila)

        if np is None:
            self.raiz.after(200, self._avisar_sem_numpy)

    # ----- construcao da interface ----------------------------------------- #
    def _montar_widgets(self):
        pad = {"padx": 12, "pady": 5}

        # Botoes de acao e progresso primeiro, ancorados embaixo: quem e
        # empacotado antes em "bottom" fica mais no fundo.
        acao = ttk.Frame(self.raiz)
        acao.pack(side="bottom", fill="x", padx=12, pady=(4, 10))

        self.btn_processar = ttk.Button(acao, text="Separar canais",
                                        style="Acao.TButton",
                                        command=self.iniciar)
        self.btn_processar.pack(side="left")
        self.btn_cancelar = ttk.Button(acao, text="Cancelar",
                                       command=self.pedir_cancelar,
                                       state="disabled")
        self.btn_cancelar.pack(side="left", padx=8)
        self.btn_abrir = ttk.Button(acao, text="Abrir pasta de saida",
                                    command=self.abrir_saida, state="disabled")
        self.btn_abrir.pack(side="left")

        prog = ttk.Frame(self.raiz)
        prog.pack(side="bottom", fill="x", padx=12)
        self.barra = ttk.Progressbar(prog, mode="determinate",
                                     style="Horizontal.TProgressbar")
        self.barra.pack(fill="x", ipady=4)
        self.lbl_status = ttk.Label(prog, text="Pronto.")
        self.lbl_status.pack(anchor="w", pady=(3, 0))

        # ---------------- 1. O que separar ----------------
        topo = ttk.LabelFrame(self.raiz, text="1. O que separar ")
        topo.pack(fill="x", **pad)

        linha_sel = ttk.Frame(topo)
        linha_sel.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Button(linha_sel, text="Escolher arquivo .wav...",
                   command=self.selecionar_arquivo).pack(side="left")
        ttk.Button(linha_sel, text="Escolher pasta (todos os .wav)...",
                   command=self.selecionar_pasta).pack(side="left", padx=8)

        self.lbl_selecao = ttk.Label(topo, text="Nada escolhido ainda.",
                                     style="Suave.TLabel")
        self.lbl_selecao.pack(anchor="w", padx=10, pady=(0, 7))

        # ---------------- 2. Formato de cada canal ----------------
        fmt = ttk.LabelFrame(self.raiz, text="2. Como salvar cada voz ")
        fmt.pack(fill="x", **pad)

        linha_fmt = ttk.Frame(fmt)
        linha_fmt.pack(fill="x", padx=10, pady=(6, 8))
        ttk.Radiobutton(linha_fmt, text="Mono (1 canal)",
                        variable=self.modo_saida,
                        value="mono").pack(side="left")
        ttk.Radiobutton(linha_fmt, text="Estereo centralizado",
                        variable=self.modo_saida,
                        value="estereo").pack(side="left", padx=(20, 8))
        ttk.Label(linha_fmt, text="a mesma voz nos dois lados",
                  style="Suave.TLabel").pack(side="left")

        # ---------------- 3. Onde salvar ----------------
        saida = ttk.LabelFrame(self.raiz, text="3. Onde salvar ")
        saida.pack(fill="x", **pad)

        linha_saida = ttk.Frame(saida)
        linha_saida.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(linha_saida, text="Salvar em:").pack(side="left")
        self.campo_saida = ttk.Entry(linha_saida, textvariable=self.pasta_saida)
        self.campo_saida.pack(side="left", fill="x", expand=True, padx=6)
        self.btn_pasta_saida = ttk.Button(linha_saida, text="Escolher...",
                                          command=self.escolher_pasta_saida)
        self.btn_pasta_saida.pack(side="left")

        self.chk_mesma = ttk.Checkbutton(
            saida, text="Salvar na mesma pasta dos arquivos de origem",
            variable=self.salvar_mesma_pasta)
        self.chk_mesma.pack(anchor="w", padx=10, pady=(0, 7))

        # ---------------- Registro ----------------
        reg = ttk.LabelFrame(self.raiz, text="Registro ")
        reg.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(
            reg, height=6, wrap="word", state="disabled",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, relief="flat",
        )
        self.log.pack(side="left", fill="both", expand=True,
                      padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(reg, command=self.log.yview)
        sb.pack(side="right", fill="y", pady=6, padx=(0, 8))
        self.log.config(yscrollcommand=sb.set)

    # ----- ajudantes ------------------------------------------------------- #
    def _pai_dialogo(self):
        """Janela a que as caixas de dialogo devem se prender.

        Sem isso a caixa pode nascer atras da janela do Estudio.
        """
        return self.raiz.winfo_toplevel()

    def _avisar_sem_numpy(self):
        messagebox.showerror(
            "Esta aba precisa ser preparada",
            "Falta um componente para separar as vozes.\n\n"
            "Feche o programa e abra de novo pelo "
            "\"abrir-audio-studio.command\": ele instala o que falta "
            "sozinho, na primeira vez.\n\n"
            "As outras abas continuam funcionando normalmente.",
            parent=self._pai_dialogo(),
        )

    # ----- escolha do que processar ---------------------------------------- #
    def selecionar_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Escolha um arquivo WAV",
            filetypes=[("Arquivos WAV", "*.wav"), ("Todos os arquivos", "*.*")],
            initialdir=self.pasta_saida.get() or ".",
            parent=self._pai_dialogo(),
        )
        if not caminho:
            return
        if not caminho.lower().endswith(".wav"):
            messagebox.showwarning("Formato nao aceito", AVISO_FORMATO,
                                   parent=self._pai_dialogo())
            return
        self.entradas = [caminho]
        self.pasta_origem = os.path.dirname(caminho)
        self.lbl_selecao.config(text="Arquivo: %s" % os.path.basename(caminho))
        self._logar("Escolhido: %s" % os.path.basename(caminho))

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(
            title="Escolha a pasta com os WAV",
            initialdir=self.pasta_saida.get() or ".",
            parent=self._pai_dialogo(),
        )
        if not pasta:
            return
        wavs = listar_wavs(pasta)
        if not wavs:
            messagebox.showwarning(
                "Nenhum WAV",
                "Nao encontrei arquivos .wav nessa pasta.\n\n" + AVISO_FORMATO,
                parent=self._pai_dialogo())
            return
        self.entradas = wavs
        self.pasta_origem = pasta
        self.lbl_selecao.config(
            text="Pasta: %s  (%d arquivo(s) .wav)" % (pasta, len(wavs)))
        self._logar("Escolhida a pasta %s com %d arquivo(s)."
                    % (pasta, len(wavs)))

    def _toggle_saida(self):
        """Liga e desliga o campo de pasta conforme a caixa de marcar."""
        if self.salvar_mesma_pasta.get():
            self.btn_pasta_saida.config(state="disabled")
            self.campo_saida.config(state="disabled")
        else:
            self.btn_pasta_saida.config(state="normal")
            self.campo_saida.config(state="normal")

    def escolher_pasta_saida(self):
        pasta = filedialog.askdirectory(
            title="Pasta de saida",
            initialdir=self.pasta_saida.get() or ".",
            parent=self._pai_dialogo(),
        )
        if pasta:
            self.pasta_saida.set(pasta)

    # ----- execucao -------------------------------------------------------- #
    def iniciar(self):
        if np is None:
            messagebox.showerror("Falta um componente",
                                 "Abra o programa pelo \"abrir-audio-studio.command\" "
                                 "para instalar o que falta.",
                                 parent=self._pai_dialogo())
            return
        if not self.entradas:
            messagebox.showinfo("Escolha algo",
                                "Escolha um arquivo ou uma pasta primeiro.",
                                parent=self._pai_dialogo())
            return
        if not self.salvar_mesma_pasta.get() and not self.pasta_saida.get().strip():
            messagebox.showinfo("Pasta de saida",
                                "Escolha a pasta de saida ou marque "
                                "'salvar na mesma pasta'.",
                                parent=self._pai_dialogo())
            return

        self.cancelar = False
        self.pastas_geradas = []
        self.rodando = True
        self.btn_processar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.btn_abrir.config(state="disabled")
        self.barra.config(maximum=len(self.entradas), value=0)

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def pedir_cancelar(self):
        self.cancelar = True
        self._status("Cancelando...")

    def abrir_saida(self):
        if not self.pastas_geradas:
            return
        # abre todas as pastas em que algo foi salvo (normalmente uma so)
        for pasta in self.pastas_geradas:
            abrir_pasta(pasta)

    def _worker(self):
        """Roda em thread separada. So fala com a tela pela fila."""
        total = len(self.entradas)
        modo = self.modo_saida.get()
        mesma = self.salvar_mesma_pasta.get()
        destino_fixo = self.pasta_saida.get().strip()
        ok = 0
        erros = []

        try:
            for i, caminho in enumerate(self.entradas, start=1):
                if self.cancelar:
                    break
                nome = os.path.basename(caminho)
                self._status("Processando %d/%d: %s" % (i, total, nome))
                try:
                    if mesma:
                        pasta_saida = os.path.dirname(caminho)
                    else:
                        pasta_saida = destino_fixo
                    pasta_saida = pastas.garantir(pasta_saida)
                    gerados = separar_wav(caminho, pasta_saida, modo_saida=modo)
                    if pasta_saida not in self.pastas_geradas:
                        self.pastas_geradas.append(pasta_saida)
                    ok += 1
                    self._logar_fila(
                        "Pronto: %s -> %s" % (
                            nome,
                            " e ".join(os.path.basename(g) for g in gerados)))
                except wave.Error:
                    # Nao e um WAV de verdade (extensao trocada, ou arquivo
                    # comprimido dentro de um .wav).
                    erros.append("%s: %s" % (nome, AVISO_FORMATO))
                    self._logar_fila("ERRO em %s: %s" % (nome, AVISO_FORMATO))
                    traceback.print_exc()
                except Exception as e:  # noqa: BLE001
                    erros.append("%s: %s" % (nome, e))
                    self._logar_fila("ERRO em %s: %s" % (nome, e))
                    traceback.print_exc()
                self._set_barra(i)
        finally:
            self._finalizar(ok, erros)

    # ----- conversa entre a thread e a tela -------------------------------- #
    def _status(self, texto):
        self.fila.put(("status", texto))

    def _set_barra(self, valor):
        self.fila.put(("barra", valor))

    def _logar_fila(self, texto):
        self.fila.put(("log", texto))

    def _finalizar(self, ok, erros):
        self.fila.put(("fim", (ok, erros)))

    def _processar_fila(self):
        """Le a fila e mexe na tela. So este metodo toca em widget."""
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "status":
                    self.lbl_status.config(text=valor)
                elif tipo == "barra":
                    self.barra.config(value=valor)
                elif tipo == "log":
                    self._logar(valor)
                elif tipo == "fim":
                    self._concluir(*valor)
        except queue.Empty:
            pass
        if self._vivo:
            self.raiz.after(100, self._processar_fila)

    def _concluir(self, ok, erros):
        self.rodando = False
        self.btn_processar.config(state="normal")
        self.btn_cancelar.config(state="disabled")
        if self.pastas_geradas:
            self.btn_abrir.config(state="normal")
        if self.cancelar:
            self.lbl_status.config(text="Cancelado. %d arquivo(s) prontos." % ok)
        else:
            self.lbl_status.config(
                text="Concluido. %d arquivo(s) processados." % ok)
        if erros:
            messagebox.showwarning(
                "Concluido com avisos",
                "Processados: %d\nFalhas: %d\n\n%s"
                % (ok, len(erros), "\n".join(erros[:10])),
                parent=self._pai_dialogo(),
            )
        elif not self.cancelar:
            messagebox.showinfo(
                "Concluido",
                "%d arquivo(s) processados.\n"
                "Para cada um foram gerados _esquerda.wav e _direita.wav." % ok,
                parent=self._pai_dialogo(),
            )

    def _logar(self, texto):
        self.log.config(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ----- fechamento ------------------------------------------------------ #
    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se avisa a thread para
        parar e se desliga a leitura da fila.
        """
        self.cancelar = True
        self.rodando = False
        self._vivo = False


def montar(pai):
    """Desenha a aba de separar canais dentro de `pai` e devolve o aplicativo."""
    return Aplicativo(pai)
