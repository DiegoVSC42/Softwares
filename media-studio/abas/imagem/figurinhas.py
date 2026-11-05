#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Normalizador de Figurinhas - aba do Estudio de Imagem.

Cada imagem (PNG ou GIF) ganha automaticamente um canvas do tamanho do seu
proprio conteudo, com uma margem pequena, e o conteudo fica centralizado.
Opcionalmente o canvas pode ser forcado a ficar quadrado (1:1, como o WhatsApp
pede) e o lado maior pode ser limitado a um numero de pixels.

GIF ANIMADO: a figurinha continua animada. Os quadros nao sao recortados um a
um -- se cada quadro fosse medido sozinho, o desenho ficaria pulando dentro do
canvas, porque cada quadro tem o seu proprio tamanho de conteudo. Em vez disso
mede-se a UNIAO do conteudo de todos os quadros, e esse mesmo recorte e esse
mesmo canvas sao aplicados a animacao inteira. Assim o movimento fica onde
estava, e so a moldura muda.

A extensao e preservada: PNG entra, PNG sai; GIF entra, GIF sai (com a mesma
duracao de quadro e o mesmo laco do original).

Esta tela nao cria janela nem define estilo: a janela e o estilo sao do
programa principal (`estudio_imagem.py` + `tema.py`).

A previa fica DENTRO da aba, sempre visivel, na coluna da direita. Antes ela
era uma janela separada que so abria com duplo clique na lista -- gesto que
ninguem adivinha. A janela foi removida: com o painel sempre a vista, ela so
somava um caminho a mais para o mesmo resultado.

A previa mostra o RESULTADO ja montado (margem aplicada, conteudo centralizado,
canvas quadrado e limite de lado quando marcados), usando exatamente a mesma
funcao `montar_figurinha()` do processamento em lote -- se usasse conta
propria, ela mentiria.

Nota de interface (macOS no modo escuro): o fundo atras da figurinha e um
xadrez desenhado no proprio PNG da previa, para a transparencia aparecer. NAO
se usa "stipple" no Canvas: o Tk do Mac ignora o stipple e pinta a area de
preto solido, tapando a imagem.
"""

import os
import platform
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageDraw, ImageSequence, ImageTk

import pastas
import tema
from tema import (COR_FUNDO, COR_PAINEL, COR_CAMPO, COR_BOTAO, COR_BORDA,
                  COR_TEXTO, COR_SUAVE, COR_APAGADO, COR_DESTAQUE, COR_OK,
                  COR_ERRO)

VERSION = "2.3.0"

APP_NAME = "Normalizador de Figurinhas"

# Extensoes aceitas na lista e na varredura de pasta.
EXTENSOES = (".png", ".gif")

# Duracao usada quando o GIF nao diz quanto tempo o quadro fica na tela.
DURACAO_PADRAO_MS = 100

# Teto de quadros que a PREVIA monta. E so para a previa nao comer memoria com
# um GIF muito longo; o arquivo salvo sai sempre com a animacao inteira.
PREVIA_MAX_QUADROS = 60

# Lado do quadro de previa, em pixels de tela. E um valor fixo (e nao "o que
# sobrar") para a coluna da direita nao mudar de largura a cada figurinha.
PREVIA_LADO = 292
# Folga entre a borda do quadro e a figurinha desenhada dentro dele.
PREVIA_FOLGA = 14
# Lado de cada quadradinho do xadrez de fundo.
XADREZ_LADO = 11


def _rgb(cor_hex):
    """Converte '#rrggbb' em (r, g, b), para pintar imagem do Pillow."""
    cor_hex = cor_hex.lstrip("#")
    return tuple(int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))


def _tabuleiro(largura, altura):
    """Xadrez, como o de editor de imagem, para a transparencia aparecer.

    O xadrez e desenhado no PNG da previa, e nao no Canvas do Tk, justamente
    para nao precisar de 'stipple' (que no Mac sai preto solido).
    """
    fundo = Image.new("RGBA", (largura, altura), _rgb(COR_CAMPO) + (255,))
    pincel = ImageDraw.Draw(fundo)
    claro = _rgb(COR_BOTAO) + (255,)
    for y in range(0, altura, XADREZ_LADO):
        for x in range(0, largura, XADREZ_LADO):
            if ((x // XADREZ_LADO) + (y // XADREZ_LADO)) % 2 == 0:
                pincel.rectangle([x, y, x + XADREZ_LADO - 1,
                                  y + XADREZ_LADO - 1], fill=claro)
    return fundo


def detectar_conteudo(img):
    """Retorna (x_min, y_min, x_max_excl, y_max_excl) da área não transparente."""
    array = np.array(img)
    alpha = array[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)

    if not rows.any() or not cols.any():
        return None

    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]
    return (int(x_min), int(y_min), int(x_max) + 1, int(y_max) + 1)


def detectar_conteudo_varios(quadros):
    """União do conteúdo de todos os quadros de uma animação.

    É a diferença entre uma figurinha animada que fica firme e uma que pula:
    medindo quadro a quadro, cada um teria um recorte diferente e o desenho
    dançaria dentro do canvas a cada troca de quadro.
    """
    caixas = [c for c in (detectar_conteudo(q) for q in quadros) if c]
    if not caixas:
        return None
    return (min(c[0] for c in caixas), min(c[1] for c in caixas),
            max(c[2] for c in caixas), max(c[3] for c in caixas))


def carregar_quadros(caminho):
    """Abre um PNG ou um GIF e devolve (quadros RGBA, durações ms, laço).

    Para GIF animado, o Pillow já entrega cada quadro composto com os
    anteriores, então `convert("RGBA")` dá o desenho completo daquele instante,
    e não só o pedacinho que mudou.
    """
    imagem = Image.open(caminho)
    n = getattr(imagem, "n_frames", 1)

    if n <= 1:
        return [imagem.convert("RGBA")], [DURACAO_PADRAO_MS], 0

    quadros = []
    duracoes = []
    for quadro in ImageSequence.Iterator(imagem):
        quadros.append(quadro.convert("RGBA"))
        duracoes.append(int(quadro.info.get("duration") or DURACAO_PADRAO_MS))
    laco = int(imagem.info.get("loop", 0) or 0)
    return quadros, duracoes, laco


def montar_figurinhas(quadros, margem_percent, forcar_quadrado, limite_lado):
    """
    Recorta a área preenchida e monta um canvas 'pouco maior' que o conteúdo,
    com o conteúdo centralizado. Recebe a LISTA de quadros (uma imagem parada
    é uma lista de um) e devolve (lista_de_canvas, info_dict).

    Esta é a ÚNICA conta de figurinha do arquivo: a prévia e o processamento
    em lote chamam as duas a mesma função, para o tamanho anunciado na tela
    ser exatamente o do arquivo que sai.
    """
    quadros = [q.convert("RGBA") for q in quadros]
    box = detectar_conteudo_varios(quadros)
    if box is None:
        raise ValueError("Imagem totalmente transparente (sem conteúdo detectável)")

    x0, y0, x1, y1 = box
    content_w = x1 - x0
    content_h = y1 - y0
    recortados = [q.crop((x0, y0, x1, y1)) for q in quadros]

    margem_px = round(max(content_w, content_h) * (margem_percent / 100))
    canvas_w = content_w + 2 * margem_px
    canvas_h = content_h + 2 * margem_px

    if forcar_quadrado:
        lado = max(canvas_w, canvas_h)
        canvas_w = canvas_h = lado

    escalado = False
    if limite_lado and max(canvas_w, canvas_h) > limite_lado:
        escala = limite_lado / max(canvas_w, canvas_h)
        canvas_w = max(1, round(canvas_w * escala))
        canvas_h = max(1, round(canvas_h * escala))
        novo_cw = max(1, round(recortados[0].width * escala))
        novo_ch = max(1, round(recortados[0].height * escala))
        recortados = [r.resize((novo_cw, novo_ch), Image.Resampling.LANCZOS)
                      for r in recortados]
        escalado = True

    finais = []
    for recorte in recortados:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        off_x = (canvas_w - recorte.width) // 2
        off_y = (canvas_h - recorte.height) // 2
        canvas.paste(recorte, (off_x, off_y), recorte)
        finais.append(canvas)

    info = {
        "content_w": content_w,
        "content_h": content_h,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "margem_px": margem_px,
        "escalado": escalado,
        "quadros": len(finais),
    }
    return finais, info


def montar_figurinha(img, margem_percent, forcar_quadrado, limite_lado):
    """Atalho de um quadro só, para quem já tinha esta função no código."""
    finais, info = montar_figurinhas([img], margem_percent, forcar_quadrado,
                                     limite_lado)
    return finais[0], info


def _rgba_para_palheta(img):
    """Converte um quadro RGBA na imagem de palheta que o GIF exige.

    O GIF não tem transparência graduada: ou o pixel aparece, ou não aparece.
    Por isso a palheta é montada com 255 cores (índices 0 a 254) e o índice
    255 fica reservado para "buraco", pintado onde o alfa é fraco.
    """
    transparente = img.getchannel("A").point(lambda a: 255 if a < 128 else 0)
    palheta = img.convert("RGB").quantize(colors=255,
                                          method=Image.Quantize.MEDIANCUT)
    palheta.paste(255, transparente)
    return palheta


def salvar_figurinha(finais, duracoes, laco, destino):
    """Grava a figurinha pronta. GIF sai GIF (animado ou não), PNG sai PNG."""
    destino = Path(destino)
    if destino.suffix.lower() == ".gif":
        palhetas = [_rgba_para_palheta(q) for q in finais]
        palhetas[0].save(
            destino, "GIF",
            save_all=True, append_images=palhetas[1:],
            duration=duracoes if len(duracoes) > 1 else duracoes[0],
            loop=laco, transparency=255, disposal=2, optimize=False)
    else:
        finais[0].save(destino, "PNG")


class NormalizadorFigurinhas:
    def __init__(self, pai):
        # `pai` e o quadro daquela aba. O resto do codigo continua chamando
        # `self.root`, para nao trocar o nome em todas as linhas.
        self.root = pai
        self.root.configure(bg=COR_FUNDO)

        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        # `rodando` e o que o programa principal olha antes de fechar.
        self.rodando = False
        self.cancel_event = threading.Event()
        self.files_selected = []
        self.fila = queue.Queue()

        self.margem_var = tk.DoubleVar(value=10.0)
        self.quadrado_var = tk.BooleanVar(value=False)
        self.limite_ativo_var = tk.BooleanVar(value=False)
        self.limite_var = tk.IntVar(value=512)
        self.progress_var = tk.IntVar(value=0)
        # Regra da casa: a saida comeca sempre na pasta de Downloads.
        self.pasta_saida = tk.StringVar(value=pastas.pasta_downloads())

        # ----- previa ao vivo -----
        # Uma unica thread trabalhadora que, ao terminar uma imagem, pega
        # sempre o pedido MAIS RECENTE e joga fora os do meio. Assim, se a
        # pessoa girar o controle de margem, a previa corre atras do valor
        # atual em vez de formar uma fila de imagens ja velhas.
        self.imagem_prev = None       # PhotoImage viva (sem isso o Tk descarta)
        self._prev_seq = 0
        self._prev_exibido = 0
        self._prev_pedido = None
        self._prev_evento = threading.Event()
        self._prev_lock = threading.Lock()
        self._prev_fim = False
        # (caminho, quadros RGBA, duracoes, laco) do ultimo arquivo aberto.
        self._prev_cache = (None, None, None, None)

        # ----- animacao da previa -----
        # Quando a figurinha e um GIF animado, a previa TAMBEM anda: e a unica
        # forma de a pessoa conferir se o desenho fica firme dentro do canvas
        # novo. Os quadros ja prontos ficam guardados aqui como PhotoImage, e
        # um `after` encadeado troca um pelo outro.
        self._anim_quadros = []
        self._anim_duracoes = []
        self._anim_indice = 0
        self._anim_after = None
        self._prev_thread = threading.Thread(target=self._worker_previa,
                                             daemon=True)
        self._prev_thread.start()

        self._build_ui()
        self.root.after(100, self._processar_fila)
        self._mostrar_aviso_previa("Escolha um PNG ou GIF para ver a prévia")

    # ---------- dialogos ----------

    def _janela(self):
        """Janela de verdade por tras da aba, para ancorar os dialogos."""
        return self.root.winfo_toplevel()

    # ---------- interface ----------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 3}

        # A ordem de empacotamento importa: tudo que fica ancorado embaixo e
        # empacotado PRIMEIRO, para nunca sair da tela quando a janela e baixa.
        # O corpo (lista + configuracoes + previa) vem por ultimo, com
        # expand=True, e e ele quem cede espaco quando falta altura.

        # --- Progresso e registro (bem no fundo da aba) ---
        progress_frame = ttk.LabelFrame(self.root, text=" Progresso ")
        progress_frame.pack(side="bottom", fill="x", **pad)

        self.progress_bar = ttk.Progressbar(progress_frame,
                                            variable=self.progress_var,
                                            style="Horizontal.TProgressbar",
                                            maximum=100)
        self.progress_bar.pack(fill="x", padx=6, pady=(6, 4))

        # Text e Tk puro: cada cor precisa ser dita na mao. A altura caiu de 7
        # para 4 linhas para abrir espaco ao painel de previa; o registro rola
        # sozinho, entao nada se perde.
        self.status_text = tk.Text(
            progress_frame, height=4, state="disabled", wrap="word",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightcolor=COR_BORDA,
            highlightthickness=0, relief="flat", borderwidth=0,
            font=self.fonte_peq)
        self.status_text.pack(fill="x", padx=6, pady=(0, 6))

        # --- Botoes de acao ---
        button_frame = ttk.Frame(self.root)
        button_frame.pack(side="bottom", fill="x", **pad)

        self.process_btn = ttk.Button(button_frame, text="Normalizar",
                                      style="Acao.TButton",
                                      command=self._start_processing)
        self.process_btn.pack(side="left")

        self.cancel_btn = ttk.Button(button_frame, text="Cancelar",
                                     command=self._cancel_processing,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=6)

        ttk.Button(button_frame, text="Limpar",
                   command=self._clear).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Abrir pasta de saída",
                   command=self._open_output).pack(side="left", padx=6)

        # --- Pasta de saida ---
        output_frame = ttk.LabelFrame(self.root, text=" Pasta de saída ")
        output_frame.pack(side="bottom", fill="x", **pad)
        linha_saida = ttk.Frame(output_frame)
        linha_saida.pack(fill="x", padx=6, pady=6)
        ttk.Entry(linha_saida, textvariable=self.pasta_saida).pack(
            side="left", fill="x", expand=True)
        ttk.Button(linha_saida, text="Escolher...",
                   command=self._select_output).pack(side="left", padx=(6, 0))

        # --- Corpo: duas colunas ---
        corpo = ttk.Frame(self.root)
        corpo.pack(side="top", fill="both", expand=True, padx=8, pady=(6, 0))

        esquerda = ttk.Frame(corpo)
        esquerda.pack(side="left", fill="both", expand=True)

        direita = ttk.Frame(corpo)
        direita.pack(side="left", fill="y", padx=(10, 0))

        self._montar_configuracoes(esquerda)
        self._montar_lista(esquerda)
        self._montar_previa(direita)

        # A previa reage a QUALQUER mudanca de opcao. A reacao fica presa na
        # VARIAVEL (`trace_add`), e nao no `command=` do Spinbox/Checkbutton:
        # o `command` so dispara quando a pessoa mexe naquele widget, entao
        # valor trocado por codigo (ao limpar a fila, por exemplo) passaria
        # despercebido e a previa mentiria.
        for var in (self.margem_var, self.quadrado_var,
                    self.limite_ativo_var, self.limite_var):
            var.trace_add("write", lambda *a: self._pedir_previa())

    def _montar_configuracoes(self, pai):
        config_frame = ttk.LabelFrame(pai, text=" Configurações ")
        config_frame.pack(side="bottom", fill="x", pady=(6, 0))

        margem_frame = ttk.Frame(config_frame)
        margem_frame.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(margem_frame, text="Margem ao redor do conteúdo:").pack(
            side="left", padx=(0, 6))
        ttk.Spinbox(margem_frame, from_=0, to=50, increment=1,
                    textvariable=self.margem_var, width=6).pack(side="left")
        ttk.Label(margem_frame, text="% do lado maior",
                  style="Suave.TLabel").pack(side="left", padx=(6, 0))

        ttk.Checkbutton(
            config_frame, variable=self.quadrado_var,
            text="Forçar canvas quadrado (1:1, como o WhatsApp pede)"
        ).pack(fill="x", padx=6, pady=2)

        limite_frame = ttk.Frame(config_frame)
        limite_frame.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Checkbutton(limite_frame, variable=self.limite_ativo_var,
                        text="Limitar o lado maior a").pack(side="left")
        ttk.Spinbox(limite_frame, from_=64, to=4096, increment=32,
                    textvariable=self.limite_var, width=6).pack(side="left",
                                                                padx=6)
        ttk.Label(limite_frame, text="px (reduz proporcionalmente)",
                  style="Suave.TLabel").pack(side="left")

    def _montar_lista(self, pai):
        file_frame = ttk.LabelFrame(pai, text=" Imagens a normalizar (PNG e GIF) ")
        file_frame.pack(side="top", fill="both", expand=True)

        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Button(btn_frame, text="Escolher imagens",
                   command=self._select_files).pack(side="left")
        ttk.Button(btn_frame, text="Escolher pasta",
                   command=self._select_folder).pack(side="left", padx=6)
        self.files_label = ttk.Label(btn_frame, text="Nenhum arquivo selecionado",
                                     style="Suave.TLabel")
        self.files_label.pack(side="right")

        ttk.Label(file_frame,
                  text="Clique num arquivo da lista para ver a prévia dele.",
                  style="Apagado.TLabel").pack(fill="x", padx=6, pady=(4, 0))

        # Listbox e Scrollbar sao Tk puro: nascem brancos se a cor nao for
        # dita aqui.
        moldura = tk.Frame(file_frame, bg=COR_BORDA, bd=0, highlightthickness=0)
        moldura.pack(fill="both", expand=True, padx=6, pady=6)
        self.listbox = tk.Listbox(
            moldura, height=5, activestyle="none", exportselection=False,
            bg=COR_CAMPO, fg=COR_TEXTO, font=self.fonte_peq,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightthickness=0,
            relief="flat", bd=0)
        rolo = tk.Scrollbar(moldura, orient="vertical",
                            command=self.listbox.yview,
                            bg=COR_BOTAO, troughcolor=COR_CAMPO,
                            activebackground=COR_BORDA,
                            highlightthickness=0, bd=0)
        self.listbox.configure(yscrollcommand=rolo.set)
        rolo.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        # Um clique simples ja troca a previa: e o gesto que a pessoa faz
        # naturalmente ao procurar um arquivo na lista.
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._pedir_previa())

    def _montar_previa(self, pai):
        previa_frame = ttk.LabelFrame(pai, text=" Prévia do resultado ")
        previa_frame.pack(fill="both", expand=True)

        # Canvas e Tk puro: a cor vai na mao, senao nasce branco.
        self.prev_canvas = tk.Canvas(
            previa_frame, width=PREVIA_LADO, height=PREVIA_LADO,
            bg=COR_CAMPO, highlightthickness=1, highlightbackground=COR_BORDA,
            bd=0, relief="flat", takefocus=0)
        self.prev_canvas.pack(padx=8, pady=(8, 6))

        # `wraplength` nos tres rotulos: sem ele, um nome de arquivo comprido
        # ou o aviso de "reduzido pelo limite" esticam a coluna da direita e a
        # tela inteira se remexe a cada troca de figurinha.
        self.lbl_prev_nome = ttk.Label(previa_frame, text="-",
                                       style="Suave.TLabel",
                                       wraplength=PREVIA_LADO)
        self.lbl_prev_nome.pack(anchor="w", padx=8)

        self.lbl_prev_tamanho = ttk.Label(previa_frame, text="",
                                          style="Destaque.TLabel",
                                          wraplength=PREVIA_LADO)
        self.lbl_prev_tamanho.pack(anchor="w", padx=8)

        self.lbl_prev_detalhe = ttk.Label(previa_frame, text="",
                                          style="Apagado.TLabel",
                                          wraplength=PREVIA_LADO)
        self.lbl_prev_detalhe.pack(anchor="w", padx=8, pady=(0, 8))

    # ---------- Seleção de arquivos ----------

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="Selecione as imagens (PNG ou GIF)",
            filetypes=[("Imagens (PNG e GIF)", "*.png *.gif"),
                       ("PNG", "*.png"), ("GIF", "*.gif"),
                       ("Todos os arquivos", "*.*")],
            parent=self._janela(),
        )
        if files:
            self.files_selected = list(files)
            self._update_file_label()
            self._update_listbox()
            self._pedir_previa()

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Escolher pasta com PNGs ou GIFs",
                                         parent=self._janela())
        if folder:
            achados = sorted(
                (f for f in Path(folder).iterdir()
                 if f.is_file() and f.suffix.lower() in EXTENSOES),
                key=lambda f: f.name.lower())
            if achados:
                self.files_selected = [str(f) for f in achados]
                self._update_file_label()
                self._update_listbox()
                self._pedir_previa()
            else:
                messagebox.showwarning("Aviso",
                                       "Nenhum PNG nem GIF encontrado nessa pasta.",
                                       parent=self._janela())

    def _update_file_label(self):
        count = len(self.files_selected)
        if count == 1:
            self.files_label.config(text="1 arquivo selecionado")
        else:
            self.files_label.config(text=f"{count} arquivos selecionados")

    def _update_listbox(self):
        self.listbox.delete(0, tk.END)
        for f in self.files_selected:
            self.listbox.insert(tk.END, Path(f).name)

    def _select_output(self):
        folder = filedialog.askdirectory(title="Escolher pasta de saída",
                                         parent=self._janela())
        if folder:
            self.pasta_saida.set(folder)

    def _clear(self):
        self.files_selected = []
        self.files_label.config(text="Nenhum arquivo selecionado")
        self.listbox.delete(0, tk.END)
        self.progress_var.set(0)
        self.status_text.config(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.config(state="disabled")
        self._pedir_previa()

    def _log(self, message):
        """Escreve no registro. So pode ser chamado do thread principal."""
        self.status_text.config(state="normal")
        self.status_text.insert("end", message + "\n")
        self.status_text.see("end")
        self.status_text.config(state="disabled")

    # ---------- Prévia ao vivo ----------

    def _opcoes_atuais(self):
        """Le as opcoes da tela, tolerando campo vazio ou meio digitado.

        Enquanto a pessoa apaga o numero do Spinbox para digitar outro, a
        variavel fica em estado invalido e `get()` levanta erro. Nesse instante
        vale mais manter o ultimo valor bom do que quebrar a previa.
        """
        try:
            margem = float(self.margem_var.get())
        except Exception:
            margem = 10.0
        try:
            limite = int(self.limite_var.get())
        except Exception:
            limite = 512
        return (margem, bool(self.quadrado_var.get()),
                limite if self.limite_ativo_var.get() else None)

    def _arquivo_da_previa(self):
        """A imagem que a previa deve mostrar: a selecionada, senao a primeira."""
        if not self.files_selected:
            return None
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.files_selected):
            return self.files_selected[sel[0]]
        return self.files_selected[0]

    def _pedir_previa(self):
        """Manda a thread montar a previa do estado ATUAL da tela.

        Roda sempre no thread principal (e o unico que pode ler widget). O
        pedido mais recente sempre vence: o worker descarta os do meio.
        """
        caminho = self._arquivo_da_previa()
        if not caminho:
            self._mostrar_aviso_previa("Escolha um PNG ou GIF para ver a prévia")
            return

        margem, quadrado, limite = self._opcoes_atuais()
        with self._prev_lock:
            self._prev_seq += 1
            self._prev_pedido = (caminho, margem, quadrado, limite,
                                 self._prev_seq)
        self._prev_evento.set()

    def _worker_previa(self):
        """Thread da previa: NAO toca em widget nenhum, so manda pela fila."""
        while True:
            self._prev_evento.wait()
            self._prev_evento.clear()
            if self._prev_fim:
                return
            with self._prev_lock:
                pedido = self._prev_pedido
                self._prev_pedido = None
            if not pedido:
                continue

            caminho, margem, quadrado, limite, seq = pedido
            try:
                origem, duracoes, _laco = self._abrir_para_previa(caminho)
                finais, info = montar_figurinhas(origem, margem, quadrado,
                                                 limite)

                # A previa nao monta um GIF longo inteiro: a animacao se repete
                # e ninguem confere quadro 300. O arquivo salvo, esse sim, sai
                # com tudo.
                finais = finais[:PREVIA_MAX_QUADROS]
                duracoes = list(duracoes[:PREVIA_MAX_QUADROS])
                while len(duracoes) < len(finais):
                    duracoes.append(DURACAO_PADRAO_MS)

                # A miniatura e so para a tela; o tamanho ANUNCIADO vem do
                # `info`, que e o tamanho real do arquivo que vai ser salvo.
                caixa = PREVIA_LADO - 2 * PREVIA_FOLGA
                primeiro = finais[0]
                escala = min(caixa / primeiro.width, caixa / primeiro.height)
                larg = max(1, int(round(primeiro.width * escala)))
                alt = max(1, int(round(primeiro.height * escala)))
                px = (PREVIA_LADO - larg) // 2
                py = (PREVIA_LADO - alt) // 2
                xadrez = _tabuleiro(larg, alt)

                telas = []
                for final in finais:
                    mini = final.resize((larg, alt), Image.Resampling.LANCZOS)
                    # O xadrez cobre SO a area da figurinha; em volta fica o
                    # fundo liso do tema. Assim a pessoa ve de imediato onde o
                    # quadro final comeca e termina, e o xadrez nao insinua
                    # transparencia onde nao ha figurinha nenhuma.
                    fundo = Image.new("RGBA", (PREVIA_LADO, PREVIA_LADO),
                                      _rgb(COR_PAINEL) + (255,))
                    fundo.paste(xadrez, (px, py))
                    fundo.paste(mini, (px, py), mini)
                    telas.append(fundo)

                texto = (f"Vai sair {info['canvas_w']} x "
                         f"{info['canvas_h']} px")
                detalhe = (f"Desenho de {info['content_w']}×{info['content_h']}px "
                           f"+ {info['margem_px']}px de margem por lado")
                if info["escalado"]:
                    detalhe += " (reduzido pelo limite)"
                if info["quadros"] > 1:
                    detalhe += f" · GIF animado, {info['quadros']} quadros"

                self.fila.put(("previa", (seq, Path(caminho).name, telas,
                                          duracoes, (px, py, larg, alt),
                                          texto, detalhe)))
            except Exception as e:
                self.fila.put(("previa_erro",
                               (seq, Path(caminho).name, str(e))))

            if self._prev_fim:
                return

    def _abrir_para_previa(self, caminho):
        """Abre a imagem, guardando a ultima aberta.

        Mexer na margem ou no limite nao muda o arquivo: sem esta memoria, cada
        toque no controle mandaria o Pillow decodificar tudo de novo, o que
        pesa em imagem grande -- e muito mais num GIF de dezenas de quadros.
        """
        antigo, quadros, duracoes, laco = self._prev_cache
        if antigo == caminho and quadros:
            return quadros, duracoes, laco
        quadros, duracoes, laco = carregar_quadros(caminho)
        self._prev_cache = (caminho, quadros, duracoes, laco)
        return quadros, duracoes, laco

    def _parar_animacao(self):
        """Interrompe o laco da previa e solta os quadros guardados."""
        if self._anim_after is not None:
            try:
                self.root.after_cancel(self._anim_after)
            except Exception:
                pass
            self._anim_after = None
        self._anim_quadros = []
        self._anim_duracoes = []
        self._anim_indice = 0

    def _proximo_quadro(self):
        """Troca o quadro na tela e agenda o seguinte. Thread principal."""
        self._anim_after = None
        if len(self._anim_quadros) < 2:
            return
        self._anim_indice = (self._anim_indice + 1) % len(self._anim_quadros)
        self.imagem_prev = self._anim_quadros[self._anim_indice]
        self.prev_canvas.itemconfigure("figurinha", image=self.imagem_prev)
        espera = max(20, int(self._anim_duracoes[self._anim_indice]))
        self._anim_after = self.root.after(espera, self._proximo_quadro)

    def _mostrar_aviso_previa(self, texto):
        """Quadro de previa vazio, com um recado curto no meio."""
        self._parar_animacao()
        self.prev_canvas.delete("all")
        self.imagem_prev = None
        self.prev_canvas.create_text(
            PREVIA_LADO / 2, PREVIA_LADO / 2, width=PREVIA_LADO - 40,
            justify="center", text=texto, fill=COR_SUAVE,
            font=self.fonte_peq)
        self.lbl_prev_nome.config(text="-")
        self.lbl_prev_tamanho.config(text="")
        self.lbl_prev_detalhe.config(text="")

    def _mostrar_previa(self, seq, nome, telas, duracoes, retangulo, texto,
                        detalhe):
        """Poe a previa na tela. So roda no thread principal."""
        if seq <= self._prev_exibido:
            return                      # chegou atrasada: ja tem coisa melhor
        self._prev_exibido = seq

        self._parar_animacao()

        # As referencias FICAM num atributo: se morrerem, o Tk descarta as
        # imagens e o quadro fica preto. E o erro classico do PhotoImage.
        self._anim_quadros = [ImageTk.PhotoImage(t) for t in telas]
        self._anim_duracoes = list(duracoes)
        self._anim_indice = 0
        self.imagem_prev = self._anim_quadros[0]

        self.prev_canvas.delete("all")
        self.prev_canvas.create_image(0, 0, image=self.imagem_prev,
                                      anchor="nw", tags="figurinha")
        if len(self._anim_quadros) > 1:
            espera = max(20, int(self._anim_duracoes[0]))
            self._anim_after = self.root.after(espera, self._proximo_quadro)

        # Contorno do canvas final, para ficar claro onde a figurinha comeca e
        # termina -- inclusive a margem transparente em volta do desenho.
        x, y, larg, alt = retangulo
        self.prev_canvas.create_rectangle(x, y, x + larg - 1, y + alt - 1,
                                          outline=COR_DESTAQUE, width=2)

        self.lbl_prev_nome.config(text=nome)
        self.lbl_prev_tamanho.config(text=texto)
        self.lbl_prev_detalhe.config(text=detalhe)

    def _falhou_previa(self, seq, nome, erro):
        if seq <= self._prev_exibido:
            return
        self._prev_exibido = seq
        self._mostrar_aviso_previa("Não consegui montar a prévia desta imagem.")
        self.lbl_prev_nome.config(text=nome)
        self.lbl_prev_detalhe.config(text=erro[:120])

    # ---------- Processamento ----------

    def _start_processing(self):
        if self.rodando:
            return
        if not self.files_selected:
            messagebox.showwarning("Aviso",
                                   "Selecione pelo menos uma imagem (PNG ou GIF).",
                                   parent=self._janela())
            return

        destino = pastas.garantir(self.pasta_saida.get().strip()
                                  or pastas.pasta_downloads())
        if not os.path.isdir(destino):
            messagebox.showerror("Erro",
                                 "Não foi possível criar a pasta de saída.",
                                 parent=self._janela())
            return
        self.pasta_saida.set(destino)

        self.rodando = True
        self.cancel_event.clear()
        self.process_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress_var.set(0)
        self.status_text.config(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.config(state="disabled")

        margem, quadrado, limite = self._opcoes_atuais()
        thread = threading.Thread(
            target=self._process_files,
            args=(list(self.files_selected), destino, margem, quadrado, limite),
            daemon=True)
        thread.start()

    def _cancel_processing(self):
        self.cancel_event.set()
        self.cancel_btn.config(state="disabled")
        self._log(">> Cancelamento solicitado, aguardando o arquivo atual terminar...")

    def _process_files(self, arquivos, destino, margem_percent,
                       forcar_quadrado, limite_lado):
        """Roda em thread separada: NAO toca na tela, so manda pela fila."""
        try:
            total = len(arquivos)
            self.fila.put(("log", f"Processando {total} arquivo(s)..."))
            self.fila.put(("log",
                           f"Margem: {margem_percent}% | Quadrado forçado: "
                           f"{'sim' if forcar_quadrado else 'não'} | "
                           f"Limite de lado: "
                           f"{limite_lado if limite_lado else 'sem limite'}\n"))

            processados = 0
            cancelado = False

            for idx, file_path in enumerate(arquivos, 1):
                if self.cancel_event.is_set():
                    cancelado = True
                    break

                try:
                    origem = Path(file_path)
                    self.fila.put(("log", f"[{idx}/{total}] {origem.name}"))

                    quadros, duracoes, laco = carregar_quadros(file_path)
                    finais, info = montar_figurinhas(
                        quadros, margem_percent, forcar_quadrado, limite_lado
                    )

                    # A extensao segue a da origem: GIF continua GIF (e
                    # continua animado), PNG continua PNG.
                    extensao = ".gif" if origem.suffix.lower() == ".gif" else ".png"
                    output_path = Path(destino) / f"figurinha_{origem.stem}{extensao}"
                    salvar_figurinha(finais, duracoes, laco, output_path)

                    self.fila.put((
                        "log",
                        f"  conteúdo {info['content_w']}×{info['content_h']}px -> "
                        f"canvas {info['canvas_w']}×{info['canvas_h']}px"
                        + (f" · {info['quadros']} quadros"
                           if info["quadros"] > 1 else "")))
                    self.fila.put(("log", f"✓ Salvo como: {output_path.name}\n"))
                    processados += 1

                except Exception as e:
                    self.fila.put(("log",
                                   f"✗ Erro em {Path(file_path).name}: {str(e)}\n"))

                self.fila.put(("progresso", int((idx / total) * 100)))

            self.fila.put(("log", "=" * 60))
            self.fila.put(("fim", (processados, total, cancelado)))

        except Exception as e:
            self.fila.put(("log", f"Erro geral: {str(e)}"))
            self.fila.put(("erro", str(e)))

    def _processar_fila(self):
        """Le o que as threads mandaram e atualiza a tela. Thread principal."""
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "log":
                    self._log(dado)
                elif tipo == "progresso":
                    self.progress_var.set(dado)
                elif tipo == "previa":
                    self._mostrar_previa(*dado)
                elif tipo == "previa_erro":
                    self._falhou_previa(*dado)
                elif tipo == "fim":
                    self._finalizar(*dado)
                elif tipo == "erro":
                    self._encerrar_botoes()
                    messagebox.showerror(
                        "Erro", f"Erro durante processamento: {dado}",
                        parent=self._janela())
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def _finalizar(self, processados, total, cancelado):
        self._encerrar_botoes()
        if cancelado:
            self._log(f"Cancelado pelo usuário. {processados}/{total} "
                      f"arquivo(s) processado(s).")
            messagebox.showinfo(
                "Cancelado",
                f"Processamento cancelado. {processados}/{total} concluídos.",
                parent=self._janela())
        else:
            self._log(f"Processamento concluído! {processados}/{total} "
                      f"arquivo(s) processado(s).")
            self.progress_var.set(100)
            messagebox.showinfo("Sucesso",
                                "Todas as figurinhas foram normalizadas!",
                                parent=self._janela())

    def _encerrar_botoes(self):
        self.rodando = False
        self.process_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

    def _open_output(self):
        folder = self.pasta_saida.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("Info", "A pasta de saída ainda não existe.",
                                parent=self._janela())
            return

        try:
            if platform.system() == "Darwin":       # macOS
                subprocess.Popen(["open", folder])
            elif platform.system() == "Windows":
                os.startfile(folder)                # type: ignore[attr-defined]
            else:                                    # Linux
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showwarning("Aviso",
                                   f"Não foi possível abrir a pasta:\n{e}",
                                   parent=self._janela())

    # ---------- fechamento ----------

    def ao_fechar(self):
        """Limpeza pedida pelo programa principal. So limpa, nao fecha nada.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se marca o cancelamento,
        para a thread parar no proximo arquivo, e se acorda a thread da previa
        com a bandeira de fim levantada, para ela sair do laco.
        """
        self.cancel_event.set()
        self.rodando = False
        self._prev_fim = True
        self._prev_evento.set()
        self._parar_animacao()
        self._prev_cache = (None, None, None, None)


def montar(pai):
    """Desenha a aba de figurinhas dentro de `pai` e devolve o aplicativo."""
    return NormalizadorFigurinhas(pai)
