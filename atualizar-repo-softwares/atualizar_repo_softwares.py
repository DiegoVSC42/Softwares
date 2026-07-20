#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atualizar_repo_softwares.py
============================

Interface grafica que mantem atualizada (via `git pull`, ou clona na
primeira vez) uma copia local do repositorio de referencia
DiegoVSC42/Softwares -- onde ficam todos os softwares/scripts publicados.

A pasta de destino e escolhida pelo usuario na primeira vez e fica salva
para as proximas execucoes (nao usamos "pasta ao lado do programa" porque
isso quebraria quando o programa vira um .exe/.app distribuido em outra
maquina).
"""

import json
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext

REPO_URL = "https://github.com/DiegoVSC42/Softwares.git"
CONFIG_PATH = Path.home() / ".atualizar_repo_softwares.json"


def _pasta_do_programa():
    """Pasta onde este programa esta rodando (fonte ou .exe/.app compilado)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def sugestao_inicial():
    """Se existir uma pasta 'softwares' ao lado do programa, sugere ela."""
    candidata = _pasta_do_programa().parent / "softwares"
    return candidata if candidata.is_dir() else None


def carregar_pasta_salva():
    try:
        dados = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        caminho = Path(dados.get("pasta_destino", ""))
        if caminho.is_dir():
            return caminho
    except (OSError, ValueError):
        pass
    return None


def salvar_pasta(caminho):
    try:
        CONFIG_PATH.write_text(
            json.dumps({"pasta_destino": str(caminho)}), encoding="utf-8"
        )
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Atualizar Softwares (contexto local)")
        self.geometry("680x460")
        self.minsize(560, 380)

        self.processo = None
        self.cancelado = False
        self.pasta_destino = carregar_pasta_salva() or sugestao_inicial()

        self._montar_widgets()
        self._checar_requisitos()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _montar_widgets(self):
        pad = {"padx": 12, "pady": 6}

        topo = tk.Frame(self)
        topo.pack(fill="x", **pad)
        tk.Label(
            topo,
            text="Mantem atualizada uma copia local do repositorio\n"
                 "DiegoVSC42/Softwares (onde ficam todos os programas).",
            justify="left",
        ).pack(anchor="w")

        linha_pasta = tk.Frame(self)
        linha_pasta.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(linha_pasta, text="Pasta de destino:").pack(side="left")
        self.pasta_var = tk.StringVar(value=self._texto_pasta())
        tk.Label(linha_pasta, textvariable=self.pasta_var, fg="#0a5").pack(
            side="left", padx=(6, 0)
        )
        tk.Button(
            linha_pasta, text="Escolher pasta...", command=self._escolher_pasta
        ).pack(side="right")

        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(self, textvariable=self.status_var, fg="#333").pack(
            anchor="w", padx=12
        )

        self.log = scrolledtext.ScrolledText(self, height=16, state="disabled")
        self.log.pack(fill="both", expand=True, padx=12, pady=6)

        botoes = tk.Frame(self)
        botoes.pack(fill="x", padx=12, pady=(0, 12))

        self.btn_atualizar = tk.Button(
            botoes, text="Atualizar agora", command=self._iniciar_pull, width=16
        )
        self.btn_atualizar.pack(side="left")

        self.btn_cancelar = tk.Button(
            botoes, text="Cancelar", command=self._cancelar, width=12,
            state="disabled",
        )
        self.btn_cancelar.pack(side="left", padx=(8, 0))

        tk.Button(botoes, text="Fechar", command=self.destroy, width=12).pack(
            side="right"
        )

    def _texto_pasta(self):
        return str(self.pasta_destino) if self.pasta_destino else "(nenhuma escolhida)"

    # ------------------------------------------------------------------
    # Escolha de pasta
    # ------------------------------------------------------------------
    def _escolher_pasta(self):
        inicial = str(self.pasta_destino) if self.pasta_destino else str(Path.home())
        escolhida = filedialog.askdirectory(
            title="Escolha (ou crie) a pasta onde fica a copia do repositorio",
            initialdir=inicial,
        )
        if escolhida:
            self.pasta_destino = Path(escolhida)
            self.pasta_var.set(self._texto_pasta())
            salvar_pasta(self.pasta_destino)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _escrever(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", texto)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _checar_requisitos(self):
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            self._escrever(
                "Git nao encontrado nesta maquina.\n"
                "Instale o Git e abra este programa de novo.\n"
            )
            self.btn_atualizar.configure(state="disabled")

    # ------------------------------------------------------------------
    # Acao principal
    # ------------------------------------------------------------------
    def _iniciar_pull(self):
        if self.pasta_destino is None:
            self._escrever("Escolha primeiro a pasta de destino, no botao acima.\n")
            return

        self.btn_atualizar.configure(state="disabled")
        self.btn_cancelar.configure(state="normal")
        self.cancelado = False
        self.status_var.set("Atualizando...")
        self._escrever(f"\n--- Atualizando {self.pasta_destino} ---\n")

        threading.Thread(target=self._rodar_pull, daemon=True).start()

    def _rodar_pull(self):
        destino = self.pasta_destino
        try:
            if not (destino / ".git").is_dir():
                self._log_thread_safe(
                    f"Ainda nao ha um clone em {destino}.\n"
                    "Clonando pela primeira vez (pode levar alguns minutos)...\n"
                )
                destino.mkdir(parents=True, exist_ok=True)
                cmd = ["git", "clone", REPO_URL, str(destino)]
            else:
                cmd = ["git", "-C", str(destino), "pull"]

            self.processo = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for linha in self.processo.stdout:
                self._log_thread_safe(linha)
            codigo = self.processo.wait()

            if self.cancelado:
                self._log_thread_safe("\nCancelado pelo usuario.\n")
                self._status_thread_safe("Cancelado.")
            elif codigo == 0:
                self._log_thread_safe("\nAtualizado com sucesso.\n")
                self._status_thread_safe("Atualizado com sucesso.")
            else:
                self._log_thread_safe(f"\nErro (codigo {codigo}).\n")
                self._status_thread_safe("Erro ao atualizar - veja o log acima.")
        except Exception as exc:  # pragma: no cover - defensivo
            self._log_thread_safe(f"\nErro inesperado: {exc}\n")
            self._status_thread_safe("Erro inesperado.")
        finally:
            self.processo = None
            self._habilitar_botoes_thread_safe()

    def _cancelar(self):
        self.cancelado = True
        if self.processo is not None:
            self.processo.terminate()
        self.status_var.set("Cancelando...")

    # ------------------------------------------------------------------
    # Chamadas seguras a partir da thread de fundo
    # ------------------------------------------------------------------
    def _log_thread_safe(self, texto):
        self.after(0, self._escrever, texto)

    def _status_thread_safe(self, texto):
        self.after(0, self.status_var.set, texto)

    def _habilitar_botoes_thread_safe(self):
        def _fn():
            self.btn_atualizar.configure(state="normal")
            self.btn_cancelar.configure(state="disabled")

        self.after(0, _fn)


if __name__ == "__main__":
    App().mainloop()
