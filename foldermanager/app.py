#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — Gerenciador de Pastas (Comparar + Copiar)
==================================================

Aplicativo de tela única que une duas ferramentas:

  1. COMPARAR    : confere se a cópia entre ORIGEM (ex.: Drive) e DESTINO
                   (ex.: NAS) está completa e correta. SOMENTE LEITURA.
  2. COPIAR      : copia para o destino apenas os arquivos que faltam.
                   A origem nunca é alterada.

O RELATÓRIO é OPCIONAL: só é gerado ao clicar em "Gerar relatório", quando o
usuário escolhe o formato (PDF, CSV ou HTML). O relatório cobre a última
comparação e, se houve uma cópia, também a última cópia realizada.

Funciona com Python 3.8+ (Tkinter já vem no Windows). Para PDF é preciso ter a
biblioteca reportlab (já embutida no executável; ou: pip install reportlab).
"""

import datetime as dt
import os
import queue
import sys
import threading
import time
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Garante que os módulos do projeto sejam encontrados, mesmo congelado no .exe
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import motor_comparacao as mcomp
import motor_copia as mcopia
import relatorio


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerenciador de Pastas — Comparar e Copiar")
        self.geometry("860x680")
        self.minsize(760, 620)

        self.fila = queue.Queue()
        self.evento_cancelar = threading.Event()
        self.rodando = False

        # Resultados guardados para o relatório
        self.dados_comparacao = None   # dict devolvido por mcomp.comparar
        self.resumo_copia = None       # dict resumo da última cópia
        self._copiar_apos_analise = False  # encadeia "analisar -> copiar"

        # Progresso: rótulo da ação atual e instante de início (para o ETA)
        self._rotulo_prog = "Processando"
        self._t_inicio = None
        # Progresso do arquivo atual (barra secundária)
        self._arq_rel = ""
        self._arq_size = 0

        self._montar_interface()
        self.after(100, self._processar_fila)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _montar_interface(self):
        pad = {"padx": 10, "pady": 6}

        ttk.Label(
            self,
            text="1) Analise as duas pastas (somente leitura).  2) Copie os "
                 "arquivos que faltam no destino.\nA cópia reaproveita a análise "
                 "— não lê tudo de novo. O relatório (PDF, CSV ou HTML) é opcional.",
            justify="left",
        ).pack(anchor="w", **pad)

        # --- Pastas ---
        frm = ttk.LabelFrame(self, text="Pastas")
        frm.pack(fill="x", **pad)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="ORIGEM (ex.: Drive):").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.var_origem = tk.StringVar()
        self.e_origem = ttk.Entry(frm, textvariable=self.var_origem)
        self.e_origem.grid(row=0, column=1, sticky="ew", padx=6)
        self.b_origem = ttk.Button(frm, text="Procurar...",
                                   command=lambda: self._escolher(self.var_origem))
        self.b_origem.grid(row=0, column=2, padx=6)

        ttk.Label(frm, text="DESTINO (ex.: NAS):").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.var_destino = tk.StringVar()
        self.e_destino = ttk.Entry(frm, textvariable=self.var_destino)
        self.e_destino.grid(row=1, column=1, sticky="ew", padx=6)
        self.b_destino = ttk.Button(frm, text="Procurar...",
                                    command=lambda: self._escolher(self.var_destino))
        self.b_destino.grid(row=1, column=2, padx=6)

        # --- Opções ---
        opc = ttk.LabelFrame(self, text="Opções")
        opc.pack(fill="x", **pad)

        self.var_hash = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opc, text="Comparar conteúdo com hash SHA-256 (mais lento, mais seguro)",
            variable=self.var_hash,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=3)

        self.var_data = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opc, text="Tratar diferença de DATA como problema "
                      "(desligado: a data costuma mudar na cópia)",
            variable=self.var_data,
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=8, pady=3)

        ttk.Label(opc, text="Tolerância de data (s):").grid(row=2, column=0, sticky="w", padx=8, pady=3)
        self.var_tol = tk.StringVar(value="2")
        ttk.Spinbox(opc, from_=0, to=3600, width=8, textvariable=self.var_tol).grid(
            row=2, column=1, sticky="w")

        self.var_overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opc, text="Ao copiar: sobrescrever arquivos que existem no destino "
                      "com tamanho diferente",
            variable=self.var_overwrite,
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=8, pady=3)

        # --- Ações ---
        acoes = ttk.Frame(self)
        acoes.pack(fill="x", **pad)
        self.btn_comparar = ttk.Button(acoes, text="1) Analisar", command=self._iniciar_comparar)
        self.btn_comparar.pack(side="left")
        self.btn_copiar = ttk.Button(acoes, text="2) Copiar faltantes", command=self._iniciar_copiar)
        self.btn_copiar.pack(side="left", padx=6)
        self.btn_relatorio = ttk.Button(acoes, text="Gerar relatório...",
                                        command=self._gerar_relatorio, state="disabled")
        self.btn_relatorio.pack(side="left", padx=6)
        self.btn_cancelar = ttk.Button(acoes, text="Pausar", command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left")
        ttk.Button(acoes, text="Limpar log", command=self._limpar_log).pack(side="right")

        # --- Status + progresso GERAL ---
        self.var_status = tk.StringVar(value="Pronto.")
        ttk.Label(self, textvariable=self.var_status).pack(anchor="w", padx=10)
        self.barra = ttk.Progressbar(self, mode="determinate")
        self.barra.pack(fill="x", **pad)

        # --- Progresso do ARQUIVO ATUAL (só na cópia) ---
        self.var_arquivo = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.var_arquivo, anchor="w",
                  foreground="#57606a").pack(fill="x", padx=10)
        self.barra_arquivo = ttk.Progressbar(self, mode="determinate")
        self.barra_arquivo.pack(fill="x", padx=10, pady=(0, 4))

        self.txt = tk.Text(self, height=12, wrap="word", state="disabled",
                           font=("Consolas", 10))
        self.txt.pack(fill="both", expand=True, **pad)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _controles(self):
        return [self.e_origem, self.e_destino, self.b_origem, self.b_destino,
                self.btn_comparar, self.btn_copiar]

    def _escolher(self, var):
        inicial = var.get() if os.path.isdir(var.get()) else None
        pasta = filedialog.askdirectory(initialdir=inicial)
        if pasta:
            var.set(pasta)

    def _log(self, texto):
        self.txt.configure(state="normal")
        self.txt.insert("end", texto + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _limpar_log(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def _validar_pastas(self, exigir_destino_existente=True):
        origem = self.var_origem.get().strip().strip('"')
        destino = self.var_destino.get().strip().strip('"')
        if not os.path.isdir(origem):
            messagebox.showerror("Erro", "A pasta de ORIGEM não existe ou não foi informada.")
            return None
        if exigir_destino_existente:
            if not os.path.isdir(destino):
                messagebox.showerror("Erro", "A pasta de DESTINO não existe ou não foi informada.")
                return None
        else:
            if not destino:
                messagebox.showerror("Erro", "Informe a pasta de DESTINO.")
                return None
        if os.path.abspath(origem) == os.path.abspath(destino):
            messagebox.showerror("Erro", "Origem e destino não podem ser a mesma pasta.")
            return None
        return origem, destino

    def _tolerancia(self):
        try:
            return float(self.var_tol.get().replace(",", "."))
        except ValueError:
            return 2.0

    def _travar(self, rodando):
        self.rodando = rodando
        estado = "disabled" if rodando else "normal"
        for w in self._controles():
            w.configure(state=estado)
        self.btn_cancelar.configure(state="normal" if rodando else "disabled")
        # O botão de relatório só fica ativo se houver dados e nada rodando
        if not rodando and self.dados_comparacao is not None:
            self.btn_relatorio.configure(state="normal")
        else:
            self.btn_relatorio.configure(state="disabled")

    def _cancelar(self):
        self.evento_cancelar.set()
        self.var_status.set("Cancelando...")
        self.btn_cancelar.configure(state="disabled")

    def _ao_fechar(self):
        if self.rodando:
            if not messagebox.askyesno("Sair", "Há uma operação em andamento. Cancelar e sair?"):
                return
            self.evento_cancelar.set()
        self.destroy()

    # ------------------------------------------------------------------ #
    # Ação: COMPARAR
    # ------------------------------------------------------------------ #
    def _iniciar_comparar(self, copiar_depois=False, exigir_destino=True):
        v = self._validar_pastas(exigir_destino_existente=exigir_destino)
        if not v:
            return
        origem, destino = v
        self._copiar_apos_analise = copiar_depois
        self._rotulo_prog = "Comparando"
        self._t_inicio = None
        self.evento_cancelar.clear()
        self._travar(True)
        self.barra.configure(mode="indeterminate", value=0)
        self.barra.start(12)
        self.var_status.set("Lendo as pastas...")
        self._log("\n" + "=" * 70)
        self._log(f"COMPARAÇÃO  |  {dt.datetime.now():%d/%m/%Y %H:%M:%S}")
        self._log(f"Origem : {origem}")
        self._log(f"Destino: {destino}")
        self._log("Lendo e comparando (somente leitura)...")

        threading.Thread(
            target=self._worker_comparar,
            args=(origem, destino, self.var_hash.get(), self._tolerancia(),
                  self.var_data.get()),
            daemon=True,
        ).start()

    def _worker_comparar(self, origem, destino, usar_hash, tol, considerar_data):
        deve_cancelar = self.evento_cancelar.is_set

        def progresso(i, total):
            self.fila.put(("progresso", (i, total)))

        def progresso_scan(rotulo, qtd):
            self.fila.put(("scan", (rotulo, qtd)))

        try:
            dados = mcomp.comparar(
                origem, destino, usar_hash=usar_hash, tolerancia=tol,
                progresso=progresso, progresso_scan=progresso_scan,
                deve_cancelar=deve_cancelar, considerar_data=considerar_data,
            )
            self.fila.put(("fim_comparar", dados))
        except mcomp.Cancelado:
            self.fila.put(("cancelado", None))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("erro", str(e)))

    # ------------------------------------------------------------------ #
    # Ação: COPIAR (reaproveita a análise; reanalisa só se preciso)
    # ------------------------------------------------------------------ #
    def _cache_valido(self):
        """True se a análise guardada corresponde às pastas/opções atuais."""
        d = self.dados_comparacao
        if d is None:
            return False
        origem = os.path.abspath(self.var_origem.get().strip().strip('"'))
        destino = os.path.abspath(self.var_destino.get().strip().strip('"'))
        return (d["origem"] == origem and d["destino"] == destino
                and d["usar_hash"] == self.var_hash.get()
                and d["considerar_data"] == self.var_data.get()
                and d["tolerancia"] == self._tolerancia())

    def _iniciar_copiar(self):
        v = self._validar_pastas(exigir_destino_existente=False)
        if not v:
            return
        sobrescrever = self.var_overwrite.get()
        if not messagebox.askyesno(
            "Confirmar cópia",
            "Copiar para o destino apenas os arquivos que faltam?\n\n"
            "A ORIGEM não será alterada. "
            + ("Arquivos divergentes SERÃO sobrescritos."
               if sobrescrever else "Nada existente no destino será sobrescrito."),
        ):
            return

        if self._cache_valido():
            self._log("\n(Reaproveitando a análise já feita — sem reler as pastas.)")
            self._executar_copia()
        else:
            # Precisa analisar antes (pastas/opções mudaram ou nunca analisou).
            self._log("\n(As pastas/opções mudaram — fazendo a análise antes de copiar.)")
            self._iniciar_comparar(copiar_depois=True, exigir_destino=False)

    def _executar_copia(self):
        """Copia usando o resultado da análise guardada (sem nova varredura)."""
        dados = self.dados_comparacao
        overwrite = self.var_overwrite.get()
        self._rotulo_prog = "Copiando"
        self._t_inicio = None
        self.evento_cancelar.clear()
        self._travar(True)
        self.barra.configure(mode="indeterminate", value=0)
        self.barra.start(12)
        self.var_status.set("Preparando a cópia...")
        self._log("\n" + "=" * 70)
        self._log(f"CÓPIA  |  {dt.datetime.now():%d/%m/%Y %H:%M:%S}")
        self._log(f"Origem : {dados['origem']}")
        self._log(f"Destino: {dados['destino']}")
        self._log(f"Sobrescrever divergentes: {'SIM' if overwrite else 'NÃO'}")

        threading.Thread(
            target=self._worker_copia, args=(dados, overwrite), daemon=True,
        ).start()

    def _worker_copia(self, dados, overwrite):
        origem, destino = dados["origem"], dados["destino"]
        try:
            os.makedirs(destino, exist_ok=True)
            acoes, ignorados = mcopia.acoes_da_comparacao(dados, overwrite)
            total_bytes = sum(a["size"] or 0 for a in acoes)

            self.fila.put(("log", f"\nA copiar            : {len(acoes)} ({mcopia.human(total_bytes)})"))
            self.fila.put(("log", f"Ignorados           : {len(ignorados)}"))

            if ignorados:
                self.fila.put(("log", "-- IGNORADOS ----------------------------------"))
                for ig in ignorados:
                    self.fila.put(("log", f"  [x] {ig['rel']}  ->  {ig['motivo']}"))

            if not acoes:
                self.fila.put(("log", ">> Nada a copiar. Destino já contém tudo da origem."))
                resumo_copia = {
                    "data": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "origem": origem, "destino": destino,
                    "sobrescrever": overwrite,
                    "copiados": 0, "bytes": 0, "falhas": 0, "ignorados": len(ignorados),
                    "lista_copiados": [], "lista_falhas": [],
                    "lista_ignorados": ignorados,
                }
                self.fila.put(("fim_copiar", resumo_copia))
                return

            # Cópia real
            n = len(acoes)
            self.fila.put(("progresso", (0, n, 0, total_bytes)))
            ok, falhas, copiados = 0, [], []
            cancelado = False
            # estado compartilhado com o callback de progresso por bloco
            estado = {"base": 0, "i": 0, "t": 0.0}

            def on_bloco(bytes_do_arquivo):
                # atualiza no maximo ~7x por segundo para nao inundar a fila
                agora = time.monotonic()
                if agora - estado["t"] >= 0.15:
                    estado["t"] = agora
                    self.fila.put(("copia_prog",
                                   (estado["i"], n, estado["base"] + bytes_do_arquivo,
                                    total_bytes, bytes_do_arquivo)))

            for i, a in enumerate(acoes, 1):
                if self.evento_cancelar.is_set():
                    self.fila.put(("log", "\n>> PAUSADO pelo usuário."))
                    cancelado = True
                    break
                estado["i"] = i
                # informa qual arquivo está sendo copiado agora (barra do arquivo)
                self.fila.put(("arq_ini", (a["rel"], a["size"] or 0)))
                try:
                    mcopia.copy_one_progress(
                        a, callback=on_bloco,
                        deve_cancelar=self.evento_cancelar.is_set)
                    ok += 1
                    copiados.append({"rel": a["rel"], "size": a["size"], "motivo": a["motivo"]})
                    self.fila.put(("log", f"  [OK] {a['rel']}  ({mcopia.human(a['size'])})"))
                except mcopia.Cancelado:
                    self.fila.put(("log", "\n>> PAUSADO no meio de um arquivo (o parcial foi removido)."))
                    self.fila.put(("log", "   Rode \"Copiar faltantes\" de novo para continuar de onde parou."))
                    cancelado = True
                    break
                except Exception as e:  # noqa: BLE001
                    falhas.append((a["rel"], str(e)))
                    self.fila.put(("log", f"  [FALHA] {a['rel']}  ->  {e}"))
                estado["base"] += a["size"] or 0
                self.fila.put(("progresso", (i, n, estado["base"], total_bytes)))

            if cancelado:
                self.fila.put(("cancelado", None))
                return

            bytes_ok = sum(c["size"] or 0 for c in copiados)
            resumo_copia = {
                "data": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "origem": origem, "destino": destino,
                "sobrescrever": overwrite,
                "copiados": ok, "bytes": bytes_ok,
                "falhas": len(falhas), "ignorados": len(ignorados),
                "lista_copiados": copiados, "lista_falhas": falhas,
                "lista_ignorados": ignorados,
            }
            self.fila.put(("log", "\n" + "=" * 70))
            self.fila.put(("log", f"Copiados com sucesso: {ok}"))
            self.fila.put(("log", f"Falhas              : {len(falhas)}"))
            self.fila.put(("fim_copiar", resumo_copia))

        except mcopia.Cancelado:
            self.fila.put(("cancelado", None))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("erro", str(e)))

    # ------------------------------------------------------------------ #
    # Ação: GERAR RELATÓRIO (opcional)
    # ------------------------------------------------------------------ #
    def _gerar_relatorio(self):
        if self.dados_comparacao is None:
            messagebox.showinfo(
                "Relatório", "Faça a análise primeiro (botão \"Analisar\").")
            return
        formato = self._escolher_formato()
        if not formato:
            return
        if formato == "pdf" and not relatorio.pdf_disponivel():
            messagebox.showinfo(
                "PDF é opcional",
                "Esta é a versão leve do app, sem o gerador de PDF.\n\n"
                "Você pode gerar o relatório em HTML e, na tela do navegador, "
                "usar Imprimir → Salvar como PDF.\n\n"
                "Se precisar do PDF nativo, use a versão completa "
                "(FolderManagerWIN-PDF).")
            return

        ext = {"pdf": ".pdf", "csv": ".csv", "html": ".html"}[formato]
        tipos = {
            "pdf": [("PDF", "*.pdf")],
            "csv": [("CSV (Excel)", "*.csv")],
            "html": [("HTML", "*.html")],
        }[formato]
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório",
            defaultextension=ext,
            filetypes=tipos + [("Todos", "*.*")],
            initialfile=relatorio.nome_padrao(formato),
        )
        if not caminho:
            return
        try:
            relatorio.gerar(formato, caminho, self.dados_comparacao, self.resumo_copia)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro ao gerar relatório", str(e))
            return
        self._log(f"\nRelatório {formato.upper()} salvo em: {caminho}")
        if messagebox.askyesno("Relatório gerado", "Relatório salvo.\nDeseja abri-lo agora?"):
            webbrowser.open(f"file://{os.path.abspath(caminho)}")

    def _escolher_formato(self):
        """Caixa de diálogo simples para escolher PDF / CSV / HTML."""
        dlg = tk.Toplevel(self)
        dlg.title("Formato do relatório")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.grab_set()
        escolha = {"valor": None}

        ttk.Label(dlg, text="Em qual formato deseja gerar o relatório?",
                  padding=12).pack()
        tem_pdf = relatorio.pdf_disponivel()
        var = tk.StringVar(value="html")
        frm = ttk.Frame(dlg, padding=(16, 0))
        frm.pack(fill="x")
        ttk.Radiobutton(frm, text="HTML — interativo; dá para imprimir como PDF pelo navegador",
                        variable=var, value="html").pack(anchor="w", pady=2)
        ttk.Radiobutton(frm, text="CSV — abre no Excel, para tratar os dados",
                        variable=var, value="csv").pack(anchor="w", pady=2)
        pdf_txt = ("PDF — visual, para imprimir/arquivar" if tem_pdf
                   else "PDF — opcional (indisponível na versão leve)")
        rb_pdf = ttk.Radiobutton(frm, text=pdf_txt, variable=var, value="pdf")
        rb_pdf.pack(anchor="w", pady=2)
        if not tem_pdf:
            rb_pdf.configure(state="disabled")

        bar = ttk.Frame(dlg, padding=12)
        bar.pack(fill="x")

        def ok():
            escolha["valor"] = var.get()
            dlg.destroy()

        def cancelar():
            dlg.destroy()

        ttk.Button(bar, text="Gerar", command=ok).pack(side="right")
        ttk.Button(bar, text="Cancelar", command=cancelar).pack(side="right", padx=6)

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + 80
        dlg.geometry(f"+{max(x,0)}+{max(y,0)}")
        self.wait_window(dlg)
        return escolha["valor"]

    # ------------------------------------------------------------------ #
    # Fila thread -> interface
    # ------------------------------------------------------------------ #
    def _processar_fila(self):
        try:
            while True:
                tipo, conteudo = self.fila.get_nowait()
                if tipo == "scan":
                    rotulo, qtd = conteudo
                    self.var_status.set(f"Lendo {rotulo}... {qtd} arquivo(s) encontrados")
                elif tipo == "status":
                    self.var_status.set(conteudo)
                elif tipo == "log":
                    self._log(conteudo)
                elif tipo == "progresso":
                    if len(conteudo) == 4:
                        i, total, bdone, btotal = conteudo
                    else:
                        i, total = conteudo
                        bdone = btotal = None
                    self._atualizar_progresso(i, total, bdone, btotal)
                elif tipo == "arq_ini":
                    rel, size = conteudo
                    self._arq_rel = rel
                    self._arq_size = size or 0
                    self.var_arquivo.set(
                        f"Arquivo atual (0% — 0 B de {mcopia.human(self._arq_size)}): {rel}")
                    self.barra_arquivo.configure(maximum=max(self._arq_size, 1), value=0)
                elif tipo == "copia_prog":
                    i, total, gdone, gtotal, fdone = conteudo
                    self._atualizar_progresso(i, total, gdone, gtotal)
                    self.barra_arquivo.configure(value=min(fdone, max(self._arq_size, 1)))
                    fpct = (fdone / self._arq_size * 100) if self._arq_size else 100
                    self.var_arquivo.set(
                        f"Arquivo atual ({fpct:.0f}% — {mcopia.human(fdone)} de "
                        f"{mcopia.human(self._arq_size)}): {self._arq_rel}")
                elif tipo == "fim_comparar":
                    self._finalizar_comparar(conteudo)
                elif tipo == "fim_copiar":
                    self._finalizar_copiar(conteudo)
                elif tipo == "cancelado":
                    self._encerrar()
                    self.barra.configure(value=0)
                    self.var_status.set("Pausado. O que já foi copiado permanece; rode de novo para continuar.")
                    self._log("\n■ Operação interrompida pelo usuário.")
                elif tipo == "erro":
                    self._encerrar()
                    self.var_status.set("Erro durante a operação.")
                    self._log("ERRO: " + conteudo)
                    messagebox.showerror("Erro", conteudo)
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    @staticmethod
    def _fmt_tempo(seg):
        """Formata segundos como '45s', '2min 05s' ou '1h 12min'."""
        seg = int(max(0, seg))
        if seg < 60:
            return f"{seg}s"
        m, s = divmod(seg, 60)
        if m < 60:
            return f"{m}min {s:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}min"

    def _atualizar_progresso(self, feito, total, bytes_feitos=None, bytes_total=None):
        """Atualiza barra, porcentagem e tempo estimado a cada arquivo."""
        agora = time.monotonic()
        if str(self.barra["mode"]) == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
            self._t_inicio = agora  # começa a cronometrar o ETA aqui

        usa_bytes = bool(bytes_total)
        bf = bytes_feitos or 0

        # A barra e a porcentagem seguem os BYTES na cópia (movem dentro de um
        # arquivo grande) e a CONTAGEM na análise.
        if usa_bytes:
            self.barra.configure(maximum=max(bytes_total, 1), value=min(bf, bytes_total))
            fracao = bf / bytes_total
        else:
            if not total:
                return
            self.barra.configure(maximum=max(total, 1), value=feito)
            fracao = (feito / total) if total else 0
        pct = fracao * 100

        eta_txt = ""
        if self._t_inicio is not None and fracao > 0:
            decorrido = agora - self._t_inicio
            if decorrido > 0:
                restante = decorrido / fracao - decorrido
                eta_txt = f" — restam ~{self._fmt_tempo(restante)}"

        bytes_txt = ""
        if usa_bytes:
            bytes_txt = f" — {mcopia.human(bf)} de {mcopia.human(bytes_total)}"

        self.var_status.set(
            f"{self._rotulo_prog} {feito}/{total} — {pct:.0f}%{bytes_txt}{eta_txt}")

    def _encerrar(self):
        if str(self.barra["mode"]) == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
        # limpa a barra do arquivo atual
        self.var_arquivo.set("")
        self.barra_arquivo.configure(value=0)
        self._travar(False)

    def _finalizar_comparar(self, dados):
        self.dados_comparacao = dados
        cont = mcomp.resumo(dados["linhas"])
        criticos = mcomp.contar_criticos(dados["linhas"])
        total = len(dados["linhas"])

        self._log("\n=== RESUMO DA ANÁLISE ===")
        for st in ["OK", "FALTANDO", "TAMANHO_DIFERENTE", "HASH_DIFERENTE",
                   "EXTRA", "DATA_DIFERENTE", "ERRO_LEITURA"]:
            if st in cont:
                self._log(f"  {mcomp.ROTULOS[st]}: {cont[st]}")
        self._log(f"\nArquivos na origem : {dados['qtd_origem']}")
        self._log(f"Arquivos no destino: {dados['qtd_destino']}")
        self._log(f"Problemas críticos : {criticos}")
        faltando = cont.get("FALTANDO", 0)
        self._log(f"Faltando no destino (seriam copiados): {faltando}")

        # Encadeamento: se a análise foi disparada pelo botão "Copiar", segue
        # direto para a cópia, reaproveitando esta leitura.
        if self._copiar_apos_analise:
            self._copiar_apos_analise = False
            self._log("\n→ Reaproveitando esta análise para copiar...")
            self._executar_copia()
            return

        # Lista os arquivos por categoria (com destaque para TAMANHO DIFERENTE).
        self._log_detalhes(dados)

        self._encerrar()
        self.barra.configure(maximum=max(total, 1), value=max(total, 1))
        if criticos == 0:
            self.var_status.set("Análise concluída: cópia íntegra. (Relatório disponível.)")
            self._log("\n✔ Cópia íntegra: nenhum problema crítico encontrado.")
        else:
            self.var_status.set(f"Análise concluída: {criticos} problema(s) crítico(s). (Relatório disponível.)")
            self._log(f"\n✖ Atenção: {criticos} problema(s) crítico(s). Veja a lista acima ou gere o relatório.")
        self.btn_relatorio.configure(state="normal")

    def _log_detalhes(self, dados):
        """Lista, no log, os arquivos de cada categoria relevante da análise.

        Categorias 'críticas e geralmente poucas' (tamanho/conteúdo diferente,
        erro de leitura) saem por inteiro. FALTANDO e SOBRANDO, que costumam ser
        muitas, saem com um limite e um aviso de 'ver relatório'.
        """
        linhas = dados["linhas"]

        def tam(v):
            return mcomp.formatar_tamanho(v) if v != "" else "?"

        def listar(status, titulo, limite=None):
            itens = [l for l in linhas if l["status"] == status]
            if not itens:
                return
            self._log(f"\n-- {titulo} ({len(itens)}) " + "-" * 10)
            for l in (itens if limite is None else itens[:limite]):
                if status == "TAMANHO_DIFERENTE":
                    self._log(f"  • {l['caminho']}")
                    self._log(f"      origem {tam(l['tam_origem'])}  x  destino {tam(l['tam_destino'])}")
                elif status == "FALTANDO":
                    self._log(f"  • {l['caminho']}  ({tam(l['tam_origem'])})")
                elif status == "EXTRA":
                    self._log(f"  • {l['caminho']}  ({tam(l['tam_destino'])})")
                else:
                    self._log(f"  • {l['caminho']}  — {l['detalhe']}")
            if limite is not None and len(itens) > limite:
                self._log(f"  ... e mais {len(itens) - limite} "
                          f"(gere o relatório para a lista completa)")

        # Primeiro os que mais importam e costumam ser poucos:
        listar("TAMANHO_DIFERENTE", "ARQUIVOS COM TAMANHO DIFERENTE")
        listar("HASH_DIFERENTE", "ARQUIVOS COM CONTEÚDO DIFERENTE (hash)")
        listar("ERRO_LEITURA", "ARQUIVOS COM ERRO DE LEITURA")
        # Estes podem ser muitos: limita para não encher o log.
        listar("FALTANDO", "FALTANDO NO DESTINO", limite=100)
        listar("EXTRA", "SOBRANDO NO DESTINO", limite=100)

    def _finalizar_copiar(self, resumo_copia):
        self.resumo_copia = resumo_copia
        self._encerrar()
        self.var_status.set(
            f"Cópia concluída: {resumo_copia['copiados']} copiado(s), "
            f"{resumo_copia['falhas']} falha(s).")
        self._log(f"\n✔ Cópia finalizada. {resumo_copia['copiados']} arquivo(s) copiado(s).")
        # Habilita relatório se já houve comparação
        if self.dados_comparacao is not None:
            self.btn_relatorio.configure(state="normal")
            self._log("  (O relatório agora inclui também esta cópia.)")
        else:
            self._log("  Dica: rode \"Analisar\" para conferir e poder gerar o relatório completo.")


def main():
    app = App()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
