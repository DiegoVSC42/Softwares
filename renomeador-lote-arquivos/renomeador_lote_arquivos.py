#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renomeador em Lote de Arquivos.

GUI em Tkinter para renomear todos os arquivos de uma pasta de uma vez:
adicionar prefixo, adicionar sufixo, remover texto do início/fim, remover
N caracteres do início/fim, localizar e substituir, numerar sequencialmente
e converter maiúsculas/minúsculas. Mostra prévia antes de aplicar e permite
desfazer a última operação.
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import atualizador  # atualizacao automatica

APP_VERSION = "1.4.2"
APP_NOME = "Renomeador em Lote de Arquivos"

_MAC = sys.platform == "darwin"

# Cores de status (usadas na prévia e na barra de status). Tons de meio-termo,
# nem muito escuros nem muito claros, para continuarem legíveis tanto em
# janelas claras quanto escuras.
COR_OK = "#1e8e3e"
COR_ERRO = "#d93025"
COR_ALERTA = "#c77b12"


class BotaoColorido(tk.Label):
    """Um rótulo clicável que funciona como botão colorido de verdade.

    No macOS, o tk.Button clássico ignora a cor de fundo enquanto está
    habilitado (limitação conhecida do Tk/Aqua — o botão nativo sempre volta
    a aparecer branco). Um Label não tem essa restrição, então simulamos o
    botão com clique, realce ao passar o mouse e aparência esmaecida quando
    desabilitado.
    """

    def __init__(self, pai, texto, comando, cor, cor_ativa, cor_desabilitada="#9e9e9e", **kw):
        cfg = {"text": texto, "bg": cor, "fg": "white", "padx": 14, "pady": 6,
               "relief": "flat", "disabledforeground": "#e0e0e0"}
        cfg.update(kw)
        super().__init__(pai, **cfg)
        self._comando = comando
        self._cor = cor
        self._cor_ativa = cor_ativa
        self._cor_desabilitada = cor_desabilitada
        self._cursor_ativo = "pointinghand" if _MAC else "hand2"
        super().config(cursor=self._cursor_ativo)
        self.bind("<Enter>", self._ao_entrar)
        self.bind("<Leave>", self._ao_sair)
        self.bind("<Button-1>", self._ao_clicar)

    def _habilitado(self):
        return str(self.cget("state")) != "disabled"

    def _ao_entrar(self, _evt):
        if self._habilitado():
            super().config(bg=self._cor_ativa)

    def _ao_sair(self, _evt):
        if self._habilitado():
            super().config(bg=self._cor)

    def _ao_clicar(self, _evt):
        if self._habilitado() and self._comando:
            self._comando()

    def config(self, **kw):
        estado = kw.get("state")
        if estado == "disabled":
            kw.setdefault("bg", self._cor_desabilitada)
            kw.setdefault("cursor", "arrow")
        elif estado == "normal":
            kw.setdefault("bg", self._cor)
            kw.setdefault("cursor", self._cursor_ativo)
        super().config(**kw)

    configure = config


def _resolver_cor_texto(root, candidata, alternativa):
    """No Mac, algumas cores do Tk (ex.: 'systemTextColor') acompanham
    sozinhas o modo claro/escuro do sistema. Testa se a versão do Tk em uso
    reconhece a cor; se não reconhecer, usa uma cor fixa como alternativa."""
    if not _MAC:
        return alternativa
    try:
        teste = tk.Label(root, fg=candidata)
        teste.destroy()
        return candidata
    except tk.TclError:
        return alternativa


# ---------------------------------------------------------------------------
# Lógica de renomeação (sem tocar em Tkinter, testável isoladamente)
# ---------------------------------------------------------------------------

def listar_arquivos(pasta, recursivo, extensoes):
    """Retorna lista de caminhos completos de arquivos, ordenada."""
    resultado = []
    if recursivo:
        for raiz, _dirs, arquivos in os.walk(pasta):
            for nome in arquivos:
                resultado.append(os.path.join(raiz, nome))
    else:
        with os.scandir(pasta) as it:
            for entrada in it:
                if entrada.is_file():
                    resultado.append(entrada.path)

    if extensoes:
        exts = {e.strip().lower() for e in extensoes.split(",") if e.strip()}
        exts = {e if e.startswith(".") else "." + e for e in exts}
        resultado = [p for p in resultado if Path(p).suffix.lower() in exts]

    resultado.sort()
    return resultado


def _nfc(texto):
    """Normaliza acentos para a forma composta (NFC).

    No Mac, o sistema de arquivos costuma devolver nomes com acento em forma
    decomposta (ex.: "o" + acento separado), enquanto o que a pessoa digita
    no campo vem em forma composta. Duas strings que parecem idênticas na
    tela podem não bater no `startswith`/`endswith`/`replace` por causa
    disso — por isso tudo passa por aqui antes de comparar.
    """
    return unicodedata.normalize("NFC", texto) if texto else texto


def aplicar_regras(nome_sem_ext, regras, indice):
    """Aplica as regras de renomeação a um nome (sem extensão) e devolve o novo nome."""
    nome = _nfc(nome_sem_ext)

    # 1) remover N caracteres do início/fim
    n_ini = regras.get("remover_n_inicio", 0)
    if n_ini > 0:
        nome = nome[n_ini:]
    n_fim = regras.get("remover_n_fim", 0)
    if n_fim > 0:
        nome = nome[: len(nome) - n_fim] if n_fim < len(nome) else ""

    # 2) remover texto exato do início/fim
    rem_ini = _nfc(regras.get("remover_texto_inicio", ""))
    if rem_ini and nome.startswith(rem_ini):
        nome = nome[len(rem_ini):]
    rem_fim = _nfc(regras.get("remover_texto_fim", ""))
    if rem_fim and nome.endswith(rem_fim):
        nome = nome[: len(nome) - len(rem_fim)]

    # 3) localizar e substituir
    localizar = _nfc(regras.get("localizar", ""))
    if localizar:
        nome = nome.replace(localizar, _nfc(regras.get("substituir", "")))

    # 4) conversão de caixa
    caixa = regras.get("caixa", "nenhum")
    if caixa == "maiusculas":
        nome = nome.upper()
    elif caixa == "minusculas":
        nome = nome.lower()
    elif caixa == "capitalizado":
        nome = nome.title()

    # 5) adicionar prefixo/sufixo
    prefixo = _nfc(regras.get("adicionar_prefixo", ""))
    sufixo = _nfc(regras.get("adicionar_sufixo", ""))
    nome = f"{prefixo}{nome}{sufixo}"

    # 6) numeração sequencial
    if regras.get("numerar", False):
        digitos = regras.get("numerar_digitos", 3)
        inicio = regras.get("numerar_inicio", 1)
        numero = str(inicio + indice).zfill(digitos)
        if regras.get("numerar_posicao", "fim") == "inicio":
            nome = f"{numero}_{nome}" if nome else numero
        else:
            nome = f"{nome}_{numero}" if nome else numero

    return nome.strip()


def gerar_plano(arquivos, regras):
    """Gera a lista de (caminho_antigo, caminho_novo, status, motivo)."""
    plano = []
    novos_nomes_por_pasta = {}

    for indice, caminho in enumerate(arquivos):
        pasta = os.path.dirname(caminho)
        nome_original = os.path.basename(caminho)
        base, ext = os.path.splitext(nome_original)

        novo_base = aplicar_regras(base, regras, indice)
        novo_nome = f"{novo_base}{ext}"
        novo_caminho = os.path.join(pasta, novo_nome)

        status = "ok"
        motivo = ""

        # aplicar_regras devolve o nome normalizado (NFC) — compara contra o
        # nome original também normalizado, senão um arquivo cujo nome no
        # disco esteja em outra forma de acentuação (comum no Mac) seria
        # marcado como "duplicado" dele mesmo mesmo sem nenhuma regra mudar
        # nada.
        if not novo_base:
            status = "erro"
            motivo = "nome ficaria vazio"
        elif novo_nome == _nfc(nome_original):
            status = "sem_alteracao"
            motivo = "nome não muda"
        else:
            chave = (pasta, novo_nome.lower())
            if chave in novos_nomes_por_pasta:
                status = "erro"
                motivo = "nome duplicado no lote"
            elif os.path.exists(novo_caminho) and os.path.normcase(novo_caminho) != os.path.normcase(caminho):
                status = "erro"
                motivo = "já existe um arquivo com esse nome"
            else:
                novos_nomes_por_pasta[chave] = caminho

        plano.append({
            "antigo": caminho,
            "novo": novo_caminho,
            "nome_antigo": nome_original,
            "nome_novo": novo_nome,
            "status": status,
            "motivo": motivo,
        })

    return plano


# ---------------------------------------------------------------------------
# Interface gráfica
# ---------------------------------------------------------------------------

class RenomeadorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NOME)
        self.root.geometry("1080x720")
        self.root.minsize(860, 560)

        # Cor de texto: no Mac acompanha o modo claro/escuro do sistema
        # sozinha; nas outras plataformas usa uma cor fixa de bom contraste.
        self.cor_texto = _resolver_cor_texto(self.root, "systemTextColor", "#1a1a1a")
        self.cor_texto_fraco = _resolver_cor_texto(self.root, "systemSecondaryLabelColor", "#666666")

        self.pasta = tk.StringVar()
        self.recursivo = tk.BooleanVar(value=False)
        self.extensoes = tk.StringVar()

        self.adicionar_prefixo = tk.StringVar()
        self.adicionar_sufixo = tk.StringVar()
        self.remover_texto_inicio = tk.StringVar()
        self.remover_texto_fim = tk.StringVar()
        self.remover_n_inicio = tk.IntVar(value=0)
        self.remover_n_fim = tk.IntVar(value=0)
        self.localizar = tk.StringVar()
        self.substituir = tk.StringVar()
        self.caixa = tk.StringVar(value="Nenhum")
        self.numerar = tk.BooleanVar(value=False)
        self.numerar_posicao = tk.StringVar(value="Fim")
        self.numerar_digitos = tk.IntVar(value=3)
        self.numerar_inicio = tk.IntVar(value=1)

        self.plano_atual = []
        self.ultima_operacao = []  # lista de (novo, antigo) para desfazer
        self.cancelado = False
        self.thread_ativa = None
        self._id_atualizacao_agendada = None

        self._montar_ui()

        # Atualiza a prévia sozinha sempre que uma regra muda (com uma pequena
        # espera, pra não recalcular a cada letra digitada) — assim não é
        # preciso lembrar de clicar em "Atualizar Prévia" toda vez.
        for var in (self.extensoes, self.adicionar_prefixo, self.adicionar_sufixo,
                    self.remover_texto_inicio, self.remover_texto_fim,
                    self.remover_n_inicio, self.remover_n_fim,
                    self.localizar, self.substituir, self.caixa,
                    self.numerar, self.numerar_posicao, self.numerar_digitos,
                    self.numerar_inicio):
            var.trace_add("write", self._agendar_previa)

    def _agendar_previa(self, *_args):
        if not self.pasta.get():
            return
        if self._id_atualizacao_agendada:
            self.root.after_cancel(self._id_atualizacao_agendada)
        self._id_atualizacao_agendada = self.root.after(400, self.atualizar_previa)

    # -- pequenos ajudantes de widget --------------------------------------------
    # Frames/LabelFrames/Entries ficam com a aparência nativa do sistema (sem cor
    # de fundo forçada), que já acompanha claro/escuro sozinha. Só o texto dos
    # rótulos recebe uma cor explícita, porque em alguns temas do Tk o texto
    # padrão fica escuro demais para ler sobre um fundo de janela escuro.

    def _label(self, pai, texto="", **kw):
        cfg = {"fg": self.cor_texto}
        cfg.update(kw)
        return tk.Label(pai, text=texto, **cfg)

    def _labelframe(self, pai, texto, **kw):
        cfg = {"fg": self.cor_texto}
        cfg.update(kw)
        return tk.LabelFrame(pai, text=texto, **cfg)

    def _checkbutton(self, pai, **kw):
        cfg = {"fg": self.cor_texto, "activeforeground": self.cor_texto,
               "selectcolor": "systemTextBackgroundColor" if _MAC else "white"}
        cfg.update(kw)
        return tk.Checkbutton(pai, **cfg)

    def _botao_colorido(self, pai, texto, cor, cor_ativa, command=None, state="normal", **kw):
        botao = BotaoColorido(pai, texto, command, cor, cor_ativa, **kw)
        if state != "normal":
            botao.config(state=state)
        return botao

    # -- construção da interface ------------------------------------------------

    def _montar_ui(self):
        pad = {"padx": 8, "pady": 4}

        # Rodapé (empacotado primeiro para garantir que fique no fundo)
        rodape = self._label(
            self.root,
            f"{APP_NOME} • v{APP_VERSION}",
            font=("Arial", 8),
            fg=self.cor_texto_fraco,
            anchor="e",
        )
        rodape.pack(side="bottom", fill="x", padx=8, pady=(0, 4))

        # Barra de status + progresso (também no fundo, acima do rodapé)
        barra_status = tk.Frame(self.root)
        barra_status.pack(side="bottom", fill="x")
        self.progresso = ttk.Progressbar(barra_status, mode="determinate")
        self.progresso.pack(side="left", fill="x", expand=True, padx=8, pady=4)
        self.label_status = self._label(barra_status, "Pronto", fg=self.cor_texto, anchor="w", width=34)
        self.label_status.pack(side="left", padx=8)

        # Botões de ação (fundo)
        frame_botoes = tk.Frame(self.root)
        frame_botoes.pack(side="bottom", fill="x", **pad)
        self._botao_colorido(frame_botoes, "Atualizar Prévia", "#2196F3", "#1976D2",
                              command=self.atualizar_previa).pack(side="left", padx=4)
        self.btn_aplicar = self._botao_colorido(frame_botoes, "Aplicar Renomeação", "#FF9800", "#F57C00",
                                                 command=self.aplicar)
        self.btn_aplicar.pack(side="left", padx=4)
        self.btn_desfazer = self._botao_colorido(frame_botoes, "Desfazer Última Operação", "#757575", "#616161",
                                                  command=self.desfazer, state="disabled")
        self.btn_desfazer.pack(side="left", padx=4)
        self.btn_cancelar = self._botao_colorido(frame_botoes, "Cancelar", "#e53935", "#c62828",
                                                  command=self.cancelar, state="disabled")
        self.btn_cancelar.pack(side="left", padx=4)

        # Topo: pasta
        frame_pasta = self._labelframe(self.root, "Pasta")
        frame_pasta.pack(side="top", fill="x", **pad)
        self._botao_colorido(frame_pasta, "Selecionar Pasta...", "#4CAF50", "#388E3C",
                              command=self.selecionar_pasta).pack(side="left", padx=6, pady=6)
        self._label(frame_pasta, textvariable=self.pasta, fg=self.cor_texto_fraco, anchor="w").pack(
            side="left", fill="x", expand=True, padx=6)
        self._checkbutton(frame_pasta, text="Incluir subpastas", variable=self.recursivo,
                           command=self.atualizar_previa).pack(side="left", padx=6)
        tk.Button(frame_pasta, text="Abrir pasta", command=self.abrir_pasta).pack(side="left", padx=6)

        self._label(self.root,
                    "Filtrar extensões (opcional, separadas por vírgula — ex.: .jpg,.png. Deixe em branco para renomear todos os arquivos.)",
                    anchor="w", fg=self.cor_texto_fraco).pack(side="top", fill="x", padx=10)
        entry_ext = tk.Entry(self.root, textvariable=self.extensoes)
        entry_ext.pack(side="top", fill="x", padx=10, pady=(0, 6))

        # Regras
        frame_regras = self._labelframe(self.root, "Regras de renomeação (todas opcionais — aplicadas na ordem abaixo, de cima para baixo)")
        frame_regras.pack(side="top", fill="x", padx=8, pady=4)

        def linha(label, widget_builder, row, col=0):
            self._label(frame_regras, label, anchor="w").grid(row=row, column=col, sticky="w", padx=6, pady=3)
            w = widget_builder(frame_regras)
            w.grid(row=row, column=col + 1, sticky="we", padx=6, pady=3)
            return w

        frame_regras.columnconfigure(1, weight=1)
        frame_regras.columnconfigure(3, weight=1)

        linha("1. Apagar do início estes caracteres:",
              lambda p: tk.Spinbox(p, from_=0, to=50, textvariable=self.remover_n_inicio, width=6),
              row=0)
        linha("2. Apagar do final estes caracteres:",
              lambda p: tk.Spinbox(p, from_=0, to=50, textvariable=self.remover_n_fim, width=6),
              row=0, col=2)

        linha("3. Remover este texto do início do nome:",
              lambda p: tk.Entry(p, textvariable=self.remover_texto_inicio),
              row=1)
        linha("4. Remover este texto do final do nome:",
              lambda p: tk.Entry(p, textvariable=self.remover_texto_fim),
              row=1, col=2)

        linha("5. Localizar este texto no nome:",
              lambda p: tk.Entry(p, textvariable=self.localizar),
              row=2)
        linha("   ...e substituir por:",
              lambda p: tk.Entry(p, textvariable=self.substituir),
              row=2, col=2)

        linha("6. Converter o nome para:",
              lambda p: ttk.Combobox(p, textvariable=self.caixa, state="readonly",
                                      values=["Nenhum", "MAIÚSCULAS", "minúsculas", "Capitalizado"]),
              row=3)

        linha("7. Adicionar este prefixo (no início):",
              lambda p: tk.Entry(p, textvariable=self.adicionar_prefixo),
              row=4)
        linha("8. Adicionar este sufixo (antes da extensão):",
              lambda p: tk.Entry(p, textvariable=self.adicionar_sufixo),
              row=4, col=2)

        frame_num = tk.Frame(frame_regras)
        frame_num.grid(row=5, column=0, columnspan=4, sticky="w", padx=6, pady=(6, 3))
        self._checkbutton(frame_num, text="9. Numerar em sequência (001, 002, 003...)",
                           variable=self.numerar).pack(side="left")
        self._label(frame_num, "posição do número:").pack(side="left", padx=(12, 2))
        ttk.Combobox(frame_num, textvariable=self.numerar_posicao, state="readonly",
                     values=["Início", "Fim"], width=8).pack(side="left")
        self._label(frame_num, "quantidade de dígitos:").pack(side="left", padx=(12, 2))
        tk.Spinbox(frame_num, from_=1, to=6, textvariable=self.numerar_digitos, width=4).pack(side="left")
        self._label(frame_num, "primeiro número:").pack(side="left", padx=(12, 2))
        tk.Spinbox(frame_num, from_=0, to=999999, textvariable=self.numerar_inicio, width=7).pack(side="left")

        # Prévia (Treeview)
        frame_previa = self._labelframe(self.root, "Prévia — confira antes de aplicar")
        frame_previa.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        colunas = ("status", "antigo", "novo")
        self.tree = ttk.Treeview(frame_previa, columns=colunas, show="headings")
        self.tree.heading("status", text="Status")
        self.tree.heading("antigo", text="Nome atual")
        self.tree.heading("novo", text="Nome novo")
        self.tree.column("status", width=170, anchor="w")
        self.tree.column("antigo", width=380, anchor="w")
        self.tree.column("novo", width=380, anchor="w")
        self.tree.tag_configure("erro", foreground=COR_ERRO)
        self.tree.tag_configure("sem_alteracao", foreground=self.cor_texto_fraco)
        self.tree.tag_configure("ok", foreground=COR_OK)

        scroll_y = ttk.Scrollbar(frame_previa, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

    # -- ações --------------------------------------------------------------

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os arquivos")
        if pasta:
            self.pasta.set(pasta)
            self.atualizar_previa()

    def abrir_pasta(self):
        pasta = self.pasta.get()
        if not pasta or not os.path.isdir(pasta):
            messagebox.showwarning(APP_NOME, "Selecione uma pasta válida primeiro.")
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", pasta])
            elif sys.platform.startswith("win"):
                os.startfile(pasta)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", pasta])
        except Exception as exc:
            messagebox.showerror(APP_NOME, f"Não consegui abrir a pasta:\n{exc}")

    def _coletar_regras(self):
        mapa_caixa = {
            "Nenhum": "nenhum",
            "MAIÚSCULAS": "maiusculas",
            "minúsculas": "minusculas",
            "Capitalizado": "capitalizado",
        }
        return {
            "remover_n_inicio": int(self.remover_n_inicio.get() or 0),
            "remover_n_fim": int(self.remover_n_fim.get() or 0),
            "remover_texto_inicio": self.remover_texto_inicio.get(),
            "remover_texto_fim": self.remover_texto_fim.get(),
            "localizar": self.localizar.get(),
            "substituir": self.substituir.get(),
            "caixa": mapa_caixa.get(self.caixa.get(), "nenhum"),
            "adicionar_prefixo": self.adicionar_prefixo.get(),
            "adicionar_sufixo": self.adicionar_sufixo.get(),
            "numerar": bool(self.numerar.get()),
            "numerar_posicao": "inicio" if self.numerar_posicao.get() == "Início" else "fim",
            "numerar_digitos": int(self.numerar_digitos.get() or 1),
            "numerar_inicio": int(self.numerar_inicio.get() or 0),
        }

    def atualizar_previa(self):
        pasta = self.pasta.get()
        if not pasta or not os.path.isdir(pasta):
            return

        try:
            arquivos = listar_arquivos(pasta, self.recursivo.get(), self.extensoes.get())
        except Exception as exc:
            messagebox.showerror(APP_NOME, f"Não consegui listar a pasta:\n{exc}")
            return

        regras = self._coletar_regras()
        self.plano_atual = gerar_plano(arquivos, regras)

        self.tree.delete(*self.tree.get_children())
        rotulos = {"ok": "será renomeado", "sem_alteracao": "sem alteração", "erro": "ERRO"}
        for item in self.plano_atual:
            rotulo = rotulos.get(item["status"], item["status"])
            if item["motivo"]:
                rotulo = f"{rotulo} ({item['motivo']})"
            self.tree.insert("", "end", values=(rotulo, item["nome_antigo"], item["nome_novo"]),
                              tags=(item["status"],))

        total = len(self.plano_atual)
        a_renomear = sum(1 for i in self.plano_atual if i["status"] == "ok")
        com_erro = sum(1 for i in self.plano_atual if i["status"] == "erro")
        self.label_status.config(
            text=f"{total} arquivo(s) — {a_renomear} a renomear, {com_erro} com erro",
            fg=COR_ERRO if com_erro else self.cor_texto,
        )

    def aplicar(self):
        if not self.plano_atual:
            messagebox.showinfo(APP_NOME, "Clique em 'Atualizar Prévia' primeiro.")
            return
        a_renomear = [i for i in self.plano_atual if i["status"] == "ok"]
        if not a_renomear:
            messagebox.showinfo(APP_NOME, "Não há nada para renomear com as regras atuais.")
            return

        if not messagebox.askyesno(
            APP_NOME,
            f"Confirma renomear {len(a_renomear)} arquivo(s)?\n\n"
            "Itens com erro na prévia serão ignorados.",
        ):
            return

        self.cancelado = False
        self.btn_aplicar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.btn_desfazer.config(state="disabled")
        self.progresso.config(maximum=len(a_renomear), value=0)

        self.thread_ativa = threading.Thread(target=self._aplicar_thread, args=(a_renomear,), daemon=True)
        self.thread_ativa.start()

    def _aplicar_thread(self, itens):
        feitos = []
        erros = []
        for indice, item in enumerate(itens, start=1):
            if self.cancelado:
                break
            try:
                os.rename(item["antigo"], item["novo"])
                feitos.append((item["novo"], item["antigo"]))
            except Exception as exc:
                erros.append(f"{item['nome_antigo']}: {exc}")
            self.root.after(0, self._atualizar_progresso, indice)

        self.root.after(0, self._finalizar_aplicacao, feitos, erros)

    def _atualizar_progresso(self, indice):
        self.progresso.config(value=indice)
        self.label_status.config(text=f"Renomeando... {indice}/{int(self.progresso['maximum'])}",
                                  fg=self.cor_texto)

    def _finalizar_aplicacao(self, feitos, erros):
        self.ultima_operacao = feitos
        self.btn_aplicar.config(state="normal")
        self.btn_cancelar.config(state="disabled")
        self.btn_desfazer.config(state="normal" if feitos else "disabled")

        if self.cancelado:
            self.label_status.config(text=f"Cancelado — {len(feitos)} arquivo(s) já renomeados", fg=COR_ALERTA)
        elif erros:
            self.label_status.config(text=f"Concluído com {len(erros)} erro(s)", fg=COR_ERRO)
            messagebox.showwarning(APP_NOME, "Alguns arquivos não puderam ser renomeados:\n\n" + "\n".join(erros))
        else:
            self.label_status.config(text=f"Concluído — {len(feitos)} arquivo(s) renomeados", fg=COR_OK)

        self.atualizar_previa()

    def desfazer(self):
        if not self.ultima_operacao:
            return
        if not messagebox.askyesno(APP_NOME, f"Desfazer a renomeação de {len(self.ultima_operacao)} arquivo(s)?"):
            return
        erros = []
        for novo, antigo in reversed(self.ultima_operacao):
            try:
                os.rename(novo, antigo)
            except Exception as exc:
                erros.append(f"{os.path.basename(novo)}: {exc}")
        self.ultima_operacao = []
        self.btn_desfazer.config(state="disabled")
        if erros:
            messagebox.showwarning(APP_NOME, "Alguns arquivos não puderam ser restaurados:\n\n" + "\n".join(erros))
        self.label_status.config(text="Desfeito", fg=COR_OK)
        self.atualizar_previa()

    def cancelar(self):
        self.cancelado = True
        self.btn_cancelar.config(state="disabled")


def main():
    root = tk.Tk()
    RenomeadorApp(root)
    atualizador.iniciar(root, "renomeador-lote-arquivos", APP_VERSION, "Renomeador em Lote")
    root.mainloop()


if __name__ == "__main__":
    main()
