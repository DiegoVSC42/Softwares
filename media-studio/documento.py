#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Le e grava arquivos .docx sem biblioteca nenhuma instalada.

Um .docx e um arquivo .zip com XML dentro. Ler e gravar na mao, com o
`zipfile` e o `xml` que ja vem no Python, evita o problema de o programa
empacotado (.app / .exe) precisar de uma biblioteca que a maquina do usuario
nao tem. E o mesmo motivo pelo qual o icone e desenhado na mao.

So o que este programa precisa esta implementado: paragrafos de texto simples.
Nao le tabela, imagem, nem formatacao, e nao grava nada disso.
"""

import os
import re
import zipfile
from xml.etree import ElementTree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": W}


# --------------------------------------------------------------------- ler

def _ler_texto(caminho):
    """Le um arquivo de texto puro, tentando as codificacoes usuais."""
    for codificacao in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(caminho, encoding=codificacao) as arquivo:
                conteudo = arquivo.read()
        except UnicodeDecodeError:
            continue
        # O TextEdit do Mac salva em RTF por padrao. Se a pessoa trocou so a
        # extensao para .txt, o que chega aqui e um monte de codigo de
        # formatacao, e nao a transcricao. Melhor avisar do que processar lixo.
        if conteudo.lstrip().startswith("{\\rtf"):
            raise ValueError(
                "Este arquivo esta em RTF, nao em texto puro. No TextEdit, "
                "use o menu Formatar e escolha 'Tornar Texto Simples' antes "
                "de salvar."
            )
        return conteudo.splitlines()
    raise ValueError("Nao consegui ler este arquivo de texto.")


def ler_paragrafos(caminho):
    """Devolve a lista de paragrafos de um arquivo.

    Aceita .docx, .txt e, na pratica, qualquer arquivo de texto puro, com
    qualquer extensao: o que manda e o conteudo, nao o nome. Assim ninguem
    perde tempo com "extensao errada".
    """
    if not os.path.exists(caminho):
        raise ValueError(
            "Este arquivo nao esta mais onde estava. Ele foi movido, "
            "renomeado ou apagado depois de entrar na lista."
        )
    if not os.access(caminho, os.R_OK):
        raise ValueError("O Mac nao deixou abrir este arquivo (sem permissao "
                         "de leitura).")

    # Um .docx e um .zip. Se o arquivo nao comeca com a assinatura de zip,
    # ele e texto, tenha a extensao que tiver.
    with open(caminho, "rb") as arquivo:
        assinatura = arquivo.read(2)
    if assinatura != b"PK":
        return _ler_texto(caminho)

    try:
        with zipfile.ZipFile(caminho) as pacote:
            bruto = pacote.read("word/document.xml")
    except KeyError:
        raise ValueError(
            "Este arquivo e um pacote compactado, mas nao um documento do "
            "Word. Se ele veio do Google Docs, baixe de novo escolhendo "
            "'Microsoft Word (.docx)'."
        )
    except zipfile.BadZipFile:
        raise ValueError(
            "Nao consegui abrir este arquivo. Ele pode estar corrompido."
        )

    raiz = ElementTree.fromstring(bruto)
    paragrafos = []
    for p in raiz.iter("{%s}p" % W):
        pedacos = []
        for filho in p.iter():
            etiqueta = filho.tag
            if etiqueta == "{%s}t" % W:
                pedacos.append(filho.text or "")
            elif etiqueta in ("{%s}tab" % W, "{%s}br" % W):
                pedacos.append(" ")
        paragrafos.append("".join(pedacos))
    return paragrafos


# ------------------------------------------------------------------ gravar

_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))
# Caracteres de controle que o Word recusa dentro do XML.
_PROIBIDOS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _texto_xml(texto):
    texto = _PROIBIDOS.sub("", texto)
    for de, para in _ESCAPES:
        texto = texto.replace(de, para)
    return texto


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# Fonte de leitura confortavel, com espaco entre paragrafos.
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="%s">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
<w:sz w:val="22"/><w:szCs w:val="22"/>
</w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
<w:name w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="276" w:lineRule="auto"/></w:pPr>
</w:style>
</w:styles>""" % W


# Os horarios no meio da fala saem em cinza, como aparecem na tela do
# TurboScribe: assim eles guiam sem competir com o texto na leitura.
_HORARIO = re.compile(r"(\(\d{1,2}:\d{2}(?::\d{2})?\))")
_CINZA = "7a7a7a"


def _paragrafo(texto, negrito=False, tamanho=None, cor=None, depois=0):
    """Monta um paragrafo de uma corrida so."""
    formato = ""
    if negrito or tamanho or cor:
        formato = "<w:rPr>%s%s%s</w:rPr>" % (
            "<w:b/>" if negrito else "",
            '<w:color w:val="%s"/>' % cor if cor else "",
            '<w:sz w:val="%d"/>' % tamanho if tamanho else "")
    espaco = ('<w:pPr><w:spacing w:after="%d"/></w:pPr>' % depois) if depois else ""
    return ('<w:p>%s<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p>'
            % (espaco, formato, _texto_xml(texto)))


def _paragrafo_fala(texto):
    """Paragrafo de fala: horarios em cinza, o resto na cor normal."""
    corridas = []
    for pedaco in _HORARIO.split(texto):
        if not pedaco:
            continue
        if _HORARIO.fullmatch(pedaco):
            corridas.append(
                '<w:r><w:rPr><w:color w:val="%s"/><w:sz w:val="18"/></w:rPr>'
                '<w:t xml:space="preserve">%s</w:t></w:r>'
                % (_CINZA, _texto_xml(pedaco)))
        else:
            corridas.append('<w:r><w:t xml:space="preserve">%s</w:t></w:r>'
                            % _texto_xml(pedaco))
    return "<w:p>%s</w:p>" % "".join(corridas)


def gravar_paragrafos(caminho, itens, titulo=None, data=None):
    """Grava o .docx.

    `itens` e a lista de pares (texto, marca) que sai do conversor: NOME sai
    em negrito, FALA sai com os horarios em cinza, VAZIO e linha em branco.
    Para compatibilidade, uma lista de textos simples tambem funciona.
    """
    corpo = []
    if titulo:
        corpo.append(_paragrafo(titulo, negrito=True, tamanho=30,
                                depois=0 if data else 280))
    if data:
        corpo.append(_paragrafo(data, cor=_CINZA, tamanho=18, depois=280))

    for item in itens:
        texto, marca = item if isinstance(item, tuple) else (item, None)
        if not texto:
            corpo.append("<w:p/>")
        elif marca == "nome":
            corpo.append(_paragrafo(texto, negrito=True))
        else:
            corpo.append(_paragrafo_fala(texto))

    documento = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="%s"><w:body>%s'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        '</w:sectPr></w:body></w:document>' % (W, "".join(corpo))
    )

    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("[Content_Types].xml", _CONTENT_TYPES)
        pacote.writestr("_rels/.rels", _RELS)
        pacote.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        pacote.writestr("word/styles.xml", _STYLES)
        pacote.writestr("word/document.xml", documento)


def gravar_texto(caminho, itens, titulo=None, data=None):
    linhas = []
    if titulo:
        linhas.append(titulo)
    if data:
        linhas.append(data)
    if linhas:
        linhas.append("")
    for item in itens:
        texto = item[0] if isinstance(item, tuple) else item
        linhas.append(texto)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
