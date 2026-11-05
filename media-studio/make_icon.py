#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desenha o icone do Media Studio e grava como PNG, sem depender de biblioteca
externa nenhuma para o PNG em si (montado na mao com zlib + struct).

Uso:  python3 make_icon.py <arquivo.png> [tamanho] [estilo] [amostras]

Estilos: grade, onda, nucleo

Tres conceitos, para tres leituras diferentes do mesmo programa:

  grade   4 blocos (video, audio, imagem, transcricao), cada um com a cor
          que ja identifica aquela familia na propria janela do programa
          (o Ok.TLabel do audio, o Destaque laranja do video...). E o
          conceito mais direto: "sao 4 programas, agora numa cara so".

  onda    um play de video que vira onda de audio. Mais enxuto, mais "logo
          de app", menos "infografico".

  nucleo  quatro braços coloridos (um por familia) convergindo num centro
          claro. O angulo proprio: nao e "4 blocos lado a lado", e "tudo
          desaguando no mesmo lugar" - que e exatamente por que este
          programa existe.

Duas coisas cuidam do acabamento, e nenhuma das duas e opcional:

* cada pixel sai da media de varias amostras (supersampling), o que da a
  borda suave que o desenho direto nao tem; e
* nada e chapado: fundo e figura tem degrade proprio, mais um fio de luz na
  borda de cima, para o icone nao parecer um adesivo colado.

A silhueta e um "squircle" (superelipse), que e a forma real dos icones do
macOS. Retangulo de cantos arredondados entrega o icone com cara de amador.

Duas rotas para o mesmo desenho:

  RAPIDA  usa numpy (calcula a imagem inteira de uma vez, em bloco) --
          sub-segundo mesmo em 1024px com 16 amostras por pixel.
  LENTA   pixel a pixel, em Python puro, sem numpy -- e o desenho
          original, mantido como rede de seguranca para quando numpy nao
          estiver disponivel (por exemplo, chamado fora do bundle, sem o
          PYTHONPATH apontando pra pasta "libs" embutida).

O `main()` tenta a rapida primeiro e so cai pra lenta se numpy faltar ou se
algo no caminho rapido der errado -- o instalador nunca fica sem icone por
causa disso, so mais lento nesse caso raro.
"""

import struct
import sys
import zlib

try:
    import numpy as np
    _TEM_NUMPY = True
except Exception:
    _TEM_NUMPY = False

# Fundo, do topo para a base (a mesma paleta escura do resto da casa).
FUNDO_TOPO = (32, 41, 58)
FUNDO_BASE = (11, 14, 20)

# Fio de luz na borda superior de cada forma.
BRILHO = (255, 240, 222)

# Uma cor por familia, coerente com o que cada uma ja usa dentro do
# programa: laranja e a cor de destaque geral (video), verde e o Ok.TLabel
# (audio), azul e roxo sao os dois que faltavam para dar 4 tons distintos
# sem repetir o laranja do Acao.TButton.
COR_VIDEO = ((255, 186, 106), (232, 126, 30))       # laranja
COR_AUDIO = ((126, 231, 135), (46, 160, 67))         # verde
COR_IMAGEM = ((121, 192, 255), (56, 139, 253))       # azul
COR_TRANSCRICAO = ((210, 168, 255), (163, 113, 247))  # roxo

ESTILOS = ("grade", "onda", "nucleo")
ESTILO = "grade"


def misturar(a, b, t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


# ---------------------------------------------------------------------------
# Formas. Tudo em coordenadas de 0 a 1, para o desenho nao depender do tamanho.
# ---------------------------------------------------------------------------

def no_squircle(x, y, margem=0.035, n=4.2):
    meio = 0.5
    raio = meio - margem
    dx = abs(x - meio) / raio
    dy = abs(y - meio) / raio
    if dx > 1.0 or dy > 1.0:
        return False
    return (dx ** n + dy ** n) <= 1.0


def em_retangulo_redondo(x, y, esq, topo, dir_, base, r):
    if x < esq or x > dir_ or y < topo or y > base:
        return False
    if r <= 0:
        return True
    cx = esq + r if x < esq + r else (dir_ - r if x > dir_ - r else None)
    cy = topo + r if y < topo + r else (base - r if y > base - r else None)
    if cx is None or cy is None:
        return True
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def no_circulo(x, y, cx, cy, r):
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def cor_do_fundo(x, y):
    # Degrade na diagonal: o canto de cima a esquerda pega mais luz.
    return misturar(FUNDO_TOPO, FUNDO_BASE, (y * 0.78) + (x * 0.22))


def _sombreado(topo, base, y, cor_topo, cor_base, brilho_ativo):
    """Degrade vertical de uma forma solida, com fio de luz no topo."""
    if brilho_ativo:
        return BRILHO
    t = 0.0 if base == topo else (y - topo) / (base - topo)
    return misturar(cor_topo, cor_base, t)


# --- estilo "grade": 4 blocos, um por familia -------------------------------

_G = 0.045       # vao entre os blocos
_M = 0.145       # margem ate a borda do squircle
_MEIO = 0.5

GRADE_BLOCOS = (
    # (esq, topo, dir, base, cor_topo, cor_base)
    (_M, _M, _MEIO - _G / 2, _MEIO - _G / 2, COR_VIDEO[0], COR_VIDEO[1]),
    (_MEIO + _G / 2, _M, 1 - _M, _MEIO - _G / 2, COR_AUDIO[0], COR_AUDIO[1]),
    (_M, _MEIO + _G / 2, _MEIO - _G / 2, 1 - _M, COR_IMAGEM[0], COR_IMAGEM[1]),
    (_MEIO + _G / 2, _MEIO + _G / 2, 1 - _M, 1 - _M,
     COR_TRANSCRICAO[0], COR_TRANSCRICAO[1]),
)
GRADE_R = 0.075
GRADE_ESPESSURA_BRILHO = 0.014


def cor_grade(x, y):
    for esq, topo, dir_, base, c_topo, c_base in GRADE_BLOCOS:
        if em_retangulo_redondo(x, y, esq, topo, dir_, base, GRADE_R):
            brilho = not em_retangulo_redondo(
                x, y - GRADE_ESPESSURA_BRILHO, esq, topo, dir_, base, GRADE_R)
            return _sombreado(topo, base, y, c_topo, c_base, brilho)
    if no_squircle(x, y):
        return cor_do_fundo(x, y)
    return None


# --- estilo "onda": play de video virando onda de audio ---------------------

PLAY = ((0.280, 0.295), (0.280, 0.705), (0.560, 0.500))   # triangulo
ONDA_BARRAS = (
    # (centro_x, meia_largura, altura) - alturas variadas, tipo forma de onda
    (0.640, 0.028, 0.150),
    (0.705, 0.028, 0.280),
    (0.770, 0.028, 0.400),
    (0.835, 0.028, 0.230),
)
ONDA_R = 0.026
ONDA_ESPESSURA_BRILHO = 0.012


def _no_triangulo(x, y, p1, p2, p3):
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d1 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
    d2 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
    d3 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
    negativo = (d1 < 0) or (d2 < 0) or (d3 < 0)
    positivo = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (negativo and positivo)


def _na_barra(x, y, i):
    cx, meia, alt = ONDA_BARRAS[i]
    topo = 0.5 - alt / 2
    base = 0.5 + alt / 2
    return em_retangulo_redondo(x, y, cx - meia, topo, cx + meia, base,
                                ONDA_R)


def cor_onda(x, y):
    if _no_triangulo(x, y, *PLAY):
        brilho = not _no_triangulo(x - 0.0, y - ONDA_ESPESSURA_BRILHO, *PLAY)
        topo_y, base_y = PLAY[0][1], PLAY[1][1]
        return _sombreado(topo_y, base_y, y, COR_VIDEO[0], COR_VIDEO[1],
                          brilho)
    for i in range(len(ONDA_BARRAS)):
        if _na_barra(x, y, i):
            _cx, _meia, alt = ONDA_BARRAS[i]
            topo = 0.5 - alt / 2
            base = 0.5 + alt / 2
            brilho = not em_retangulo_redondo(
                x, y - ONDA_ESPESSURA_BRILHO,
                _cx - _meia, topo, _cx + _meia, base, ONDA_R)
            cores = (COR_VIDEO, COR_AUDIO, COR_IMAGEM, COR_TRANSCRICAO)
            c_topo, c_base = cores[i % len(cores)]
            return _sombreado(topo, base, y, c_topo, c_base, brilho)
    if no_squircle(x, y):
        return cor_do_fundo(x, y)
    return None


# --- estilo "nucleo": 4 bracos coloridos convergindo num centro claro -------

NUCLEO_CX, NUCLEO_CY = 0.5, 0.5
NUCLEO_R_CENTRO = 0.100
NUCLEO_LARGURA = 0.150      # largura de cada braco
NUCLEO_COMPRIMENTO = 0.300  # do fim do centro ate a ponta
NUCLEO_R_BRACO = 0.060
NUCLEO_GAP = 0.018          # afastamento do centro, pra nao virar uma mancha so

# Ordem: cima (video), direita (audio), baixo (imagem), esquerda (transcricao)
NUCLEO_BRACOS = (
    ("cima", COR_VIDEO),
    ("direita", COR_AUDIO),
    ("baixo", COR_IMAGEM),
    ("esquerda", COR_TRANSCRICAO),
)


def _faixa_braco(direcao):
    meia = NUCLEO_LARGURA / 2
    inicio = NUCLEO_R_CENTRO + NUCLEO_GAP
    fim = inicio + NUCLEO_COMPRIMENTO
    if direcao == "cima":
        return (NUCLEO_CX - meia, NUCLEO_CY - fim,
                NUCLEO_CX + meia, NUCLEO_CY - inicio)
    if direcao == "baixo":
        return (NUCLEO_CX - meia, NUCLEO_CY + inicio,
                NUCLEO_CX + meia, NUCLEO_CY + fim)
    if direcao == "esquerda":
        return (NUCLEO_CX - fim, NUCLEO_CY - meia,
                NUCLEO_CX - inicio, NUCLEO_CY + meia)
    return (NUCLEO_CX + inicio, NUCLEO_CY - meia,
            NUCLEO_CX + fim, NUCLEO_CY + meia)


def cor_nucleo(x, y):
    for direcao, (c_topo, c_base) in NUCLEO_BRACOS:
        esq, topo, dir_, base = _faixa_braco(direcao)
        if em_retangulo_redondo(x, y, esq, topo, dir_, base, NUCLEO_R_BRACO):
            brilho = not em_retangulo_redondo(
                x, y - 0.012, esq, topo, dir_, base, NUCLEO_R_BRACO)
            # O degrade sempre corre "de longe do centro" para "perto do
            # centro", nao em y cru, pra funcionar nos 4 bracos.
            if direcao in ("cima", "baixo"):
                perto = (base - y) / (base - topo) if direcao == "baixo" \
                    else (y - topo) / (base - topo)
            else:
                perto = (dir_ - x) / (dir_ - esq) if direcao == "esquerda" \
                    else (x - esq) / (dir_ - esq)
            return _sombreado(0, 1, 1 - perto, c_topo, c_base, brilho)
    if no_circulo(x, y, NUCLEO_CX, NUCLEO_CY, NUCLEO_R_CENTRO):
        borda = not no_circulo(x, y - 0.010, NUCLEO_CX, NUCLEO_CY,
                               NUCLEO_R_CENTRO)
        if borda:
            return BRILHO
        return misturar((255, 255, 255), (238, 228, 214),
                        (y - (NUCLEO_CY - NUCLEO_R_CENTRO))
                        / (2 * NUCLEO_R_CENTRO))
    if no_squircle(x, y):
        return cor_do_fundo(x, y)
    return None


# ---------------------------------------------------------------------------

def configurar(estilo):
    global ESTILO
    if estilo not in ESTILOS:
        raise SystemExit("estilo desconhecido: %s (use %s)"
                         % (estilo, ", ".join(ESTILOS)))
    ESTILO = estilo


def cor_da_amostra(x, y):
    if ESTILO == "grade":
        return cor_grade(x, y)
    if ESTILO == "onda":
        return cor_onda(x, y)
    if ESTILO == "nucleo":
        return cor_nucleo(x, y)
    return None


# ---------------------------------------------------------------------------
# Caminho LENTO: pixel a pixel, em Python puro. Rede de seguranca para quando
# numpy nao estiver disponivel. Um icone de 1024px com 16 amostras por pixel
# aqui pode passar de um minuto numa maquina mais lenta -- e foi exatamente
# isso que deixou um instalador real parecendo travado. O caminho RAPIDO
# (mais abaixo) resolve isso fazendo a mesma conta em bloco, com numpy.
# ---------------------------------------------------------------------------

def desenhar(lado, amostras=3):
    """Matriz lado x lado de RGBA. Cada pixel e a media de amostras x amostras
    pontos, o que suaviza toda borda do desenho."""
    tela = []
    passo = 1.0 / (lado * amostras)
    meio_passo = passo / 2.0
    total = float(amostras * amostras)

    for py in range(lado):
        linha = []
        base_y = py * amostras
        for px in range(lado):
            base_x = px * amostras
            soma_r = soma_g = soma_b = 0.0
            cobertos = 0
            for sy in range(amostras):
                y = (base_y + sy) * passo + meio_passo
                for sx in range(amostras):
                    x = (base_x + sx) * passo + meio_passo
                    cor = cor_da_amostra(x, y)
                    if cor is None:
                        continue
                    cobertos += 1
                    soma_r += cor[0]
                    soma_g += cor[1]
                    soma_b += cor[2]
            if cobertos == 0:
                linha.append((0, 0, 0, 0))
                continue
            linha.append((
                int(round(soma_r / cobertos)),
                int(round(soma_g / cobertos)),
                int(round(soma_b / cobertos)),
                int(round(255 * cobertos / total)),
            ))
        tela.append(linha)
    return tela


def gravar_png(caminho, tela):
    largura = len(tela[0])
    cru = bytearray()
    for linha in tela:
        cru.append(0)  # filtro "nenhum"
        for r, g, b, a in linha:
            cru += bytes((r, g, b, a))

    def bloco(tipo, dados):
        conteudo = tipo + dados
        return (struct.pack(">I", len(dados)) + conteudo
                + struct.pack(">I", zlib.crc32(conteudo) & 0xFFFFFFFF))

    cabecalho = struct.pack(">IIBBBBB", largura, len(tela), 8, 6, 0, 0, 0)
    with open(caminho, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(bloco(b"IHDR", cabecalho))
        f.write(bloco(b"IDAT", zlib.compress(bytes(cru), 9)))
        f.write(bloco(b"IEND", b""))


# ---------------------------------------------------------------------------
# Caminho RAPIDO: a mesma conta acima, mas em bloco (a imagem inteira de uma
# vez), com numpy. Cada funcao "_np" abaixo e a versao vetorizada da sua
# irma sem sufixo, e segue a MESMA ordem de prioridade (primeira forma que
# cobrir o ponto vence) atraves de uma mascara "ja_atribuido", pra dar
# pixel-a-pixel o mesmo resultado do caminho lento.
# ---------------------------------------------------------------------------

def _no_squircle_np(X, Y, margem=0.035, n=4.2):
    meio = 0.5
    raio = meio - margem
    dx = np.abs(X - meio) / raio
    dy = np.abs(Y - meio) / raio
    dentro_caixa = (dx <= 1.0) & (dy <= 1.0)
    valor = np.where(dentro_caixa, dx ** n + dy ** n, 2.0)
    return valor <= 1.0


def _em_retangulo_redondo_np(X, Y, esq, topo, dir_, base, r):
    dentro = (X >= esq) & (X <= dir_) & (Y >= topo) & (Y <= base)
    if r <= 0:
        return dentro
    cx = np.clip(X, esq + r, dir_ - r)
    cy = np.clip(Y, topo + r, base - r)
    no_canto_x = (X < esq + r) | (X > dir_ - r)
    no_canto_y = (Y < topo + r) | (Y > base - r)
    no_canto = no_canto_x & no_canto_y
    dist2 = (X - cx) ** 2 + (Y - cy) ** 2
    return dentro & (~no_canto | (dist2 <= r * r))


def _no_circulo_np(X, Y, cx, cy, r):
    return (X - cx) ** 2 + (Y - cy) ** 2 <= r * r


def _cor_do_fundo_np(X, Y):
    t = np.clip((Y * 0.78) + (X * 0.22), 0.0, 1.0)
    r = FUNDO_TOPO[0] + (FUNDO_BASE[0] - FUNDO_TOPO[0]) * t
    g = FUNDO_TOPO[1] + (FUNDO_BASE[1] - FUNDO_TOPO[1]) * t
    b = FUNDO_TOPO[2] + (FUNDO_BASE[2] - FUNDO_TOPO[2]) * t
    return r, g, b


def _sombreado_np(topo, base, Y, cor_topo, cor_base, brilho_mask):
    t = (np.zeros(Y.shape) if base == topo
         else np.clip((Y - topo) / (base - topo), 0.0, 1.0))
    r = cor_topo[0] + (cor_base[0] - cor_topo[0]) * t
    g = cor_topo[1] + (cor_base[1] - cor_topo[1]) * t
    b = cor_topo[2] + (cor_base[2] - cor_topo[2]) * t
    r = np.where(brilho_mask, BRILHO[0], r)
    g = np.where(brilho_mask, BRILHO[1], g)
    b = np.where(brilho_mask, BRILHO[2], b)
    return r, g, b


def _compor(R, G, B, assigned, m, r, g, b):
    m = m & ~assigned
    R = np.where(m, r, R)
    G = np.where(m, g, G)
    B = np.where(m, b, B)
    return R, G, B, assigned | m


def _cor_grade_np(X, Y):
    shape = X.shape
    assigned = np.zeros(shape, dtype=bool)
    R = np.zeros(shape)
    G = np.zeros(shape)
    B = np.zeros(shape)
    for esq, topo, dir_, base, c_topo, c_base in GRADE_BLOCOS:
        m = _em_retangulo_redondo_np(X, Y, esq, topo, dir_, base, GRADE_R)
        brilho = ~_em_retangulo_redondo_np(
            X, Y - GRADE_ESPESSURA_BRILHO, esq, topo, dir_, base, GRADE_R)
        r, g, b = _sombreado_np(topo, base, Y, c_topo, c_base, brilho)
        R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)
    m = _no_squircle_np(X, Y)
    r, g, b = _cor_do_fundo_np(X, Y)
    R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)
    return R, G, B, assigned


def _cor_onda_np(X, Y):
    shape = X.shape
    assigned = np.zeros(shape, dtype=bool)
    R = np.zeros(shape)
    G = np.zeros(shape)
    B = np.zeros(shape)

    (ax, ay), (bx, by), (cx, cy) = PLAY

    def no_triangulo_np(Xp, Yp):
        d1 = (Xp - bx) * (ay - by) - (ax - bx) * (Yp - by)
        d2 = (Xp - cx) * (by - cy) - (bx - cx) * (Yp - cy)
        d3 = (Xp - ax) * (cy - ay) - (cx - ax) * (Yp - ay)
        negativo = (d1 < 0) | (d2 < 0) | (d3 < 0)
        positivo = (d1 > 0) | (d2 > 0) | (d3 > 0)
        return ~(negativo & positivo)

    m = no_triangulo_np(X, Y)
    brilho = ~no_triangulo_np(X, Y - ONDA_ESPESSURA_BRILHO)
    topo_y, base_y = PLAY[0][1], PLAY[1][1]
    r, g, b = _sombreado_np(topo_y, base_y, Y, COR_VIDEO[0], COR_VIDEO[1],
                            brilho)
    R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)

    cores = (COR_VIDEO, COR_AUDIO, COR_IMAGEM, COR_TRANSCRICAO)
    for i in range(len(ONDA_BARRAS)):
        cxb, meia, alt = ONDA_BARRAS[i]
        topo = 0.5 - alt / 2
        base = 0.5 + alt / 2
        m = _em_retangulo_redondo_np(X, Y, cxb - meia, topo, cxb + meia,
                                     base, ONDA_R)
        brilho = ~_em_retangulo_redondo_np(
            X, Y - ONDA_ESPESSURA_BRILHO, cxb - meia, topo, cxb + meia,
            base, ONDA_R)
        c_topo, c_base = cores[i % len(cores)]
        r, g, b = _sombreado_np(topo, base, Y, c_topo, c_base, brilho)
        R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)

    m = _no_squircle_np(X, Y)
    r, g, b = _cor_do_fundo_np(X, Y)
    R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)
    return R, G, B, assigned


def _cor_nucleo_np(X, Y):
    shape = X.shape
    assigned = np.zeros(shape, dtype=bool)
    R = np.zeros(shape)
    G = np.zeros(shape)
    B = np.zeros(shape)

    for direcao, (c_topo, c_base) in NUCLEO_BRACOS:
        esq, topo, dir_, base = _faixa_braco(direcao)
        m = _em_retangulo_redondo_np(X, Y, esq, topo, dir_, base,
                                     NUCLEO_R_BRACO)
        brilho = ~_em_retangulo_redondo_np(
            X, Y - 0.012, esq, topo, dir_, base, NUCLEO_R_BRACO)
        if direcao in ("cima", "baixo"):
            if direcao == "baixo":
                perto = (base - Y) / (base - topo)
            else:
                perto = (Y - topo) / (base - topo)
        else:
            if direcao == "esquerda":
                perto = (dir_ - X) / (dir_ - esq)
            else:
                perto = (X - esq) / (dir_ - esq)
        r, g, b = _sombreado_np(0, 1, 1 - perto, c_topo, c_base, brilho)
        R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)

    m = _no_circulo_np(X, Y, NUCLEO_CX, NUCLEO_CY, NUCLEO_R_CENTRO)
    borda = ~_no_circulo_np(X, Y - 0.010, NUCLEO_CX, NUCLEO_CY,
                            NUCLEO_R_CENTRO)
    t = np.clip((Y - (NUCLEO_CY - NUCLEO_R_CENTRO)) / (2 * NUCLEO_R_CENTRO),
               0.0, 1.0)
    miolo_r = 255 + (238 - 255) * t
    miolo_g = 255 + (228 - 255) * t
    miolo_b = 255 + (214 - 255) * t
    r = np.where(borda, BRILHO[0], miolo_r)
    g = np.where(borda, BRILHO[1], miolo_g)
    b = np.where(borda, BRILHO[2], miolo_b)
    R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)

    m = _no_squircle_np(X, Y)
    r, g, b = _cor_do_fundo_np(X, Y)
    R, G, B, assigned = _compor(R, G, B, assigned, m, r, g, b)
    return R, G, B, assigned


def desenhar_numpy(lado, amostras, estilo):
    n = lado * amostras
    passo = 1.0 / n
    meio_passo = passo / 2.0
    coord = np.arange(n) * passo + meio_passo
    X, Y = np.meshgrid(coord, coord)   # X varia por coluna, Y por linha

    if estilo == "grade":
        R, G, B, cov = _cor_grade_np(X, Y)
    elif estilo == "onda":
        R, G, B, cov = _cor_onda_np(X, Y)
    else:
        R, G, B, cov = _cor_nucleo_np(X, Y)

    total = float(amostras * amostras)
    covf = cov.astype(np.float64)

    def em_blocos(arr):
        return arr.reshape(lado, amostras, lado, amostras)

    Rb, Gb, Bb, Cb = em_blocos(R), em_blocos(G), em_blocos(B), em_blocos(covf)
    cobertos = Cb.sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        r_media = np.nan_to_num((Rb * Cb).sum(axis=(1, 3)) / cobertos)
        g_media = np.nan_to_num((Gb * Cb).sum(axis=(1, 3)) / cobertos)
        b_media = np.nan_to_num((Bb * Cb).sum(axis=(1, 3)) / cobertos)
    alpha = 255.0 * cobertos / total

    r8 = np.clip(np.round(r_media), 0, 255).astype(np.uint8)
    g8 = np.clip(np.round(g_media), 0, 255).astype(np.uint8)
    b8 = np.clip(np.round(b_media), 0, 255).astype(np.uint8)
    a8 = np.clip(np.round(alpha), 0, 255).astype(np.uint8)

    return np.stack([r8, g8, b8, a8], axis=-1)  # (lado, lado, 4)


def gravar_png_numpy(caminho, array):
    """Mesmo formato PNG de `gravar_png`, escrito direto de um array numpy
    uint8 (lado, lado, 4), sem passar por listas Python -- e o que faz a
    gravacao tambem ficar rapida, nao so o calculo dos pixels."""
    altura, largura = array.shape[0], array.shape[1]
    filtro = np.zeros((altura, 1), dtype=np.uint8)
    linhas = np.concatenate(
        [filtro, array.reshape(altura, largura * 4).astype(np.uint8)],
        axis=1)
    cru = linhas.tobytes()

    def bloco(tipo, dados):
        conteudo = tipo + dados
        return (struct.pack(">I", len(dados)) + conteudo
                + struct.pack(">I", zlib.crc32(conteudo) & 0xFFFFFFFF))

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 6, 0, 0, 0)
    with open(caminho, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(bloco(b"IHDR", cabecalho))
        f.write(bloco(b"IDAT", zlib.compress(cru, 9)))
        f.write(bloco(b"IEND", b""))


def main():
    if len(sys.argv) < 2:
        print("uso: make_icon.py <arquivo.png> [tamanho] [estilo] [amostras]")
        print("estilos: %s" % ", ".join(ESTILOS))
        return 1
    destino = sys.argv[1]
    lado = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    estilo = sys.argv[3] if len(sys.argv) > 3 else ESTILO
    amostras = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    configurar(estilo)

    if _TEM_NUMPY:
        try:
            array = desenhar_numpy(lado, amostras, estilo)
            gravar_png_numpy(destino, array)
            print("icone gravado em %s (%dx%d, estilo %s, %d amostras por "
                  "pixel, via numpy)"
                  % (destino, lado, lado, estilo, amostras * amostras))
            return 0
        except Exception as e:
            # Qualquer tropeco no caminho rapido (numpy instalado mas com
            # problema, por exemplo) cai pro caminho lento abaixo, que nao
            # depende de nada externo. Mais devagar, mas sempre funciona.
            sys.stderr.write(
                "aviso: caminho rapido (numpy) falhou (%s); desenhando "
                "pixel a pixel...\n" % e)

    gravar_png(destino, desenhar(lado, amostras))
    print("icone gravado em %s (%dx%d, estilo %s, %d amostras por pixel)"
          % (destino, lado, lado, estilo, amostras * amostras))
    return 0


if __name__ == "__main__":
    sys.exit(main())
