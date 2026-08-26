"""Paleta e estilo visual compartilhados pelo Estudio de Video.

Este arquivo existe para que as cinco abas tenham exatamente a mesma cara.
Antes, cada programa pintava a propria janela com o seu `_estilo()`; agora o
estilo e definido UMA vez, aqui, e vale para todas as abas.

Por que pintar tudo na mao: no macOS o tema nativo do Tk nao acompanha o modo
escuro do sistema. Ele desenha campos com fundo claro, e como o texto herda a
cor clara do sistema, o resultado e letra clara em fundo claro, ilegivel. O
tema 'clam' e o unico que aceita cor em todos os widgets.
"""

import sys
from tkinter import ttk

# Paleta escura ja validada no Mac (macOS Tahoe, modo escuro).
COR_FUNDO = "#0d1117"
COR_PAINEL = "#161b22"
COR_CAMPO = "#21262d"
COR_BOTAO = "#30363d"
COR_BOTAO_HOVER = "#3d444d"
COR_BORDA = "#3d444d"
COR_TEXTO = "#e6edf3"
COR_SUAVE = "#a8b3bf"
COR_APAGADO = "#6e7681"
COR_DESTAQUE = "#ff9d3d"

# Apelido antigo, mantido porque a aba de quadros chama a cor de moldura.
COR_MOLDURA = COR_DESTAQUE

COR_OK = "#3fb950"
COR_ERRO = "#f85149"


def fontes():
    """Devolve (fonte base, fonte de apoio) do sistema atual."""
    base = ("Helvetica", 13) if sys.platform == "darwin" else ("Segoe UI", 10)
    peq = (base[0], base[1] - 2)
    return base, peq


def aplicar_estilo(janela):
    """Aplica a paleta na janela inteira. Chamar uma vez, no inicio.

    `janela` e a janela principal (Tk). Os `option_add` precisam sair dela
    porque valem para a arvore inteira de widgets, inclusive os widgets Tk
    puros que o ttk cria por baixo (como a lista que abre no Combobox).
    """
    s = ttk.Style()
    try:
        s.theme_use("clam")
    except Exception:
        pass

    base, peq = fontes()
    janela.option_add("*Font", base)

    s.configure(".", background=COR_FUNDO, foreground=COR_TEXTO,
                fieldbackground=COR_CAMPO, font=base)
    s.configure("TFrame", background=COR_FUNDO)
    s.configure("Painel.TFrame", background=COR_PAINEL)
    s.configure("TLabel", background=COR_FUNDO, foreground=COR_TEXTO)
    s.configure("Suave.TLabel", background=COR_FUNDO, foreground=COR_SUAVE,
                font=peq)
    s.configure("Apagado.TLabel", background=COR_FUNDO, foreground=COR_APAGADO,
                font=peq)
    s.configure("Destaque.TLabel", background=COR_FUNDO,
                foreground=COR_DESTAQUE, font=peq)
    s.configure("Ok.TLabel", background=COR_FUNDO, foreground=COR_OK, font=peq)
    s.configure("Erro.TLabel", background=COR_FUNDO, foreground=COR_ERRO,
                font=peq)
    s.configure("Titulo.TLabel", background=COR_FUNDO, foreground=COR_TEXTO,
                font=(base[0], base[1] + 3, "bold"))

    s.configure("TLabelframe", background=COR_FUNDO, foreground=COR_TEXTO,
                bordercolor=COR_BORDA, darkcolor=COR_FUNDO,
                lightcolor=COR_FUNDO, relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=COR_FUNDO,
                foreground=COR_SUAVE, font=peq)

    s.configure("TButton", background=COR_BOTAO, foreground=COR_TEXTO,
                bordercolor=COR_BORDA, darkcolor=COR_BOTAO,
                lightcolor=COR_BOTAO, focuscolor=COR_BORDA,
                relief="flat", padding=(10, 6))
    s.map("TButton",
          background=[("disabled", COR_PAINEL),
                      ("pressed", COR_BORDA),
                      ("active", COR_BOTAO_HOVER)],
          foreground=[("disabled", COR_APAGADO)])

    # Botao principal de cada aba (o que dispara o trabalho).
    s.configure("Acao.TButton", background=COR_DESTAQUE, foreground="#1a1a1a",
                bordercolor=COR_DESTAQUE, darkcolor=COR_DESTAQUE,
                lightcolor=COR_DESTAQUE, relief="flat", padding=(14, 7))
    s.map("Acao.TButton",
          background=[("disabled", COR_PAINEL), ("active", "#ffb063")],
          foreground=[("disabled", COR_APAGADO)])

    s.configure("TEntry", fieldbackground=COR_CAMPO, foreground=COR_TEXTO,
                insertcolor=COR_TEXTO, bordercolor=COR_BORDA,
                lightcolor=COR_BORDA, darkcolor=COR_BORDA,
                selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
                padding=(6, 5))
    s.map("TEntry",
          fieldbackground=[("disabled", COR_PAINEL), ("readonly", COR_PAINEL)],
          foreground=[("disabled", COR_APAGADO)],
          bordercolor=[("focus", COR_DESTAQUE)],
          lightcolor=[("focus", COR_DESTAQUE)])

    s.configure("TCombobox", fieldbackground=COR_CAMPO, background=COR_BOTAO,
                foreground=COR_TEXTO, arrowcolor=COR_TEXTO,
                bordercolor=COR_BORDA, lightcolor=COR_BORDA,
                darkcolor=COR_BORDA, selectbackground=COR_CAMPO,
                selectforeground=COR_TEXTO, padding=(6, 5))
    s.map("TCombobox",
          fieldbackground=[("readonly", COR_CAMPO), ("disabled", COR_PAINEL)],
          foreground=[("disabled", COR_APAGADO)],
          selectbackground=[("readonly", COR_CAMPO)],
          selectforeground=[("readonly", COR_TEXTO)],
          bordercolor=[("focus", COR_DESTAQUE)],
          arrowcolor=[("disabled", COR_APAGADO)])

    s.configure("TCheckbutton", background=COR_FUNDO, foreground=COR_TEXTO,
                indicatorcolor=COR_CAMPO, focuscolor=COR_FUNDO)
    s.map("TCheckbutton",
          background=[("active", COR_FUNDO)],
          foreground=[("disabled", COR_APAGADO)],
          indicatorcolor=[("selected", COR_DESTAQUE),
                          ("disabled", COR_PAINEL)])

    s.configure("TRadiobutton", background=COR_FUNDO, foreground=COR_TEXTO,
                indicatorcolor=COR_CAMPO, focuscolor=COR_FUNDO)
    s.map("TRadiobutton",
          background=[("active", COR_FUNDO)],
          foreground=[("disabled", COR_APAGADO)],
          indicatorcolor=[("selected", COR_DESTAQUE),
                          ("disabled", COR_PAINEL)])

    s.configure("Horizontal.TScale", background=COR_FUNDO,
                troughcolor=COR_CAMPO, bordercolor=COR_BORDA,
                lightcolor=COR_DESTAQUE, darkcolor=COR_DESTAQUE)
    s.configure("Horizontal.TProgressbar", background=COR_DESTAQUE,
                troughcolor=COR_CAMPO, bordercolor=COR_BORDA,
                lightcolor=COR_DESTAQUE, darkcolor=COR_DESTAQUE)

    s.configure("TSeparator", background=COR_BORDA)

    s.configure("Treeview", background=COR_CAMPO, fieldbackground=COR_CAMPO,
                foreground=COR_TEXTO, bordercolor=COR_BORDA, relief="flat")
    s.map("Treeview",
          background=[("selected", COR_DESTAQUE)],
          foreground=[("selected", "#1a1a1a")])
    s.configure("Treeview.Heading", background=COR_BOTAO, foreground=COR_TEXTO,
                relief="flat", font=peq)
    s.map("Treeview.Heading", background=[("active", COR_BOTAO_HOVER)])

    # As abas do proprio Estudio.
    s.configure("TNotebook", background=COR_FUNDO, bordercolor=COR_BORDA,
                tabmargins=(10, 8, 10, 0))
    s.configure("TNotebook.Tab", background=COR_PAINEL, foreground=COR_SUAVE,
                bordercolor=COR_BORDA, lightcolor=COR_PAINEL,
                darkcolor=COR_PAINEL, padding=(16, 9), font=base)
    s.map("TNotebook.Tab",
          background=[("selected", COR_FUNDO), ("active", COR_BOTAO)],
          foreground=[("selected", COR_DESTAQUE), ("active", COR_TEXTO)],
          lightcolor=[("selected", COR_FUNDO)],
          expand=[("selected", (0, 0, 0, 2))])

    # Abas de dentro de uma aba (a de cortar tem duas). Ficam propositalmente
    # mais discretas que as abas do Estudio, para a pessoa nao confundir as
    # duas fileiras.
    s.configure("Interna.TNotebook", background=COR_FUNDO, borderwidth=0,
                tabmargins=(2, 4, 2, 0))
    s.configure("Interna.TNotebook.Tab", background=COR_FUNDO,
                foreground=COR_APAGADO, bordercolor=COR_FUNDO,
                lightcolor=COR_FUNDO, darkcolor=COR_FUNDO,
                padding=(12, 5), font=peq)
    s.map("Interna.TNotebook.Tab",
          background=[("selected", COR_CAMPO), ("active", COR_PAINEL)],
          foreground=[("selected", COR_TEXTO), ("active", COR_SUAVE)],
          lightcolor=[("selected", COR_CAMPO)],
          darkcolor=[("selected", COR_CAMPO)])

    # A lista que abre no Combobox e Tk puro, nao ttk: so muda por option_add.
    janela.option_add("*TCombobox*Listbox.background", COR_CAMPO)
    janela.option_add("*TCombobox*Listbox.foreground", COR_TEXTO)
    janela.option_add("*TCombobox*Listbox.selectBackground", COR_DESTAQUE)
    janela.option_add("*TCombobox*Listbox.selectForeground", "#1a1a1a")
    janela.option_add("*TCombobox*Listbox.font", base)

    return s
