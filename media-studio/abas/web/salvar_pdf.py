#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Salvar em PDF: aba do Media Studio para guardar matérias da internet.

A pessoa cola um ou vários links, um por linha, e cada página aberta vira um
PDF de leitura na pasta de Downloads. Um link que falha não para os outros.

Toda a parte de ler a página e gravar o PDF fica em `pagina_pdf.py`; aqui só
mora a tela. Conteúdo só para assinantes não é aberto.
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pagina_pdf
import pastas
from tema import (COR_BORDA, COR_CAMPO, COR_DESTAQUE, COR_ERRO, COR_OK,
                  COR_SUAVE, COR_TEXTO, fontes)

APP_NOME = "Salvar em PDF"


def _abrir(caminho):
    """Abre o arquivo ou a pasta no programa padrão do sistema."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    elif os.name == "nt":
        os.startfile(caminho)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", caminho])


def _resumo(r):
    """Tamanho do PDF em linguagem simples, para o registro."""
    paginas = "1 página" if r.paginas == 1 else f"{r.paginas} páginas"
    if r.imagens == 0:
        imagens = "sem imagem"
    elif r.imagens == 1:
        imagens = "1 imagem"
    else:
        imagens = f"{r.imagens} imagens"
    return f"{paginas}, {r.palavras} palavras, {imagens}"


class App:
    def __init__(self, pai):
        self.raiz = pai
        self.fila = queue.Queue()
        self.rodando = False
        self.parar = threading.Event()
        self.ultimo_pdf = ""
        self.pasta = tk.StringVar(value=pastas.pasta_downloads())
        self._montar_ui()
        self.raiz.after(100, self._processar_fila)

    # ------------------------------------------------------------------ tela
    def _montar_ui(self):
        pad = {"padx": 12, "pady": 4}

        topo = ttk.Frame(self.raiz)
        topo.pack(fill="x", **pad)
        ttk.Label(
            topo, text="Links das páginas (um por linha):",
        ).pack(anchor="w")

        caixa = ttk.Frame(topo)
        caixa.pack(fill="x", pady=(2, 0))
        self.links = tk.Text(
            caixa, height=5, wrap="none", font=fontes()[0],
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightthickness=1,
            relief="flat", padx=6, pady=4,
        )
        self.links.pack(side="left", fill="both", expand=True)
        rolagem = ttk.Scrollbar(caixa, command=self.links.yview)
        rolagem.pack(side="right", fill="y")
        self.links.config(yscrollcommand=rolagem.set)
        self.links.bind("<Command-Return>", self._atalho)
        self.links.bind("<Control-Return>", self._atalho)

        ttk.Label(
            topo,
            text="Funciona com páginas abertas. Conteúdo só para assinantes "
                 "não é aberto.",
            style="Suave.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        destino = ttk.Frame(self.raiz)
        destino.pack(fill="x", **pad)
        ttk.Label(destino, text="Salvar em:").pack(side="left")
        ttk.Entry(destino, textvariable=self.pasta).pack(
            side="left", fill="x", expand=True, padx=(6, 6))
        ttk.Button(destino, text="Escolher...",
                   command=self._escolher_pasta).pack(side="left")

        acoes = ttk.Frame(self.raiz)
        acoes.pack(fill="x", **pad)
        self.btn_salvar = ttk.Button(
            acoes, text="Salvar em PDF", style="Acao.TButton",
            command=self._iniciar)
        self.btn_salvar.pack(side="left")
        self.btn_cancelar = ttk.Button(
            acoes, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left", padx=(8, 0))
        self.btn_abrir = ttk.Button(
            acoes, text="Abrir PDF", command=self._abrir_pdf,
            state="disabled")
        self.btn_abrir.pack(side="left", padx=(8, 0))
        self.btn_pasta = ttk.Button(
            acoes, text="Abrir pasta", command=self._abrir_pasta)
        self.btn_pasta.pack(side="left", padx=(8, 0))

        progresso = ttk.Frame(self.raiz)
        progresso.pack(fill="x", **pad)
        self.barra = ttk.Progressbar(progresso, mode="determinate",
                                     maximum=100)
        self.barra.pack(fill="x")
        self.status = ttk.Label(progresso, text="Pronto.")
        self.status.pack(anchor="w", pady=(4, 0))

        quadro = ttk.LabelFrame(self.raiz, text="Registro ")
        quadro.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.log = tk.Text(
            quadro, height=8, wrap="word", state="disabled", font=fontes()[1],
            bg=COR_CAMPO, fg=COR_SUAVE, highlightbackground=COR_BORDA,
            highlightthickness=1, relief="flat", padx=6, pady=4,
        )
        self.log.pack(fill="both", expand=True, padx=6, pady=6)
        self.log.tag_configure("ok", foreground=COR_OK)
        self.log.tag_configure("erro", foreground=COR_ERRO)

    def _registrar(self, texto, marca=None):
        self.log.config(state="normal")
        self.log.insert("end", texto + "\n", marca or ())
        self.log.see("end")
        self.log.config(state="disabled")

    # ---------------------------------------------------------------- botoes
    def _atalho(self, _evento=None):
        self._iniciar()
        return "break"

    def _escolher_pasta(self):
        escolhida = filedialog.askdirectory(
            parent=self.raiz.winfo_toplevel(), initialdir=self.pasta.get())
        if escolhida:
            self.pasta.set(escolhida)

    def _abrir_pdf(self):
        if self.ultimo_pdf and os.path.exists(self.ultimo_pdf):
            _abrir(self.ultimo_pdf)

    def _abrir_pasta(self):
        pasta = pastas.garantir(self.pasta.get().strip()
                                or pastas.pasta_downloads())
        _abrir(pasta)

    def _cancelar(self):
        self.parar.set()
        self.status.config(text="Cancelando...")

    def _iniciar(self):
        if self.rodando:
            return
        linhas = self.links.get("1.0", "end").splitlines()
        links = [l.strip() for l in linhas if l.strip()]
        if not links:
            messagebox.showinfo(
                APP_NOME, "Cole pelo menos um link.",
                parent=self.raiz.winfo_toplevel())
            return
        pasta = pastas.garantir(self.pasta.get().strip()
                                or pastas.pasta_downloads())
        self.pasta.set(pasta)
        self.parar.clear()
        self.rodando = True
        self.ultimo_pdf = ""
        self.barra["value"] = 0
        self.btn_salvar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.btn_abrir.config(state="disabled")
        threading.Thread(target=self._trabalhar, args=(links, pasta),
                         daemon=True).start()

    # --------------------------------------------------------------- trabalho
    def _trabalhar(self, links, pasta):
        """Roda fora da tela: nada aqui mexe em widget, só usa a fila."""
        certos = falhas = 0
        total = len(links)
        for indice, link in enumerate(links, 1):
            if self.parar.is_set():
                break
            prefixo = f"Link {indice} de {total}: " if total > 1 else ""

            def progresso(pct, texto, prefixo=prefixo, indice=indice):
                geral = ((indice - 1) * 100 + pct) / total
                self.fila.put(("progresso", geral, prefixo + texto))

            self.fila.put(("log", f"Abrindo: {link}", None))
            try:
                r = pagina_pdf.salvar_pagina_em_pdf(
                    link, pasta, progresso, self.parar.is_set)
            except pagina_pdf.Cancelado:
                break
            except pagina_pdf.ErroPagina as e:
                falhas += 1
                self.fila.put(("log", str(e), "erro"))
                continue
            except Exception as e:
                falhas += 1
                self.fila.put(("log", f"Erro inesperado: {e}", "erro"))
                continue
            certos += 1
            self.fila.put(("pdf", r.caminho))
            self.fila.put((
                "log",
                f"Salvo: {os.path.basename(r.caminho)} ({_resumo(r)})", "ok"))
            if r.imagens_perdidas:
                self.fila.put((
                    "log",
                    f"Aviso: {r.imagens_perdidas} imagem(ns) não baixou "
                    "e ficou de fora.", None))
        self.fila.put(("fim", certos, falhas, self.parar.is_set()))

    def _processar_fila(self):
        try:
            while True:
                item = self.fila.get_nowait()
                tipo = item[0]
                if tipo == "progresso":
                    self.barra["value"] = item[1]
                    self.status.config(text=item[2])
                elif tipo == "log":
                    self._registrar(item[1], item[2])
                elif tipo == "pdf":
                    self.ultimo_pdf = item[1]
                elif tipo == "fim":
                    self._terminar(item[1], item[2], item[3])
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.raiz.after(100, self._processar_fila)

    def _terminar(self, certos, falhas, cancelado):
        self.rodando = False
        self.btn_salvar.config(state="normal")
        self.btn_cancelar.config(state="disabled")
        if self.ultimo_pdf:
            self.btn_abrir.config(state="normal")
        if cancelado:
            self.status.config(text="Cancelado.")
        elif falhas and not certos:
            self.barra["value"] = 0
            self.status.config(text="Nenhum PDF foi salvo. Veja o registro.")
        elif falhas:
            self.barra["value"] = 100
            self.status.config(
                text=f"{certos} salvo(s), {falhas} com problema. "
                     "Veja o registro.")
        else:
            self.barra["value"] = 100
            self.status.config(
                text="PDF salvo." if certos == 1
                else f"{certos} PDFs salvos.")

    def ao_fechar(self):
        self.parar.set()


def montar(pai):
    """Desenha a aba dentro de `pai` e devolve o aplicativo."""
    return App(pai)
