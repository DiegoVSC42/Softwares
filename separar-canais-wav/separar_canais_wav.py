#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Separar Canais WAV
==================

Separa um arquivo WAV estereo (em que uma trilha toca no canal esquerdo e
outra no canal direito) em dois arquivos independentes:

    nome_esquerda.wav   -> apenas o que tocava no canal esquerdo (L)
    nome_direita.wav    -> apenas o que tocava no canal direito (R)

Cada arquivo de saida pode ser gerado em dois formatos (selecionavel na GUI):

    - Mono (1 canal): arquivo com um unico canal, so a trilha isolada.
    - Estereo centralizado: arquivo estereo com a mesma trilha nos dois lados
      (a trilha isolada toca igual em L e R, ficando "centralizada").

Modos de processamento (GUI):
    - Arquivo unico
    - Pasta inteira (processa todos os .wav da pasta)

Interface grafica em Tkinter (nao exige instalacao). Processamento de audio
usa numpy. Suporta WAV PCM de 8, 16, 24 e 32 bits.
"""

import os
import sys
import wave
import threading
import traceback
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import numpy as np
except ImportError:  # mensagem amigavel se numpy faltar ao rodar o .py
    np = None


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
    Lança ValueError se o arquivo nao for estereo (2 canais).
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
#  Interface grafica (Tkinter)
# --------------------------------------------------------------------------- #

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Separar Canais WAV — Esquerda / Direita")
        self.geometry("620x440")
        self.minsize(560, 420)
        self.resizable(True, True)

        self.entradas = []          # lista de caminhos de WAV a processar
        self.pasta_origem = None    # pasta de referencia para saida
        self.cancelar = False
        self.thread = None
        self.pastas_geradas = []    # pastas onde os arquivos foram salvos

        self._montar_widgets()

        if np is None:
            messagebox.showerror(
                "Dependencia ausente",
                "O modulo 'numpy' nao esta instalado.\n\n"
                "Instale com:\n    pip install numpy\n\n"
                "(No executavel gerado, o numpy ja vem embutido.)",
            )

    # ----- construcao da interface ----------------------------------------- #
    def _montar_widgets(self):
        pad = {"padx": 10, "pady": 6}

        topo = ttk.LabelFrame(self, text="1. O que processar")
        topo.pack(fill="x", **pad)

        ttk.Button(topo, text="Selecionar arquivo .wav",
                   command=self.selecionar_arquivo).grid(row=0, column=0, padx=8, pady=8)
        ttk.Button(topo, text="Selecionar pasta (todos os .wav)",
                   command=self.selecionar_pasta).grid(row=0, column=1, padx=8, pady=8)

        self.lbl_selecao = ttk.Label(topo, text="Nada selecionado.", foreground="#555")
        self.lbl_selecao.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        # Formato de saida
        fmt = ttk.LabelFrame(self, text="2. Formato de saida de cada canal")
        fmt.pack(fill="x", **pad)

        self.modo_saida = tk.StringVar(value="mono")
        ttk.Radiobutton(fmt, text="Mono (1 canal) — so a trilha isolada",
                        variable=self.modo_saida, value="mono").pack(anchor="w", padx=8, pady=2)
        ttk.Radiobutton(fmt, text="Estereo centralizado — mesma trilha nos dois lados",
                        variable=self.modo_saida, value="estereo").pack(anchor="w", padx=8, pady=2)

        # Pasta de saida
        saida = ttk.LabelFrame(self, text="3. Onde salvar")
        saida.pack(fill="x", **pad)

        self.salvar_mesma_pasta = tk.BooleanVar(value=True)
        ttk.Checkbutton(saida, text="Salvar na mesma pasta dos arquivos de origem",
                        variable=self.salvar_mesma_pasta,
                        command=self._toggle_saida).pack(anchor="w", padx=8, pady=4)

        linha_saida = ttk.Frame(saida)
        linha_saida.pack(fill="x", padx=8, pady=(0, 6))
        self.btn_pasta_saida = ttk.Button(linha_saida, text="Escolher pasta de saida...",
                                           command=self.escolher_pasta_saida, state="disabled")
        self.btn_pasta_saida.pack(side="left")
        self.pasta_saida = tk.StringVar(value="")
        self.lbl_pasta_saida = ttk.Label(linha_saida, textvariable=self.pasta_saida,
                                          foreground="#555")
        self.lbl_pasta_saida.pack(side="left", padx=8)

        # Acao + progresso
        acao = ttk.Frame(self)
        acao.pack(fill="x", **pad)

        self.btn_processar = ttk.Button(acao, text="Separar canais",
                                        command=self.iniciar)
        self.btn_processar.pack(side="left", padx=(0, 8))
        self.btn_cancelar = ttk.Button(acao, text="Cancelar",
                                       command=self.pedir_cancelar, state="disabled")
        self.btn_cancelar.pack(side="left")

        self.btn_abrir = ttk.Button(acao, text="Abrir pasta de saida",
                                    command=self.abrir_saida, state="disabled")
        self.btn_abrir.pack(side="left", padx=8)

        self.barra = ttk.Progressbar(self, mode="determinate")
        self.barra.pack(fill="x", padx=10, pady=(4, 2))

        self.lbl_status = ttk.Label(self, text="Pronto.", foreground="#333")
        self.lbl_status.pack(anchor="w", padx=10, pady=(0, 10))

    # ----- callbacks de selecao -------------------------------------------- #
    def selecionar_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione um arquivo WAV",
            filetypes=[("Arquivos WAV", "*.wav"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return
        self.entradas = [caminho]
        self.pasta_origem = os.path.dirname(caminho)
        self.lbl_selecao.config(
            text="Arquivo: %s" % os.path.basename(caminho))

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os WAV")
        if not pasta:
            return
        wavs = listar_wavs(pasta)
        if not wavs:
            messagebox.showwarning("Nenhum WAV",
                                   "Nao encontrei arquivos .wav nessa pasta.")
            return
        self.entradas = wavs
        self.pasta_origem = pasta
        self.lbl_selecao.config(
            text="Pasta: %s  (%d arquivo(s) .wav)" % (pasta, len(wavs)))

    def _toggle_saida(self):
        if self.salvar_mesma_pasta.get():
            self.btn_pasta_saida.config(state="disabled")
            self.pasta_saida.set("")
        else:
            self.btn_pasta_saida.config(state="normal")

    def escolher_pasta_saida(self):
        pasta = filedialog.askdirectory(title="Pasta de saida")
        if pasta:
            self.pasta_saida.set(pasta)

    # ----- execucao -------------------------------------------------------- #
    def iniciar(self):
        if np is None:
            messagebox.showerror("Dependencia ausente",
                                 "Instale o numpy para usar o programa.")
            return
        if not self.entradas:
            messagebox.showinfo("Selecione algo",
                                "Escolha um arquivo ou uma pasta primeiro.")
            return
        if not self.salvar_mesma_pasta.get() and not self.pasta_saida.get():
            messagebox.showinfo("Pasta de saida",
                                "Escolha a pasta de saida ou marque "
                                "'salvar na mesma pasta'.")
            return

        self.cancelar = False
        self.pastas_geradas = []
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
        total = len(self.entradas)
        modo = self.modo_saida.get()
        ok = 0
        erros = []

        for i, caminho in enumerate(self.entradas, start=1):
            if self.cancelar:
                break
            nome = os.path.basename(caminho)
            self._status("Processando %d/%d: %s" % (i, total, nome))
            try:
                if self.salvar_mesma_pasta.get():
                    pasta_saida = os.path.dirname(caminho)
                else:
                    pasta_saida = self.pasta_saida.get()
                separar_wav(caminho, pasta_saida, modo_saida=modo)
                if pasta_saida not in self.pastas_geradas:
                    self.pastas_geradas.append(pasta_saida)
                ok += 1
            except Exception as e:  # noqa: BLE001
                erros.append("%s: %s" % (nome, e))
                traceback.print_exc()
            self._set_barra(i)

        self._finalizar(ok, erros)

    # ----- helpers de UI thread-safe --------------------------------------- #
    def _status(self, texto):
        self.after(0, lambda: self.lbl_status.config(text=texto))

    def _set_barra(self, valor):
        self.after(0, lambda: self.barra.config(value=valor))

    def _finalizar(self, ok, erros):
        def concluir():
            self.btn_processar.config(state="normal")
            self.btn_cancelar.config(state="disabled")
            if self.pastas_geradas:
                self.btn_abrir.config(state="normal")
            if self.cancelar:
                self.lbl_status.config(text="Cancelado. %d arquivo(s) prontos." % ok)
            else:
                self.lbl_status.config(text="Concluido. %d arquivo(s) processados." % ok)
            if erros:
                messagebox.showwarning(
                    "Concluido com avisos",
                    "Processados: %d\nFalhas: %d\n\n%s"
                    % (ok, len(erros), "\n".join(erros[:10])),
                )
            elif not self.cancelar:
                messagebox.showinfo(
                    "Concluido",
                    "%d arquivo(s) processados.\n"
                    "Para cada um foram gerados _esquerda.wav e _direita.wav." % ok,
                )
        self.after(0, concluir)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
