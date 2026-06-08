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
            text="Compare duas pastas (somente leitura) e copie os arquivos que "
                 "faltam no destino.\nO relatório é opcional: gere quando quiser, "
                 "em PDF, CSV ou HTML.",
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
        self.btn_comparar = ttk.Button(acoes, text="1) Comparar", command=self._iniciar_comparar)
        self.btn_comparar.pack(side="left")
        self.btn_verificar = ttk.Button(acoes, text="Simular cópia", command=self._iniciar_simular)
        self.btn_verificar.pack(side="left", padx=6)
        self.btn_copiar = ttk.Button(acoes, text="2) Copiar faltantes", command=self._iniciar_copiar)
        self.btn_copiar.pack(side="left")
        self.btn_relatorio = ttk.Button(acoes, text="Gerar relatório...",
                                        command=self._gerar_relatorio, state="disabled")
        self.btn_relatorio.pack(side="left", padx=6)
        self.btn_cancelar = ttk.Button(acoes, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left")
        ttk.Button(acoes, text="Limpar log", command=self._limpar_log).pack(side="right")

        # --- Status + progresso ---
        self.var_status = tk.StringVar(value="Pronto.")
        ttk.Label(self, textvariable=self.var_status).pack(anchor="w", padx=10)
        self.barra = ttk.Progressbar(self, mode="determinate")
        self.barra.pack(fill="x", **pad)

        self.txt = tk.Text(self, height=14, wrap="word", state="disabled",
                           font=("Consolas", 10))
        self.txt.pack(fill="both", expand=True, **pad)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _controles(self):
        return [self.e_origem, self.e_destino, self.b_origem, self.b_destino,
                self.btn_comparar, self.btn_verificar, self.btn_copiar]

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
    def _iniciar_comparar(self):
        v = self._validar_pastas(exigir_destino_existente=True)
        if not v:
            return
        origem, destino = v
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
    # Ação: SIMULAR / COPIAR
    # ------------------------------------------------------------------ #
    def _iniciar_simular(self):
        self._iniciar_copia(dry_run=True)

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
        self._iniciar_copia(dry_run=False)

    def _iniciar_copia(self, dry_run):
        v = self._validar_pastas(exigir_destino_existente=False)
        if not v:
            return
        origem, destino = v
        self.evento_cancelar.clear()
        self._travar(True)
        self.barra.configure(mode="indeterminate", value=0)
        self.barra.start(12)
        self.var_status.set("Analisando a origem...")
        self._log("\n" + "=" * 70)
        self._log(f"{'SIMULAÇÃO DE CÓPIA' if dry_run else 'CÓPIA'}  |  {dt.datetime.now():%d/%m/%Y %H:%M:%S}")
        self._log(f"Origem : {origem}")
        self._log(f"Destino: {destino}")
        self._log(f"Sobrescrever divergentes: {'SIM' if self.var_overwrite.get() else 'NÃO'}")

        threading.Thread(
            target=self._worker_copia,
            args=(origem, destino, self.var_overwrite.get(), dry_run),
            daemon=True,
        ).start()

    def _worker_copia(self, origem, destino, overwrite, dry_run):
        deve_cancelar = self.evento_cancelar.is_set
        contador = {"n": 0}

        def prog(rel):
            contador["n"] += 1
            if contador["n"] % 50 == 0:
                self.fila.put(("status", f"Analisando... {contador['n']} arquivos lidos"))

        try:
            os.makedirs(destino, exist_ok=True)
            acoes, ignorados = mcopia.build_plan(
                origem, destino, overwrite, progress_cb=prog, deve_cancelar=deve_cancelar)
            total_bytes = sum(a["size"] or 0 for a in acoes)

            self.fila.put(("log", f"\nArquivos analisados : {contador['n']}"))
            self.fila.put(("log", f"A copiar            : {len(acoes)} ({mcopia.human(total_bytes)})"))
            self.fila.put(("log", f"Ignorados           : {len(ignorados)}"))

            if ignorados:
                self.fila.put(("log", "-- IGNORADOS ----------------------------------"))
                for ig in ignorados:
                    self.fila.put(("log", f"  [x] {ig['rel']}  ->  {ig['motivo']}"))

            if dry_run:
                self.fila.put(("log", "-- SERIAM COPIADOS (simulação) ----------------"))
                for a in acoes:
                    self.fila.put(("log", f"  [+] {a['rel']}  ({mcopia.human(a['size'])})  | {a['motivo']}"))
                self.fila.put(("log", "\n>> Simulação concluída. Nenhum arquivo foi copiado."))
                self.fila.put(("fim_simular", len(acoes)))
                return

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
            self.fila.put(("progresso", (0, len(acoes))))
            ok, falhas, copiados = 0, [], []
            for i, a in enumerate(acoes, 1):
                if self.evento_cancelar.is_set():
                    self.fila.put(("log", "\n>> CANCELADO pelo usuário."))
                    break
                try:
                    mcopia.copy_one(a)
                    ok += 1
                    copiados.append({"rel": a["rel"], "size": a["size"], "motivo": a["motivo"]})
                    self.fila.put(("log", f"  [OK] {a['rel']}  ({mcopia.human(a['size'])})"))
                except Exception as e:  # noqa: BLE001
                    falhas.append((a["rel"], str(e)))
                    self.fila.put(("log", f"  [FALHA] {a['rel']}  ->  {e}"))
                self.fila.put(("progresso", (i, len(acoes))))
                self.fila.put(("status", f"Copiando... {i}/{len(acoes)}"))

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
                "Relatório", "Faça uma comparação primeiro (botão \"Comparar\").")
            return
        formato = self._escolher_formato()
        if not formato:
            return
        if formato == "pdf" and not relatorio.pdf_disponivel():
            messagebox.showerror(
                "PDF indisponível",
                "A biblioteca 'reportlab' não está instalada.\n\n"
                "Use o executável (que já inclui o PDF) ou instale com:\n"
                "    pip install reportlab\n\n"
                "Você ainda pode gerar o relatório em CSV ou HTML.")
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
        var = tk.StringVar(value="pdf")
        frm = ttk.Frame(dlg, padding=(16, 0))
        frm.pack(fill="x")
        ttk.Radiobutton(frm, text="PDF — visual, para imprimir/arquivar",
                        variable=var, value="pdf").pack(anchor="w", pady=2)
        ttk.Radiobutton(frm, text="CSV — abre no Excel, para tratar os dados",
                        variable=var, value="csv").pack(anchor="w", pady=2)
        ttk.Radiobutton(frm, text="HTML — interativo, filtros e busca na tela",
                        variable=var, value="html").pack(anchor="w", pady=2)

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
                    i, total = conteudo
                    if str(self.barra["mode"]) == "indeterminate":
                        self.barra.stop()
                        self.barra.configure(mode="determinate")
                    if total:
                        self.barra.configure(maximum=total, value=i)
                        self.var_status.set(f"Processando... {i} de {total}")
                elif tipo == "fim_comparar":
                    self._finalizar_comparar(conteudo)
                elif tipo == "fim_simular":
                    self._finalizar_simples(f"Simulação: {conteudo} arquivo(s) seriam copiados.")
                elif tipo == "fim_copiar":
                    self._finalizar_copiar(conteudo)
                elif tipo == "cancelado":
                    self._encerrar()
                    self.barra.configure(value=0)
                    self.var_status.set("Cancelado pelo usuário. Nada foi alterado.")
                    self._log("\n■ Operação cancelada.")
                elif tipo == "erro":
                    self._encerrar()
                    self.var_status.set("Erro durante a operação.")
                    self._log("ERRO: " + conteudo)
                    messagebox.showerror("Erro", conteudo)
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _encerrar(self):
        if str(self.barra["mode"]) == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
        self._travar(False)

    def _finalizar_simples(self, msg):
        self._encerrar()
        self.var_status.set(msg)

    def _finalizar_comparar(self, dados):
        self.dados_comparacao = dados
        cont = mcomp.resumo(dados["linhas"])
        criticos = mcomp.contar_criticos(dados["linhas"])
        total = len(dados["linhas"])
        self._encerrar()
        self.barra.configure(maximum=max(total, 1), value=max(total, 1))

        self._log("\n=== RESUMO DA COMPARAÇÃO ===")
        for st in ["OK", "FALTANDO", "TAMANHO_DIFERENTE", "HASH_DIFERENTE",
                   "EXTRA", "DATA_DIFERENTE", "ERRO_LEITURA"]:
            if st in cont:
                self._log(f"  {mcomp.ROTULOS[st]}: {cont[st]}")
        self._log(f"\nArquivos na origem : {dados['qtd_origem']}")
        self._log(f"Arquivos no destino: {dados['qtd_destino']}")
        self._log(f"Problemas críticos : {criticos}")

        if criticos == 0:
            self.var_status.set("Comparação concluída: cópia íntegra. (Relatório disponível.)")
            self._log("\n✔ Cópia íntegra: nenhum problema crítico encontrado.")
        else:
            self.var_status.set(f"Comparação concluída: {criticos} problema(s) crítico(s). (Relatório disponível.)")
            self._log(f"\n✖ Atenção: {criticos} problema(s) crítico(s). Gere o relatório para detalhes.")
        self.btn_relatorio.configure(state="normal")

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
            self._log("  Dica: rode \"Comparar\" para conferir e poder gerar o relatório completo.")


def main():
    app = App()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
