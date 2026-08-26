#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redimensionar - aba do Estudio de Imagem.

Pega varias fotos de campanha e gera, para cada uma, uma versao no tamanho e
na proporcao pedidos (feed, Stories, capa do Facebook, capa do X...). Trabalha
em lote e NUNCA mexe no arquivo original: sempre grava um arquivo novo na
pasta de destino.

O coracao da tela e o ENQUADRAMENTO: como a foto original quase nunca tem a
proporcao de saida, alguem precisa decidir o que fica e o que sai. Aqui essa
decisao e da pessoa, em duas estrategias:

  - "Cortar pelo centro": corta sempre pelo meio;
  - "Encaixar inteira, com fundo": nao corta nada, encaixa a foto toda e
    preenche a sobra com cor solida ou com a propria foto desfocada.

Trocar de estrategia JOGA FORA os ajustes feitos a mao: quem troca esta
pedindo outro criterio de enquadramento, e ajuste guardado tinha prioridade
sobre a estrategia -- os botoes pareciam mortos depois do primeiro arrasto.

No meio da tela mora a PREVIA AO VIVO: dois quadros lado a lado, "Antes" (a
foto inteira, com a moldura laranja mostrando onde o corte vai cair) e
"Depois" (o resultado ja reenquadrado e redimensionado). Ela reage na hora a
qualquer escolha e diz, embaixo, o tamanho exato que vai sair.

A moldura do "Antes" e AJUSTAVEL: da para arrastar com o mouse e para mexer
nas tres barras de ajuste fino (horizontal, vertical e tamanho da moldura),
logo abaixo da previa. Os dois caminhos mexem no MESMO valor guardado, entao
arrastar move as barras e mexer nas barras move a moldura.

O ajuste e POR FOTO e fica guardado em `self.ajustes` (dicionario indexado
pelo caminho do arquivo). Quem esta tratando um lote pode ajustar a foto 3,
ir olhar a foto 4 e voltar para a 3 sem perder o trabalho; as fotos ja
ajustadas aparecem marcadas com um ponto na lista da esquerda. Dois botoes
completam: "Voltar ao automatico" (apaga o ajuste da foto atual) e "Aplicar a
todas" (copia o enquadramento atual para as outras fotos da fila).

O ajuste e guardado em PROPORCAO da foto (centro em fracao de 0 a 1 e tamanho
em fracao do maior recorte possivel), nunca em pixels. E o que faz o ajuste
sobreviver a troca de proporcao de saida e valer para fotos de tamanhos
diferentes quando se manda aplicar a todas.

Nota: existia um modo "Mirar cada foto na mao", que abria uma janela por foto
so para arrastar a moldura. Ele saiu: a propria aba agora faz a mesma coisa,
melhor -- sem janela extra, sem obrigar um clique por foto e podendo ajustar
so as fotos que precisam.

Notas de interface (macOS no modo escuro):
  - as cores vem de `tema.py`; esta tela nao define estilo nenhum;
  - a moldura da previa e marcada com contorno, linhas tracejadas e cantos
    reforcados. Nada de retangulo "meio transparente" no Canvas: o Tk do Mac
    ignora esse recurso e pinta a area de preto solido, tapando a foto.

Esta tela nao cria janela nem define estilo: a janela e o estilo sao do
programa principal (`estudio_imagem.py` + `tema.py`).
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import (
    StringVar, DoubleVar, BooleanVar, END, DISABLED, NORMAL,
    colorchooser, filedialog, messagebox, ttk,
)
from tkinter.scrolledtext import ScrolledText

import pastas
import tema
from tema import (COR_FUNDO, COR_CAMPO, COR_BOTAO, COR_BOTAO_HOVER, COR_BORDA,
                  COR_TEXTO, COR_SUAVE, COR_APAGADO, COR_DESTAQUE)

try:
    from PIL import Image, ImageOps, ImageFilter
except ImportError:  # pragma: no cover - mensagem amigavel fora da GUI
    print("Falta a biblioteca Pillow. Instale com: pip install Pillow")
    raise

APP_NOME = "Redimensionar"
# 1.1.0: entrou a previa ao vivo (Antes/Depois) dentro da aba.
# 1.2.0: a moldura do "Antes" virou ajustavel (mouse + tres barras), com o
#        ajuste guardado por foto; saiu o modo "Mirar cada foto na mao".
# 1.3.0: saiu o modo "Cortar mirando o rosto" (e o OpenCV junto), e trocar de
#        estrategia passou a descartar os ajustes feitos a mao.
# A versao que aparece no rodape e a do Estudio inteiro, em `estudio_imagem.py`.
APP_VERSION = "1.3.0"

EXTENSOES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif")

# Proporcoes de saida: rotulo, largura, altura, tamanho exato em pixels.
# (0, 0) = a proporcao da propria foto. (-1, -1) = a que a pessoa escrever.
# As duas capas de rede social tem PIXEL exato, e nao so proporcao: e o
# tamanho que o site pede, entao ele ja vem pronto quando ninguem escolhe
# outra largura.
PROPORCOES = [
    ("1:1  quadrado (feed)", 1, 1, None),
    ("4:5  retrato (feed do Instagram)", 4, 5, None),
    ("9:16  em pe (Stories, Reels)", 9, 16, None),
    ("16:9  deitado (YouTube, capa, slide)", 16, 9, None),
    ("3:4  retrato classico", 3, 4, None),
    ("2:3  retrato classico de camera", 2, 3, None),
    ("851 x 315  capa do Facebook", 851, 315, (851, 315)),
    ("1500 x 500  capa do X", 1500, 500, (1500, 500)),
    ("Livre  (mantem a proporcao original)", 0, 0, None),
    ("Personalizada  (escrever ao lado)", -1, -1, None),
]

# Tamanho de saida: rotulo e largura em pixels. 0 = nao mexe, -1 = escrita.
TAMANHOS = [
    ("Nao mexer no tamanho (so reenquadra)", 0),
    ("Largura 1080 px (feed)", 1080),
    ("Largura 1350 px (feed alto)", 1350),
    ("Largura 1920 px (Full HD)", 1920),
    ("Largura 2560 px", 2560),
    ("Largura 3840 px (4K)", 3840),
    ("Largura personalizada (escrever ao lado)", -1),
]

FORMATOS = ["Manter o original", "JPG", "PNG", "WEBP"]

# Estrategias de enquadramento: valor guardado e rotulo mostrado.
# O antigo "manual" (uma janela de mira por foto) saiu: a moldura da propria
# previa e ajustavel, o que resolve melhor o mesmo problema. E o "rosto" saiu
# a pedido do dono: a mira automatica errava com frequencia e, no fim, quem
# resolvia era o arrasto da moldura mesmo.
MODOS = [
    ("centro", "Cortar pelo centro"),
    ("fundo", "Encaixar inteira, com fundo"),
]

SUFIXO_PADRAO = " - {L}x{A}"

# Limites da barra "Tamanho da moldura", em porcentagem do maior recorte
# possivel. O piso de 15% e o mesmo do Estudio de Video, e existe para a
# moldura nao virar um ponto impossivel de arrastar.
ZOOM_MIN = 15.0
ZOOM_MAX = 100.0

# Marca que aparece na lista das fotos com enquadramento ajustado a mao.
MARCA_AJUSTE = "• "

# Os dois recados da linha embaixo das barras. Ficam aqui, juntos, porque
# precisam caber na MESMA largura (ver a largura fixa de `lbl_dica`): recado
# comprido demais empurraria a coluna do meio e espremeria a lista de fotos.
DICA_AJUSTE = "Arraste a moldura ou use as barras."
DICA_SEM_CORTE = "Encaixando inteira, nada e cortado."

# Recado de quando a troca de estrategia joga fora o que foi ajustado a mao.
# So aparece se havia mesmo ajuste para descartar: escrever a toa encheria o
# registro de linhas que nao contam nada.
AVISO_TROCA = "Enquadramento trocado: os ajustes feitos a mao foram refeitos."

# --- previa ao vivo da aba -------------------------------------------------
# Antes de qualquer conta de enquadramento a foto e reduzida para caber neste
# lado. E o que faz a previa ser instantanea mesmo com foto de 24 megapixels:
# o corte e o desfoque trabalham sempre numa miniatura.
PREV_TRABALHO = 1000

# Tamanho de referencia de cada um dos dois quadros ("Antes" e "Depois").
# E so o ponto de PEDIDO: os dois canvas esticam para ocupar o que sobrar de
# altura na aba, entao a previa na tela continua grande. A altura pedida caiu
# de 330 para 264 quando entraram as barras de ajuste fino embaixo -- e o que
# faz a aba inteira continuar cabendo na janela sem barra de rolagem.
PREV_W = 196
PREV_H = 264


# ---------------------------------------------------------------------------
# Funcoes soltas (nao dependem da tela, e por isso rodam na thread sem risco)
# ---------------------------------------------------------------------------
def abrir_no_sistema(caminho: str) -> None:
    """Abre uma pasta no Finder (Mac) ou no Explorer (Windows)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", caminho])
        elif os.name == "nt":
            os.startfile(caminho)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", caminho])
    except Exception:
        pass


def preparar(img, com_alpha: bool):
    """Corrige a orientacao gravada pela camera e ajusta o modo de cor.

    Sem o `exif_transpose`, foto tirada de lado no celular sai deitada: o
    arquivo guarda a imagem girada e um aviso dizendo como endireitar, e quem
    ignora o aviso corta o lugar errado.
    """
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if com_alpha:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
    elif img.mode in ("RGBA", "LA", "P"):
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        conv = img.convert("RGBA")
        fundo.paste(conv, mask=conv.split()[-1])
        img = fundo
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def tem_transparencia(img) -> bool:
    return img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info)


def caixa_de_corte(larg, alt, razao, cx, cy):
    """Maior retangulo na proporcao pedida, centrado no ponto de interesse."""
    cw = float(larg)
    ch = cw / razao
    if ch > alt:
        ch = float(alt)
        cw = ch * razao
    cw = max(1, int(round(cw)))
    ch = max(1, int(round(ch)))
    x = int(round(cx * larg - cw / 2.0))
    y = int(round(cy * alt - ch / 2.0))
    x = max(0, min(x, larg - cw))
    y = max(0, min(y, alt - ch))
    return x, y, cw, ch


def caixa_do_ajuste(larg, alt, razao, cx, cy, escala):
    """Caixa de corte de um ajuste feito a mao, em pixels.

    O ajuste e guardado sempre em PROPORCAO da foto -- centro (`cx`, `cy`) de
    0 a 1 e `escala` de 0.15 a 1 do maior recorte possivel -- e nunca em
    pixels. Tres coisas so funcionam por causa disso:

      - trocar a proporcao de saida NAO joga o ajuste fora: o centro escolhido
        continua valendo e so o tamanho da moldura e refeito para a proporcao
        nova, encaixando de volta dentro da foto;
      - "Aplicar a todas" funciona num lote de fotos de tamanhos diferentes;
      - a conta da previa (feita numa miniatura) e a do arquivo final (feita
        na foto inteira) dao no mesmo enquadramento.

    Com `escala` igual a 1 e o centro do automatico, o resultado e exatamente
    o de `caixa_de_corte`.
    """
    _, _, maxw, maxh = caixa_de_corte(larg, alt, razao, 0.5, 0.5)
    fator = max(0.05, min(1.0, float(escala)))
    # Largura e altura encolhem pelo MESMO fator, entao a proporcao da moldura
    # continua sendo a do maior recorte, que ja e a proporcao pedida.
    cw = max(1, min(maxw, int(round(maxw * fator))))
    ch = max(1, min(maxh, int(round(maxh * fator))))
    x = int(round(float(cx) * larg - cw / 2.0))
    y = int(round(float(cy) * alt - ch / 2.0))
    x = max(0, min(x, larg - cw))
    y = max(0, min(y, alt - ch))
    return x, y, cw, ch


def fracao_da_caixa(larg, alt, x, y, cw, ch):
    """Onde a moldura esta dentro do curso possivel, de 0 a 1 em cada eixo.

    E o valor que as barras horizontal e vertical mostram: 0 e encostada na
    esquerda (ou no topo), 1 e encostada na direita (ou no rodape). Quando a
    moldura ocupa o lado inteiro nao ha curso nenhum, e ai o meio (0.5) e a
    unica resposta honesta.
    """
    curso_x = larg - cw
    curso_y = alt - ch
    fx = (x / float(curso_x)) if curso_x > 0 else 0.5
    fy = (y / float(curso_y)) if curso_y > 0 else 0.5
    return max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))


def caminho_livre(pasta: Path, nome: str, ext: str) -> Path:
    """Caminho que ainda nao existe, para nunca apagar arquivo de outro dia."""
    alvo = pasta / (nome + ext)
    n = 2
    while alvo.exists():
        alvo = pasta / ("%s (%d)%s" % (nome, n, ext))
        n += 1
    return alvo


# ---------------------------------------------------------------------------
# A aba
# ---------------------------------------------------------------------------
class RedimensionarGUI:
    def __init__(self, pai):
        self.raiz = pai
        self.raiz.configure(bg=COR_FUNDO)
        self.fonte_base, self.fonte_peq = tema.fontes()

        self.arquivos: list[Path] = []
        self.fila: queue.Queue = queue.Queue()
        self.cancelar = False
        self.rodando = False
        self.ultimo_destino: Path | None = None

        self.var_prop = StringVar(value=PROPORCOES[3][0])   # 16:9
        self.var_prop_l = StringVar(value="16")
        self.var_prop_a = StringVar(value="9")
        self.var_tam = StringVar(value=TAMANHOS[1][0])      # 1080
        self.var_tam_px = StringVar(value="1080")
        self.var_ampliar = BooleanVar(value=False)
        self.var_modo = StringVar(value="centro")
        self.var_fundo = StringVar(value="desfoque")
        self.var_cor = StringVar(value="#ffffff")
        self.var_formato = StringVar(value=FORMATOS[0])
        self.var_qualidade = DoubleVar(value=90.0)
        self.var_pasta = StringVar(value=pastas.pasta_downloads())
        self.var_sufixo = StringVar(value=SUFIXO_PADRAO)

        # --- enquadramento ajustado a mao ------------------------------------
        # Um ajuste por FOTO, guardado pelo caminho do arquivo e sempre em
        # proporcao: {"cx": 0..1, "cy": 0..1, "escala": 0.15..1}. Ver
        # `caixa_do_ajuste` para o porque de nao guardar pixels.
        self.ajustes: dict[str, dict] = {}
        # Enquadramento que esta na tela AGORA, ajustado a mao ou nao. E o que
        # o botao "Aplicar a todas" copia para as outras fotos.
        self._frac_atual = (0.5, 0.5, 1.0)
        # Geometria do ultimo desenho do quadro "Antes", para as contas do
        # mouse: (larg, alt da miniatura, canto x, canto y, largura e altura
        # da foto ja desenhada no canvas, razao de saida).
        self._geo = None
        # Trava contra laco: arrastar o mouse mexe nas barras, e as barras
        # mexem na moldura. Sem ela, um chamaria o outro sem fim.
        self._ajustando = False
        self._arrastando = False
        self._ax = self._ay = 0.0
        # Rotulos que a lista da esquerda esta mostrando, para so reescrever a
        # lista quando a marca de "ajustada a mao" realmente mudar.
        self._rotulos: list[str] = []
        # Estrategia que estava valendo da ultima vez que `_modo_mudou` rodou.
        # Comeca ja com o valor inicial de proposito: `_modo_mudou` e chamado
        # uma vez na montagem da tela, e ali NAO houve troca nenhuma -- sem
        # esta memoria, abrir a aba ja escreveria o aviso no registro.
        self._modo_anterior = self.var_modo.get()

        self.var_h = DoubleVar(value=50.0)
        self.var_v = DoubleVar(value=50.0)
        self.var_zoom = DoubleVar(value=100.0)

        # --- previa ao vivo --------------------------------------------------
        # Uma unica thread trabalhadora. Quando ela termina uma imagem, pega
        # sempre o pedido MAIS RECENTE e joga fora os do meio: se a pessoa
        # troca tres vezes de proporcao, so a ultima interessa, e a tela nunca
        # fica exibindo uma fila de resultados atrasados.
        #
        # O PhotoImage precisa ficar guardado num atributo: se so a chamada do
        # Canvas segurar a imagem, o Python a recolhe e o quadro fica preto.
        self.imagem_prev_antes = None
        self.imagem_prev_depois = None
        self._prev_seq = 0
        self._prev_exibido = 0
        self._prev_pedido = None
        self._prev_evento = threading.Event()
        self._prev_lock = threading.Lock()
        self._prev_fim = False
        self._prev_agendado = None     # id do `after` que amortece os pedidos
        self._prev_tam = (0, 0)        # tamanho de canvas do ultimo desenho
        self._n_tmp = 0                # so para o plano B de PNG temporario
        # Cache usado SO dentro da thread: a miniatura da foto. Sem ele, cada
        # mexida num controle reabriria o arquivo, que e a parte cara.
        self._mini_cache = {}

        self._montar()
        self._prev_thread = threading.Thread(target=self._worker_previa,
                                             daemon=True)
        self._prev_thread.start()
        self._prop_mudou()
        self._tam_mudou()
        self._modo_mudou()
        self._formato_mudou()
        self.raiz.after(120, self._processar_fila)

    # -------------------------------------------------------------- janela
    def _janela(self):
        """Janela de verdade por tras da aba, para ancorar os dialogos."""
        return self.raiz.winfo_toplevel()

    # ------------------------------------------------------------ interface
    def _montar(self):
        pad = {"padx": 8, "pady": 3}

        # Tudo que e ancorado embaixo entra PRIMEIRO. Assim, quando a janela
        # e baixa, quem cede altura e a lista de fotos (que rola sozinha), e
        # nao o botao de acao nem o registro de mensagens.

        # --- registro e progresso (no fundo da aba) ---
        frm_prog = ttk.LabelFrame(self.raiz, text=" Progresso ")
        frm_prog.pack(side="bottom", fill="x", **pad)
        self.lbl_status = ttk.Label(frm_prog, text="Pronto.",
                                    style="Suave.TLabel")
        self.lbl_status.pack(fill="x", padx=6, pady=(5, 0))
        self.barra = ttk.Progressbar(frm_prog, mode="determinate",
                                     style="Horizontal.TProgressbar",
                                     maximum=100)
        self.barra.pack(fill="x", padx=6, pady=3)
        self.log = ScrolledText(
            frm_prog, height=2, state=DISABLED, wrap="word",
            bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightcolor=COR_BORDA,
            relief="flat", borderwidth=0, font=self.fonte_peq)
        self.log.pack(fill="x", padx=6, pady=(0, 5))
        try:
            self.log.vbar.configure(bg=COR_BOTAO, troughcolor=COR_CAMPO,
                                    activebackground=COR_BOTAO_HOVER,
                                    highlightthickness=0, bd=0)
        except Exception:
            pass

        # --- acao ---
        frm_acao = ttk.Frame(self.raiz)
        frm_acao.pack(side="bottom", fill="x", **pad)
        self.btn_ok = ttk.Button(frm_acao, text="Redimensionar",
                                 style="Acao.TButton", command=self._iniciar)
        self.btn_ok.pack(side="left")
        self.btn_cancelar = ttk.Button(frm_acao, text="Cancelar",
                                       command=self._pedir_cancelar,
                                       state=DISABLED)
        self.btn_cancelar.pack(side="left", padx=6)
        ttk.Button(frm_acao, text="Abrir pasta de destino",
                   command=self._abrir_pasta).pack(side="left")

        # --- saida ---
        # Duas linhas em vez de tres: o sufixo divide a primeira linha com o
        # formato e a qualidade. Cada linha economizada aqui embaixo vira
        # altura de previa la em cima, que e onde ela faz falta.
        frm_saida = ttk.LabelFrame(self.raiz, text=" Saida ")
        frm_saida.pack(side="bottom", fill="x", **pad)

        linha = ttk.Frame(frm_saida)
        linha.pack(fill="x", padx=6, pady=(5, 2))
        ttk.Label(linha, text="Formato:").pack(side="left")
        ttk.Combobox(linha, textvariable=self.var_formato, values=FORMATOS,
                     state="readonly", width=16).pack(side="left", padx=(4, 12))
        self.lbl_qual = ttk.Label(linha, text="Qualidade:")
        self.lbl_qual.pack(side="left")
        self.sld_qual = ttk.Scale(linha, from_=40, to=100,
                                  variable=self.var_qualidade,
                                  style="Horizontal.TScale", length=120)
        self.sld_qual.pack(side="left", padx=4)
        self.lbl_qual_val = ttk.Label(linha, text="90",
                                      style="Destaque.TLabel", width=4)
        self.lbl_qual_val.pack(side="left")
        ttk.Label(linha, text="Sufixo:").pack(side="left", padx=(12, 0))
        ttk.Entry(linha, textvariable=self.var_sufixo, width=14).pack(
            side="left", padx=4)
        ttk.Label(linha, text="{L} e {A} = largura e altura",
                  style="Apagado.TLabel").pack(side="left")

        linha = ttk.Frame(frm_saida)
        linha.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Label(linha, text="Pasta:").pack(side="left")
        ttk.Entry(linha, textvariable=self.var_pasta).pack(
            side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(linha, text="Escolher...",
                   command=self._escolher_pasta).pack(side="left", padx=(6, 0))

        # --- corpo: fila | previa | escolhas ---
        # Tres colunas, e nao duas: a previa precisa de um lugar fixo no meio,
        # entre a fila (que diz de QUE foto se fala) e as escolhas (que dizem
        # COMO ela vai ficar). A fila e a previa esticam quando sobra largura;
        # a coluna das escolhas fica no tamanho dos seus campos.
        corpo = ttk.Frame(self.raiz)
        corpo.pack(side="top", fill="both", expand=True, **pad)
        # 240 e nao 216: com a coluna do meio pedindo mais largura (as barras
        # de ajuste fino), a da esquerda encolhia ate cortar o nome dos dois
        # botoes de cima ("Imagens...", "Pasta...").
        corpo.columnconfigure(0, weight=1, minsize=240)
        corpo.columnconfigure(1, weight=2, minsize=2 * PREV_W + 24)
        corpo.columnconfigure(2, weight=0)
        corpo.rowconfigure(0, weight=1)

        esq = ttk.Frame(corpo)
        esq.grid(row=0, column=0, sticky="nsew")
        meio = ttk.Frame(corpo)
        meio.grid(row=0, column=1, sticky="nsew", padx=8)
        dir_ = ttk.Frame(corpo)
        dir_.grid(row=0, column=2, sticky="nsew")

        self._bloco_fotos(esq)
        self._bloco_previa(meio)
        self._bloco_proporcao(dir_)
        self._bloco_enquadramento(dir_)

    def _bloco_fotos(self, pai):
        # Titulo curto de proposito: esta coluna e a mais estreita das tres, e
        # titulo comprido de LabelFrame nao quebra linha, some cortado.
        cx = ttk.LabelFrame(pai, text=" Fotos (originais intactos) ")
        cx.pack(fill="both", expand=True)

        # O contador e os botoes de mexer na fila ficam ancorados no FUNDO e
        # empacotados ANTES da lista: quando falta altura, quem cede e a lista
        # (que rola sozinha), e nao o que se clica.
        self.lbl_fila = ttk.Label(cx, text="Nenhuma imagem na fila.",
                                  style="Suave.TLabel")
        self.lbl_fila.pack(side="bottom", anchor="e", padx=8, pady=(2, 6))

        botoes = ttk.Frame(cx)
        botoes.pack(side="bottom", fill="x", padx=6)
        ttk.Button(botoes, text="Remover",
                   command=self._remover).pack(side="left")
        ttk.Button(botoes, text="Limpar",
                   command=self._limpar).pack(side="left", padx=6)

        barra = ttk.Frame(cx)
        barra.pack(fill="x", padx=6, pady=(5, 0))
        # Rotulos curtos: a coluna e estreita e botao comprido sai cortado.
        # O titulo do quadro ja diz que o assunto aqui e foto.
        ttk.Button(barra, text="Imagens...",
                   command=self._add_arquivos).pack(side="left")
        ttk.Button(barra, text="Pasta...",
                   command=self._add_pasta).pack(side="left", padx=6)

        # Listbox e Scrollbar sao Tk puro: cada cor precisa ser dita aqui,
        # senao nascem brancas no modo escuro do Mac.
        moldura = tk.Frame(cx, bg=COR_BORDA, bd=0, highlightthickness=0)
        moldura.pack(fill="both", expand=True, padx=6, pady=6)
        self.lista = tk.Listbox(
            moldura, height=5, width=20, activestyle="none",
            selectmode="extended",
            bg=COR_CAMPO, fg=COR_TEXTO, font=self.fonte_peq,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightbackground=COR_BORDA, highlightthickness=0,
            relief="flat", bd=0)
        rolo = tk.Scrollbar(moldura, command=self.lista.yview,
                            bg=COR_BOTAO, troughcolor=COR_CAMPO,
                            activebackground=COR_BOTAO_HOVER,
                            highlightthickness=0, bd=0)
        self.lista.configure(yscrollcommand=rolo.set)
        rolo.pack(side="right", fill="y")
        self.lista.pack(side="left", fill="both", expand=True, padx=1, pady=1)

        # Clicar num item da fila troca a foto da previa.
        self.lista.bind("<<ListboxSelect>>", lambda _e: self._pedir_previa())

    def _bloco_previa(self, pai):
        """Os dois quadros da previa: a foto inteira e o resultado.

        Por que dois quadros lado a lado, e nao so o resultado: quem prepara
        foto de campanha precisa ver as DUAS coisas -- o que vai sobrar e,
        principalmente, o que vai ser jogado fora. A moldura laranja no quadro
        da esquerda e essa resposta; o quadro da direita e o arquivo que sai.
        Lado a lado cabem os dois sem custar altura, que e o que falta aqui.
        """
        self.cx_previa = ttk.LabelFrame(pai, text=" Previa ")
        self.cx_previa.pack(fill="both", expand=True)

        # O bloco de ajuste fino entra PRIMEIRO, ancorado no fundo: numa janela
        # baixa quem cede altura e a imagem, e os controles ficam sempre a
        # vista. Ele mora aqui, colado na previa, porque e a previa que ele
        # mexe.
        self._bloco_ajuste(self.cx_previa)

        # O texto do tamanho final entra ANTES, ancorado no fundo: numa janela
        # baixa quem encolhe e a imagem, e a medida continua a vista.
        # E o mesmo rotulo que antes ficava ao lado da caixa de ampliar --
        # aqui ele nao e repeticao, e a legenda do que se esta vendo.
        self.lbl_resumo = ttk.Label(self.cx_previa, text="-",
                                    style="Destaque.TLabel", anchor="center",
                                    justify="center")
        self.lbl_resumo.pack(side="bottom", fill="x", padx=6, pady=(2, 6))
        # Rede de seguranca: se o texto crescer mais do que a coluna (fonte
        # maior, nome de proporcao comprido), ele quebra em duas linhas em vez
        # de sair cortado pela metade. A largura vem do QUADRO, nunca do
        # proprio rotulo, senao a quebra mudaria a medida que a gerou.
        self.cx_previa.bind("<Configure>", self._ajustar_quebra)

        quadros = ttk.Frame(self.cx_previa)
        quadros.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        quadros.columnconfigure(0, weight=1, uniform="prev")
        quadros.columnconfigure(1, weight=1, uniform="prev")
        quadros.rowconfigure(0, weight=1)

        # Canvas e Tk puro: fundo preto na mao, para a foto aparecer recortada
        # do painel e a borda nao nascer branca no modo escuro do Mac.
        self.cv_antes = tk.Canvas(quadros, width=PREV_W, height=PREV_H,
                                  bg="#000000", highlightthickness=1,
                                  highlightbackground=COR_BORDA, bd=0,
                                  relief="flat")
        self.cv_antes.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        self.cv_depois = tk.Canvas(quadros, width=PREV_W, height=PREV_H,
                                   bg="#000000", highlightthickness=1,
                                   highlightbackground=COR_BORDA, bd=0,
                                   relief="flat")
        self.cv_depois.grid(row=0, column=1, sticky="nsew", padx=(3, 0))

        # Janela maior = previa maior. O <Configure> chega muitas vezes durante
        # um arrasto de janela, mas o amortecimento de `_pedir_previa` junta
        # tudo num pedido so.
        self.cv_depois.bind("<Configure>", self._previa_redimensionou)

        # A moldura do "Antes" e arrastavel, na mesma mecanica da aba de
        # extrair quadros do Estudio de Video.
        self.cv_antes.bind("<ButtonPress-1>", self._mouse_desce)
        self.cv_antes.bind("<B1-Motion>", self._mouse_arrasta)
        self.cv_antes.bind("<ButtonRelease-1>", self._mouse_sobe)

    def _bloco_ajuste(self, pai):
        """As tres barras de ajuste fino da moldura.

        Numa grade de DUAS colunas de controles: em pe seriam tres fileiras,
        e a aba nao caberia mais na janela. Os dois botoes de enquadramento
        moram no quadro "Enquadramento", na coluna da direita, que e larga --
        aqui eles nao cabiam sem cortar o nome pela metade.

        As barras nascem com `length` curto de proposito: o valor pedido e o
        que decide a largura MINIMA desta coluna, e coluna do meio larga
        demais espreme a lista de fotos, na esquerda. Com `sticky="ew"` e
        peso na coluna, elas esticam sozinhas quando sobra espaco.
        """
        cx = ttk.Frame(pai)
        cx.pack(side="bottom", fill="x", padx=6, pady=(0, 5))
        # So as duas colunas de barra esticam, e em partes iguais. Sem
        # `uniform` de proposito: com ele, qualquer widget que atravessasse
        # uma das duas obrigaria a outra a crescer igual, e a barra horizontal
        # acabava espremida a zero.
        cx.columnconfigure(1, weight=1)
        cx.columnconfigure(4, weight=1)

        ttk.Label(cx, text="Horizontal:", style="Suave.TLabel").grid(
            row=0, column=0, sticky="w")
        self.sld_h = ttk.Scale(cx, from_=0, to=100, variable=self.var_h,
                               length=70, style="Horizontal.TScale")
        self.sld_h.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        self.lbl_h = ttk.Label(cx, text="50", style="Destaque.TLabel", width=4,
                               anchor="e")
        self.lbl_h.grid(row=0, column=2, sticky="e", padx=(0, 10))

        ttk.Label(cx, text="Vertical:", style="Suave.TLabel").grid(
            row=0, column=3, sticky="w")
        self.sld_v = ttk.Scale(cx, from_=0, to=100, variable=self.var_v,
                               length=70, style="Horizontal.TScale")
        self.sld_v.grid(row=0, column=4, sticky="ew", padx=(4, 4))
        self.lbl_v = ttk.Label(cx, text="50", style="Destaque.TLabel", width=4,
                               anchor="e")
        self.lbl_v.grid(row=0, column=5, sticky="e")

        ttk.Label(cx, text="Tamanho:", style="Suave.TLabel").grid(
            row=1, column=0, sticky="w")
        self.sld_zoom = ttk.Scale(cx, from_=ZOOM_MIN, to=ZOOM_MAX,
                                  variable=self.var_zoom, length=70,
                                  style="Horizontal.TScale")
        self.sld_zoom.grid(row=1, column=1, sticky="ew", padx=(4, 4))
        self.lbl_zoom = ttk.Label(cx, text="100%", style="Destaque.TLabel",
                                  width=4, anchor="e")
        self.lbl_zoom.grid(row=1, column=2, sticky="e", padx=(0, 10))

        # O recado ocupa uma fileira propria, atravessando as SEIS colunas: se
        # atravessasse so metade delas, a largura que ele pede cairia toda em
        # cima de uma barra so, e ela sumiria. Largura fixa em letras para o
        # texto trocar de tamanho (ao mudar de modo) sem mexer na coluna.
        self.lbl_dica = ttk.Label(
            cx, text=DICA_AJUSTE, style="Apagado.TLabel", anchor="w",
            width=36)
        self.lbl_dica.grid(row=2, column=0, columnspan=6, sticky="ew",
                           pady=(1, 0))

        # Regra da casa: a reacao mora na VARIAVEL, nunca no `command=` do
        # Scale. O `command` so dispara quando a pessoa arrasta AQUELE widget,
        # e estes tres valores tambem mudam por codigo -- e o que acontece o
        # tempo todo, porque arrastar a moldura no mouse move as barras.
        for v in (self.var_h, self.var_v, self.var_zoom):
            v.trace_add("write", lambda *a: self._ajuste_mudou())

    def _ajustar_quebra(self, ev):
        """Ensina a legenda ate onde ela pode ir antes de quebrar a linha.

        So mexe quando o valor muda mesmo: reconfigurar o rotulo a cada
        <Configure> poderia devolver outro <Configure> e girar em falso.
        """
        largura = max(140, ev.width - 20)
        try:
            if int(self.lbl_resumo.cget("wraplength")) != largura:
                self.lbl_resumo.configure(wraplength=largura)
        except Exception:
            pass

    def _previa_redimensionou(self, _ev=None):
        """Refaz a previa quando o quadro muda de tamanho de verdade."""
        largura = max(1, self.cv_depois.winfo_width())
        altura = max(1, self.cv_depois.winfo_height())
        # Sem esta comparacao, cada redesenho pediria outro redesenho.
        if (abs(largura - self._prev_tam[0]) > 8
                or abs(altura - self._prev_tam[1]) > 8):
            self._pedir_previa()

    def _bloco_proporcao(self, pai):
        cx = ttk.LabelFrame(pai, text=" Proporcao e tamanho ")
        cx.pack(fill="x")

        # Cada campo personalizado fica na MESMA linha do combo a que ele
        # pertence. Sao duas linhas a menos, e a aba inteira passa a caber na
        # janela sem barra de rolagem.
        linha = ttk.Frame(cx)
        linha.pack(fill="x", padx=6, pady=(5, 2))
        ttk.Label(linha, text="Proporcao:").pack(side="left")
        ttk.Combobox(linha, textvariable=self.var_prop, state="readonly",
                     width=24, values=[p[0] for p in PROPORCOES]).pack(
                         side="left", padx=(4, 8))
        self.ent_prop_l = ttk.Entry(linha, textvariable=self.var_prop_l,
                                    width=5, justify="center")
        self.ent_prop_l.pack(side="left")
        ttk.Label(linha, text="por", style="Suave.TLabel").pack(side="left",
                                                                padx=4)
        self.ent_prop_a = ttk.Entry(linha, textvariable=self.var_prop_a,
                                    width=5, justify="center")
        self.ent_prop_a.pack(side="left")

        linha = ttk.Frame(cx)
        linha.pack(fill="x", padx=6, pady=2)
        ttk.Label(linha, text="Tamanho:").pack(side="left")
        ttk.Combobox(linha, textvariable=self.var_tam, state="readonly",
                     width=24, values=[t[0] for t in TAMANHOS]).pack(
                         side="left", padx=(4, 8))
        self.ent_tam_px = ttk.Entry(linha, textvariable=self.var_tam_px,
                                    width=7, justify="center")
        self.ent_tam_px.pack(side="left")
        ttk.Label(linha, text="px", style="Suave.TLabel").pack(side="left",
                                                               padx=4)

        # O resumo do tamanho mudou de lugar: agora ele e a legenda da previa.
        # Aqui sobra so a caixa de ampliar, sozinha na linha.
        linha = ttk.Frame(cx)
        linha.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Checkbutton(linha, text="Permitir ampliar fotos menores",
                        variable=self.var_ampliar).pack(side="left")

        # Toda reacao mora na VARIAVEL: o `command` de combo, caixa e barra so
        # dispara quando a pessoa mexe naquele widget, e varios desses valores
        # tambem mudam por codigo.
        for v in (self.var_prop, self.var_prop_l, self.var_prop_a):
            v.trace_add("write", lambda *a: self._prop_mudou())
        for v in (self.var_tam, self.var_tam_px, self.var_ampliar):
            v.trace_add("write", lambda *a: self._tam_mudou())
        self.var_formato.trace_add("write", lambda *a: self._formato_mudou())
        self.var_qualidade.trace_add("write", lambda *a: self._qual_mudou())

    def _bloco_enquadramento(self, pai):
        cx = ttk.LabelFrame(pai, text=" Enquadramento (o que fazer com a "
                                      "sobra) ")
        cx.pack(fill="x", pady=(6, 0))

        for valor, rotulo in MODOS:
            ttk.Radiobutton(cx, text=rotulo, value=valor,
                            variable=self.var_modo).pack(anchor="w", padx=8,
                                                         pady=1)

        linha = ttk.Frame(cx)
        linha.pack(fill="x", padx=8, pady=(4, 6))
        ttk.Label(linha, text="Fundo:", style="Suave.TLabel").pack(side="left")
        self.rb_desfoque = ttk.Radiobutton(linha, text="foto desfocada",
                                           value="desfoque",
                                           variable=self.var_fundo)
        self.rb_desfoque.pack(side="left", padx=(6, 8))
        self.rb_cor = ttk.Radiobutton(linha, text="cor solida", value="cor",
                                      variable=self.var_fundo)
        self.rb_cor.pack(side="left")
        self.btn_cor = ttk.Button(linha, text="Escolher cor...",
                                  command=self._escolher_cor)
        self.btn_cor.pack(side="left", padx=8)
        self.amostra = tk.Label(linha, text="      ", bg=self.var_cor.get(),
                                relief="flat", bd=0,
                                highlightthickness=1,
                                highlightbackground=COR_BORDA)
        self.amostra.pack(side="left")

        # Os dois botoes do enquadramento ajustado a mao moram AQUI, e nao
        # colados nas barras: esta coluna e larga, e la no meio os nomes
        # sairiam cortados pela metade. E o assunto e o mesmo -- enquadrar.
        # A linha so existe porque saiu o modo "Mirar cada foto na mao": o
        # quadro perdeu um botao de escolha e ganhou esta fileira no lugar.
        linha = ttk.Frame(cx)
        linha.pack(fill="x", padx=8, pady=(0, 6))
        self.btn_auto = ttk.Button(linha, text="Voltar ao automatico",
                                   command=self._voltar_automatico)
        self.btn_auto.pack(side="left")
        self.btn_todas = ttk.Button(linha, text="Aplicar a todas",
                                    command=self._aplicar_todas)
        self.btn_todas.pack(side="left", padx=8)
        ttk.Label(linha, text="a moldura desta foto",
                  style="Apagado.TLabel").pack(side="left")

        # A cor tambem entra aqui: ela muda a previa do modo "encaixar
        # inteira", e quem a altera e o seletor de cor, nunca um `command`.
        for v in (self.var_modo, self.var_fundo, self.var_cor):
            v.trace_add("write", lambda *a: self._modo_mudou())

    # -------------------------------------------------------- reacoes da tela
    def _item_prop(self):
        for item in PROPORCOES:
            if item[0] == self.var_prop.get():
                return item
        return PROPORCOES[0]

    def _razao(self, img_w=0, img_h=0):
        """Razao largura/altura pedida. 0 quando ela e a da propria foto."""
        _, a, b, _ = self._item_prop()
        if a == -1:
            try:
                la = float(self.var_prop_l.get().replace(",", "."))
                al = float(self.var_prop_a.get().replace(",", "."))
                if la > 0 and al > 0:
                    return la / al
            except ValueError:
                pass
            return 0.0
        if a == 0:
            return 0.0
        return float(a) / float(b)

    def _largura_alvo(self):
        rotulo = self.var_tam.get()
        for nome, px in TAMANHOS:
            if nome == rotulo:
                if px == -1:
                    try:
                        v = int(float(self.var_tam_px.get()))
                        return v if v > 0 else 0
                    except ValueError:
                        return 0
                return px
        return 0

    def _prop_mudou(self):
        item = self._item_prop()
        personalizada = item[1] == -1
        estado = NORMAL if personalizada else DISABLED
        self.ent_prop_l.configure(state=estado)
        self.ent_prop_a.configure(state=estado)
        self._resumir()

    def _tam_mudou(self):
        escrita = self.var_tam.get() == TAMANHOS[-1][0]
        self.ent_tam_px.configure(state=NORMAL if escrita else DISABLED)
        self._resumir()

    def _modo_mudou(self):
        # Trocar de estrategia joga fora o que foi ajustado a mao. Sem isto os
        # botoes de enquadramento pareciam mortos: o ajuste guardado tem
        # prioridade sobre a estrategia, e como quase toda foto acaba
        # arrastada, trocar de opcao nao mudava nada na tela. Quem troca esta
        # pedindo outro criterio -- e o pedido novo manda.
        #
        # A comparacao com `_modo_anterior` e o que impede o aviso de aparecer
        # na montagem da tela: `_modo_mudou` e chamado uma vez no `__init__`,
        # sem troca nenhuma. O `var_fundo` e a cor tambem passam por aqui, e
        # nao sao motivo para descartar ajuste de enquadramento.
        modo = self.var_modo.get()
        if modo != self._modo_anterior:
            self._modo_anterior = modo
            if self.ajustes:
                self.ajustes.clear()
                self._frac_atual = (0.5, 0.5, 1.0)
                self._marcar_lista()
                self._logar(AVISO_TROCA)

        fundo = modo == "fundo"
        estado = NORMAL if fundo else DISABLED
        self.rb_desfoque.configure(state=estado)
        self.rb_cor.configure(state=estado)
        # O botao de cor so faz sentido quando o fundo escolhido e cor solida.
        cor = fundo and self.var_fundo.get() == "cor"
        self.btn_cor.configure(state=NORMAL if cor else DISABLED)
        # A amostra e pintada aqui, e nao dentro do seletor de cor: assim ela
        # acompanha a variavel mesmo quando a cor e trocada por codigo.
        try:
            self.amostra.configure(bg=self.var_cor.get())
        except Exception:
            pass
        # Encaixando a foto inteira nao se corta nada, entao nao ha
        # enquadramento a escolher: as barras, os botoes e o arrasto do mouse
        # ficam desligados, com o motivo escrito na linha de recado.
        ajustavel = NORMAL if not fundo else DISABLED
        for w in (self.sld_h, self.sld_v, self.sld_zoom,
                  self.btn_auto, self.btn_todas):
            w.configure(state=ajustavel)
        self.lbl_dica.configure(text=DICA_SEM_CORTE if fundo else DICA_AJUSTE)
        self._valores_barras()
        self._resumir()

    def _formato_mudou(self):
        # PNG nao tem controle de qualidade: ele nunca perde informacao.
        png = self.var_formato.get() == "PNG"
        self.sld_qual.configure(state=DISABLED if png else NORMAL)
        self.lbl_qual.configure(state=DISABLED if png else NORMAL)
        self.lbl_qual_val.configure(
            text="-" if png else str(int(self.var_qualidade.get())))

    def _qual_mudou(self):
        if self.var_formato.get() != "PNG":
            self.lbl_qual_val.configure(text=str(int(self.var_qualidade.get())))

    def _resumir(self):
        """Legenda da previa: o que vai sair, antes de gastar tempo.

        Este e o texto de reserva, calculado so com as escolhas da tela. Assim
        que a previa fica pronta, ela troca por um valor exato, que ja leva em
        conta o tamanho real da foto selecionada.
        """
        item = self._item_prop()
        razao = self._razao()
        largura = self._largura_alvo()
        exato = item[3]

        if item[1] == -1 and razao <= 0:
            self.lbl_resumo.configure(
                text="Escreva a proporcao com dois numeros maiores que zero.")
        elif razao <= 0:
            self.lbl_resumo.configure(
                text=("Vai sair na proporcao de cada foto, com %d px de "
                      "largura" % largura) if largura
                else "Cada foto vai sair igual a original")
        elif exato and not largura:
            self.lbl_resumo.configure(text="Vai sair %d x %d px" % exato)
        elif largura:
            self.lbl_resumo.configure(
                text="Vai sair %d x %d px"
                     % (largura, max(1, int(round(largura / razao)))))
        else:
            self.lbl_resumo.configure(
                text="Vai sair no maior tamanho que cada foto permitir")
        self._pedir_previa()

    # ------------------------------------------------------------ lista
    def _add_arquivos(self):
        caminhos = filedialog.askopenfilenames(
            title="Escolha as imagens",
            filetypes=[("Imagens", " ".join("*" + e for e in EXTENSOES)),
                       ("Todos os arquivos", "*.*")],
            parent=self._janela())
        for c in caminhos:
            self._adicionar(Path(c))

    def _add_pasta(self):
        pasta = filedialog.askdirectory(title="Escolha a pasta com as imagens",
                                        parent=self._janela())
        if not pasta:
            return
        achados = 0
        try:
            itens = sorted(Path(pasta).iterdir())
        except OSError:
            itens = []
        for p in itens:
            if p.is_file() and p.suffix.lower() in EXTENSOES:
                if self._adicionar(p):
                    achados += 1
        self._logar("Pasta varrida: %d imagem(ns) adicionada(s)." % achados)

    def _adicionar(self, p: Path) -> bool:
        if p in self.arquivos:
            return False
        self.arquivos.append(p)
        self.lista.insert(END, p.name)
        self._rotulos.append(p.name)
        self._contar()
        return True

    def _remover(self):
        for i in sorted(self.lista.curselection(), reverse=True):
            self.lista.delete(i)
            # O ajuste sai junto com a foto: guardar enquadramento de arquivo
            # que nao esta mais na fila so faria a memoria crescer a toa.
            self.ajustes.pop(str(self.arquivos[i]), None)
            del self.arquivos[i]
            del self._rotulos[i]
        self._contar()

    def _limpar(self):
        self.arquivos.clear()
        self.ajustes.clear()
        self._rotulos.clear()
        self.lista.delete(0, END)
        self._contar()

    def _marcar_lista(self):
        """Poe um ponto antes do nome das fotos ajustadas a mao.

        Quem esta tratando um lote precisa saber, batendo o olho, em quais
        fotos ja mexeu. A lista so e reescrita quando alguma marca muda de
        verdade: reescrever a cada arrasto do mouse piscaria a tela inteira e
        derrubaria a selecao.
        """
        novos = [(MARCA_AJUSTE if str(p) in self.ajustes else "") + p.name
                 for p in self.arquivos]
        if novos == self._rotulos:
            return
        escolha = list(self.lista.curselection())
        topo = self.lista.yview()[0]
        self.lista.delete(0, END)
        for i, texto in enumerate(novos):
            self.lista.insert(END, texto)
            # Cor de destaque reforca a marca: o ponto sozinho e discreto
            # demais num nome comprido de arquivo de celular.
            if novos[i].startswith(MARCA_AJUSTE):
                try:
                    self.lista.itemconfigure(i, foreground=COR_DESTAQUE)
                except Exception:
                    pass
        for i in escolha:
            if i < len(novos):
                self.lista.selection_set(i)
        try:
            self.lista.yview_moveto(topo)
        except Exception:
            pass
        self._rotulos = novos

    def _contar(self):
        # A fila mudou: a previa pode estar mostrando foto que saiu, ou nao
        # estar mostrando nada quando ja ha foto para mostrar.
        self._pedir_previa()
        n = len(self.arquivos)
        if n == 0:
            texto = "Nenhuma imagem na fila."
        elif n == 1:
            texto = "1 imagem na fila."
        else:
            texto = "%d imagens na fila." % n
        self.lbl_fila.configure(text=texto)

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(
            title="Onde salvar as imagens",
            initialdir=self.var_pasta.get() or pastas.pasta_downloads(),
            parent=self._janela())
        if pasta:
            self.var_pasta.set(pasta)

    def _escolher_cor(self):
        escolha = colorchooser.askcolor(color=self.var_cor.get(),
                                        title="Cor do fundo",
                                        parent=self._janela())
        if escolha and escolha[1]:
            # So mexer na variavel basta: o `trace` dela repinta a amostra e
            # refaz a previa.
            self.var_cor.set(escolha[1])

    def _abrir_pasta(self):
        destino = str(self.ultimo_destino or self.var_pasta.get().strip())
        if not destino or not os.path.isdir(destino):
            messagebox.showinfo(APP_NOME, "A pasta de destino ainda nao existe.",
                                parent=self._janela())
            return
        abrir_no_sistema(destino)

    # --------------------------------------------------------- previa ao vivo
    def _foto_selecionada(self):
        """Caminho da foto que a previa deve mostrar, ou None se a fila vazia.

        Sem nada selecionado, a previa mostra a PRIMEIRA da fila: e a proxima
        a ser processada, entao e a que interessa ver.
        """
        if not self.arquivos:
            return None
        escolha = self.lista.curselection()
        i = escolha[0] if escolha else 0
        return self.arquivos[min(i, len(self.arquivos) - 1)]

    def _pedir_previa(self):
        """Marca que a previa precisa ser refeita, sem refazer na hora.

        Um unico controle pode disparar varias mudancas seguidas (o campo de
        proporcao dispara a cada tecla). O `after` junta essa rajada num pedido
        so, e a thread ainda descarta o que sobrar.
        """
        if not hasattr(self, "cv_depois"):
            return
        if self._prev_agendado is not None:
            try:
                self.raiz.after_cancel(self._prev_agendado)
            except Exception:
                pass
        self._prev_agendado = self.raiz.after(70, self._enviar_previa)

    def _enviar_previa(self):
        """Monta o pedido e entrega a thread. So esta parte le os widgets."""
        self._prev_agendado = None
        caminho = self._foto_selecionada()
        if caminho is None:
            self._previa_vazia("Adicione uma foto para ver a previa")
            return

        larg_d = self.cv_depois.winfo_width()
        alt_d = self.cv_depois.winfo_height()
        larg_a = self.cv_antes.winfo_width()
        alt_a = self.cv_antes.winfo_height()
        # winfo_* devolve 1 enquanto o widget nao foi desenhado; ate la vale o
        # tamanho de referencia.
        if larg_d <= 4 or alt_d <= 4:
            larg_d = alt_d = 0
        if larg_a <= 4 or alt_a <= 4:
            larg_a = alt_a = 0
        larg_d, alt_d = larg_d or PREV_W, alt_d or PREV_H
        larg_a, alt_a = larg_a or PREV_W, alt_a or PREV_H
        self._prev_tam = (larg_d, alt_d)

        item = self._item_prop()
        if item[1] == -1 and self._razao() <= 0:
            self._previa_vazia("Escreva a proporcao para ver a previa")
            return

        # O ajuste vai como tupla simples, e nao como o dicionario vivo: a
        # thread nao pode ler estrutura que a tela ainda esta mexendo.
        guardado = self.ajustes.get(str(caminho))
        ajuste = None if not guardado else (guardado["cx"], guardado["cy"],
                                            guardado["escala"])

        with self._prev_lock:
            self._prev_seq += 1
            self._prev_pedido = (
                self._prev_seq, str(caminho), self._razao(),
                self._largura_alvo(), bool(self.var_ampliar.get()),
                self.var_modo.get(), self.var_fundo.get(), self.var_cor.get(),
                item[3], larg_a - 4, alt_a - 4, larg_d - 4, alt_d - 4, ajuste)
        self._prev_evento.set()

    def _previa_vazia(self, recado):
        """Limpa os dois quadros e escreve um recado curto no lugar."""
        # Sem previa nao ha geometria: o mouse e as barras ficam sem chao e
        # precisam saber disso, senao mirariam numa foto que nao esta ali.
        self._geo = None
        self.imagem_prev_antes = None
        self.imagem_prev_depois = None
        for canvas in (self.cv_antes, self.cv_depois):
            canvas.delete("all")
        larg = max(60, self.cv_depois.winfo_width() or PREV_W)
        alt = max(60, self.cv_depois.winfo_height() or PREV_H)
        self.cv_depois.create_text(larg / 2, alt / 2, text=recado,
                                   fill=COR_SUAVE, font=self.fonte_peq,
                                   width=larg - 24, justify="center")
        try:
            self.cx_previa.configure(text=" Previa ")
        except Exception:
            pass

    # --- daqui para baixo, tudo roda NA THREAD (nada toca widget) -----------
    def _worker_previa(self):
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
            try:
                resultado = self._render_previa(pedido)
            except Exception as erro:
                resultado = {"erro": str(erro)}
            if self._prev_fim:
                return
            # A resposta volta pela mesma fila do lote: quem desenha e sempre
            # `_processar_fila`, na thread da tela.
            self.fila.put(("previa", (pedido[0], resultado)))

    def _miniatura(self, caminho):
        """Foto reduzida ao tamanho de trabalho, com o tamanho original junto.

        Todo o resto da previa acontece em cima desta copia pequena. Ela fica
        em cache: mexer num controle nao pode custar reabrir o arquivo.
        """
        try:
            marca = os.path.getmtime(caminho)
        except OSError:
            marca = 0
        guardada = self._mini_cache.get(caminho)
        if guardada and guardada[0] == marca:
            return guardada[1], guardada[2], guardada[3]

        with Image.open(caminho) as bruta:
            img = preparar(bruta, False)
        larg, alt = img.size
        maior = max(larg, alt)
        if maior > PREV_TRABALHO:
            fator = PREV_TRABALHO / float(maior)
            img = img.resize((max(1, int(larg * fator)),
                              max(1, int(alt * fator))), Image.LANCZOS)
        # Guarda so as ultimas fotos: um lote de 300 imagens nao pode virar
        # 300 miniaturas na memoria.
        if len(self._mini_cache) > 3:
            self._mini_cache.clear()
        self._mini_cache[caminho] = (marca, img, larg, alt)
        return img, larg, alt

    def _render_previa(self, pedido):
        """Monta as duas imagens da previa. Roda inteiramente na thread."""
        (_seq, caminho, razao, largura, ampliar, modo, fundo, cor, exato,
         larg_a, alt_a, larg_d, alt_d, ajuste) = pedido

        mini, org_w, org_h = self._miniatura(caminho)
        mw, mh = mini.size

        # O tamanho anunciado vem das medidas REAIS da foto, nao da miniatura.
        saida_w, saida_h = self._plano(org_w, org_h, razao, largura, ampliar,
                                       modo, exato)
        r = float(saida_w) / float(saida_h)

        res = {"nome": os.path.basename(caminho), "modo": modo,
               "largura": saida_w, "altura": saida_h}

        # ---- Antes: a foto inteira, encolhida ate caber no quadro
        esc = min(larg_a / float(mw), alt_a / float(mh))
        aw = max(1, int(mw * esc))
        ah = max(1, int(mh * esc))
        res["antes"] = mini.resize((aw, ah), Image.LANCZOS)
        ox, oy = (larg_a - aw) // 2, (alt_a - ah) // 2
        res["antes_pos"] = (ox, oy)
        # Geometria que a tela precisa para as contas do mouse e das barras.
        res["geo"] = (mw, mh, ox, oy, aw, ah, r)
        res["ajustada"] = ajuste is not None

        if modo == "fundo":
            # Encaixando, nada e descartado: a moldura envolve a foto inteira.
            res["caixa"] = (ox, oy, ox + aw, oy + ah)
            res["inteira"] = True
            res["descarte"] = 0.0
            res["frac"] = (0.5, 0.5, 1.0)
            res["pos"] = (0.5, 0.5, 1.0)
            esc_d = min(larg_d / float(saida_w), alt_d / float(saida_h))
            pw = max(8, int(saida_w * esc_d))
            ph = max(8, int(saida_h * esc_d))
            depois = self._encaixar(mini, pw, ph, fundo, cor, False)
        else:
            if ajuste is not None:
                # A pessoa ja mexeu nesta foto: o enquadramento dela manda, e a
                # estrategia automatica fica de fora.
                cxf, cyf, escf = ajuste
            else:
                # Cortando pelo centro o ponto de interesse e sempre o meio da
                # foto, com a moldura no maior tamanho que couber.
                cxf, cyf, escf = 0.5, 0.5, 1.0
            x, y, cw, ch = caixa_do_ajuste(mw, mh, r, cxf, cyf, escf)
            res["caixa"] = (ox + x * esc, oy + y * esc,
                            ox + (x + cw) * esc, oy + (y + ch) * esc)
            res["inteira"] = False
            res["descarte"] = 1.0 - (float(cw) * ch) / (float(mw) * mh)
            # Devolve o enquadramento JA limitado a foto, e nao o que foi
            # pedido: e assim que as barras passam a mostrar a verdade mesmo
            # quando o ajuste encostou na borda.
            res["frac"] = ((x + cw / 2.0) / mw, (y + ch / 2.0) / mh, escf)
            fx, fy = fracao_da_caixa(mw, mh, x, y, cw, ch)
            res["pos"] = (fx, fy, escf)
            esc_d = min(larg_d / float(saida_w), alt_d / float(saida_h))
            pw = max(8, int(saida_w * esc_d))
            ph = max(8, int(saida_h * esc_d))
            depois = mini.crop((x, y, x + cw, y + ch))
            depois = depois.resize((pw, ph), Image.LANCZOS)

        res["depois"] = depois.convert("RGB")
        res["depois_pos"] = ((larg_d - pw) // 2, (alt_d - ph) // 2)
        return res

    # --- e daqui para baixo, tudo de volta na thread da tela ---------------
    def _foto_tk(self, img):
        """Converte uma imagem do Pillow em imagem do Tk.

        O caminho preferido e o `ImageTk`. Se essa parte do Pillow nao estiver
        disponivel na maquina, grava um PNG temporario e deixa o proprio Tk
        abrir, que ele sabe ler PNG.
        """
        try:
            from PIL import ImageTk
            return ImageTk.PhotoImage(img, master=self.raiz)
        except Exception:
            pass
        try:
            import tempfile
            self._n_tmp = (self._n_tmp + 1) % 4
            alvo = os.path.join(tempfile.gettempdir(),
                                "estudio-imagem-prev-%d.png" % self._n_tmp)
            img.save(alvo, format="PNG")
            return tk.PhotoImage(file=alvo, master=self.raiz)
        except Exception:
            return None

    def _mostrar_previa(self, seq, res):
        """Desenha o resultado da thread. Chamado so por `_processar_fila`."""
        # Resposta atrasada (chegou depois de uma mais nova) e descartada.
        if seq <= self._prev_exibido:
            return
        self._prev_exibido = seq

        if "erro" in res:
            self._geo = None
            self._previa_vazia("Nao consegui montar a previa desta foto.")
            self.lbl_resumo.configure(text="Previa indisponivel")
            return

        self.imagem_prev_antes = self._foto_tk(res["antes"])
        self.imagem_prev_depois = self._foto_tk(res["depois"])

        # Guarda a geometria ANTES de desenhar: e ela que o mouse e as barras
        # usam para converter clique em fracao da foto.
        self._geo = res["geo"]
        self._frac_atual = res["frac"]
        self._sincronizar_barras(*res["pos"])

        self.cv_antes.delete("all")
        if self.imagem_prev_antes is not None:
            self.cv_antes.create_image(res["antes_pos"][0], res["antes_pos"][1],
                                       anchor="nw", image=self.imagem_prev_antes)
        if res["inteira"]:
            self._moldura_previa(self.cv_antes, *res["caixa"])
        else:
            # A moldura e redesenhada a partir do enquadramento de AGORA, e nao
            # do que a thread devolveu: durante um arrasto pode chegar uma
            # resposta calculada com a posicao anterior, e a moldura piscaria
            # para tras.
            self._desenhar_moldura()
        # O aviso de "enquadrada a mao" fica AQUI, na tarja do quadro, e nao na
        # legenda de baixo: na legenda ele fazia a linha passar da largura da
        # coluna e sair cortada.
        if res["inteira"]:
            rotulo_antes = "Antes (nada e cortado)"
        elif res["ajustada"]:
            rotulo_antes = "Antes - a mao"
        else:
            rotulo_antes = "Antes"
        self._rotulo_previa(self.cv_antes, rotulo_antes)

        self.cv_depois.delete("all")
        if self.imagem_prev_depois is not None:
            self.cv_depois.create_image(res["depois_pos"][0],
                                        res["depois_pos"][1], anchor="nw",
                                        image=self.imagem_prev_depois)
        self._rotulo_previa(self.cv_depois, "Depois")

        # Texto curto: ele e a legenda dos dois quadros, e a coluna do meio nao
        # e larga. O que importa e o tamanho final; o resto e uma palavra.
        texto = "Vai sair %d x %d px" % (res["largura"], res["altura"])
        if res["descarte"] > 0.005:
            texto += "  •  corta %d%%" % round(res["descarte"] * 100)
        self.lbl_resumo.configure(text=texto)

        nome = res["nome"]
        if len(nome) > 34:
            nome = nome[:31] + "..."
        try:
            self.cx_previa.configure(text=" Previa: %s " % nome)
        except Exception:
            pass

    def _rotulo_previa(self, canvas, texto):
        """Escreve o nome do quadro no canto de cima.

        A tarja atras e um retangulo de cor CHEIA, e nao um retangulo
        "meio transparente": o Tk do Mac ignora esse efeito e pinta preto
        solido. Sem a tarja, a letra some por cima da moldura laranja quando
        o corte encosta na borda da foto.
        """
        fonte = (self.fonte_peq[0], max(9, self.fonte_peq[1] - 1), "bold")
        item = canvas.create_text(9, 8, anchor="nw", text=texto,
                                  fill=COR_TEXTO, font=fonte)
        x1, y1, x2, y2 = canvas.bbox(item)
        tarja = canvas.create_rectangle(x1 - 4, y1 - 3, x2 + 4, y2 + 3,
                                        fill=COR_FUNDO, outline=COR_BORDA,
                                        width=1)
        canvas.tag_lower(tarja, item)

    def _moldura_previa(self, canvas, x1, y1, x2, y2):
        """Marca no 'Antes' a area que vai ficar.

        Nada de retangulo meio transparente para escurecer a sobra: o Tk do
        Mac ignora o `stipple` e pinta a area de preto solido, tapando
        justamente a foto que a pessoa quer conferir. A marcacao e feita com
        contorno, linhas dos tercos e cantos reforcados.
        """
        # Tudo com a etiqueta "moldura": e assim que o arrasto do mouse
        # consegue apagar so a moldura e redesenha-la, sem refazer a foto --
        # que e a parte cara e o que deixaria o arrasto travado.
        canvas.delete("moldura")

        # Contorno escuro por baixo, para a moldura aparecer em foto clara.
        canvas.create_rectangle(x1 - 2, y1 - 2, x2 + 2, y2 + 2,
                                outline="#000000", width=3, tags="moldura")
        canvas.create_rectangle(x1, y1, x2, y2, outline=COR_DESTAQUE, width=3,
                                tags="moldura")

        for i in (1, 2):
            xt = x1 + (x2 - x1) * i / 3
            yt = y1 + (y2 - y1) * i / 3
            canvas.create_line(xt, y1, xt, y2, fill=COR_DESTAQUE, width=1,
                               dash=(3, 5), tags="moldura")
            canvas.create_line(x1, yt, x2, yt, fill=COR_DESTAQUE, width=1,
                               dash=(3, 5), tags="moldura")

        lado = max(8, min(24, (x2 - x1) / 6))
        for px, py, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1),
                               (x1, y2, 1, -1), (x2, y2, -1, -1)):
            canvas.create_line(px, py, px + dx * lado, py, fill="#ffffff",
                               width=4, tags="moldura")
            canvas.create_line(px, py, px, py + dy * lado, fill="#ffffff",
                               width=4, tags="moldura")

    # ------------------------------------------------- moldura ajustavel
    # Duas maos mexem no MESMO enquadramento: o mouse, arrastando a moldura no
    # quadro "Antes", e as tres barras de ajuste fino. Para elas nao ficarem
    # chamando uma a outra sem fim, existe a trava `self._ajustando`: quando
    # uma delas escreve nas variaveis das barras, o observador dessas
    # variaveis ve a trava levantada e nao faz nada.
    def _numero(self, var, padrao):
        """Le uma DoubleVar sem explodir se ela estiver num estado esquisito."""
        try:
            return float(var.get())
        except Exception:
            return padrao

    def _escala_atual(self):
        """Tamanho da moldura (0.15 a 1) do enquadramento que esta na tela."""
        caminho = self._foto_selecionada()
        aj = self.ajustes.get(str(caminho)) if caminho is not None else None
        return aj["escala"] if aj else self._frac_atual[2]

    def _caixa_atual(self):
        """Moldura de agora, em pixels da miniatura mostrada no 'Antes'."""
        mw, mh, _ox, _oy, _aw, _ah, razao = self._geo
        caminho = self._foto_selecionada()
        aj = self.ajustes.get(str(caminho)) if caminho is not None else None
        if aj:
            cx, cy, esc = aj["cx"], aj["cy"], aj["escala"]
        else:
            cx, cy, esc = self._frac_atual
        return caixa_do_ajuste(mw, mh, razao, cx, cy, esc)

    def _desenhar_moldura(self):
        """Redesenha SO a moldura, direto no canvas.

        E o que faz o arrasto ser fluido: refazer a imagem do 'Depois' custa
        caro e fica com a thread; a moldura e quatro linhas e sai na hora.
        """
        if self._geo is None or self.var_modo.get() == "fundo":
            return
        mw, mh, ox, oy, aw, ah, _razao = self._geo
        x, y, cw, ch = self._caixa_atual()
        ex, ey = aw / float(mw), ah / float(mh)
        self._moldura_previa(self.cv_antes, ox + x * ex, oy + y * ey,
                             ox + (x + cw) * ex, oy + (y + ch) * ey)

    def _valores_barras(self):
        """Escreve o numero de cada barra ao lado dela.

        Encaixando a foto inteira nao ha enquadramento, e os tres numeros
        viram um traco -- o mesmo sinal que a qualidade ja usa quando o
        formato e PNG. E o unico jeito de a barra desligada PARECER desligada:
        o estilo e global, vem de `tema.py`, e esta tela nao pinta widget.
        """
        vazio = self.var_modo.get() == "fundo"
        try:
            self.lbl_h.configure(
                text="-" if vazio
                else "%d" % round(self._numero(self.var_h, 50)))
            self.lbl_v.configure(
                text="-" if vazio
                else "%d" % round(self._numero(self.var_v, 50)))
            self.lbl_zoom.configure(
                text="-" if vazio
                else "%d%%" % round(self._numero(self.var_zoom, 100)))
        except Exception:
            pass

    def _sincronizar_barras(self, fx, fy, escala):
        """Poe as barras no valor do enquadramento que esta na tela.

        Chamado quando quem mandou foi o mouse (ou a troca de foto), e nao a
        propria barra. A trava impede que escrever aqui volte como um novo
        pedido de mover a moldura.
        """
        self._ajustando = True
        try:
            self.var_h.set(round(max(0.0, min(1.0, fx)) * 100.0, 1))
            self.var_v.set(round(max(0.0, min(1.0, fy)) * 100.0, 1))
            self.var_zoom.set(round(max(ZOOM_MIN, min(ZOOM_MAX,
                                                      escala * 100.0)), 1))
        finally:
            self._ajustando = False
        self._valores_barras()

    def _ajuste_mudou(self):
        """Alguem mexeu numa das tres barras: a moldura vai atras."""
        self._valores_barras()
        if self._ajustando:
            return
        if self._geo is None or self.var_modo.get() == "fundo":
            return
        caminho = self._foto_selecionada()
        if caminho is None:
            return

        mw, mh, _ox, _oy, _aw, _ah, razao = self._geo
        esc = max(ZOOM_MIN, min(ZOOM_MAX,
                                self._numero(self.var_zoom, 100.0))) / 100.0
        _, _, maxw, maxh = caixa_de_corte(mw, mh, razao, 0.5, 0.5)
        cw = max(1, min(maxw, int(round(maxw * esc))))
        ch = max(1, min(maxh, int(round(maxh * esc))))
        # As barras horizontal e vertical dizem ONDE, dentro do curso possivel,
        # a moldura esta: 0 encostada num lado, 100 no outro. Assim elas nunca
        # apontam para fora da foto, seja qual for o tamanho da moldura.
        fx = max(0.0, min(1.0, self._numero(self.var_h, 50.0) / 100.0))
        fy = max(0.0, min(1.0, self._numero(self.var_v, 50.0) / 100.0))
        x = (mw - cw) * fx
        y = (mh - ch) * fy
        self._guardar_ajuste(caminho, (x + cw / 2.0) / mw,
                             (y + ch / 2.0) / mh, esc)

    def _guardar_ajuste(self, caminho, cx, cy, escala):
        """Grava o enquadramento desta foto e atualiza a tela."""
        self.ajustes[str(caminho)] = {"cx": float(cx), "cy": float(cy),
                                      "escala": float(escala)}
        self._frac_atual = (float(cx), float(cy), float(escala))
        self._marcar_lista()
        self._desenhar_moldura()
        self._pedir_previa()

    # ------------------------------------------------------------ o mouse
    def _pos_na_foto(self, ev):
        """Converte um clique no canvas em pixels da miniatura da foto."""
        mw, mh, ox, oy, aw, ah, _razao = self._geo
        return ((ev.x - ox) * mw / float(aw), (ev.y - oy) * mh / float(ah))

    def _mouse_desce(self, ev):
        if self._geo is None or self.var_modo.get() == "fundo":
            return
        if self._foto_selecionada() is None:
            return
        x, y, cw, ch = self._caixa_atual()
        px, py = self._pos_na_foto(ev)
        if x <= px <= x + cw and y <= py <= y + ch:
            # Clicou dentro: a moldura anda junto com o ponto agarrado, sem
            # dar aquele pulo de centralizar no cursor.
            self._ax, self._ay = px - x, py - y
        else:
            # Clicou fora: a moldura vai para la de uma vez, ja centrada no
            # cursor, e o arrasto continua dali.
            self._ax, self._ay = cw / 2.0, ch / 2.0
            self._mover_moldura(px - self._ax, py - self._ay)
        self._arrastando = True

    def _mouse_arrasta(self, ev):
        if not self._arrastando or self._geo is None:
            return
        px, py = self._pos_na_foto(ev)
        self._mover_moldura(px - self._ax, py - self._ay)

    def _mouse_sobe(self, _ev=None):
        self._arrastando = False

    def _mover_moldura(self, x, y):
        """Poe o canto de cima da moldura em (x, y), em pixels da miniatura."""
        caminho = self._foto_selecionada()
        if caminho is None or self._geo is None:
            return
        mw, mh, _ox, _oy, _aw, _ah, _razao = self._geo
        _x, _y, cw, ch = self._caixa_atual()
        # A moldura nunca sai da foto.
        x = max(0.0, min(float(x), float(mw - cw)))
        y = max(0.0, min(float(y), float(mh - ch)))
        esc = self._escala_atual()
        self._guardar_ajuste(caminho, (x + cw / 2.0) / mw,
                             (y + ch / 2.0) / mh, esc)
        # E aqui que o arrasto move as barras: a mao de volta do mao dupla.
        fx, fy = fracao_da_caixa(mw, mh, x, y, cw, ch)
        self._sincronizar_barras(fx, fy, esc)

    # ------------------------------------------------------- os dois botoes
    def _voltar_automatico(self):
        """Apaga o ajuste desta foto: ela volta a seguir a estrategia."""
        caminho = self._foto_selecionada()
        if caminho is None:
            return
        if self.ajustes.pop(str(caminho), None) is None:
            self._logar("%s ja estava no enquadramento automatico."
                        % caminho.name)
            return
        self._marcar_lista()
        # A previa refaz o calculo pela estrategia e, quando chegar, poe as
        # barras no valor dela.
        self._pedir_previa()
        self._logar("Enquadramento automatico devolvido a " + caminho.name)

    def _aplicar_todas(self):
        """Copia o enquadramento de agora para as outras fotos da fila.

        Copia a PROPORCAO (centro e tamanho em fracao), nunca os pixels: num
        lote de fotos parecidas mas de tamanhos diferentes, e a fracao que
        cai no mesmo lugar em todas.
        """
        if not self.arquivos:
            messagebox.showinfo(APP_NOME, "Nao ha fotos na fila.",
                                parent=self._janela())
            return
        caminho = self._foto_selecionada()
        if caminho is None:
            return
        aj = self.ajustes.get(str(caminho))
        if aj:
            cx, cy, esc = aj["cx"], aj["cy"], aj["escala"]
        else:
            # Sem ajuste proprio, vale o enquadramento que a previa esta
            # mostrando -- o automatico desta foto.
            cx, cy, esc = self._frac_atual
        for p in self.arquivos:
            self.ajustes[str(p)] = {"cx": float(cx), "cy": float(cy),
                                    "escala": float(esc)}
        self._frac_atual = (float(cx), float(cy), float(esc))
        self._marcar_lista()
        self._pedir_previa()
        self._logar("Enquadramento aplicado a %d foto(s)." % len(self.arquivos))

    # -------------------------------------------------------------- calculo
    def _plano(self, img_w, img_h, razao, largura, ampliar, modo, exato):
        """Decide o tamanho final da imagem que vai ser gravada.

        Devolve (largura, altura). Vale para os dois modos: a diferenca
        entre cortar e encaixar aparece so no limite de "nao ampliar", porque
        cortando o maior quadro possivel e menor que a foto, e encaixando ele
        e maior.
        """
        if razao <= 0:                       # Livre: a proporcao e da foto
            razao = float(img_w) / float(img_h)
            if not largura:
                return img_w, img_h

        if modo == "fundo":
            # A moldura precisa CONTER a foto inteira.
            base_w = max(float(img_w), float(img_h) * razao)
        else:
            # A moldura precisa CABER dentro da foto.
            base_w = min(float(img_w), float(img_h) * razao)

        if largura:
            saida_w = float(largura)
        elif exato:
            saida_w = float(exato[0])
        else:
            saida_w = base_w

        if not ampliar and saida_w > base_w:
            # Arredondando para BAIXO: um pixel a mais aqui viraria um pixel
            # de altura a mais la, e a moldura deixaria de caber na foto --
            # foi como 9:16 de uma foto de 1080 de altura saia com 1081.
            saida_w = int(base_w)

        saida_w = max(1, int(saida_w))
        saida_h = max(1, int(round(saida_w / razao)))

        # Cortando, a moldura nunca pode passar da foto quando a pessoa nao
        # autorizou ampliar.
        if not ampliar and modo != "fundo":
            if saida_h > img_h:
                saida_h = img_h
                saida_w = max(1, int(saida_h * razao))
            if saida_w > img_w:
                saida_w = img_w
                saida_h = max(1, int(round(saida_w / razao)))
        return saida_w, saida_h

    # -------------------------------------------------------------- execucao
    def _iniciar(self):
        if self.rodando:
            return
        if not self.arquivos:
            messagebox.showwarning(APP_NOME,
                                   "Adicione pelo menos uma imagem.",
                                   parent=self._janela())
            return
        item = self._item_prop()
        if item[1] == -1 and self._razao() <= 0:
            messagebox.showwarning(
                APP_NOME,
                "Escreva a proporcao personalizada com dois numeros maiores "
                "que zero, por exemplo 16 por 9.",
                parent=self._janela())
            return
        if self.var_tam.get() == TAMANHOS[-1][0] and not self._largura_alvo():
            messagebox.showwarning(APP_NOME,
                                   "Escreva a largura em pixels, por exemplo "
                                   "1080.",
                                   parent=self._janela())
            return

        destino = Path(pastas.garantir(self.var_pasta.get().strip()
                                       or pastas.pasta_downloads()))
        if not destino.is_dir():
            messagebox.showerror(APP_NOME,
                                 "Nao foi possivel criar a pasta de destino.",
                                 parent=self._janela())
            return

        modo = self.var_modo.get()
        razao = self._razao()
        # Uma copia congelada do que foi ajustado a mao: a thread nao pode ler
        # o dicionario vivo, que a tela continua podendo mexer.
        ajustes = {k: dict(v) for k, v in self.ajustes.items()}

        self.ultimo_destino = destino
        self.cancelar = False
        self.rodando = True
        self.btn_ok.configure(state=DISABLED)
        self.btn_cancelar.configure(state=NORMAL)
        self.barra.configure(value=0)

        threading.Thread(
            target=self._trabalhar,
            args=(list(self.arquivos), destino, razao, self._largura_alvo(),
                  bool(self.var_ampliar.get()), modo, self.var_fundo.get(),
                  self.var_cor.get(), self.var_formato.get(),
                  int(self.var_qualidade.get()),
                  self.var_sufixo.get(), self._item_prop()[3], ajustes),
            daemon=True).start()

    def _pedir_cancelar(self):
        self.cancelar = True
        self.fila.put(("log", "Cancelando..."))

    def _trabalhar(self, arquivos, destino, razao, largura, ampliar, modo,
                   fundo, cor, formato, qualidade, sufixo, exato, ajustes):
        total = len(arquivos)
        ok = falhas = 0
        self.fila.put(("lote", (0, total)))

        for i, caminho in enumerate(arquivos, start=1):
            if self.cancelar:
                break
            self.fila.put(("status", "[%d/%d] %s" % (i, total, caminho.name)))
            try:
                nome = self._uma_foto(
                    caminho, destino, razao, largura, ampliar, modo,
                    fundo, cor, formato, qualidade, sufixo, exato,
                    ajustes.get(str(caminho)))
                ok += 1
                self.fila.put(("log", "OK: " + nome))
            except Exception as erro:
                falhas += 1
                self.fila.put(("log", "FALHA em %s (%s)" % (caminho.name, erro)))
            self.fila.put(("lote", (i, total)))

        self.fila.put(("fim", (ok, falhas, self.cancelar)))

    def _uma_foto(self, caminho, destino, razao, largura, ampliar, modo,
                  fundo, cor, formato, qualidade, sufixo, exato, ajuste):
        """Gera UMA imagem. Devolve o nome do arquivo gravado."""
        with Image.open(caminho) as bruta:
            alpha = (formato in ("PNG", "WEBP")
                     or (formato == "Manter o original"
                         and caminho.suffix.lower() in (".png", ".webp")))
            # Encaixando com fundo, a sobra e sempre preenchida: nao ha o que
            # ficar transparente, e RGB gera arquivo menor.
            alpha = alpha and modo != "fundo" and tem_transparencia(bruta)
            img = preparar(bruta, alpha)

        img_w, img_h = img.size
        saida_w, saida_h = self._plano(img_w, img_h, razao, largura, ampliar,
                                       modo, exato)
        r = float(saida_w) / float(saida_h)

        if modo == "fundo":
            final = self._encaixar(img, saida_w, saida_h, fundo, cor, alpha)
        else:
            if ajuste is not None:
                # Foto enquadrada a mao: manda o que a pessoa escolheu, e a
                # estrategia automatica nem e consultada. Como o ajuste esta em
                # proporcao, a conta feita aqui na foto inteira cai exatamente
                # no mesmo lugar que a previa mostrou na miniatura.
                #
                # Moldura menor que 100% quer dizer aproximar: o recorte sai
                # menor que o tamanho final pedido e e ampliado na hora de
                # gravar. E o preco de aproximar, e foi a pessoa que pediu.
                x, y, cw, ch = caixa_do_ajuste(img_w, img_h, r, ajuste["cx"],
                                               ajuste["cy"], ajuste["escala"])
            else:
                # Cortando pelo centro: o maior retangulo na proporcao pedida,
                # tirado do meio da foto.
                x, y, cw, ch = caixa_de_corte(img_w, img_h, r, 0.5, 0.5)
            final = img.crop((x, y, x + cw, y + ch))
            if (cw, ch) != (saida_w, saida_h):
                final = final.resize((saida_w, saida_h), Image.LANCZOS)

        return self._gravar(final, caminho, destino, formato, qualidade,
                            sufixo, saida_w, saida_h)

    def _encaixar(self, img, saida_w, saida_h, fundo, cor, alpha):
        """Encaixa a foto inteira na moldura e preenche a sobra."""
        escala = min(saida_w / img.size[0], saida_h / img.size[1])
        dw = max(1, int(round(img.size[0] * escala)))
        dh = max(1, int(round(img.size[1] * escala)))
        frente = img.resize((dw, dh), Image.LANCZOS)

        if fundo == "desfoque":
            # Efeito comum em Stories: a propria foto, ampliada ate cobrir a
            # moldura e bem desfocada, vira o pano de fundo. O raio acompanha
            # o tamanho da saida, senao em foto grande o borrao some.
            cobre = max(saida_w / img.size[0], saida_h / img.size[1])
            bw = max(1, int(round(img.size[0] * cobre)))
            bh = max(1, int(round(img.size[1] * cobre)))
            base = img.convert("RGB").resize((bw, bh), Image.LANCZOS)
            base = base.crop(((bw - saida_w) // 2, (bh - saida_h) // 2,
                              (bw - saida_w) // 2 + saida_w,
                              (bh - saida_h) // 2 + saida_h))
            base = base.filter(
                ImageFilter.GaussianBlur(max(6, saida_w / 22.0)))
            if alpha:
                base = base.convert("RGBA")
        else:
            modo_cor = "RGBA" if alpha else "RGB"
            base = Image.new(modo_cor, (saida_w, saida_h),
                             cor if not alpha else cor)

        px = (saida_w - dw) // 2
        py = (saida_h - dh) // 2
        if frente.mode == "RGBA":
            base.paste(frente, (px, py), frente)
        else:
            base.paste(frente, (px, py))
        return base

    def _gravar(self, img, origem: Path, destino: Path, formato, qualidade,
                sufixo, saida_w, saida_h):
        alvo = formato
        if alvo == "Manter o original":
            ext = origem.suffix.lower()
            alvo = {".png": "PNG", ".webp": "WEBP"}.get(ext, "JPG")

        ext = {"JPG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[alvo]
        texto = (sufixo or "").replace("{L}", str(saida_w)) \
                              .replace("{A}", str(saida_h))
        arquivo = caminho_livre(destino, origem.stem + texto, ext)

        if alvo == "JPG" and img.mode != "RGB":
            img = img.convert("RGB")

        if alvo == "JPG":
            img.save(arquivo, format="JPEG", quality=int(qualidade),
                     optimize=True, progressive=True,
                     subsampling=2 if qualidade < 90 else 0)
        elif alvo == "WEBP":
            img.save(arquivo, format="WEBP", quality=int(qualidade), method=6)
        else:
            img.save(arquivo, format="PNG", optimize=True, compress_level=9)
        return arquivo.name

    # ---------------------------------------------------------- fila e log
    def _processar_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "status":
                    self.lbl_status.configure(text=dado)
                elif tipo == "lote":
                    i, total = dado
                    self.barra.configure(value=(i / total * 100) if total else 0)
                elif tipo == "log":
                    self._logar(dado)
                elif tipo == "previa":
                    self._mostrar_previa(*dado)
                elif tipo == "fim":
                    self._terminar(*dado)
        except queue.Empty:
            pass
        # 70 ms em vez de 120: e por esta fila que a previa chega na tela, e
        # nesse ritmo ela acompanha quem troca de opcao sem parecer atrasada.
        self.raiz.after(70, self._processar_fila)

    def _terminar(self, ok, falhas, cancelado):
        self.rodando = False
        self.btn_ok.configure(state=NORMAL)
        self.btn_cancelar.configure(state=DISABLED)
        if cancelado:
            self.lbl_status.configure(text="Cancelado.")
            self._logar("Cancelado. Prontas: %d, falhas: %d." % (ok, falhas))
            return

        self.barra.configure(value=100)
        self.lbl_status.configure(text="Pronto: %d imagem(ns)." % ok)
        self._logar("Concluido. Prontas: %d, falhas: %d." % (ok, falhas))
        resumo = "Foram geradas %d imagem(ns)." % ok
        if falhas:
            resumo += "\nFalhas: %d." % falhas
        if ok and messagebox.askyesno(APP_NOME,
                                      resumo + "\n\nQuer abrir a pasta?",
                                      parent=self._janela()):
            self._abrir_pasta()
        elif not ok:
            messagebox.showinfo(APP_NOME, resumo, parent=self._janela())

    def _logar(self, msg):
        self.log.configure(state=NORMAL)
        self.log.insert(END, msg + "\n")
        self.log.see(END)
        self.log.configure(state=DISABLED)

    # ------------------------------------------------------------ fechamento
    def ao_fechar(self):
        """Limpeza pedida pelo programa principal: nao destroi janela nenhuma.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se marca o cancelamento,
        para a thread parar no proximo arquivo, e se acorda a thread da previa
        para ela sair do `wait()` e terminar.
        """
        self.cancelar = True
        self.rodando = False
        self._arrastando = False
        self._prev_fim = True
        try:
            self._prev_evento.set()
        except Exception:
            pass
        self._mini_cache.clear()
        self.ajustes.clear()


def montar(pai):
    """Desenha a aba de redimensionar dentro de `pai` e devolve o aplicativo."""
    return RedimensionarGUI(pai)
