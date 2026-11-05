#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprimir Imagem - aba do Estudio de Imagem.

Reduz o peso de imagens ate caber num tamanho maximo escolhido pelo usuario
(por exemplo, 200 KB por foto). O programa procura sozinho a melhor combinacao
de qualidade e de tamanho em pixels que ainda respeite o limite pedido,
sempre tentando primeiro a maior qualidade possivel.

Tambem aceita link de imagem na internet (inclusive Google Drive e Dropbox):
o link e baixado e a imagem entra na lista.

Esta tela nao cria janela nem define estilo: a janela e o estilo sao do
programa principal (`estudio_imagem.py` + `tema.py`).
"""

import io
import os
import queue
import re
import ssl
import subprocess
import sys
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import pastas
import tema
from tema import (COR_FUNDO, COR_CAMPO, COR_BOTAO, COR_BOTAO_HOVER, COR_BORDA,
                  COR_TEXTO, COR_DESTAQUE, COR_OK, COR_ERRO)

# certifi precisa ser importado no nivel do modulo para o PyInstaller
# detectar o import e embutir a lista de certificados no executavel.
try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - mensagem amigavel fora da GUI
    print("Falta a biblioteca Pillow. Instale com: pip install Pillow")
    raise

APP_VERSION = "1.3.2"
APP_NOME = "Comprimir Imagem"

EXTENSOES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif")

# Escalas de reducao de pixels tentadas, da maior para a menor.
ESCALAS = [1.0, 0.92, 0.85, 0.78, 0.70, 0.62, 0.55, 0.48, 0.40, 0.33, 0.25, 0.18]

# Numero de cores tentadas quando a saida e PNG.
CORES_PNG = [256, 128, 64, 32, 16]


# ====================================================================== util
def formatar_bytes(n):
    """Devolve o tamanho em texto curto (por exemplo, '183 KB').

    Conta como o Finder do Mac e o Explorer do Windows contam hoje:
    1 KB = 1000 bytes e 1 MB = 1000 KB. Se usassemos 1024, um arquivo de
    2 MB para o programa apareceria como "2,1 MB" para o usuario.
    """
    if n is None:
        return "-"
    if n < 1000:
        return "%d B" % n
    if n < 1000 * 1000:
        return "%.0f KB" % (n / 1000.0)
    return "%.2f MB" % (n / (1000.0 * 1000.0))


def abrir_no_sistema(caminho):
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


def pasta_padrao_saida():
    """Pasta que ja vem preenchida como destino: a Downloads do usuario."""
    return pastas.pasta_downloads()


def pasta_das_baixadas():
    """Pasta onde as imagens baixadas por link sao guardadas."""
    return pastas.garantir(os.path.join(pastas.pasta_downloads(),
                                        "imagens-baixadas"))


# =========================================================== baixar por link
NAVEGADOR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _contexto_ssl():
    """Contexto SSL usando o pacote de certificados do certifi.

    Sem isso, o programa empacotado (PyInstaller) pode falhar ao baixar com
    "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate": o
    Python embutido no executavel nao enxerga a mesma cadeia de certificados
    raiz do sistema operacional, mesmo com a internet funcionando.
    """
    try:
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    return ssl.create_default_context()


def id_do_google_drive(url):
    """Extrai o identificador do arquivo num link do Google Drive."""
    for padrao in (r"/file/d/([A-Za-z0-9_-]{10,})",
                   r"[?&]id=([A-Za-z0-9_-]{10,})",
                   r"/d/([A-Za-z0-9_-]{10,})"):
        achou = re.search(padrao, url)
        if achou:
            return achou.group(1)
    return None


def normalizar_link(url):
    """Transforma links de compartilhamento em links de download direto."""
    url = url.strip()
    baixo = url.lower()

    if "drive.google.com" in baixo or "docs.google.com" in baixo:
        ident = id_do_google_drive(url)
        if ident:
            return ("https://drive.usercontent.google.com/download"
                    "?id=%s&export=download&confirm=t" % ident)

    if "dropbox.com" in baixo:
        base = url.split("?")[0]
        return base + "?dl=1"

    if "1drv.ms" in baixo or "onedrive.live.com" in baixo:
        return url

    return url


def _nome_do_cabecalho(resposta, url):
    """Descobre o nome do arquivo pelo cabecalho ou pela propria URL."""
    disp = resposta.headers.get("Content-Disposition", "") or ""
    achou = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disp)
    if achou:
        nome = urllib.parse.unquote(achou.group(1)).strip()
        if nome:
            return os.path.basename(nome)
    caminho = urllib.parse.urlparse(url).path
    nome = os.path.basename(urllib.parse.unquote(caminho))
    if nome and "." in nome:
        return nome
    tipo = (resposta.headers.get("Content-Type", "") or "").split(";")[0].strip()
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
           "image/gif": ".gif", "image/bmp": ".bmp",
           "image/tiff": ".tiff"}.get(tipo, ".jpg")
    return "imagem-baixada" + ext


def baixar_imagem(url, destino_pasta, avisar, cancelou):
    """Baixa uma imagem de um link e devolve o caminho do arquivo salvo."""
    direto = normalizar_link(url)
    contexto = _contexto_ssl()
    pedido = urllib.request.Request(direto, headers={
        "User-Agent": NAVEGADOR,
        "Accept": "image/*,*/*;q=0.8",
    })

    with urllib.request.urlopen(pedido, timeout=60, context=contexto) as resp:
        tipo = (resp.headers.get("Content-Type", "") or "").lower()
        bruto = resp.read()
        nome = _nome_do_cabecalho(resp, direto)

    # O Google Drive as vezes devolve uma pagina de confirmacao em vez do
    # arquivo quando ele e grande. Nesse caso, pegamos o link real da pagina.
    if "text/html" in tipo and "drive.usercontent.google.com" in direto:
        pagina = bruto.decode("utf-8", "ignore")
        achou = re.search(r'name="confirm"\s+value="([^"]+)"', pagina)
        uuid = re.search(r'name="uuid"\s+value="([^"]+)"', pagina)
        if achou or uuid:
            extra = direto
            if achou:
                extra = re.sub(r"confirm=[^&]*", "confirm=" + achou.group(1), extra)
            if uuid:
                extra += "&uuid=" + uuid.group(1)
            pedido = urllib.request.Request(extra, headers={"User-Agent": NAVEGADOR})
            with urllib.request.urlopen(pedido, timeout=120,
                                        context=contexto) as resp2:
                bruto = resp2.read()
                nome = _nome_do_cabecalho(resp2, extra)
        else:
            raise RuntimeError(
                "o link do Google Drive nao esta publico. Abra o arquivo no "
                "Drive, clique em Compartilhar e deixe como 'Qualquer pessoa "
                "com o link'.")

    if cancelou():
        raise InterruptedError

    # Confere se o que veio e mesmo uma imagem que o programa consegue abrir.
    try:
        with Image.open(io.BytesIO(bruto)) as teste:
            teste.verify()
    except Exception:
        raise RuntimeError("o link nao devolveu uma imagem que eu consiga abrir.")

    pastas.garantir(destino_pasta)
    caminho = os.path.join(destino_pasta, nome)
    base, ext = os.path.splitext(caminho)
    contador = 2
    while os.path.exists(caminho):
        caminho = "%s (%d)%s" % (base, contador, ext)
        contador += 1
    with open(caminho, "wb") as arq:
        arq.write(bruto)
    avisar("Baixado: %s (%s)" % (os.path.basename(caminho),
                                 formatar_bytes(len(bruto))))
    return caminho


def preparar_imagem(img, com_alpha):
    """Corrige a orientacao e ajusta o modo de cor da imagem."""
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if com_alpha:
        if img.mode not in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        elif img.mode == "P":
            img = img.convert("RGBA")
    else:
        if img.mode in ("RGBA", "LA", "P"):
            fundo = Image.new("RGB", img.size, (255, 255, 255))
            conv = img.convert("RGBA")
            fundo.paste(conv, mask=conv.split()[-1])
            img = fundo
        elif img.mode != "RGB":
            img = img.convert("RGB")
    return img


def redimensionar(img, escala, lado_maximo):
    """Aplica a escala e, se pedido, limita o maior lado da imagem."""
    largura, altura = img.size
    if lado_maximo and max(largura, altura) > lado_maximo:
        fator = float(lado_maximo) / float(max(largura, altura))
        largura = max(1, int(largura * fator))
        altura = max(1, int(altura * fator))
    if escala < 1.0:
        largura = max(1, int(largura * escala))
        altura = max(1, int(altura * escala))
    if (largura, altura) == img.size:
        return img
    return img.resize((largura, altura), Image.LANCZOS)


def salvar_em_memoria(img, formato, qualidade, sem_metadados):
    """Grava a imagem num buffer e devolve os bytes gerados."""
    buf = io.BytesIO()
    parametros = {}
    if formato == "JPEG":
        parametros = {
            "format": "JPEG",
            "quality": int(qualidade),
            "optimize": True,
            "progressive": True,
            "subsampling": 2 if qualidade < 90 else 0,
        }
    elif formato == "WEBP":
        parametros = {"format": "WEBP", "quality": int(qualidade), "method": 6}
    elif formato == "PNG":
        parametros = {"format": "PNG", "optimize": True, "compress_level": 9}
    if not sem_metadados:
        exif = img.info.get("exif")
        if exif and formato in ("JPEG", "WEBP"):
            parametros["exif"] = exif
        icc = img.info.get("icc_profile")
        if icc:
            parametros["icc_profile"] = icc
    img.save(buf, **parametros)
    return buf.getvalue()


# ============================================================ motor principal
class Compressor:
    """Encontra a melhor versao da imagem que ainda cabe no limite pedido."""

    def __init__(self, limite_bytes, formato_alvo, lado_maximo,
                 sem_metadados, qualidade_minima=25):
        self.limite = limite_bytes
        self.formato_alvo = formato_alvo          # "MANTER", "JPEG", "WEBP", "PNG"
        self.lado_maximo = lado_maximo            # 0 = nao limitar
        self.sem_metadados = sem_metadados
        self.qualidade_minima = qualidade_minima

    def formato_de(self, caminho):
        """Decide o formato de saida para um arquivo de entrada."""
        if self.formato_alvo != "MANTER":
            return self.formato_alvo
        ext = os.path.splitext(caminho)[1].lower()
        if ext in (".png",):
            return "PNG"
        if ext in (".webp",):
            return "WEBP"
        if ext in (".gif", ".bmp", ".tif", ".tiff"):
            return "JPEG"
        return "JPEG"

    def extensao_de(self, formato):
        return {"JPEG": ".jpg", "WEBP": ".webp", "PNG": ".png"}[formato]

    def comprimir(self, caminho, cancelou):
        """Devolve (bytes_finais, formato, tamanho_px, aviso) ou levanta erro."""
        formato = self.formato_de(caminho)
        com_alpha = formato in ("PNG", "WEBP")

        with Image.open(caminho) as bruta:
            base = preparar_imagem(bruta, com_alpha)
            base.load()

        melhor = None      # (dados, tamanho_px)
        ultimo = None      # menor resultado obtido, mesmo acima do limite

        for escala in ESCALAS:
            if cancelou():
                raise InterruptedError
            img = redimensionar(base, escala, self.lado_maximo)

            if formato == "PNG":
                dados = self._tentar_png(img, cancelou)
            else:
                dados = self._tentar_qualidade(img, formato, cancelou)

            if dados is not None:
                melhor = (dados, img.size)
                break

            corrente = self._menor_possivel(img, formato)
            if ultimo is None or len(corrente) < len(ultimo[0]):
                ultimo = (corrente, img.size)

        if melhor is not None:
            return melhor[0], formato, melhor[1], ""

        dados, tamanho = ultimo
        aviso = ("nao coube no limite; salvo no menor tamanho possivel (%s)"
                 % formatar_bytes(len(dados)))
        return dados, formato, tamanho, aviso

    def _tentar_qualidade(self, img, formato, cancelou):
        """Busca binaria pela maior qualidade que ainda cabe no limite."""
        baixo, alto = self.qualidade_minima, 95
        achou = None
        # Teste rapido: se nem na qualidade minima couber, desiste desta escala.
        minimo = salvar_em_memoria(img, formato, baixo, self.sem_metadados)
        if len(minimo) > self.limite:
            return None
        achou = minimo
        while baixo <= alto:
            if cancelou():
                raise InterruptedError
            meio = (baixo + alto) // 2
            dados = salvar_em_memoria(img, formato, meio, self.sem_metadados)
            if len(dados) <= self.limite:
                achou = dados
                baixo = meio + 1
            else:
                alto = meio - 1
        return achou

    def _tentar_png(self, img, cancelou):
        """Tenta o PNG cheio e, se nao couber, vai reduzindo o numero de cores."""
        dados = salvar_em_memoria(img, "PNG", 0, self.sem_metadados)
        if len(dados) <= self.limite:
            return dados
        for cores in CORES_PNG:
            if cancelou():
                raise InterruptedError
            reduzida = img.convert("RGBA").quantize(
                colors=cores, method=Image.FASTOCTREE)
            dados = salvar_em_memoria(reduzida, "PNG", 0, self.sem_metadados)
            if len(dados) <= self.limite:
                return dados
        return None

    def _menor_possivel(self, img, formato):
        """Menor arquivo que esta escala consegue gerar (para o caso de falha)."""
        if formato == "PNG":
            reduzida = img.convert("RGBA").quantize(
                colors=CORES_PNG[-1], method=Image.FASTOCTREE)
            return salvar_em_memoria(reduzida, "PNG", 0, self.sem_metadados)
        return salvar_em_memoria(img, formato, self.qualidade_minima,
                                 self.sem_metadados)


# ==================================================================== interface
class Aplicacao:
    def __init__(self, pai):
        self.raiz = pai
        self.raiz.configure(bg=COR_FUNDO)

        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self.arquivos = []
        self.trabalhando = False
        # O programa principal olha `rodando` antes de fechar a janela.
        self.rodando = False
        self.cancelar = threading.Event()
        self.fila = queue.Queue()
        self.pasta_saida_real = ""

        self.var_limite = tk.StringVar(value="2")
        self.var_unidade = tk.StringVar(value="MB")
        self.var_formato = tk.StringVar(value="Manter o formato original")
        self.var_limitar_lado = tk.BooleanVar(value=False)
        self.var_lado = tk.StringVar(value="1920")
        self.var_sem_meta = tk.BooleanVar(value=True)
        self.var_sufixo = tk.StringVar(value="-comprimida")
        self.links = []
        self.comprimir_depois = False
        self.var_link = tk.StringVar(value="")
        self.var_avisar_fim = tk.BooleanVar(value=True)
        self.var_saida_texto = tk.StringVar(value="")
        self.var_pasta = tk.StringVar(value=pasta_padrao_saida())
        self.var_status = tk.StringVar(value="Pronto. Adicione imagens para comecar.")

        self._montar()
        self.raiz.after(120, self._ler_fila)

    # ---------------------------------------------------- janela para dialogos
    def _janela(self):
        """A janela de verdade, para os dialogos nascerem em cima dela."""
        return self.raiz.winfo_toplevel()

    # ------------------------------------------------------------- interface
    def _montar(self):
        corpo = ttk.Frame(self.raiz)
        corpo.pack(fill="both", expand=True, padx=12, pady=(10, 8))

        # Botoes de acao e registro entram primeiro, ancorados embaixo: assim
        # eles nunca saem de vista e quem cede espaco sao as listas.
        self._bloco_acao(corpo)
        self._bloco_opcoes(corpo)

        # Imagens e links lado a lado: sao dois caminhos para a mesma coisa,
        # e juntos na mesma faixa a tela fica bem mais curta.
        topo = ttk.Frame(corpo)
        topo.pack(side="top", fill="both", expand=True)
        topo.columnconfigure(0, weight=1, uniform="colunas")
        topo.columnconfigure(1, weight=1, uniform="colunas")
        topo.rowconfigure(0, weight=1)
        coluna_esq = ttk.Frame(topo)
        coluna_esq.grid(row=0, column=0, sticky="nsew")
        coluna_dir = ttk.Frame(topo)
        coluna_dir.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._bloco_arquivos(coluna_esq)
        self._bloco_link(coluna_dir)

    def _bloco_arquivos(self, pai):
        cx = ttk.Labelframe(pai, text="Imagens", padding=(8, 6))
        cx.pack(fill="both", expand=True, pady=(0, 6))

        barra = ttk.Frame(cx)
        barra.pack(fill="x")
        ttk.Button(barra, text="Adicionar imagens",
                   command=self._add_arquivos).pack(side="left")
        ttk.Button(barra, text="Adicionar pasta",
                   command=self._add_pasta).pack(side="left", padx=6)

        moldura = tk.Frame(cx, bg=COR_BORDA, bd=0, highlightthickness=0)
        moldura.pack(fill="both", expand=True, pady=(6, 0))
        self.lista = tk.Listbox(
            moldura, height=4, activestyle="none", selectmode="extended",
            bg=COR_CAMPO, fg=COR_TEXTO, font=self.fonte_peq,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightthickness=0, bd=0)
        rolo = tk.Scrollbar(moldura, command=self.lista.yview,
                            bg=COR_BOTAO, troughcolor=COR_CAMPO,
                            activebackground=COR_BOTAO_HOVER,
                            highlightthickness=0, bd=0)
        self.lista.configure(yscrollcommand=rolo.set)
        rolo.pack(side="right", fill="y")
        self.lista.pack(side="left", fill="both", expand=True, padx=1, pady=1)

        botoes = ttk.Frame(cx)
        botoes.pack(fill="x", pady=(6, 0))
        ttk.Button(botoes, text="Remover",
                   command=self._remover).pack(side="left")
        ttk.Button(botoes, text="Limpar",
                   command=self._limpar).pack(side="left", padx=6)
        self.rotulo_lista = ttk.Label(botoes, text="Nenhuma imagem na lista.",
                                      style="Suave.TLabel")
        self.rotulo_lista.pack(side="right")

    def _bloco_link(self, pai):
        cx = ttk.Labelframe(pai, text="Links de imagens na internet",
                            padding=(8, 6))
        cx.pack(fill="both", expand=True, pady=(0, 6))

        linha = ttk.Frame(cx)
        linha.pack(fill="x")
        self.campo_link = ttk.Entry(linha, textvariable=self.var_link)
        self.campo_link.pack(side="left", fill="x", expand=True)
        self.campo_link.bind("<Return>", lambda e: self._add_link())
        ttk.Button(linha, text="+  Adicionar", command=self._add_link
                   ).pack(side="left", padx=(6, 0))

        moldura = tk.Frame(cx, bg=COR_BORDA, bd=0, highlightthickness=0)
        moldura.pack(fill="both", expand=True, pady=(6, 0))
        self.lista_links = tk.Listbox(
            moldura, height=3, activestyle="none", selectmode="extended",
            bg=COR_CAMPO, fg=COR_TEXTO, font=self.fonte_peq,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightthickness=0, bd=0)
        rolo = tk.Scrollbar(moldura, command=self.lista_links.yview,
                            bg=COR_BOTAO, troughcolor=COR_CAMPO,
                            activebackground=COR_BOTAO_HOVER,
                            highlightthickness=0, bd=0)
        self.lista_links.configure(yscrollcommand=rolo.set)
        rolo.pack(side="right", fill="y")
        self.lista_links.pack(side="left", fill="both", expand=True,
                              padx=1, pady=1)

        botoes = ttk.Frame(cx)
        botoes.pack(fill="x", pady=(6, 0))
        ttk.Button(botoes, text="Remover",
                   command=self._remover_link).pack(side="left")
        ttk.Button(botoes, text="Limpar",
                   command=self._limpar_links).pack(side="left", padx=6)
        self.rotulo_links = ttk.Label(botoes, text="Nenhum link na fila.",
                                      style="Suave.TLabel")
        self.rotulo_links.pack(side="right")

    def _bloco_opcoes(self, pai):
        cx = ttk.Labelframe(pai, text="Opcoes", padding=(8, 6))
        cx.pack(side="bottom", fill="x", pady=(0, 6))

        l0 = ttk.Frame(cx)
        l0.pack(fill="x", pady=(0, 6))
        ttk.Label(l0, text="Cada imagem no maximo:").pack(side="left")
        ttk.Entry(l0, textvariable=self.var_limite,
                  width=6).pack(side="left", padx=(6, 4))
        ttk.Combobox(l0, textvariable=self.var_unidade, width=4,
                     state="readonly", values=["KB", "MB"]).pack(side="left")
        for texto, valor, unidade in (("100 KB", "100", "KB"),
                                      ("300 KB", "300", "KB"),
                                      ("500 KB", "500", "KB"),
                                      ("1 MB", "1", "MB"),
                                      ("2 MB", "2", "MB"),
                                      ("5 MB", "5", "MB")):
            ttk.Button(l0, text=texto, width=6,
                       command=lambda v=valor, u=unidade: self._atalho(v, u)
                       ).pack(side="left", padx=2)

        l1 = ttk.Frame(cx)
        l1.pack(fill="x")
        ttk.Label(l1, text="Formato:").pack(side="left")
        ttk.Combobox(l1, textvariable=self.var_formato, width=26,
                     state="readonly",
                     values=["Manter o formato original",
                             "JPEG (menor peso, sem fundo transparente)",
                             "WebP (menor peso ainda, moderno)",
                             "PNG (mantem fundo transparente)"]
                     ).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(l1, text="Maior lado no maximo",
                        variable=self.var_limitar_lado).pack(side="left")
        ttk.Entry(l1, textvariable=self.var_lado, width=6).pack(side="left", padx=6)
        ttk.Label(l1, text="pixels", style="Suave.TLabel").pack(side="left")

        l2 = ttk.Frame(cx)
        l2.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(l2, text="Remover metadados (local, camera, data)",
                        variable=self.var_sem_meta).pack(side="left")
        ttk.Checkbutton(l2, text="Avisar quando terminar",
                        variable=self.var_avisar_fim).pack(side="left", padx=(14, 0))
        ttk.Label(l2, text="   Fim do nome:").pack(side="left")
        ttk.Entry(l2, textvariable=self.var_sufixo, width=14).pack(side="left",
                                                                   padx=6)

        l3 = ttk.Frame(cx)
        l3.pack(fill="x", pady=(6, 0))
        ttk.Label(l3, text="Salvar em:").pack(side="left")
        ttk.Entry(l3, textvariable=self.var_pasta).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(l3, text="Escolher pasta",
                   command=self._escolher_pasta).pack(side="left")

    def _bloco_acao(self, pai):
        # Ordem de empacotamento: quem entra primeiro em "bottom" fica mais
        # embaixo. Por isso o registro vem antes do rotulo que o apresenta.
        self.log = ScrolledText(pai, height=4, bg=COR_CAMPO, fg=COR_TEXTO,
                                insertbackground=COR_TEXTO,
                                selectbackground=COR_DESTAQUE,
                                selectforeground="#1a1a1a",
                                highlightthickness=1,
                                highlightbackground=COR_BORDA,
                                bd=0, font=self.fonte_peq, wrap="word")
        self.log.pack(side="bottom", fill="x")
        self.log.tag_configure("ok", foreground=COR_OK)
        self.log.tag_configure("erro", foreground=COR_ERRO)
        self.log.tag_configure("aviso", foreground=COR_DESTAQUE)
        self.log.configure(state="disabled")
        # A barra de rolagem do registro e Tk puro: precisa de cor na mao.
        try:
            self.log.vbar.configure(bg=COR_BOTAO, troughcolor=COR_CAMPO,
                                    activebackground=COR_BOTAO_HOVER,
                                    highlightthickness=0, bd=0)
        except Exception:
            pass

        ttk.Label(pai, text="Registro do que foi feito",
                  style="Suave.TLabel").pack(side="bottom", anchor="w",
                                             pady=(6, 2))

        self.rotulo_saida = ttk.Label(pai, textvariable=self.var_saida_texto,
                                      style="Destaque.TLabel",
                                      wraplength=1100, justify="left")
        self.rotulo_saida.pack(side="bottom", anchor="w", pady=(2, 0))

        ttk.Label(pai, textvariable=self.var_status,
                  style="Suave.TLabel").pack(side="bottom", anchor="w")

        self.barra = ttk.Progressbar(pai, mode="determinate",
                                     style="Horizontal.TProgressbar")
        self.barra.pack(side="bottom", fill="x", pady=(8, 3))

        botoes = ttk.Frame(pai)
        botoes.pack(side="bottom", fill="x", pady=(4, 0))
        self.bt_ok = ttk.Button(botoes, text="Comprimir", style="Acao.TButton",
                                command=self._comecar)
        self.bt_ok.pack(side="left")
        self.bt_cancelar = ttk.Button(botoes, text="Cancelar", state="disabled",
                                      command=self._cancelar)
        self.bt_cancelar.pack(side="left", padx=8)
        self.bt_abrir = ttk.Button(botoes, text="Abrir pasta de saida",
                                   state="disabled", command=self._abrir_saida)
        self.bt_abrir.pack(side="left")

    # ------------------------------------------------------------- comandos
    def _atalho(self, valor, unidade):
        self.var_limite.set(valor)
        self.var_unidade.set(unidade)

    def _add_arquivos(self):
        nomes = filedialog.askopenfilenames(
            title="Escolha as imagens",
            parent=self._janela(),
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif"),
                       ("Todos os arquivos", "*.*")])
        self._incluir(nomes)

    def _add_pasta(self):
        pasta = filedialog.askdirectory(title="Escolha a pasta com as imagens",
                                        parent=self._janela())
        if not pasta:
            return
        achados = []
        for raiz, _, arquivos in os.walk(pasta):
            for nome in sorted(arquivos):
                if nome.lower().endswith(EXTENSOES):
                    achados.append(os.path.join(raiz, nome))
        if not achados:
            messagebox.showinfo(APP_NOME, "Nao encontrei imagens nessa pasta.",
                                parent=self._janela())
            return
        self._incluir(achados)

    def _incluir(self, caminhos):
        novos = 0
        for c in caminhos:
            if c and c not in self.arquivos and os.path.isfile(c):
                self.arquivos.append(c)
                try:
                    peso = formatar_bytes(os.path.getsize(c))
                except OSError:
                    peso = "-"
                self.lista.insert("end", "%s   (%s)" % (os.path.basename(c), peso))
                novos += 1
        self._atualizar_rotulo()
        if novos:
            self.var_status.set("%d imagem(ns) adicionada(s)." % novos)

    def _add_link(self):
        """Coloca na fila o link (ou os links) escritos no campo."""
        texto = self.var_link.get().strip()
        candidatos = [p for p in texto.replace(",", " ").split() if p]
        validos = [p for p in candidatos if p.lower().startswith("http")]
        if not validos:
            messagebox.showwarning(
                APP_NOME,
                "Cole um endereco que comece com http, por exemplo o link de "
                "compartilhamento do Google Drive.",
                parent=self._janela())
            return
        novos = 0
        for url in validos:
            if url in self.links:
                continue
            self.links.append(url)
            self.lista_links.insert("end", "%d.  %s" % (len(self.links), url))
            novos += 1
        self.var_link.set("")
        self.campo_link.focus_set()
        self._atualizar_rotulo_links()
        if novos:
            self.var_status.set(
                "%d link(s) na fila. Clique em Comprimir." % len(self.links))

    def _remover_link(self):
        selecao = list(self.lista_links.curselection())
        for i in reversed(selecao):
            del self.links[i]
        self._redesenhar_links()

    def _limpar_links(self):
        self.links = []
        self._redesenhar_links()

    def _redesenhar_links(self):
        self.lista_links.delete(0, "end")
        for i, url in enumerate(self.links, start=1):
            self.lista_links.insert("end", "%d.  %s" % (i, url))
        self._atualizar_rotulo_links()

    def _atualizar_rotulo_links(self):
        if not self.links:
            self.rotulo_links.configure(text="Nenhum link na fila.")
        else:
            self.rotulo_links.configure(
                text="%d link(s) na fila." % len(self.links))

    def _baixar_link(self):
        if self.trabalhando:
            return
        # Se o usuario escreveu algo e clicou direto em Baixar, aproveitamos.
        if self.var_link.get().strip():
            self._add_link()
        validos = list(self.links)
        if not validos:
            messagebox.showwarning(
                APP_NOME,
                "A fila de links esta vazia. Cole um endereco e clique em "
                "+ Adicionar.",
                parent=self._janela())
            return

        self._marcar_trabalhando(True)
        self.cancelar.clear()
        self.bt_ok.configure(state="disabled")
        self.bt_cancelar.configure(state="normal")
        self.barra.configure(maximum=len(validos), value=0)
        self._escrever("--- Baixando %d link(s) ---" % len(validos))
        threading.Thread(target=self._trabalhar_download,
                         args=(validos,), daemon=True).start()

    def _trabalhar_download(self, links):
        destino = pasta_das_baixadas()
        baixados = []
        prontos = []   # links que baixaram: saem da fila e nao voltam
        for indice, url in enumerate(links, start=1):
            if self.cancelar.is_set():
                self.fila.put(("status", "Cancelado pelo usuario."))
                break
            self.fila.put(("status", "Baixando %d de %d..." % (indice, len(links))))
            try:
                caminho = baixar_imagem(
                    url, destino,
                    lambda m: self.fila.put(("log", "OK " + m, "ok")),
                    self.cancelar.is_set)
                baixados.append(caminho)
                prontos.append(url)
            except InterruptedError:
                self.fila.put(("status", "Cancelado pelo usuario."))
                break
            except Exception as erro:
                self.fila.put(("log", "ERRO ao baixar %s: %s" % (url, erro), "erro"))
            finally:
                self.fila.put(("progresso", indice))
        self.fila.put(("baixou", baixados, prontos))

    def _remover(self):
        selecao = list(self.lista.curselection())
        for i in reversed(selecao):
            self.lista.delete(i)
            del self.arquivos[i]
        self._atualizar_rotulo()

    def _limpar(self):
        self.lista.delete(0, "end")
        self.arquivos = []
        self._atualizar_rotulo()

    def _atualizar_rotulo(self):
        if not self.arquivos:
            self.rotulo_lista.configure(text="Nenhuma imagem na lista.")
            return
        total = 0
        for c in self.arquivos:
            try:
                total += os.path.getsize(c)
            except OSError:
                pass
        self.rotulo_lista.configure(
            text="%d imagem(ns), somando %s."
                 % (len(self.arquivos), formatar_bytes(total)))

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Escolha onde salvar",
                                        parent=self._janela(),
                                        initialdir=self.var_pasta.get().strip()
                                        or pastas.pasta_downloads())
        if pasta:
            self.var_pasta.set(pasta)

    def _abrir_saida(self):
        if self.pasta_saida_real and os.path.isdir(self.pasta_saida_real):
            abrir_no_sistema(self.pasta_saida_real)

    def _cancelar(self):
        self.cancelar.set()
        self.var_status.set("Cancelando...")

    def _marcar_trabalhando(self, ligado):
        """Um lugar so para os dois avisos de 'estou ocupada'.

        `trabalhando` e de uso interno; `rodando` e o que o Estudio consulta
        antes de fechar a janela.
        """
        self.trabalhando = ligado
        self.rodando = ligado

    # ------------------------------------------------------------- execucao
    def _limite_em_bytes(self):
        texto = self.var_limite.get().strip().replace(",", ".")
        try:
            valor = float(texto)
        except ValueError:
            return None
        if valor <= 0:
            return None
        # 1000 e nao 1024: e assim que o Finder e o Explorer mostram o
        # tamanho, e e por ali que o usuario confere se respeitou o limite.
        fator = 1000 if self.var_unidade.get() == "KB" else 1000 * 1000
        return int(valor * fator)

    def _formato_escolhido(self):
        texto = self.var_formato.get()
        if texto.startswith("JPEG"):
            return "JPEG"
        if texto.startswith("WebP"):
            return "WEBP"
        if texto.startswith("PNG"):
            return "PNG"
        return "MANTER"

    def _comecar(self):
        if self.trabalhando:
            return
        limite = self._limite_em_bytes()
        if limite is None:
            messagebox.showwarning(
                APP_NOME, "Escreva um tamanho maximo valido (por exemplo, 500).",
                parent=self._janela())
            return

        # Se ainda ha link esperando, o botao Comprimir baixa primeiro e
        # emenda a compressao sozinho: o usuario nao precisa clicar em Baixar.
        if self.links or self.var_link.get().strip():
            self.comprimir_depois = True
            self._baixar_link()
            return

        if not self.arquivos:
            messagebox.showwarning(
                APP_NOME,
                "Adicione pelo menos uma imagem, ou cole um link na fila.",
                parent=self._janela())
            return

        lado = 0
        if self.var_limitar_lado.get():
            try:
                lado = int(self.var_lado.get().strip())
            except ValueError:
                lado = 0
            if lado < 50:
                messagebox.showwarning(
                    APP_NOME, "O maior lado precisa ter pelo menos 50 pixels.",
                    parent=self._janela())
                return

        self._marcar_trabalhando(True)
        self.cancelar.clear()
        self.bt_ok.configure(state="disabled")
        self.bt_cancelar.configure(state="normal")
        self.bt_abrir.configure(state="disabled")
        self.var_saida_texto.set("")
        self.barra.configure(maximum=len(self.arquivos), value=0)
        self._escrever("--- Comecando: %d imagem(ns), limite de %s cada ---"
                       % (len(self.arquivos), formatar_bytes(limite)))

        args = (list(self.arquivos), limite, self._formato_escolhido(), lado,
                self.var_sem_meta.get(), self.var_sufixo.get().strip(),
                self.var_pasta.get().strip())
        threading.Thread(target=self._trabalhar, args=args, daemon=True).start()

    def _trabalhar(self, arquivos, limite, formato, lado, sem_meta, sufixo, pasta):
        motor = Compressor(limite, formato, lado, sem_meta)
        feitos = 0
        falhas = 0
        avisos = 0
        ganho_antes = 0
        ganho_depois = 0
        saida_final = ""

        for indice, caminho in enumerate(arquivos, start=1):
            if self.cancelar.is_set():
                self.fila.put(("status", "Cancelado pelo usuario."))
                break
            nome = os.path.basename(caminho)
            self.fila.put(("status", "Comprimindo %d de %d: %s"
                           % (indice, len(arquivos), nome)))
            try:
                destino_pasta = pasta or os.path.join(
                    os.path.dirname(caminho), "comprimidas")
                destino_pasta = pastas.garantir(destino_pasta)
                saida_final = destino_pasta

                original = os.path.getsize(caminho)
                dados, fmt, tamanho, aviso = motor.comprimir(
                    caminho, self.cancelar.is_set)

                base_nome = os.path.splitext(nome)[0] + sufixo
                destino = os.path.join(destino_pasta,
                                       base_nome + motor.extensao_de(fmt))
                destino = self._nome_livre(destino, caminho)
                with open(destino, "wb") as arq:
                    arq.write(dados)

                ganho_antes += original
                ganho_depois += len(dados)
                feitos += 1
                if aviso:
                    avisos += 1
                    self.fila.put(("log", "! %s: %s" % (nome, aviso), "aviso"))
                else:
                    corte = 100 - (len(dados) * 100.0 / original) if original else 0
                    self.fila.put((
                        "log",
                        "OK %s: %s -> %s (menos %.0f%%, %dx%d px)"
                        % (nome, formatar_bytes(original), formatar_bytes(len(dados)),
                           max(corte, 0), tamanho[0], tamanho[1]),
                        "ok"))
            except InterruptedError:
                self.fila.put(("status", "Cancelado pelo usuario."))
                break
            except Exception as erro:
                falhas += 1
                self.fila.put(("log", "ERRO %s: %s" % (nome, erro), "erro"))
            finally:
                self.fila.put(("progresso", indice))

        resumo = "Terminado. %d pronta(s)" % feitos
        if avisos:
            resumo += ", %d fora do limite" % avisos
        if falhas:
            resumo += ", %d com erro" % falhas
        if ganho_antes:
            resumo += ". Total: %s -> %s" % (formatar_bytes(ganho_antes),
                                             formatar_bytes(ganho_depois))
        self.fila.put(("log", "--- %s ---" % resumo, "ok" if not falhas else "aviso"))
        self.fila.put(("fim", saida_final, resumo))

    def _nome_livre(self, destino, origem):
        """Evita apagar o arquivo original quando a saida cai na mesma pasta."""
        if os.path.abspath(destino) != os.path.abspath(origem):
            return destino
        base, ext = os.path.splitext(destino)
        return base + "-comprimida" + ext

    # ------------------------------------------------------------- fila/UI
    def _escrever(self, texto, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n", tag or "")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _avisar_terminou(self, resumo):
        """Caixa de aviso no fim, com atalho para abrir a pasta de destino."""
        if not self.var_avisar_fim.get():
            return
        abrir = messagebox.askyesno(
            APP_NOME,
            "%s\n\nAs imagens estao em:\n%s\n\nQuer abrir essa pasta agora?"
            % (resumo, self.pasta_saida_real),
            parent=self._janela())
        if abrir:
            abrir_no_sistema(self.pasta_saida_real)

    def _ler_fila(self):
        try:
            while True:
                item = self.fila.get_nowait()
                tipo = item[0]
                if tipo == "status":
                    self.var_status.set(item[1])
                elif tipo == "log":
                    self._escrever(item[1], item[2] if len(item) > 2 else None)
                elif tipo == "progresso":
                    self.barra.configure(value=item[1])
                elif tipo == "fim":
                    self.pasta_saida_real = item[1]
                    self.var_status.set(item[2])
                    self._marcar_trabalhando(False)
                    self.bt_ok.configure(state="normal")
                    self.bt_cancelar.configure(state="disabled")
                    if self.pasta_saida_real:
                        self.bt_abrir.configure(state="normal")
                        self.var_saida_texto.set(
                            "Imagens salvas em: " + self.pasta_saida_real)
                        self._avisar_terminou(item[2])
                elif tipo == "baixou":
                    self._marcar_trabalhando(False)
                    self.bt_ok.configure(state="normal")
                    self.bt_cancelar.configure(state="disabled")
                    baixados = item[1]
                    prontos = item[2] if len(item) > 2 else []
                    emendar = self.comprimir_depois
                    self.comprimir_depois = False
                    # Sem isso, o link continuaria na fila e o Comprimir
                    # mandaria baixar tudo de novo, sem fim.
                    if prontos:
                        self.links = [u for u in self.links if u not in prontos]
                        self._redesenhar_links()
                    if baixados:
                        self._incluir(baixados)
                        self.var_link.set("")
                        if emendar:
                            self.var_status.set(
                                "Download pronto. Comprimindo...")
                            self._comecar()
                        else:
                            self.var_status.set(
                                "%d imagem(ns) baixada(s) e adicionada(s) a lista."
                                % len(baixados))
                    else:
                        self.var_status.set("Nenhuma imagem foi baixada.")
        except queue.Empty:
            pass
        self.raiz.after(120, self._ler_fila)

    # ------------------------------------------------------------ fechamento
    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        Quem pergunta se pode fechar com trabalho em andamento e o programa
        principal, olhando `self.rodando`. Aqui so se avisa a thread para
        parar.
        """
        self.cancelar.set()
        self._marcar_trabalhando(False)


def montar(pai):
    """Desenha a aba de comprimir dentro de `pai` e devolve o aplicativo."""
    return Aplicacao(pai)
