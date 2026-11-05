#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Le uma pagina aberta da internet e grava o conteudo principal em PDF.

Este arquivo nao tem interface: a tela fica em `abas/web/salvar_pdf.py`.

O PDF sai em formato de leitura (titulo, autor, data, imagens e texto), sem
menu, propaganda nem "leia tambem". O que entra e o mesmo que o site entrega
a qualquer visitante sem login.

LIMITE DE PROPOSITO: conteudo pago nao e aberto. Quando a propria pagina se
declara so para assinantes (o campo `isAccessibleForFree` igual a false), o
programa para e avisa, mesmo que o texto esteja escondido dentro do HTML.
"""

import html
import http.client
import json
import math
import os
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from io import BytesIO
from xml.etree import ElementTree

# Nivel de modulo de proposito: o PyInstaller precisa "ver" o import para
# embutir os certificados. Sem certifi, cai no pacote do proprio sistema.
try:
    import certifi
except ImportError:
    certifi = None

AGENTE = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/130.0 Safari/537.36")
LIMITE_PAGINA = 15 * 1024 * 1024
LIMITE_IMAGEM = 20 * 1024 * 1024
TEMPO_LIMITE = 30
MINIMO_PALAVRAS = 60
MENOR_IMAGEM = 200  # largura em pixels; abaixo disso e icone ou logotipo

TAGS_VAZIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
               "link", "meta", "param", "source", "track", "wbr"}
TAGS_BLOCO = {"address", "article", "aside", "blockquote", "div", "dl",
              "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
              "header", "hr", "main", "nav", "ol", "p", "pre", "section",
              "table", "ul"}
TAGS_FORA = {"aside", "audio", "button", "canvas", "embed", "footer", "form",
             "head", "header", "iframe", "input", "link", "meta", "nav",
             "noscript", "object", "script", "select", "style", "svg",
             "template", "textarea", "video"}
CLASSES_FORA = re.compile(
    r"(^|[\s_-])(ads?|advert\w*|anuncio\w*|banner\w*|breadcrumbs?|comment\w*|"
    r"comentario\w*|compartilh\w*|cookie\w*|leia-tambem|modal|newsletter\w*|"
    r"outbrain|popup|promo\w*|publicidade|read-more|recomend\w*|related|"
    r"relacionad\w*|share\w*|sharing|side-item|sidebar|social|taboola|"
    r"tag-?cloud|tags-?list)([\s_-]|$)|(post|entry|article|content)-tags?\b",
    re.I)
# O WordPress poe o assunto da materia na classe do proprio texto
# ("tag-social", "category-ads"), e layouts usam "has-sidebar" no bloco que
# guarda tudo. Essas classes nao dizem o que o bloco e, entao nao contam.
CLASSES_DESCRITIVAS = re.compile(
    r"^(tag|category|format|type|status|has|with|no|is)-", re.I)
TAGS_SEMPRE_DENTRO = {"article", "body", "html", "main"}
CLASSES_DESTAQUE = re.compile(
    r"featured|hero|lead-image|main-image|post-thumbnail|top-image|"
    r"wp-post-image", re.I)
CLASSES_SUBTITULO = re.compile(
    r"subtitle|subtitulo|standfirst|linha-fina|article-deck|\bdeck\b", re.I)
CLASSES_AUTOR = re.compile(
    r"byline|author|autor|publication-data__from", re.I)
CLASSES_TOPO = re.compile(
    r"(^|\s)(site-)?header|masthead|navbar|site-brand", re.I)
LIMITE_LOGO = 2 * 1024 * 1024
LIXO_CURTO = re.compile(
    r"^(publicidade|continua (depois|ap[oó]s) d[ao] publicidade|"
    r"leia (tamb[eé]m|mais)|veja (tamb[eé]m|mais)|saiba mais)\W*$", re.I)


class ErroPagina(Exception):
    """Falha com mensagem pronta para mostrar na tela."""


class PaginaFechada(ErroPagina):
    """A propria pagina se declarou conteudo so para assinantes."""


class Cancelado(Exception):
    """A pessoa apertou Cancelar."""


@dataclass
class Materia:
    url: str
    titulo: str = ""
    subtitulo: str = ""
    autor: str = ""
    data: str = ""
    site: str = ""
    logos: list = field(default_factory=list)
    blocos: list = field(default_factory=list)


@dataclass
class Resultado:
    caminho: str
    titulo: str
    palavras: int
    imagens: int
    imagens_perdidas: int
    paginas: int


# ------------------------------------------------------------------ rede

def _contexto_ssl():
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def normalizar_link(link):
    """Devolve o link pronto para abrir, ou levanta ErroPagina."""
    link = (link or "").strip()
    if link and "://" not in link:
        link = "https://" + link
    partes = urllib.parse.urlsplit(link)
    if partes.scheme not in ("http", "https") or "." not in partes.netloc:
        raise ErroPagina("Esse texto não parece um link de página.")
    return link


def _baixar(url, limite, referer=None):
    cabecalhos = {
        "User-Agent": AGENTE,
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    if referer:
        cabecalhos["Referer"] = referer
    pedido = urllib.request.Request(url, headers=cabecalhos)
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE,
                                context=_contexto_ssl()) as resposta:
        dados = resposta.read(limite + 1)
        if len(dados) > limite:
            raise ErroPagina("A página é grande demais para salvar.")
        return dados, resposta.headers.get_content_charset(), resposta.geturl()


def _texto_da_pagina(url):
    # Duas tentativas: a conexao pode cair no meio da leitura, e isso costuma
    # se resolver sozinho na vez seguinte.
    for tentativa in (1, 2):
        try:
            dados, charset, final = _baixar(url, LIMITE_PAGINA)
            break
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403):
                raise ErroPagina(
                    "O site recusou o acesso a esta página (erro "
                    f"{e.code}). Ela pode exigir login ou assinatura.") from e
            if e.code == 404:
                raise ErroPagina(
                    "Essa página não existe mais (erro 404).") from e
            raise ErroPagina(f"O site respondeu com erro {e.code}.") from e
        except ssl.SSLCertVerificationError as e:
            raise ErroPagina(
                "Não consegui confirmar a segurança do site. "
                f"Detalhe: {e}") from e
        except (urllib.error.URLError, http.client.HTTPException,
                TimeoutError, OSError) as e:
            if tentativa == 2:
                raise ErroPagina(
                    "Não consegui abrir a página. Confira o link e a "
                    "internet.") from e
            time.sleep(1)
    if not charset:
        achado = re.search(rb'charset=["\']?([\w-]+)', dados[:4096])
        charset = achado.group(1).decode("ascii") if achado else "utf-8"
    try:
        return dados.decode(charset, errors="replace"), final
    except LookupError:
        return dados.decode("utf-8", errors="replace"), final


# ------------------------------------------------------------- arvore HTML

class No:
    __slots__ = ("tag", "attrs", "filhos", "pai")

    def __init__(self, tag, attrs, pai=None):
        self.tag = tag
        self.attrs = attrs
        self.filhos = []
        self.pai = pai

    @property
    def classes(self):
        return f'{self.attrs.get("class") or ""} {self.attrs.get("id") or ""}'


class Arvore(HTMLParser):
    """Monta uma arvore simples e tolera HTML mal fechado."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = No("#raiz", {})
        self.atual = self.raiz

    def handle_starttag(self, tag, attrs):
        # <p> e <li> nao precisam de fechamento em HTML.
        if self.atual.tag == "p" and tag in TAGS_BLOCO:
            self.atual = self.atual.pai
        elif self.atual.tag == "li" and tag == "li":
            self.atual = self.atual.pai
        no = No(tag, {k: (v or "") for k, v in attrs}, self.atual)
        self.atual.filhos.append(no)
        if tag not in TAGS_VAZIAS:
            self.atual = no

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in TAGS_VAZIAS and self.atual.tag == tag:
            self.atual = self.atual.pai

    def handle_endtag(self, tag):
        no = self.atual
        while no is not None and no.tag != tag:
            no = no.pai
        if no is not None and no.pai is not None:
            self.atual = no.pai

    def handle_data(self, data):
        self.atual.filhos.append(data)


def _percorrer(no):
    pilha = [no]
    while pilha:
        atual = pilha.pop()
        yield atual
        pilha.extend(f for f in reversed(atual.filhos)
                     if not isinstance(f, str))


def _fora(no):
    """True para o que nao e conteudo: menu, propaganda, escondidos."""
    if no.tag in TAGS_FORA:
        return True
    if no.attrs.get("aria-hidden") == "true" or "hidden" in no.attrs:
        return True
    estilo = no.attrs.get("style", "").replace(" ", "").lower()
    if "display:none" in estilo or "visibility:hidden" in estilo:
        return True
    if no.tag in TAGS_SEMPRE_DENTRO:
        return False
    uteis = " ".join(c for c in no.classes.split()
                     if not CLASSES_DESCRITIVAS.match(c))
    return bool(CLASSES_FORA.search(uteis))


def _dentro_de_fora(no):
    while no is not None:
        if no.tag != "header" and _fora(no):
            return True
        no = no.pai
    return False


def _texto(no):
    partes = []

    def juntar(atual):
        for filho in atual.filhos:
            if isinstance(filho, str):
                partes.append(filho)
            elif not _fora(filho):
                juntar(filho)

    juntar(no)
    return re.sub(r"\s+", " ", "".join(partes)).strip()


def _texto_de_links(no):
    return sum(len(_texto(a)) for a in _percorrer(no) if a.tag == "a")


def achar_corpo(raiz):
    """Acha o bloco com mais texto corrido.

    Cada paragrafo da pontos para o pai, para o avo e para o bisavo, com peso
    menor a cada nivel. Assim o texto e encontrado tanto com paragrafos
    soltos dentro do bloco quanto com cada um embrulhado na propria caixa,
    que e como o Valor e O Globo montam as materias.
    """
    pontos = {}
    nos = {}
    for p in _percorrer(raiz):
        if p.tag != "p" or _dentro_de_fora(p):
            continue
        tamanho = len(_texto(p))
        if tamanho < 40:
            continue
        valor = tamanho - _texto_de_links(p)
        ancestral = p.pai
        for peso in (1, 2, 3):
            if ancestral is None:
                break
            pontos[id(ancestral)] = pontos.get(id(ancestral), 0) + valor / peso
            nos[id(ancestral)] = ancestral
            ancestral = ancestral.pai
    if not pontos:
        return None
    return nos[max(pontos, key=pontos.get)]


# ------------------------------------------------------------ texto e marcas

def _esc(texto):
    return html.escape(texto, quote=True)


def _limpar(marcado):
    """Tira o que nenhuma fonte desenha (emoji, simbolos de uso privado)."""
    marcado = "".join(c for c in unicodedata.normalize("NFC", marcado)
                      if ord(c) <= 0xFFFF
                      and unicodedata.category(c) not in ("Co", "Cs", "Cc")
                      or c in "\n\t")
    marcado = re.sub(r"\s+", " ", marcado)
    marcado = re.sub(r"\s*<br/>\s*", "<br/>", marcado)
    return re.sub(r"^(<br/>)+|(<br/>)+$", "", marcado.strip()).strip()


def _sem_marcas(marcado):
    return html.unescape(re.sub(r"<[^>]+>", " ", marcado))


def _marcar(filhos, base):
    """Transforma texto com negrito, italico e link no formato do PDF.

    Vem da arvore, por isso cada marca aberta sai sempre fechada.
    """
    partes = []
    for filho in filhos:
        if isinstance(filho, str):
            partes.append(_esc(filho))
            continue
        if filho.tag == "br":
            partes.append("<br/>")
            continue
        if _fora(filho) or filho.tag in ("img", "picture", "figure"):
            continue
        dentro = _marcar(filho.filhos, base)
        if not _sem_marcas(dentro).strip():
            continue
        if filho.tag in ("b", "strong"):
            dentro = f"<b>{dentro}</b>"
        elif filho.tag in ("i", "em", "cite"):
            dentro = f"<i>{dentro}</i>"
        elif filho.tag in ("sub", "sup"):
            dentro = f"<{filho.tag}>{dentro}</{filho.tag}>"
        elif filho.tag == "a":
            alvo = urllib.parse.urljoin(base, filho.attrs.get("href", ""))
            if alvo.startswith(("http://", "https://")):
                dentro = (f'<a href="{_esc(alvo)}" color="#1a5fb4">'
                          f"{dentro}</a>")
        partes.append(dentro)
    return "".join(partes)


def _url_imagem(img, base):
    conjunto = img.attrs.get("data-srcset") or img.attrs.get("srcset") or ""
    if not conjunto and img.pai is not None and img.pai.tag == "picture":
        for irmao in img.pai.filhos:
            if not isinstance(irmao, str) and irmao.tag == "source":
                conjunto = irmao.attrs.get("srcset", "")
                if conjunto:
                    break
    melhor, maior = "", -1
    for item in conjunto.split(","):
        pedacos = item.split()
        if not pedacos:
            continue
        medida = pedacos[1] if len(pedacos) > 1 else "1w"
        numero = re.sub(r"[^\d.]", "", medida) or "1"
        if float(numero) > maior:
            melhor, maior = pedacos[0], float(numero)
    candidatos = [melhor] + [img.attrs.get(a, "") for a in
                             ("data-src", "data-lazy-src", "data-original",
                              "src")]
    for url in candidatos:
        url = url.strip()
        if url and not url.startswith("data:") and "{{" not in url:
            return urllib.parse.urljoin(base, url)
    return ""


def _imagem_de(no, base):
    """Devolve (url, legenda) de uma <figure> ou <img>, ou None."""
    img = None
    for filho in _percorrer(no):
        if filho.tag == "img":
            img = filho
            break
    if img is None:
        return None
    url = _url_imagem(img, base)
    if not url:
        return None
    legenda = ""
    for filho in _percorrer(no):
        if filho.tag == "figcaption":
            legenda = _limpar(_marcar(filho.filhos, base))
            break
    return url, legenda


def _contem_bloco(no):
    return any(f.tag in TAGS_BLOCO or f.tag in ("img", "picture")
               for f in _percorrer(no) if f is not no)


def _blocos(no, base, saida):
    """Transforma o corpo da materia numa lista simples de blocos."""
    trecho = []

    def descarregar():
        marcado = _limpar(_marcar(trecho, base))
        trecho.clear()
        limpo = _sem_marcas(marcado).strip()
        if limpo and not LIXO_CURTO.match(limpo):
            saida.append(("p", marcado))

    for filho in no.filhos:
        if isinstance(filho, str):
            trecho.append(filho)
            continue
        if _fora(filho):
            continue
        if filho.tag not in TAGS_BLOCO and filho.tag not in (
                "img", "picture", "li") and not _contem_bloco(filho):
            trecho.append(filho)
            continue
        descarregar()
        if filho.tag in ("figure", "img", "picture"):
            imagem = _imagem_de(filho, base)
            if imagem:
                saida.append(("img",) + imagem)
        elif re.fullmatch(r"h[1-6]", filho.tag):
            marcado = _limpar(_marcar(filho.filhos, base))
            if _sem_marcas(marcado).strip():
                saida.append(("h", marcado))
        elif filho.tag == "p":
            _blocos(filho, base, saida)
        elif filho.tag == "blockquote":
            marcado = _limpar(_marcar(filho.filhos, base))
            if _sem_marcas(marcado).strip():
                saida.append(("q", marcado))
        elif filho.tag in ("ul", "ol"):
            numero = 0
            for item in filho.filhos:
                if isinstance(item, str) or item.tag != "li" or _fora(item):
                    continue
                numero += 1
                marcado = _limpar(_marcar(item.filhos, base))
                if _sem_marcas(marcado).strip():
                    marca = f"{numero}." if filho.tag == "ol" else "•"
                    saida.append(("li", marca, marcado))
        elif filho.tag == "table":
            for linha in _percorrer(filho):
                if linha.tag != "tr":
                    continue
                celulas = [_limpar(_marcar(c.filhos, base))
                           for c in linha.filhos
                           if not isinstance(c, str)
                           and c.tag in ("td", "th")]
                celulas = [c for c in celulas if c]
                if celulas:
                    saida.append(("p", " · ".join(celulas)))
        else:
            _blocos(filho, base, saida)
    descarregar()


# ---------------------------------------------------------------- metadados

def _metas(raiz):
    metas = {}
    for no in _percorrer(raiz):
        if no.tag != "meta":
            continue
        for chave in ("property", "name", "itemprop"):
            nome = no.attrs.get(chave, "").lower()
            if nome and nome not in metas and "content" in no.attrs:
                metas[nome] = html.unescape(no.attrs["content"]).strip()
    return metas


def _objetos_jsonld(raiz):
    def abrir(item):
        if isinstance(item, list):
            for parte in item:
                yield from abrir(parte)
        elif isinstance(item, dict):
            yield item
            yield from abrir(item.get("@graph", []))

    for no in _percorrer(raiz):
        if no.tag == "script" and "ld+json" in no.attrs.get("type", ""):
            bruto = "".join(f for f in no.filhos if isinstance(f, str))
            try:
                yield from abrir(json.loads(bruto))
            except ValueError:
                continue


def _falso(valor):
    return valor is False or str(valor).strip().lower() == "false"


def pagina_fechada(raiz, metas, objetos):
    """True quando a propria pagina se declara so para assinantes."""
    if _falso(metas.get("isaccessibleforfree", "")):
        return True
    for objeto in objetos:
        if _falso(objeto.get("isAccessibleForFree", "")):
            return True
        partes = objeto.get("hasPart", [])
        partes = partes if isinstance(partes, list) else [partes]
        for parte in partes:
            if isinstance(parte, dict) and _falso(
                    parte.get("isAccessibleForFree", "")):
                return True
    return False


def _nome_autor(valor):
    if isinstance(valor, list):
        nomes = [_nome_autor(v) for v in valor]
        return ", ".join(n for n in nomes if n)
    if isinstance(valor, dict):
        return str(valor.get("name") or "").strip()
    return str(valor or "").strip()


def _achar_autor(raiz, metas, objetos):
    for objeto in objetos:
        nome = _nome_autor(objeto.get("author"))
        if nome:
            return nome
    for no in _percorrer(raiz):
        if no.attrs.get("itemprop") != "author":
            continue
        for filho in _percorrer(no):
            if (filho.attrs.get("itemprop") == "name"
                    and filho.attrs.get("content")):
                return html.unescape(filho.attrs["content"]).strip()
        if 0 < len(_texto(no)) < 80:
            return _texto(no)
    for chave in ("author", "article:author"):
        valor = metas.get(chave, "")
        if valor and not valor.startswith("http"):
            return valor
    for no in _percorrer(raiz):
        if (no.tag in ("a", "div", "p", "span", "address")
                and CLASSES_AUTOR.search(no.classes)
                and not _dentro_de_fora(no)):
            texto = _texto(no)
            if 2 < len(texto) < 80:
                return re.sub(r"^(por|by)\s+", "", texto, flags=re.I)
    return ""


def _formatar_data(valor):
    valor = (valor or "").strip()
    try:
        data = datetime.fromisoformat(
            re.sub(r"\.\d+", "", valor).replace("Z", "+00:00"))
    except ValueError:
        return valor[:30]
    if "T" not in valor:
        return data.strftime("%d/%m/%Y")
    return data.strftime("%d/%m/%Y às %Hh%M")


def _achar_data(raiz, metas, objetos):
    for objeto in objetos:
        if objeto.get("datePublished"):
            return _formatar_data(str(objeto["datePublished"]))
    for chave in ("article:published_time", "datepublished", "date"):
        if metas.get(chave):
            return _formatar_data(metas[chave])
    for no in _percorrer(raiz):
        if no.tag == "time" and no.attrs.get("datetime"):
            return _formatar_data(no.attrs["datetime"])
    return ""


def _achar_titulo(raiz, metas, objetos):
    for no in _percorrer(raiz):
        if no.tag == "h1" and not _dentro_de_fora(no) and _texto(no):
            return _texto(no)
    if metas.get("og:title"):
        return metas["og:title"]
    for objeto in objetos:
        if objeto.get("headline"):
            return str(objeto["headline"]).strip()
    for no in _percorrer(raiz):
        if no.tag == "title" and _texto(no):
            return _texto(no)
    return "Página sem título"


def _achar_subtitulo(raiz, metas):
    for no in _percorrer(raiz):
        if (no.tag in ("h2", "p", "div")
                and CLASSES_SUBTITULO.search(no.classes)
                and not _dentro_de_fora(no)):
            texto = _texto(no)
            if 20 < len(texto) < 500:
                return texto
    return metas.get("og:description") or metas.get("description") or ""


def _no_topo(no):
    while no is not None:
        if no.tag == "header" or CLASSES_TOPO.search(no.classes):
            return True
        no = no.pai
    return False


def _achar_logos(raiz, objetos, base):
    """Links de logo do jornal, do mais confiavel para o menos."""
    achados = []

    def juntar(valor):
        if isinstance(valor, list):
            for item in valor:
                juntar(item)
        elif isinstance(valor, dict):
            juntar(valor.get("url") or valor.get("contentUrl"))
        elif isinstance(valor, str) and valor.strip():
            if not valor.startswith("data:"):
                achados.append(urllib.parse.urljoin(base, valor.strip()))

    for objeto in objetos:
        publicador = objeto.get("publisher")
        if isinstance(publicador, dict):
            juntar(publicador.get("logo"))
    for no in _percorrer(raiz):
        if no.attrs.get("itemprop") != "publisher":
            continue
        for filho in _percorrer(no):
            if filho.attrs.get("itemprop") != "logo":
                continue
            for item in _percorrer(filho):
                if item.attrs.get("itemprop") == "url":
                    juntar(item.attrs.get("content", ""))
                elif item.tag == "img":
                    juntar(_url_imagem(item, base))
    for no in _percorrer(raiz):
        if no.tag != "img":
            continue
        pistas = (f'{no.classes} {no.attrs.get("alt", "")} '
                  f'{no.attrs.get("src", "")}')
        if "logo" in pistas.lower() and _no_topo(no):
            juntar(_url_imagem(no, base))
    return list(dict.fromkeys(achados))


def _achar_destaque(raiz, corpo, metas, base):
    """Foto principal, que costuma ficar fora do bloco de texto."""
    for no in _percorrer(raiz):
        if (no.tag in ("figure", "div", "img")
                and CLASSES_DESTAQUE.search(no.classes)
                and not _dentro_de_fora(no)):
            imagem = _imagem_de(no, base)
            if imagem:
                return imagem
    url = metas.get("og:image", "")
    return (urllib.parse.urljoin(base, url), "") if url else None


def analisar(codigo_html, url):
    """Transforma o HTML numa Materia. Nao acessa a internet."""
    arvore = Arvore()
    arvore.feed(codigo_html)
    arvore.close()
    raiz = arvore.raiz
    metas = _metas(raiz)
    objetos = list(_objetos_jsonld(raiz))

    if pagina_fechada(raiz, metas, objetos):
        raise PaginaFechada(
            "Esta página é só para assinantes, e o programa não abre "
            "conteúdo pago. Quem tem assinatura pode entrar no site pelo "
            "navegador e usar Arquivo > Imprimir > Salvar como PDF.")

    corpo = achar_corpo(raiz)
    if corpo is None:
        raise ErroPagina(
            "Não encontrei o texto nesta página. Ela pode exigir login ou "
            "só montar o texto dentro do navegador.")

    materia = Materia(url=url)
    materia.titulo = _limpar(_esc(_achar_titulo(raiz, metas, objetos)))
    materia.subtitulo = _limpar(_esc(_achar_subtitulo(raiz, metas)))
    materia.autor = _limpar(_esc(_achar_autor(raiz, metas, objetos)))
    materia.data = _limpar(_esc(_achar_data(raiz, metas, objetos)))
    materia.site = _limpar(_esc(
        metas.get("og:site_name")
        or urllib.parse.urlsplit(url).netloc.replace("www.", "")))
    materia.logos = _achar_logos(raiz, objetos, url)
    _blocos(corpo, url, materia.blocos)

    # O titulo e o subtitulo ja saem no cabecalho do PDF.
    def repetido(bloco):
        if bloco[0] not in ("h", "p"):
            return False
        limpo = _sem_marcas(bloco[1]).strip()
        return limpo in (html.unescape(materia.titulo),
                         html.unescape(materia.subtitulo))

    materia.blocos = [b for b in materia.blocos if not repetido(b)]

    destaque = _achar_destaque(raiz, corpo, metas, url)
    ja_tem = {b[1] for b in materia.blocos if b[0] == "img"}
    if destaque and destaque[0] not in ja_tem:
        materia.blocos.insert(0, ("img",) + destaque)

    if contar_palavras(materia) < MINIMO_PALAVRAS:
        raise ErroPagina(
            "Encontrei muito pouco texto nesta página. Ela pode exigir login "
            "ou só montar o texto dentro do navegador.")
    return materia


def contar_palavras(materia):
    return sum(len(_sem_marcas(b[-1]).split()) for b in materia.blocos
               if b[0] in ("p", "h", "q", "li"))


# ------------------------------------------------------------------ imagens

def _preparar_imagem(url, referer):
    """Baixa e devolve (bytes JPEG, largura, altura), ou None.

    Imagem nunca derruba o PDF: se falhar, a pagina sai sem ela.
    """
    from PIL import Image

    # Duas tentativas: servidor de imagem as vezes falha uma vez e responde
    # na seguinte, e foi assim que uma foto sumiu do PDF nos testes.
    for tentativa in (1, 2):
        try:
            dados, _, _ = _baixar(url, LIMITE_IMAGEM, referer=referer)
            foto = Image.open(BytesIO(dados))
            foto.load()
            break
        except Exception:
            if tentativa == 2:
                return None
            time.sleep(0.5)
    if foto.width < MENOR_IMAGEM or foto.height < 100:
        return "pequena"
    if foto.mode in ("RGBA", "LA", "P"):
        foto = foto.convert("RGBA")
        fundo = Image.new("RGB", foto.size, "white")
        fundo.paste(foto, mask=foto.getchannel("A"))
        foto = fundo
    else:
        foto = foto.convert("RGB")
    if foto.width > 1600:
        foto = foto.resize((1600, round(foto.height * 1600 / foto.width)),
                           Image.LANCZOS)
    saida = BytesIO()
    foto.save(saida, "JPEG", quality=85, optimize=True)
    return saida.getvalue(), foto.width, foto.height


# --------------------------------------------------------------- logo em SVG
#
# Os jornais publicam o logo em SVG, formato que a biblioteca de PDF nao abre.
# Logo costuma ser desenho simples (caminhos de uma cor), entao estes poucos
# recursos bastam, sem instalar mais nada, e ele sai nitido em qualquer zoom.
# O que fugir disso (degrade, texto, foto embutida) devolve None, e o PDF
# mostra o nome do site escrito.

class SvgComplexo(Exception):
    """O desenho usa algo que este leitor simples nao sabe desenhar."""


NUMERO = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
COMANDOS = "MmLlHhVvCcSsQqTtAaZz"
IDENTIDADE = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiplicar(a, b):
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4],
            a[1] * b[4] + a[3] * b[5] + a[5])


def _ler_transformacao(texto):
    matriz = IDENTIDADE
    for nome, argumentos in re.findall(r"(\w+)\s*\(([^)]*)\)", texto or ""):
        v = [float(n) for n in NUMERO.findall(argumentos)]
        if nome == "matrix" and len(v) == 6:
            passo = tuple(v)
        elif nome == "translate" and v:
            passo = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif nome == "scale" and v:
            passo = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif nome == "rotate" and len(v) == 1:
            c, s = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
            passo = (c, s, -s, c, 0.0, 0.0)
        else:
            raise SvgComplexo(nome)
        matriz = _multiplicar(matriz, passo)
    return matriz


def _arco(x1, y1, rx, ry, graus, grande, varre, x2, y2):
    """Troca um arco por curvas, com a conta do apendice do padrao SVG."""
    if x1 == x2 and y1 == y2:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [("L", x2, y2)]
    giro = math.radians(graus % 360)
    c, s = math.cos(giro), math.sin(giro)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = c * dx + s * dy, -s * dx + c * dy
    excesso = xp ** 2 / rx ** 2 + yp ** 2 / ry ** 2
    if excesso > 1:
        rx, ry = rx * math.sqrt(excesso), ry * math.sqrt(excesso)
    baixo = rx ** 2 * yp ** 2 + ry ** 2 * xp ** 2
    alto = max(0.0, rx ** 2 * ry ** 2 - baixo)
    fator = math.sqrt(alto / baixo) if baixo else 0.0
    if grande == varre:
        fator = -fator
    cxp, cyp = fator * rx * yp / ry, -fator * ry * xp / rx
    cx = c * cxp - s * cyp + (x1 + x2) / 2
    cy = s * cxp + c * cyp + (y1 + y2) / 2
    inicio = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    fim = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx)
    abertura = fim - inicio
    if varre and abertura < 0:
        abertura += 2 * math.pi
    elif not varre and abertura > 0:
        abertura -= 2 * math.pi
    partes = max(1, math.ceil(abs(abertura) / (math.pi / 2) - 1e-9))
    passo = abertura / partes
    t = 4 / 3 * math.tan(passo / 4)

    def ponto(px, py):
        return (cx + rx * px * c - ry * py * s,
                cy + rx * px * s + ry * py * c)

    saida = []
    a = inicio
    for _ in range(partes):
        b = a + passo
        saida.append(("C",) + ponto(math.cos(a) - t * math.sin(a),
                                    math.sin(a) + t * math.cos(a))
                     + ponto(math.cos(b) + t * math.sin(b),
                             math.sin(b) - t * math.cos(b))
                     + ponto(math.cos(b), math.sin(b)))
        a = b
    saida[-1] = saida[-1][:5] + (x2, y2)
    return saida


def _ler_caminho(d):
    """Le o atributo `d` e devolve segmentos com coordenadas absolutas."""
    i = 0
    n = len(d)
    comando = None
    saida = []
    x = y = x0 = y0 = 0.0
    controle = None  # ultimo ponto de controle, para os comandos S e T
    anterior = ""

    def pular():
        nonlocal i
        while i < n and d[i] in " ,\t\r\n":
            i += 1

    def numero():
        nonlocal i
        pular()
        achado = NUMERO.match(d, i)
        if not achado:
            raise SvgComplexo("numero")
        i = achado.end()
        return float(achado.group())

    def bandeira():
        # Em SVG compacto as bandeiras do arco vem coladas: "a1 1 0 01.5.5".
        nonlocal i
        pular()
        if i >= n or d[i] not in "01":
            raise SvgComplexo("bandeira")
        i += 1
        return d[i - 1] == "1"

    while True:
        pular()
        if i >= n:
            return saida
        if d[i] in COMANDOS:
            comando = d[i]
            i += 1
        elif comando is None or comando in "Zz":
            raise SvgComplexo("caminho")
        relativo = comando.islower()
        tipo = comando.upper()
        ox, oy = (x, y) if relativo else (0.0, 0.0)

        if tipo == "Z":
            saida.append(("Z",))
            x, y = x0, y0
        elif tipo == "M":
            x, y = numero() + ox, numero() + oy
            x0, y0 = x, y
            saida.append(("M", x, y))
            comando = "l" if relativo else "L"
        elif tipo == "L":
            x, y = numero() + ox, numero() + oy
            saida.append(("L", x, y))
        elif tipo == "H":
            x = numero() + ox
            saida.append(("L", x, y))
        elif tipo == "V":
            y = numero() + oy
            saida.append(("L", x, y))
        elif tipo in "CS":
            if tipo == "C":
                x1, y1 = numero() + ox, numero() + oy
            elif anterior in ("C", "S"):
                x1, y1 = 2 * x - controle[0], 2 * y - controle[1]
            else:
                x1, y1 = x, y
            x2, y2 = numero() + ox, numero() + oy
            x, y = numero() + ox, numero() + oy
            saida.append(("C", x1, y1, x2, y2, x, y))
            controle = (x2, y2)
        elif tipo in "QT":
            if tipo == "Q":
                qx, qy = numero() + ox, numero() + oy
            elif anterior in ("Q", "T"):
                qx, qy = 2 * x - controle[0], 2 * y - controle[1]
            else:
                qx, qy = x, y
            fx, fy = numero() + ox, numero() + oy
            saida.append(("C", x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y),
                          fx + 2 / 3 * (qx - fx), fy + 2 / 3 * (qy - fy),
                          fx, fy))
            x, y = fx, fy
            controle = (qx, qy)
        else:  # A
            rx, ry, graus = numero(), numero(), numero()
            grande, varre = bandeira(), bandeira()
            fx, fy = numero() + ox, numero() + oy
            saida.extend(_arco(x, y, rx, ry, graus, grande, varre, fx, fy))
            x, y = fx, fy
        anterior = tipo


def _ler_cor(valor):
    v = (valor or "").strip().lower()
    if v in ("none", "transparent"):
        return None
    if v in ("", "black", "currentcolor"):
        return "#000000"
    if v == "white":
        return "#ffffff"
    if re.fullmatch(r"#[0-9a-f]{6}", v):
        return v
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        return "#" + "".join(c * 2 for c in v[1:])
    achado = re.fullmatch(r"rgb\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)", v)
    if achado:
        return "#" + "".join(f"{min(255, int(n)):02x}"
                             for n in achado.groups())
    raise SvgComplexo(v)  # degrade, por exemplo


def _propriedades(no):
    achadas = {k: no.get(k) for k in ("fill", "fill-rule", "stroke")
               if no.get(k)}
    for par in (no.get("style") or "").split(";"):
        nome, _, valor = par.partition(":")
        nome = nome.strip().lower()
        if nome in ("fill", "fill-rule", "stroke", "background-color"):
            achadas[nome] = valor.strip()
    return achadas


def _forma_simples(tag, no):
    """Retangulo, circulo e poligono viram caminhos comuns."""
    def n(nome):
        return float(NUMERO.match(no.get(nome) or "0").group())

    if tag == "rect":
        x, y, w, h = n("x"), n("y"), n("width"), n("height")
        return [("M", x, y), ("L", x + w, y), ("L", x + w, y + h),
                ("L", x, y + h), ("Z",)]
    if tag in ("circle", "ellipse"):
        cx, cy = n("cx"), n("cy")
        rx = n("r") if tag == "circle" else n("rx")
        ry = n("r") if tag == "circle" else n("ry")
        return ([("M", cx - rx, cy)]
                + _arco(cx - rx, cy, rx, ry, 0, False, True, cx + rx, cy)
                + _arco(cx + rx, cy, rx, ry, 0, False, True, cx - rx, cy)
                + [("Z",)])
    pontos = [float(p) for p in NUMERO.findall(no.get("points") or "")]
    pares = list(zip(pontos[::2], pontos[1::2]))
    if not pares:
        return []
    return ([("M",) + pares[0]] + [("L",) + p for p in pares[1:]] + [("Z",)])


def _transformar(segmento, m):
    saida = [segmento[0]]
    for i in range(1, len(segmento), 2):
        x, y = segmento[i], segmento[i + 1]
        saida += [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]
    return tuple(saida)


def ler_svg(dados):
    """Le o logo em SVG. Devolve as formas, ou None se nao der para desenhar.

    Texto vindo da internet: `<!ENTITY` e recusado porque serve para montar
    arquivos que explodem a memoria de quem le.
    """
    if b"<!ENTITY" in dados:
        return None
    try:
        raiz = ElementTree.fromstring(dados)
        if raiz.tag.rsplit("}", 1)[-1] != "svg":
            return None
        caixa = [float(n) for n in NUMERO.findall(raiz.get("viewBox") or "")]
        if len(caixa) != 4:
            caixa = [0.0, 0.0, float(NUMERO.match(raiz.get("width")).group()),
                     float(NUMERO.match(raiz.get("height")).group())]
        fundo = None
        if "background-color" in _propriedades(raiz):
            fundo = _ler_cor(_propriedades(raiz)["background-color"])
        formas = []

        def visitar(no, matriz, herdado):
            tag = no.tag.rsplit("}", 1)[-1]
            if tag in ("defs", "clipPath", "title", "desc", "metadata"):
                return
            if tag not in ("svg", "g", "a", "path", "rect", "circle",
                           "ellipse", "polygon", "polyline"):
                raise SvgComplexo(tag)  # texto, foto embutida, estilo em CSS
            atuais = dict(herdado)
            atuais.update(_propriedades(no))
            if _ler_cor(atuais.get("stroke", "none")) is not None:
                raise SvgComplexo("contorno")
            matriz = _multiplicar(matriz,
                                  _ler_transformacao(no.get("transform")))
            if tag in ("svg", "g", "a"):
                for filho in no:
                    visitar(filho, matriz, atuais)
                return
            cor = _ler_cor(atuais.get("fill", ""))
            if cor is None:
                return
            segmentos = (_ler_caminho(no.get("d") or "") if tag == "path"
                         else _forma_simples(tag, no))
            if segmentos:
                formas.append((cor, atuais.get("fill-rule", "nonzero"),
                               [_transformar(s, matriz) for s in segmentos]))

        visitar(raiz, (1.0, 0.0, 0.0, 1.0, -caixa[0], -caixa[1]), {})
    except (SvgComplexo, ElementTree.ParseError, ValueError, TypeError,
            AttributeError, IndexError, ZeroDivisionError):
        return None
    if not formas or caixa[2] <= 0 or caixa[3] <= 0:
        return None
    # Logo todo branco sem fundo proprio sumiria na pagina branca.
    def claro(cor):
        return sum(int(cor[i:i + 2], 16) for i in (1, 3, 5)) > 700
    if fundo is None and all(claro(f[0]) for f in formas):
        return None
    return {"formas": formas, "fundo": fundo,
            "largura": caixa[2], "altura": caixa[3]}


def _preparar_logo(url, referer):
    """Baixa o logo. Falha aqui nunca derruba o PDF."""
    from PIL import Image

    try:
        dados, _, _ = _baixar(url, LIMITE_LOGO, referer=referer)
        if b"<svg" in dados[:4096].lower():
            return ler_svg(dados)
        foto = Image.open(BytesIO(dados))
        foto.load()
        foto = foto.convert("RGBA")
    except Exception:
        return None
    fundo = Image.new("RGB", foto.size, "white")
    fundo.paste(foto, mask=foto.getchannel("A"))
    if fundo.width < 40 or fundo.convert("L").getextrema()[0] > 235:
        return None  # pequeno demais, ou branco que sumiria na pagina
    saida = BytesIO()
    fundo.save(saida, "PNG", optimize=True)
    return {"foto": saida.getvalue(), "largura": fundo.width,
            "altura": fundo.height}


# ---------------------------------------------------------------------- PDF

LOGO_LARGURA = 150  # pontos, no topo da primeira pagina
LOGO_ALTURA = 32

FONTES_MAC = "/System/Library/Fonts/Supplemental"
FONTES_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
JOGOS_DE_FONTE = (
    (FONTES_MAC, "Georgia.ttf", "Georgia Bold.ttf", "Georgia Italic.ttf",
     "Georgia Bold Italic.ttf"),
    (FONTES_WIN, "georgia.ttf", "georgiab.ttf", "georgiai.ttf",
     "georgiaz.ttf"),
)


def _registrar_fonte():
    """Embute a Georgia quando existe; senao usa a Times padrao do PDF.

    Fonte embutida acerta qualquer acento e aspas curvas, e o PDF sai igual
    em qualquer computador.
    """
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for pasta, normal, negrito, italico, ambos in JOGOS_DE_FONTE:
        arquivos = [os.path.join(pasta, n)
                    for n in (normal, negrito, italico, ambos)]
        if not all(os.path.isfile(a) for a in arquivos):
            continue
        try:
            nomes = ("Leitura", "Leitura-B", "Leitura-I", "Leitura-BI")
            for nome, arquivo in zip(nomes, arquivos):
                pdfmetrics.registerFont(TTFont(nome, arquivo))
            addMapping("Leitura", 0, 0, "Leitura")
            addMapping("Leitura", 1, 0, "Leitura-B")
            addMapping("Leitura", 0, 1, "Leitura-I")
            addMapping("Leitura", 1, 1, "Leitura-BI")
            return "Leitura", "Leitura-B", "Leitura-I"
        except Exception:
            continue
    return "Times-Roman", "Times-Bold", "Times-Italic"


def _garantir_pasta_atual():
    """Evita o erro "[Errno 2]" ao abrir a biblioteca de PDF.

    O reportlab pergunta a pasta atual na primeira vez que abre. Numa janela
    que sobreviveu a uma reinstalacao, essa pasta nao existe mais.
    """
    try:
        os.getcwd()
    except OSError:
        os.chdir(os.path.expanduser("~"))


def gravar_pdf(materia, destino, ao_progresso=None, deve_parar=None):
    """Grava a Materia em PDF. Devolve (imagens, perdidas, paginas)."""
    _garantir_pasta_atual()
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (Flowable, HRFlowable,
                                        Image as ImagemPDF, KeepTogether,
                                        Paragraph, SimpleDocTemplate, Spacer)
    except ImportError as e:
        raise ErroPagina(
            "Falta o componente que gera o PDF. Rode o instalador do Media "
            "Studio de novo, com a internet ligada.") from e

    avisar = ao_progresso or (lambda pct, texto: None)
    parar = deve_parar or (lambda: False)
    normal, negrito, italico = _registrar_fonte()
    tinta = HexColor("#1f2328")
    apoio = HexColor("#57606a")

    def estilo(nome, **extra):
        base = {"fontName": normal, "textColor": tinta, "alignment": TA_LEFT}
        base.update(extra)
        return ParagraphStyle(nome, **base)

    e_site = estilo("site", fontName=negrito, fontSize=9, leading=12,
                    textColor=apoio, spaceAfter=6)
    e_titulo = estilo("titulo", fontName=negrito, fontSize=23, leading=28,
                      spaceAfter=10)
    e_subtitulo = estilo("subtitulo", fontSize=12.5, leading=18,
                         textColor=apoio, spaceAfter=10)
    e_dados = estilo("dados", fontSize=9, leading=13, textColor=apoio)
    e_corpo = estilo("corpo", fontSize=11, leading=17, spaceAfter=9)
    e_inter = estilo("inter", fontName=negrito, fontSize=13.5, leading=18,
                     spaceBefore=10, spaceAfter=6, keepWithNext=1)
    e_citacao = estilo("citacao", fontName=italico, fontSize=11, leading=17,
                       leftIndent=16, spaceAfter=9, textColor=apoio)
    e_item = estilo("item", fontSize=11, leading=17, leftIndent=16,
                    bulletIndent=2, spaceAfter=4)
    e_legenda = estilo("legenda", fontName=italico, fontSize=8.5, leading=12,
                       textColor=apoio, spaceBefore=4, spaceAfter=12)

    margem = 2.2 * cm
    recuo = 6  # o quadro de texto do reportlab tem 6 pontos de folga por lado
    largura = A4[0] - 2 * (margem + recuo)
    altura_max = (A4[1] - 2 * margem) * 0.55

    hoje = datetime.now().strftime("%d/%m/%Y")
    site_rodape = _sem_marcas(materia.site)

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(normal, 8)
        canvas.setFillColor(apoio)
        canvas.drawString(margem + recuo, 1.2 * cm,
                          f"Fonte: {site_rodape}. Salvo em {hoje}.")
        canvas.drawRightString(A4[0] - margem - recuo, 1.2 * cm,
                               f"Página {doc.page}")
        canvas.restoreState()

    class LogoVetorial(Flowable):
        """Desenha o logo em traco, para ficar nitido em qualquer zoom."""

        def __init__(self, logo, largura_pt, altura_pt):
            super().__init__()
            self.logo = logo
            self.width = largura_pt
            self.height = altura_pt

        def wrap(self, *_):
            return self.width, self.height

        def draw(self):
            tela = self.canv
            escala = self.width / self.logo["largura"]
            if self.logo["fundo"]:
                tela.setFillColor(HexColor(self.logo["fundo"]))
                tela.rect(0, 0, self.width, self.height, stroke=0, fill=1)

            def px(x, y):
                return x * escala, self.height - y * escala

            for cor, regra, segmentos in self.logo["formas"]:
                caminho = tela.beginPath()
                for s in segmentos:
                    if s[0] == "M":
                        caminho.moveTo(*px(s[1], s[2]))
                    elif s[0] == "L":
                        caminho.lineTo(*px(s[1], s[2]))
                    elif s[0] == "C":
                        caminho.curveTo(*px(s[1], s[2]), *px(s[3], s[4]),
                                        *px(s[5], s[6]))
                    else:
                        caminho.close()
                tela.setFillColor(HexColor(cor))
                tela.drawPath(caminho, stroke=0, fill=1,
                              fillMode=0 if regra == "evenodd" else 1)

    def topo_com_logo():
        avisar(25, "Buscando o logo do site...")
        for url in materia.logos:
            logo = _preparar_logo(url, materia.url)
            if not logo:
                continue
            escala = min(LOGO_LARGURA / logo["largura"],
                         LOGO_ALTURA / logo["altura"])
            larg_pt = logo["largura"] * escala
            alt_pt = logo["altura"] * escala
            if "foto" in logo:
                return ImagemPDF(BytesIO(logo["foto"]), width=larg_pt,
                                 height=alt_pt, hAlign="LEFT")
            return LogoVetorial(logo, larg_pt, alt_pt)
        return None

    def maiusculas(marcado):
        return _esc(html.unescape(marcado).upper())

    logo_pdf = topo_com_logo()
    if logo_pdf is not None:
        historia = [logo_pdf, Spacer(1, 8)]
    else:
        historia = [Paragraph(maiusculas(materia.site), e_site)]
    historia.append(Paragraph(materia.titulo, e_titulo))
    if materia.subtitulo:
        historia.append(Paragraph(materia.subtitulo, e_subtitulo))
    dados = " · ".join(d for d in (materia.autor, materia.data) if d)
    if dados:
        historia.append(Paragraph(dados, e_dados))
    link = _esc(materia.url)
    historia.append(Paragraph(
        f'<a href="{link}" color="#1a5fb4">{link}</a>',
        estilo("link", fontSize=7.5, leading=11, spaceBefore=2)))
    historia.append(Spacer(1, 8))
    historia.append(HRFlowable(width="100%", thickness=0.6, color=apoio,
                               spaceAfter=14))

    total = max(1, sum(1 for b in materia.blocos if b[0] == "img"))
    imagens = perdidas = vistas = 0
    for bloco in materia.blocos:
        if parar():
            raise Cancelado()
        tipo = bloco[0]
        if tipo == "p":
            historia.append(Paragraph(bloco[1], e_corpo))
        elif tipo == "h":
            historia.append(Paragraph(bloco[1], e_inter))
        elif tipo == "q":
            historia.append(Paragraph(bloco[1], e_citacao))
        elif tipo == "li":
            historia.append(Paragraph(bloco[2], e_item, bulletText=bloco[1]))
        elif tipo == "img":
            vistas += 1
            avisar(30 + 50 * vistas / total,
                   f"Baixando a imagem {vistas} de {total}...")
            foto = _preparar_imagem(bloco[1], materia.url)
            if foto == "pequena":
                continue
            if foto is None:
                perdidas += 1
                continue
            dados_foto, larg, alt = foto
            escala = min(largura / larg, altura_max / alt)
            grupo = [ImagemPDF(BytesIO(dados_foto), width=larg * escala,
                               height=alt * escala, hAlign="LEFT")]
            if bloco[2]:
                grupo.append(Paragraph(bloco[2], e_legenda))
            else:
                grupo.append(Spacer(1, 12))
            historia.append(KeepTogether(grupo))
            imagens += 1

    avisar(85, "Montando o PDF...")
    temporario = destino + ".parcial"
    documento = SimpleDocTemplate(
        temporario, pagesize=A4, leftMargin=margem, rightMargin=margem,
        topMargin=margem, bottomMargin=margem,
        title=_sem_marcas(materia.titulo),
        author=_sem_marcas(materia.autor or materia.site),
        subject=materia.url, creator="Media Studio")
    try:
        documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)
        if parar():
            raise Cancelado()
        os.replace(temporario, destino)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)
    return imagens, perdidas, documento.page


# ------------------------------------------------------------- nome do PDF

def caminho_livre(pasta, titulo, site):
    """Nome do arquivo a partir do titulo, sem apagar PDF ja existente."""
    limpo = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", _sem_marcas(titulo))
    limpo = re.sub(r"\s+", " ", limpo).strip(" .")
    if len(limpo) > 90:
        limpo = limpo[:90].rsplit(" ", 1)[0]
    site = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", _sem_marcas(site)).strip()
    base = f"{limpo or 'Pagina'} - {site}" if site else (limpo or "Pagina")
    caminho = os.path.join(pasta, base + ".pdf")
    numero = 2
    while os.path.exists(caminho):
        caminho = os.path.join(pasta, f"{base} ({numero}).pdf")
        numero += 1
    return caminho


# --------------------------------------------------------- caminho completo

def salvar_pagina_em_pdf(link, pasta, ao_progresso=None, deve_parar=None):
    """Faz tudo: abre o link, separa o conteudo e grava o PDF."""
    avisar = ao_progresso or (lambda pct, texto: None)
    parar = deve_parar or (lambda: False)

    url = normalizar_link(link)
    avisar(5, "Abrindo a página...")
    codigo, final = _texto_da_pagina(url)
    if parar():
        raise Cancelado()

    avisar(20, "Separando o texto...")
    materia = analisar(codigo, final)

    os.makedirs(pasta, exist_ok=True)
    destino = caminho_livre(pasta, materia.titulo, materia.site)
    imagens, perdidas, paginas = gravar_pdf(materia, destino, avisar, parar)
    avisar(100, "Pronto.")
    return Resultado(destino, _sem_marcas(materia.titulo),
                     contar_palavras(materia), imagens, perdidas, paginas)
