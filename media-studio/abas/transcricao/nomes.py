"""Aba "Nomes de Rondonia" do Transcript Studio.

Listas de nomes com grafia conferida: candidatos de 2026 (nome de urna),
municipios e hospitais. Um clique no nome e ele vai para a area de
transferencia, pronto para colar na transcricao.

Esta aba nao cria janela nem define estilo: a janela e o estilo sao da
`transcript_studio.py`. Ela so desenha dentro do quadro que recebe.
"""

import subprocess
import tkinter as tk
from tkinter import ttk

import dados
import tema

EH_MAC = tema.EH_MAC


class Lista(ttk.Frame):
    """Uma lista clicavel. Clicou na linha, o nome esta copiado. As colunas
    mudam conforme a lista: candidato tem numero e partido, hospital tem
    municipio, cidade tem so o nome."""

    def __init__(self, pai, app, itens, colunas):
        super().__init__(pai, style="Painel.TFrame")
        self.app = app
        self.itens = itens
        self.colunas = colunas
        self.visiveis = []

        ids = [c[0] for c in colunas]
        self.tree = ttk.Treeview(self, columns=ids, show="headings",
                                 selectmode="browse", style="Escuro.Treeview")
        for cid, titulo, largura, estica in colunas:
            self.tree.heading(cid, text=titulo, anchor="w")
            # O minimo e metade do desejado para a coluna poder encolher
            # quando a janela esta bem estreita, em vez de sair da tela.
            self.tree.column(cid, width=largura, minwidth=max(44, largura // 2),
                             stretch=estica, anchor="w")

        # Listras alternadas: em lista longa, e o que evita o olho pular linha.
        self.tree.tag_configure("par", background=tema.COR_PAINEL)
        self.tree.tag_configure("impar", background=tema.COR_CAMPO)

        barra = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        # Um clique basta. Nada de duplo clique: o gesto tem que ser curto.
        self.tree.bind("<Button-1>", self._clicou)
        self.tree.bind("<Return>", lambda e: self._copiar_selecionado())

        self.filtrar("")

    def filtrar(self, termo):
        termo = dados.chave_alfabetica(termo.strip())
        if termo:
            self.visiveis = [
                it for it in self.itens
                if termo in dados.chave_alfabetica(" ".join(str(x) for x in it))
            ]
        else:
            self.visiveis = list(self.itens)

        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.visiveis):
            self.tree.insert("", "end", iid=str(i), values=item,
                             tags=("par" if i % 2 == 0 else "impar",))
        return len(self.visiveis)

    def _clicou(self, evento):
        if self.tree.identify_region(evento.x, evento.y) != "cell":
            return
        linha = self.tree.identify_row(evento.y)
        if not linha:
            return
        self.tree.selection_set(linha)
        self._copiar(int(linha))

    def _copiar_selecionado(self):
        sel = self.tree.selection()
        if sel:
            self._copiar(int(sel[0]))

    def _copiar(self, indice):
        if indice < len(self.visiveis):
            self.app.copiar(self.visiveis[indice])

    def copiar_primeiro(self):
        if self.visiveis:
            self.tree.selection_set("0")
            self.tree.see("0")
            self._copiar(0)


class AbaNomes:
    def __init__(self, pai):
        self.pai = pai
        self.raiz = pai.winfo_toplevel()
        self.rodando = False            # esta aba nunca fica ocupada
        self.com_detalhes = tk.BooleanVar(value=False)
        self.listas = {}
        self._apagar_status = None
        self._montar()

    # ------------------------------------------------------------------ tela

    def _montar(self):
        self.status = ttk.Label(self.pai, text="Clique num nome para copiar.",
                                style="Suave.TLabel", anchor="w")
        self.status.pack(side="bottom", fill="x", padx=12, pady=(6, 6))

        opcoes = ttk.Frame(self.pai)
        opcoes.pack(side="bottom", fill="x", padx=10, pady=(4, 0))
        ttk.Checkbutton(opcoes, text="Copiar com os detalhes ao lado do nome",
                        variable=self.com_detalhes).pack(side="left")

        topo = ttk.Frame(self.pai)
        topo.pack(side="top", fill="x", padx=10, pady=(12, 6))
        self.var_busca = tk.StringVar()
        self.campo = ttk.Entry(topo, textvariable=self.var_busca)
        self.campo.pack(side="left", fill="x", expand=True)
        self.var_busca.trace_add("write", lambda *a: self._buscou())
        self.campo.bind("<Return>", self._enter_na_busca)
        self.campo.bind("<Escape>", lambda e: self.var_busca.set(""))
        ttk.Button(topo, text="Limpar", width=7,
                   command=lambda: self.var_busca.set("")).pack(side="left",
                                                                padx=(6, 0))

        ttk.Label(self.pai,
                  text="Digite para filtrar. Enter copia o primeiro da lista.",
                  style="Suave.TLabel").pack(side="top", fill="x", padx=12,
                                             pady=(0, 8))

        self.abas = ttk.Notebook(self.pai)
        self.abas.pack(side="top", fill="both", expand=True, padx=8,
                       pady=(0, 4))
        self.abas.bind("<<NotebookTabChanged>>", lambda e: self._buscou())

        # --- Candidatos, com as sub-abas por cargo ---
        quadro = ttk.Frame(self.abas)
        self.abas.add(quadro, text="Candidatos")
        self.sub = ttk.Notebook(quadro)
        self.sub.pack(fill="both", expand=True, pady=(4, 0))
        self.sub.bind("<<NotebookTabChanged>>", lambda e: self._buscou())

        cols = [("nome", "Nome de urna", 190, True), ("num", "Nº", 58, False),
                ("part", "Partido", 96, False)]
        for chave, rotulo in (("governador", "Gov."), ("senador", "Sen."),
                              ("federal", "Dep. Fed."),
                              ("estadual", "Dep. Est.")):
            lista = Lista(self.sub, self, dados.candidatos(chave), cols)
            self.sub.add(lista, text=rotulo)
            self.listas[chave] = lista

        lista_cid = Lista(self.abas, self, [(c,) for c in dados.cidades()],
                          [("nome", "Município", 300, True)])
        self.abas.add(lista_cid, text="Cidades")
        self.listas["cidades"] = lista_cid

        lista_hosp = Lista(self.abas, self, dados.hospitais(),
                           [("nome", "Hospital", 232, True),
                            ("mun", "Município", 108, False)])
        self.abas.add(lista_hosp, text="Hospitais")
        self.listas["hospitais"] = lista_hosp

        self.campo.focus_set()

    # ---------------------------------------------------------- comportamento

    def _lista_ativa(self):
        aba = self.abas.tab(self.abas.select(), "text")
        if aba == "Cidades":
            return self.listas["cidades"]
        if aba == "Hospitais":
            return self.listas["hospitais"]
        return {"Gov.": self.listas["governador"],
                "Sen.": self.listas["senador"],
                "Dep. Fed.": self.listas["federal"],
                "Dep. Est.": self.listas["estadual"]}[
            self.sub.tab(self.sub.select(), "text")]

    def _buscou(self):
        # Enquanto a aba esta sendo montada ainda nao ha listas para consultar.
        if not getattr(self, "sub", None) or len(self.listas) < 6:
            return
        try:
            lista = self._lista_ativa()
        except tk.TclError:
            return
        quantos = lista.filtrar(self.var_busca.get())
        termo = self.var_busca.get().strip()
        if termo and quantos == 0:
            self._status("Nenhum nome encontrado.", tema.COR_DESTAQUE)
        elif termo:
            self._status("%d %s na busca." % (
                quantos, "nome" if quantos == 1 else "nomes"), tema.COR_SUAVE)
        else:
            self._status("%d nomes. Clique para copiar." % quantos,
                         tema.COR_SUAVE)

    def _enter_na_busca(self, evento):
        try:
            lista = self._lista_ativa()
        except Exception:
            return "break"
        lista.copiar_primeiro()
        return "break"

    def copiar(self, item):
        texto = item[0]
        if self.com_detalhes.get() and len(item) > 1:
            extras = [str(x) for x in item[1:] if str(x).strip()]
            if len(extras) >= 2:          # candidato: numero e partido
                texto = "%s (%s, %s)" % (item[0], extras[1], extras[0])
            elif extras:                  # hospital: municipio
                texto = "%s (%s)" % (item[0], extras[0])

        self.raiz.clipboard_clear()
        self.raiz.clipboard_append(texto)
        self.raiz.update()

        # No Mac, o Tk so entrega o texto quando outro programa pede, e se a
        # janela fechar antes disso a area de transferencia volta vazia. O
        # pbcopy grava de uma vez.
        if EH_MAC:
            try:
                subprocess.run(["pbcopy"], input=texto.encode("utf-8"),
                               check=False, timeout=2)
            except Exception:
                pass

        self._status("Copiado: %s" % texto, tema.COR_OK, some_em=4000)

    def _status(self, texto, cor, some_em=None):
        self.status.configure(
            text=texto,
            style="Ok.TLabel" if cor == tema.COR_OK else "Suave.TLabel")
        if self._apagar_status is not None:
            try:
                self.raiz.after_cancel(self._apagar_status)
            except Exception:
                pass
            self._apagar_status = None
        if some_em:
            def voltar():
                self._apagar_status = None
                self._buscou()
            self._apagar_status = self.raiz.after(some_em, voltar)

    def ao_fechar(self):
        if self._apagar_status is not None:
            try:
                self.raiz.after_cancel(self._apagar_status)
            except Exception:
                pass
            self._apagar_status = None


def montar(pai):
    return AbaNomes(pai)
