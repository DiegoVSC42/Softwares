"""
Comparador de Planilhas
========================
Programa com interface gráfica (Tkinter) para comparar duas planilhas
(CSV ou XLSX) e gerar uma terceira com o resultado de uma operação:

- União: todas as linhas da planilha A mais as linhas da planilha B que
  ainda não existem na A.
- Interseção: só as linhas que existem nas duas planilhas (com os dados
  vindos da planilha A).
- Remoção: as linhas da planilha A removendo as que também estão na
  planilha B. Opcionalmente, acrescenta as linhas exclusivas da B.

A comparação é feita por um ou mais critérios escolhidos pelo usuário,
cada um ligando uma coluna da planilha A a uma coluna da planilha B
(ex.: "E-mail" na A com "Email do contato" na B). As duas planilhas NÃO
precisam ter os mesmos cabeçalhos — o programa tenta parear colunas com
nomes iguais (ignorando acento/maiúsculas) automaticamente ao carregar,
mas qualquer par pode ser ajustado ou trocado manualmente.

Colunas de telefone podem ser marcadas com o tipo "Telefone (Brasil)":
antes de comparar, os números são normalizados (removendo formatação,
código do país e completando o 9º dígito de celulares) para que duas
planilhas com padrões de telefone diferentes ainda sejam comparadas
corretamente.
"""
import os
import re
import threading
import traceback
import unicodedata
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

APP_TITLE = "Comparador de Planilhas"
APP_VERSION = "1.1.0"
EXTENSOES = [
    ("Planilhas (CSV ou Excel)", "*.csv *.xlsx *.xlsm *.xls"),
    ("CSV", "*.csv"),
    ("Excel", "*.xlsx *.xlsm *.xls"),
    ("Todos os arquivos", "*.*"),
]
TIPO_TEXTO = "Texto"
TIPO_TELEFONE = "Telefone (Brasil)"
TIPOS_COLUNA = [TIPO_TEXTO, TIPO_TELEFONE]
PALAVRAS_TELEFONE = ("telefone", "fone", "celular", "whats", "tel", "contato")


# ------------------------------------------------------------------
# Núcleo de lógica (sem interface) — fácil de testar isoladamente.
# ------------------------------------------------------------------
def carregar_tabela(caminho):
    caminho_lower = caminho.lower()
    if caminho_lower.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(caminho, dtype=str)

    ultimo_erro = None
    for encoding in ("utf-8-sig", "utf-8", "latin1", "cp1252"):
        try:
            return pd.read_csv(caminho, sep=None, engine="python", dtype=str, encoding=encoding)
        except Exception as e:  # tenta o próximo encoding
            ultimo_erro = e
    raise ValueError(f"Não consegui ler o arquivo {os.path.basename(caminho)}: {ultimo_erro}")


def salvar_tabela(df, caminho):
    caminho_lower = caminho.lower()
    if caminho_lower.endswith((".xlsx", ".xlsm")):
        df.to_excel(caminho, index=False)
    else:
        df.to_csv(caminho, index=False, encoding="utf-8-sig")


def _sem_acento(texto):
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def _chave_nome_coluna(nome):
    return _sem_acento(str(nome)).strip().lower()


def parear_colunas_por_nome(colunas_a, colunas_b):
    """Sugere pares (coluna_de_A, coluna_de_B) casando nomes iguais, ignorando
    acento, maiúsculas/minúsculas e espaços nas pontas. As planilhas não
    precisam ter os mesmos cabeçalhos — isto é só um ponto de partida; o
    usuário pode trocar qualquer par na tela."""
    mapa_b = {}
    for cb in colunas_b:
        mapa_b.setdefault(_chave_nome_coluna(cb), cb)
    usados_b = set()
    pares = []
    for ca in colunas_a:
        cb = mapa_b.get(_chave_nome_coluna(ca))
        if cb is not None and cb not in usados_b:
            pares.append((ca, cb))
            usados_b.add(cb)
    return pares


def coluna_parece_telefone(nome_coluna):
    nome = _sem_acento(str(nome_coluna)).lower()
    return any(palavra in nome for palavra in PALAVRAS_TELEFONE)


def normalizar_numero_telefone(bruto, ddd_padrao=""):
    """Retorna (ddd, numero) já validados, ou (None, motivo)."""
    d = re.sub(r"\D", "", str(bruto))
    if not d:
        return None, "vazio"
    d = d.lstrip("0")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) in (8, 9):
        if not ddd_padrao:
            return None, "sem DDD"
        d = ddd_padrao + d
    if len(d) == 10:
        ddd, resto = d[:2], d[2:]
        if resto[0] in "6789":  # celular antigo sem o 9
            resto = "9" + resto
    elif len(d) == 11:
        ddd, resto = d[:2], d[2:]
    else:
        return None, f"quantidade de dígitos inválida ({len(d)})"
    if not (11 <= int(ddd) <= 99) or ddd[1] == "0":
        return None, f"DDD inválido ({ddd})"
    return ddd, resto


def normalizar_telefone_chave(bruto, ddd_padrao=""):
    """Chave de comparação para telefones, tolerante a formatos diferentes.

    Sempre que possível usa o número validado (ddd + número, com o 9º
    dígito completado). Quando não dá para validar (ex.: falta o DDD e
    nenhum DDD padrão foi informado), cai para os dígitos disponíveis, só
    tratando código do país e zeros à esquerda — assim a linha continua
    participando da comparação em vez de ser descartada.
    """
    ddd, resto = normalizar_numero_telefone(bruto, ddd_padrao)
    if ddd is not None:
        return ddd + resto
    d = re.sub(r"\D", "", str(bruto)).lstrip("0")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    return d


_MARCA_VAZIO = "\x00__vazio__\x00"


def _serie_normalizada(df, coluna, tipo, ddd_padrao, ignorar_caixa_espacos):
    serie = df[coluna].fillna("").astype(str)
    if tipo == TIPO_TELEFONE:
        valores = serie.apply(lambda v: normalizar_telefone_chave(v, ddd_padrao))
    elif ignorar_caixa_espacos:
        valores = serie.str.strip().str.lower()
    else:
        valores = serie

    # Linhas sem valor utilizável nesta coluna (célula vazia, ou telefone
    # sem nenhum dígito reconhecível) NUNCA devem contar como "iguais" só
    # por coincidirem em branco — cada uma vira uma sentinela única, para
    # não bater por acaso com outra linha vazia da outra planilha.
    vazio = valores.astype(str).str.strip() == ""
    if vazio.any():
        # id(df) distingue a planilha A da B (índices de linha se repetem entre
        # as duas, então só a posição não bastaria para evitar colisão).
        valores = valores.astype(str).copy()
        valores.loc[vazio] = [f"{_MARCA_VAZIO}{id(df)}:{coluna}:{i}" for i in valores.index[vazio]]
    return valores


def _chave_comparacao(df, criterios, lado, ddd_padrao="", ignorar_caixa_espacos=True):
    """criterios: lista de tuplas (coluna_em_A, coluna_em_B, tipo).
    lado: "a" ou "b" — escolhe, de cada critério, a coluna do lado certo,
    já que a coluna pode ter nomes diferentes nas duas planilhas."""
    series = []
    for col_a, col_b, tipo in criterios:
        coluna = col_a if lado == "a" else col_b
        series.append(_serie_normalizada(df, coluna, tipo, ddd_padrao, ignorar_caixa_espacos).astype(str))

    if not series:
        return pd.Series([""] * len(df), index=df.index)

    chave = series[0]
    for s in series[1:]:
        chave = chave.str.cat(s, sep="||")
    return chave


def op_uniao(df_a, df_b, criterios, ddd_padrao="", ignorar_caixa_espacos=True):
    chave_b = _chave_comparacao(df_b, criterios, "b", ddd_padrao, ignorar_caixa_espacos)
    chave_a_set = set(_chave_comparacao(df_a, criterios, "a", ddd_padrao, ignorar_caixa_espacos))
    somente_em_b = df_b[~chave_b.isin(chave_a_set)]
    return pd.concat([df_a, somente_em_b], ignore_index=True, sort=False)


def op_intersecao(df_a, df_b, criterios, ddd_padrao="", ignorar_caixa_espacos=True):
    chave_a = _chave_comparacao(df_a, criterios, "a", ddd_padrao, ignorar_caixa_espacos)
    chave_b_set = set(_chave_comparacao(df_b, criterios, "b", ddd_padrao, ignorar_caixa_espacos))
    return df_a[chave_a.isin(chave_b_set)].reset_index(drop=True)


def op_remocao(df_a, df_b, criterios, incluir_exclusivos_b=False, ddd_padrao="", ignorar_caixa_espacos=True):
    chave_a = _chave_comparacao(df_a, criterios, "a", ddd_padrao, ignorar_caixa_espacos)
    chave_b = _chave_comparacao(df_b, criterios, "b", ddd_padrao, ignorar_caixa_espacos)
    chave_b_set = set(chave_b)
    resultado = df_a[~chave_a.isin(chave_b_set)].reset_index(drop=True)
    if incluir_exclusivos_b:
        chave_a_set = set(chave_a)
        exclusivos_b = df_b[~chave_b.isin(chave_a_set)]
        resultado = pd.concat([resultado, exclusivos_b], ignore_index=True, sort=False)
    return resultado


def estatisticas(df_a, df_b, criterios, ddd_padrao="", ignorar_caixa_espacos=True):
    """Contagens usadas na pré-visualização, sem gerar a planilha inteira."""
    chave_a = _chave_comparacao(df_a, criterios, "a", ddd_padrao, ignorar_caixa_espacos)
    chave_b = _chave_comparacao(df_b, criterios, "b", ddd_padrao, ignorar_caixa_espacos)
    set_a = set(chave_a)
    set_b = set(chave_b)

    total_a = len(df_a)
    total_b = len(df_b)
    removidas_de_a = int(chave_a.isin(set_b).sum())  # linhas de A que tambem estao em B
    exclusivas_de_b = int((~chave_b.isin(set_a)).sum())  # linhas de B que nao estao em A

    restantes_apos_remocao = total_a - removidas_de_a

    return {
        "total_a": total_a,
        "total_b": total_b,
        "removidas_de_a": removidas_de_a,
        "restantes_apos_remocao": restantes_apos_remocao,
        "exclusivas_de_b": exclusivas_de_b,
        "uniao_total": total_a + exclusivas_de_b,
        "intersecao_total": removidas_de_a,
        "remocao_simples_total": restantes_apos_remocao,
        "remocao_com_exclusivos_total": restantes_apos_remocao + exclusivas_de_b,
    }


# ------------------------------------------------------------------
# Interface gráfica
# ------------------------------------------------------------------
class ComparadorApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("680x640")
        root.minsize(620, 480)

        self.caminho_a = tk.StringVar()
        self.caminho_b = tk.StringVar()
        self.operacao = tk.StringVar(value="uniao")
        self.incluir_exclusivos_b = tk.BooleanVar(value=False)
        self.ignorar_caixa_espacos = tk.BooleanVar(value=True)
        self.ddd_padrao = tk.StringVar(value="")
        self.status = tk.StringVar(value="Selecione as duas planilhas e clique em Carregar.")
        self.status.trace_add("write", self._atualizar_painel_status)

        self.df_a = None
        self.df_b = None
        self.criterios = []
        self.cancelar_flag = threading.Event()
        self.trabalhando = False

        self._montar_widgets()

    # ---------------- widgets ----------------
    # Ordem de empacotamento: primeiro tudo que é de tamanho fixo, ancorado no
    # rodapé (side="bottom") — assim essas partes NUNCA ficam escondidas
    # quando a janela é reduzida. A área de critérios é a única flexível
    # (side="top", expand=True) e é montada por último, ocupando só o espaço
    # que sobrar no meio.
    def _montar_widgets(self):
        pad = {"padx": 10, "pady": 6}

        # --- Rodapé (empacotado primeiro para garantir que fique no fundo
        # de verdade, abaixo de tudo, mesmo com os outros blocos ancorados
        # em side="bottom" descritos no comentário acima) ---
        ttk.Label(
            self.root, text=f"{APP_TITLE} • v{APP_VERSION}",
            foreground="#8b949e", font=("Segoe UI", 8), anchor="e",
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 4))

        # --- 1. Planilhas de entrada (fixo, topo) ---
        frame_arquivos = ttk.LabelFrame(self.root, text="1. Planilhas de entrada")
        frame_arquivos.pack(side="top", fill="x", **pad)

        self._linha_arquivo(frame_arquivos, "Planilha A:", self.caminho_a, self._escolher_a)
        self._linha_arquivo(frame_arquivos, "Planilha B:", self.caminho_b, self._escolher_b)

        btn_carregar = ttk.Button(frame_arquivos, text="Carregar planilhas", command=self._iniciar_carregamento)
        btn_carregar.pack(pady=(2, 8))
        self.btn_carregar = btn_carregar

        # --- painel de status/resultado (fixo, rodapé) ---
        frame_status = ttk.LabelFrame(self.root, text="Status")
        frame_status.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        self.txt_status = tk.Text(
            frame_status, height=6, wrap="word", state="disabled",
            bg="#f2f2f2", fg="#111111", relief="flat", padx=6, pady=4,
        )
        self.txt_status.pack(fill="x")

        # --- barra de progresso (fixo, rodapé) ---
        self.barra_progresso = ttk.Progressbar(self.root, mode="indeterminate")
        self.barra_progresso.pack(side="bottom", fill="x", padx=10, pady=(0, 4))

        # --- botões de ação (fixo, rodapé) ---
        frame_acao = ttk.Frame(self.root)
        frame_acao.pack(side="bottom", fill="x", **pad)

        self.btn_previa = ttk.Button(
            frame_acao, text="Pré-visualizar contagem", command=self._iniciar_previa, state="disabled"
        )
        self.btn_previa.pack(side="left")

        self.btn_processar = ttk.Button(
            frame_acao, text="Processar e salvar resultado...", command=self._iniciar_processamento, state="disabled"
        )
        self.btn_processar.pack(side="left", padx=8)

        self.btn_cancelar = ttk.Button(frame_acao, text="Cancelar", command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left")

        # --- 3. Operação (fixo, rodapé, acima dos botões de ação) ---
        frame_opcoes = ttk.LabelFrame(self.root, text="3. Operação")
        frame_opcoes.pack(side="bottom", fill="x", **pad)

        ttk.Radiobutton(
            frame_opcoes, text="União (A + o que for novo em B)", variable=self.operacao, value="uniao"
        ).pack(anchor="w", padx=6)
        ttk.Radiobutton(
            frame_opcoes, text="Interseção (só o que está nas duas)", variable=self.operacao, value="intersecao"
        ).pack(anchor="w", padx=6)
        ttk.Radiobutton(
            frame_opcoes,
            text="Remoção (A removendo o que está em B)",
            variable=self.operacao,
            value="remocao",
            command=self._atualizar_estado_checkbox_exclusivos,
        ).pack(anchor="w", padx=6)

        self.chk_exclusivos_b = ttk.Checkbutton(
            frame_opcoes,
            text="   Incluir também as linhas que só existem na planilha B",
            variable=self.incluir_exclusivos_b,
            state="disabled",
        )
        self.chk_exclusivos_b.pack(anchor="w", padx=6, pady=(0, 4))

        ttk.Checkbutton(
            frame_opcoes,
            text="Ignorar maiúsculas/minúsculas e espaços ao comparar (recomendado)",
            variable=self.ignorar_caixa_espacos,
        ).pack(anchor="w", padx=6, pady=(2, 2))

        linha_ddd = ttk.Frame(frame_opcoes)
        linha_ddd.pack(anchor="w", padx=6, pady=(0, 6))
        ttk.Label(linha_ddd, text="DDD padrão para telefones sem DDD (opcional):").pack(side="left")
        ttk.Entry(linha_ddd, textvariable=self.ddd_padrao, width=4).pack(side="left", padx=6)

        # --- 2. Critérios de comparação (única área flexível, ocupa o meio) ---
        frame_colunas = ttk.LabelFrame(
            self.root, text="2. Critérios de comparação (qual coluna da A corresponde a qual coluna da B)"
        )
        frame_colunas.pack(side="top", fill="both", expand=True, **pad)

        aviso = ttk.Label(
            frame_colunas,
            text=(
                "As planilhas não precisam ter o mesmo cabeçalho. Colunas com nomes iguais já vêm "
                "pareadas ao carregar; ajuste ou use \"+ Adicionar critério\" para mais colunas (ex.: "
                "nome e telefone juntos). Para telefone, use o tipo \"Telefone (Brasil)\"."
            ),
            wraplength=620,
        )
        aviso.pack(anchor="w", padx=6, pady=(4, 2))

        cabecalho = ttk.Frame(frame_colunas)
        cabecalho.pack(anchor="w", fill="x", padx=4, pady=(4, 0))
        ttk.Label(cabecalho, text="Coluna em A", width=20).pack(side="left")
        ttk.Label(cabecalho, text="", width=3).pack(side="left")
        ttk.Label(cabecalho, text="Coluna em B", width=20).pack(side="left")
        ttk.Label(cabecalho, text="Tipo", width=16).pack(side="left", padx=(8, 0))

        canvas = tk.Canvas(frame_colunas, borderwidth=0, highlightthickness=0, height=110)
        scrollbar = ttk.Scrollbar(frame_colunas, orient="vertical", command=canvas.yview)
        self.frame_criterios = ttk.Frame(canvas)
        self.frame_criterios.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.frame_criterios, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        scrollbar.pack(side="right", fill="y")

        self.btn_add_criterio = ttk.Button(
            frame_colunas, text="+ Adicionar critério", command=lambda: self._adicionar_criterio(), state="disabled"
        )
        self.btn_add_criterio.pack(anchor="w", padx=6, pady=(0, 6))

    def _atualizar_painel_status(self, *_args):
        texto = self.status.get()
        self.txt_status.configure(state="normal")
        self.txt_status.delete("1.0", "end")
        self.txt_status.insert("1.0", texto)
        self.txt_status.configure(state="disabled")

    def _linha_arquivo(self, parent, rotulo, variavel, comando):
        linha = ttk.Frame(parent)
        linha.pack(fill="x", padx=6, pady=2)
        ttk.Label(linha, text=rotulo, width=12).pack(side="left")
        ttk.Entry(linha, textvariable=variavel, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(linha, text="Procurar...", command=comando).pack(side="left")

    def _escolher_a(self):
        caminho = filedialog.askopenfilename(title="Selecione a planilha A", filetypes=EXTENSOES)
        if caminho:
            self.caminho_a.set(caminho)

    def _escolher_b(self):
        caminho = filedialog.askopenfilename(title="Selecione a planilha B", filetypes=EXTENSOES)
        if caminho:
            self.caminho_b.set(caminho)

    def _atualizar_estado_checkbox_exclusivos(self):
        if self.operacao.get() == "remocao":
            self.chk_exclusivos_b.configure(state="normal")
        else:
            self.chk_exclusivos_b.configure(state="disabled")

    # ---------------- critérios de comparação (coluna A <-> coluna B) ----------------
    def _adicionar_criterio(self, col_a_padrao="", col_b_padrao="", tipo_padrao=None):
        colunas_a = list(self.df_a.columns) if self.df_a is not None else []
        colunas_b = list(self.df_b.columns) if self.df_b is not None else []
        if tipo_padrao is None:
            base = col_a_padrao or col_b_padrao
            tipo_padrao = TIPO_TELEFONE if base and coluna_parece_telefone(base) else TIPO_TEXTO

        linha = ttk.Frame(self.frame_criterios)
        linha.pack(anchor="w", fill="x", padx=4, pady=2)

        col_a_var = tk.StringVar(value=col_a_padrao)
        col_b_var = tk.StringVar(value=col_b_padrao)
        tipo_var = tk.StringVar(value=tipo_padrao)

        ttk.Combobox(
            linha, textvariable=col_a_var, values=colunas_a, state="readonly", width=20
        ).pack(side="left")
        ttk.Label(linha, text=" ↔ ", width=3, anchor="center").pack(side="left")
        ttk.Combobox(
            linha, textvariable=col_b_var, values=colunas_b, state="readonly", width=20
        ).pack(side="left")
        ttk.Combobox(
            linha, textvariable=tipo_var, values=TIPOS_COLUNA, state="readonly", width=16
        ).pack(side="left", padx=(8, 0))

        item = {"frame": linha, "col_a": col_a_var, "col_b": col_b_var, "tipo": tipo_var}
        ttk.Button(
            linha, text="Remover", width=8, command=lambda: self._remover_criterio(item)
        ).pack(side="left", padx=(8, 0))

        self.criterios.append(item)
        return item

    def _remover_criterio(self, item):
        item["frame"].destroy()
        if item in self.criterios:
            self.criterios.remove(item)

    # ---------------- carregamento ----------------
    def _iniciar_carregamento(self):
        if self.trabalhando:
            return
        if not self.caminho_a.get() or not self.caminho_b.get():
            messagebox.showwarning(APP_TITLE, "Escolha as duas planilhas antes de carregar.")
            return

        self._travar_interface(True, cancelavel=True)
        self.status.set("Carregando planilhas...")
        self.barra_progresso.start(12)
        self.cancelar_flag.clear()
        threading.Thread(target=self._trabalho_carregar, daemon=True).start()

    def _trabalho_carregar(self):
        try:
            df_a = carregar_tabela(self.caminho_a.get())
            if self.cancelar_flag.is_set():
                self.root.after(0, self._carregamento_cancelado)
                return
            df_b = carregar_tabela(self.caminho_b.get())
            if self.cancelar_flag.is_set():
                self.root.after(0, self._carregamento_cancelado)
                return
            pares_sugeridos = parear_colunas_por_nome(list(df_a.columns), list(df_b.columns))
            self.root.after(0, self._carregamento_ok, df_a, df_b, pares_sugeridos)
        except Exception as e:
            traceback.print_exc()
            self.root.after(0, self._carregamento_erro, str(e))

    def _carregamento_cancelado(self):
        self.status.set("Carregamento cancelado.")
        self.barra_progresso.stop()
        self._travar_interface(False)

    def _carregamento_ok(self, df_a, df_b, pares_sugeridos):
        self.df_a, self.df_b = df_a, df_b
        self.barra_progresso.stop()
        self._travar_interface(False)

        for widget in self.frame_criterios.winfo_children():
            widget.destroy()
        self.criterios = []
        self.btn_add_criterio.configure(state="normal")

        if pares_sugeridos:
            for col_a, col_b in pares_sugeridos:
                self._adicionar_criterio(col_a, col_b)
            aviso_pares = f"{len(pares_sugeridos)} coluna(s) pareada(s) automaticamente pelo nome."
        else:
            self._adicionar_criterio()
            aviso_pares = (
                "Não encontrei colunas com nomes iguais nas duas planilhas. "
                "Escolha manualmente, na linha abaixo, qual coluna de A corresponde a qual coluna de B."
            )

        self.status.set(
            f"Carregado: A com {len(df_a)} linhas, B com {len(df_b)} linhas. "
            f"{aviso_pares} Confira os critérios e use Pré-visualizar contagem antes de processar."
        )

    def _carregamento_erro(self, mensagem):
        self.barra_progresso.stop()
        self._travar_interface(False)
        self.status.set("Erro ao carregar. Veja os detalhes na mensagem.")
        messagebox.showerror(APP_TITLE, f"Não consegui carregar as planilhas:\n\n{mensagem}")

    # ---------------- processamento ----------------
    def _coletar_criterios_e_ddd(self):
        """Lê os critérios e o DDD padrão da tela. Retorna (criterios, ddd_padrao)
        ou None se algo estiver faltando/errado (já mostra o aviso ao usuário)."""
        criterios = [
            (item["col_a"].get(), item["col_b"].get(), item["tipo"].get())
            for item in self.criterios
            if item["col_a"].get() and item["col_b"].get()
        ]
        if not criterios:
            messagebox.showwarning(
                APP_TITLE,
                "Adicione ao menos um critério completo, escolhendo a coluna de A e a coluna de B correspondente.",
            )
            return None

        ddd_padrao = self.ddd_padrao.get().strip()
        if ddd_padrao and not re.fullmatch(r"[1-9][1-9]", ddd_padrao):
            messagebox.showwarning(APP_TITLE, "O DDD padrão deve ter 2 dígitos (ex.: 62).")
            return None

        return criterios, ddd_padrao

    def _iniciar_previa(self):
        if self.trabalhando or self.df_a is None or self.df_b is None:
            return
        coletado = self._coletar_criterios_e_ddd()
        if coletado is None:
            return
        criterios, ddd_padrao = coletado

        self._travar_interface(True, cancelavel=False)
        self.status.set("Calculando a pré-visualização...")
        self.barra_progresso.start(12)
        threading.Thread(
            target=self._trabalho_previa, args=(criterios, ddd_padrao), daemon=True
        ).start()

    def _trabalho_previa(self, criterios, ddd_padrao):
        try:
            ignorar = self.ignorar_caixa_espacos.get()
            est = estatisticas(self.df_a, self.df_b, criterios, ddd_padrao, ignorar)
            self.root.after(0, self._previa_ok, est)
        except Exception as e:
            traceback.print_exc()
            self.root.after(0, self._processamento_erro, str(e))

    def _previa_ok(self, est):
        self.barra_progresso.stop()
        self._travar_interface(False)

        operacao = self.operacao.get()
        if operacao == "uniao":
            estimativa = f"Resultado estimado da União: {est['uniao_total']} linha(s)."
        elif operacao == "intersecao":
            estimativa = f"Resultado estimado da Interseção: {est['intersecao_total']} linha(s)."
        elif self.incluir_exclusivos_b.get():
            estimativa = f"Resultado estimado da Remoção (com exclusivos de B): {est['remocao_com_exclusivos_total']} linha(s)."
        else:
            estimativa = f"Resultado estimado da Remoção: {est['remocao_simples_total']} linha(s)."

        mensagem = (
            f"Pré-visualização — Planilha A: {est['total_a']} linha(s) | Planilha B: {est['total_b']} linha(s)\n\n"
            f"{est['removidas_de_a']} linha(s) de A também estão em B "
            f"→ seriam removidas na Remoção (A ficaria com {est['restantes_apos_remocao']} linha(s)).\n"
            f"{est['exclusivas_de_b']} linha(s) de B não estão em A "
            f"→ entram na União, ou na Remoção se marcar \"incluir exclusivos de B\".\n\n"
            f"{estimativa}"
        )
        self.status.set(mensagem)

    def _iniciar_processamento(self):
        if self.trabalhando or self.df_a is None or self.df_b is None:
            return

        coletado = self._coletar_criterios_e_ddd()
        if coletado is None:
            return
        criterios, ddd_padrao = coletado

        self._travar_interface(True, cancelavel=True)
        self.status.set("Processando...")
        self.barra_progresso.start(12)
        self.cancelar_flag.clear()
        threading.Thread(
            target=self._trabalho_processar, args=(criterios, ddd_padrao), daemon=True
        ).start()

    def _trabalho_processar(self, criterios, ddd_padrao):
        try:
            if self.cancelar_flag.is_set():
                self.root.after(0, self._processamento_cancelado)
                return

            operacao = self.operacao.get()
            ignorar = self.ignorar_caixa_espacos.get()

            if operacao == "uniao":
                resultado = op_uniao(self.df_a, self.df_b, criterios, ddd_padrao, ignorar)
            elif operacao == "intersecao":
                resultado = op_intersecao(self.df_a, self.df_b, criterios, ddd_padrao, ignorar)
            else:
                resultado = op_remocao(
                    self.df_a, self.df_b, criterios, self.incluir_exclusivos_b.get(), ddd_padrao, ignorar
                )

            if self.cancelar_flag.is_set():
                self.root.after(0, self._processamento_cancelado)
                return

            self.root.after(0, self._processamento_ok, resultado)
        except Exception as e:
            traceback.print_exc()
            self.root.after(0, self._processamento_erro, str(e))

    def _processamento_cancelado(self):
        self.status.set("Processamento cancelado.")
        self.barra_progresso.stop()
        self._travar_interface(False)

    def _processamento_ok(self, resultado):
        self.barra_progresso.stop()
        self._travar_interface(False)

        caminho_saida = filedialog.asksaveasfilename(
            title="Salvar resultado como",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not caminho_saida:
            self.status.set(
                f"Resultado pronto ({len(resultado)} linhas), mas não foi salvo. "
                "Clique em Processar novamente para salvar."
            )
            return

        try:
            salvar_tabela(resultado, caminho_saida)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Não consegui salvar o arquivo:\n\n{e}")
            return

        resumo_extra = ""
        if self.operacao.get() == "remocao" and not self.incluir_exclusivos_b.get():
            removidas = len(self.df_a) - len(resultado)
            resumo_extra = f" ({removidas} linha(s) removida(s) de A por estarem em B)"

        self.status.set(
            f"Pronto! A: {len(self.df_a)} linhas | B: {len(self.df_b)} linhas | "
            f"Resultado: {len(resultado)} linhas{resumo_extra}.\nSalvo em: {caminho_saida}"
        )
        messagebox.showinfo(
            APP_TITLE,
            f"Resultado salvo com sucesso!\n\n{len(resultado)} linha(s){resumo_extra} em:\n{caminho_saida}",
        )

    def _processamento_erro(self, mensagem):
        self.barra_progresso.stop()
        self._travar_interface(False)
        self.status.set("Erro ao processar. Veja os detalhes na mensagem.")
        messagebox.showerror(APP_TITLE, f"Não consegui processar as planilhas:\n\n{mensagem}")

    # ---------------- utilitários de interface ----------------
    def _cancelar(self):
        self.cancelar_flag.set()
        self.status.set("Cancelando...")

    def _travar_interface(self, travando, cancelavel=False):
        self.trabalhando = travando
        estado = "disabled" if travando else "normal"
        pronto = (not travando) and self.df_a is not None and self.df_b is not None
        self.btn_carregar.configure(state=estado)
        self.btn_processar.configure(state="normal" if pronto else "disabled")
        self.btn_previa.configure(state="normal" if pronto else "disabled")
        self.btn_cancelar.configure(state="normal" if (travando and cancelavel) else "disabled")


def main():
    root = tk.Tk()
    app = ComparadorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
