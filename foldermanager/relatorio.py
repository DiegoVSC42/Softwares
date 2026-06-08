#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relatorio.py
============

Geração de relatórios da comparação (e, opcionalmente, da última cópia
realizada) em três formatos:

  - HTML : interativo (filtros por aba, copiar caminho). Melhor para navegar
           muitos arquivos na tela.
  - CSV  : abre no Excel. Melhor para tratar os dados em planilha.
  - PDF  : visual, para imprimir/arquivar. Usa a biblioteca reportlab.

O relatório é OPCIONAL: só é gerado quando o usuário clica no botão
"Gerar relatório" e escolhe o formato.

Estrutura de 'dados' (devolvida por motor_comparacao.comparar):
    {
        "linhas": [...], "erros": [...],
        "qtd_origem": int, "qtd_destino": int,
        "origem": str, "destino": str,
        "usar_hash": bool, "tolerancia": float, "considerar_data": bool,
    }

Estrutura opcional de 'copia' (resumo da última cópia, montado pelo app):
    {
        "data": "dd/mm/AAAA HH:MM:SS",
        "origem": str, "destino": str,
        "sobrescrever": bool,
        "copiados": int, "bytes": int, "falhas": int, "ignorados": int,
        "lista_copiados": [ {"rel": str, "size": int, "motivo": str}, ... ],
        "lista_falhas":   [ (rel, erro), ... ],
        "lista_ignorados":[ {"rel": str, "motivo": str}, ... ],
    }
"""

import csv
import datetime as dt
import html
import os

from motor_comparacao import (
    CORES, ROTULOS, CRITICAS,
    formatar_tamanho, separar_data_hora, subpasta_principal, resumo,
)


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def gravar_csv(caminho, dados, copia=None):
    linhas = dados["linhas"]
    cabecalho = [
        "caminho_relativo", "subpasta_principal", "presenca", "status", "detalhe",
        "tamanho_origem_bytes", "tamanho_destino_bytes",
        "data_origem", "data", "hora", "data_destino",
        "caminho_completo_origem", "caminho_completo_destino",
    ]
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cabecalho)
        for l in linhas:
            d_data, d_hora = separar_data_hora(l["data_origem"])
            w.writerow([
                l["caminho"], subpasta_principal(l["caminho"]),
                l.get("presenca", ""), l["status"], l["detalhe"],
                l["tam_origem"], l["tam_destino"],
                l["data_origem"], d_data, d_hora, l["data_destino"],
                l.get("abs_origem", ""), l.get("abs_destino", ""),
            ])

        if copia:
            w.writerow([])
            w.writerow(["=== ÚLTIMA CÓPIA REALIZADA ==="])
            w.writerow(["data", copia.get("data", "")])
            w.writerow(["copiados", copia.get("copiados", 0)])
            w.writerow(["bytes_copiados", copia.get("bytes", 0)])
            w.writerow(["falhas", copia.get("falhas", 0)])
            w.writerow(["ignorados", copia.get("ignorados", 0)])
            w.writerow([])
            w.writerow(["copia_status", "caminho_relativo", "tamanho_bytes", "motivo"])
            for a in copia.get("lista_copiados", []):
                w.writerow(["COPIADO", a.get("rel", ""), a.get("size", ""), a.get("motivo", "")])
            for rel, err in copia.get("lista_falhas", []):
                w.writerow(["FALHA", rel, "", err])
            for ig in copia.get("lista_ignorados", []):
                w.writerow(["IGNORADO", ig.get("rel", ""), "", ig.get("motivo", "")])


# --------------------------------------------------------------------------- #
# HTML interativo
# --------------------------------------------------------------------------- #
def gravar_html(caminho, dados, copia=None):
    origem = dados["origem"]
    destino = dados["destino"]
    usar_hash = dados["usar_hash"]
    tolerancia = dados["tolerancia"]
    considerar_data = dados["considerar_data"]

    linhas = dados["linhas"]
    cont = resumo(linhas)
    total = len(linhas)
    ok = cont.get("OK", 0)
    criticos = sum(cont.get(c, 0) for c in CRITICAS)
    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    ordem_cards = ["OK", "FALTANDO", "TAMANHO_DIFERENTE", "HASH_DIFERENTE",
                   "EXTRA", "DATA_DIFERENTE", "ERRO_LEITURA"]
    cards = ""
    for st in ordem_cards:
        if st not in cont:
            continue
        cards += f"""
        <div class="card" style="border-top:4px solid {CORES[st]}">
            <div class="num" style="color:{CORES[st]}">{cont[st]}</div>
            <div class="lbl">{ROTULOS[st]}</div>
        </div>"""

    def chave_ordem(l):
        prio = {"FALTANDO": 0, "TAMANHO_DIFERENTE": 1, "HASH_DIFERENTE": 2,
                "ERRO_LEITURA": 3, "EXTRA": 4, "DATA_DIFERENTE": 5, "OK": 6}
        return (prio.get(l["status"], 9), l["caminho"])

    linhas_ordenadas = sorted(linhas, key=chave_ordem)

    def cel_caminho(valor):
        if not valor:
            return '<td class="full">—</td>'
        v = html.escape(valor)
        return (
            f'<td class="full"><span class="p">{v}</span>'
            f'<button class="copy" data-copy="{v}" title="Copiar caminho">⧉</button></td>'
        )

    trs = []
    for l in linhas_ordenadas:
        cor = CORES.get(l["status"], "#57606a")
        tam_o = formatar_tamanho(l["tam_origem"]) if l["tam_origem"] != "" else "—"
        tam_d = formatar_tamanho(l["tam_destino"]) if l["tam_destino"] != "" else "—"
        d_data, d_hora = separar_data_hora(l["data_origem"])
        trs.append(f"""
        <tr data-status="{l['status']}">
            <td class="path">{html.escape(l['caminho'])}</td>
            <td class="num-cell">{html.escape(subpasta_principal(l['caminho']))}</td>
            <td class="num-cell">{l.get('presenca', '—')}</td>
            <td><span class="tag" style="background:{cor}">{ROTULOS.get(l['status'], l['status'])}</span></td>
            <td>{html.escape(l['detalhe'])}</td>
            <td class="num-cell">{tam_o}</td>
            <td class="num-cell">{tam_d}</td>
            <td class="num-cell">{l['data_origem'] or '—'}</td>
            <td class="num-cell">{d_data or '—'}</td>
            <td class="num-cell">{d_hora or '—'}</td>
            <td class="num-cell">{l['data_destino'] or '—'}</td>
            {cel_caminho(l.get('abs_origem', ''))}
            {cel_caminho(l.get('abs_destino', ''))}
        </tr>""")

    erros_html = ""
    if dados["erros"]:
        itens = "".join(
            f"<li>{html.escape(c)} — {html.escape(m)}</li>" for c, m in dados["erros"]
        )
        erros_html = f"""
        <div class="aviso">
            <strong>Avisos de leitura ({len(dados['erros'])}):</strong>
            <ul>{itens}</ul>
        </div>"""

    veredito_cor = "#1a7f37" if criticos == 0 else "#cf222e"
    veredito_txt = (
        "Cópia íntegra: nenhum problema crítico encontrado."
        if criticos == 0
        else f"Atenção: {criticos} problema(s) crítico(s) encontrado(s)."
    )

    metodo = "caminho relativo + nome + tamanho"
    if usar_hash:
        metodo += " + hash SHA-256 do conteúdo"
    metodo += (" + data de modificação" if considerar_data
               else " (data apenas informativa, não conta como erro)")

    ordem_abas = ["FALTANDO", "TAMANHO_DIFERENTE", "HASH_DIFERENTE", "EXTRA",
                  "DATA_DIFERENTE", "ERRO_LEITURA", "OK"]
    abas = f'<button class="aba on" data-f="ALL">Todos ({total})</button>'
    if (total - ok) > 0:
        abas += f'<button class="aba" data-f="PROBLEMA" style="--c:#cf222e">Só problemas ({total - ok})</button>'
    for st in ordem_abas:
        if st in cont:
            abas += (f'<button class="aba" data-f="{st}" style="--c:{CORES[st]}">'
                     f'{ROTULOS[st]} ({cont[st]})</button>')

    # Bloco da última cópia (opcional)
    copia_html = ""
    if copia:
        itens_cop = ""
        for a in copia.get("lista_copiados", [])[:5000]:
            itens_cop += (f"<tr><td class='path'>{html.escape(a.get('rel',''))}</td>"
                          f"<td class='num-cell'>{formatar_tamanho(a.get('size',0))}</td>"
                          f"<td>{html.escape(a.get('motivo',''))}</td></tr>")
        falhas_cop = ""
        for rel, err in copia.get("lista_falhas", []):
            falhas_cop += (f"<tr><td class='path'>{html.escape(rel)}</td>"
                           f"<td class='num-cell'>—</td>"
                           f"<td style='color:#cf222e'>{html.escape(err)}</td></tr>")
        ign_cop = ""
        for ig in copia.get("lista_ignorados", []):
            ign_cop += (f"<tr><td class='path'>{html.escape(ig.get('rel',''))}</td>"
                        f"<td class='num-cell'>—</td>"
                        f"<td style='color:#9a6700'>{html.escape(ig.get('motivo',''))}</td></tr>")
        copia_html = f"""
    <h2 style="margin-top:32px">Última cópia realizada</h2>
    <div class="meta">
        <div><strong>Data:</strong> {html.escape(copia.get('data',''))}</div>
        <div><strong>Sobrescrever divergentes:</strong> {"SIM" if copia.get('sobrescrever') else "NÃO"}</div>
        <div><strong>Copiados:</strong> {copia.get('copiados',0)} ({formatar_tamanho(copia.get('bytes',0))})</div>
        <div><strong>Falhas:</strong> {copia.get('falhas',0)} &nbsp;|&nbsp; <strong>Ignorados:</strong> {copia.get('ignorados',0)}</div>
    </div>
    <table>
        <thead><tr><th>Caminho relativo</th><th>Tamanho</th><th>Situação / motivo</th></tr></thead>
        <tbody>{itens_cop}{falhas_cop}{ign_cop}</tbody>
    </table>"""

    documento = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório de comparação de pastas</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
            margin: 0; background: #f6f8fa; color: #1f2328; }}
    .wrap {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 22px; margin: 0 0 4px; }}
    h2 {{ font-size: 18px; }}
    .sub {{ color: #57606a; font-size: 13px; margin-bottom: 20px; }}
    .veredito {{ padding: 14px 18px; border-radius: 8px; color: #fff;
                 font-weight: 600; margin-bottom: 20px; background: {veredito_cor}; }}
    .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
    .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
             padding: 14px 18px; min-width: 130px; flex: 1; }}
    .num {{ font-size: 28px; font-weight: 700; }}
    .lbl {{ font-size: 12px; color: #57606a; margin-top: 2px; }}
    .meta {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
             padding: 14px 18px; margin-bottom: 20px; font-size: 13px; }}
    .meta div {{ margin: 3px 0; }}
    .meta code {{ background: #eff1f3; padding: 1px 6px; border-radius: 4px;
                  word-break: break-all; }}
    .filtros {{ display: flex; flex-wrap: wrap; gap: 0; margin-bottom: 0;
                border-bottom: 2px solid #d0d7de; }}
    .aba {{ border: none; background: transparent; cursor: pointer;
            padding: 9px 14px; font-size: 13px; color: #57606a;
            border-bottom: 3px solid transparent; margin-bottom: -2px; }}
    .aba:hover {{ color: #1f2328; background: #eef1f3; }}
    .aba.on {{ color: #1f2328; font-weight: 600;
               border-bottom-color: var(--c, #1f2328); }}
    table {{ width: 100%; border-collapse: collapse; background: #fff;
             border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden;
             font-size: 13px; }}
    th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid #eaeef2;
              vertical-align: top; }}
    th {{ background: #f6f8fa; font-size: 12px; color: #57606a; position: sticky;
          top: 0; }}
    .path {{ font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
             word-break: break-all; }}
    .num-cell {{ white-space: nowrap; color: #57606a; }}
    .tag {{ color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 11px;
            font-weight: 600; white-space: nowrap; }}
    .aviso {{ background: #fff8c5; border: 1px solid #d4a72c; border-radius: 8px;
              padding: 12px 16px; margin-top: 20px; font-size: 13px; }}
    .aviso ul {{ margin: 8px 0 0; padding-left: 20px; }}
    .full {{ font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
             font-size: 11px; color: #424a53; word-break: break-all; min-width: 220px; }}
    .full .p {{ user-select: all; }}
    .copy {{ border: 1px solid #d0d7de; background: #fff; cursor: pointer;
             border-radius: 4px; margin-left: 6px; padding: 0 5px; font-size: 12px; }}
    .copy:hover {{ background: #eef1f3; }}
    .copy.ok {{ background: #1a7f37; color: #fff; border-color: #1a7f37; }}
</style>
</head>
<body>
<div class="wrap">
    <h1>Relatório de comparação de pastas</h1>
    <div class="sub">Gerado em {agora} — somente leitura (a comparação não altera arquivos)</div>

    <div class="veredito">{veredito_txt}</div>

    <div class="cards">{cards}</div>

    <div class="meta">
        <div><strong>Origem:</strong> <code>{html.escape(origem)}</code> — {dados['qtd_origem']} arquivo(s)</div>
        <div><strong>Destino:</strong> <code>{html.escape(destino)}</code> — {dados['qtd_destino']} arquivo(s)</div>
        <div><strong>Método de comparação:</strong> {metodo}</div>
        <div><strong>Tolerância de data:</strong> {tolerancia:g} segundo(s)</div>
        <div><strong>Total de itens analisados:</strong> {total}</div>
    </div>

    <div class="filtros">{abas}</div>

    <table id="tabela">
        <thead>
            <tr>
                <th>Caminho relativo</th>
                <th>Subpasta principal</th>
                <th>Presença</th>
                <th>Status</th>
                <th>Detalhe</th>
                <th>Tam. origem</th>
                <th>Tam. destino</th>
                <th>Data origem</th>
                <th>Data</th>
                <th>Hora</th>
                <th>Data destino</th>
                <th>Caminho completo na origem</th>
                <th>Caminho completo no destino</th>
            </tr>
        </thead>
        <tbody>{''.join(trs)}</tbody>
    </table>

    {erros_html}
    {copia_html}
</div>

<script>
    const botoes = document.querySelectorAll('.filtros .aba');
    const linhas = document.querySelectorAll('#tabela tbody tr');
    botoes.forEach(b => b.addEventListener('click', () => {{
        botoes.forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        const f = b.dataset.f;
        linhas.forEach(tr => {{
            const s = tr.dataset.status;
            let mostra;
            if (f === 'ALL') mostra = true;
            else if (f === 'PROBLEMA') mostra = (s !== 'OK');
            else mostra = (s === f);
            tr.style.display = mostra ? '' : 'none';
        }});
    }}));

    document.querySelectorAll('.copy').forEach(b => b.addEventListener('click', () => {{
        const txt = b.dataset.copy;
        navigator.clipboard.writeText(txt).then(() => {{
            const orig = b.textContent;
            b.textContent = '✔'; b.classList.add('ok');
            setTimeout(() => {{ b.textContent = orig; b.classList.remove('ok'); }}, 1200);
        }});
    }}));
</script>
</body>
</html>"""

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(documento)


# --------------------------------------------------------------------------- #
# PDF (reportlab)
# --------------------------------------------------------------------------- #
def pdf_disponivel():
    """Indica se a biblioteca reportlab está instalada."""
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def gravar_pdf(caminho, dados, copia=None, limite_linhas=4000):
    """
    Gera o relatório em PDF. Requer reportlab (pip install reportlab).

    Para manter o PDF utilizável, as linhas OK só são listadas se o total
    couber em 'limite_linhas'; caso contrário, lista apenas os problemas e
    informa quantos OK foram omitidos (eles continuam contados no resumo).
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)

    linhas = dados["linhas"]
    cont = resumo(linhas)
    total = len(linhas)
    ok = cont.get("OK", 0)
    criticos = sum(cont.get(c, 0) for c in CRITICAS)
    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    styles = getSampleStyleSheet()
    st_titulo = ParagraphStyle("t", parent=styles["Title"], fontSize=18, spaceAfter=4)
    st_sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#57606a"))
    st_h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6)
    st_cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, leading=9)
    st_cell_path = ParagraphStyle("cp", parent=styles["Normal"], fontSize=6.5,
                                  leading=8, fontName="Courier")

    doc = SimpleDocTemplate(
        caminho, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title="Relatório de comparação de pastas",
    )
    elementos = []

    elementos.append(Paragraph("Relatório de comparação de pastas", st_titulo))
    elementos.append(Paragraph(
        f"Gerado em {agora} — somente leitura (a comparação não altera arquivos)", st_sub))
    elementos.append(Spacer(1, 8))

    # Veredito
    if criticos == 0:
        ver_txt, ver_cor = "Cópia íntegra: nenhum problema crítico encontrado.", colors.HexColor("#1a7f37")
    else:
        ver_txt, ver_cor = f"Atenção: {criticos} problema(s) crítico(s) encontrado(s).", colors.HexColor("#cf222e")
    t_ver = Table([[Paragraph(f"<b>{ver_txt}</b>", ParagraphStyle(
        "v", parent=styles["Normal"], textColor=colors.white, fontSize=11))]],
        colWidths=[doc.width])
    t_ver.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ver_cor),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(t_ver)
    elementos.append(Spacer(1, 10))

    # Resumo (cartões em linha)
    ordem = ["OK", "FALTANDO", "TAMANHO_DIFERENTE", "HASH_DIFERENTE",
             "EXTRA", "DATA_DIFERENTE", "ERRO_LEITURA"]
    presentes = [st for st in ordem if st in cont]
    if presentes:
        cab = [Paragraph(f"<b>{ROTULOS[st]}</b>", st_cell) for st in presentes]
        val = [Paragraph(f'<font color="{CORES[st]}" size="13"><b>{cont[st]}</b></font>', st_cell)
               for st in presentes]
        t_res = Table([cab, val], colWidths=[doc.width / len(presentes)] * len(presentes))
        t_res.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elementos.append(t_res)
    elementos.append(Spacer(1, 8))

    # Metadados
    metodo = "caminho relativo + nome + tamanho"
    if dados["usar_hash"]:
        metodo += " + hash SHA-256"
    metodo += (" + data" if dados["considerar_data"] else " (data informativa)")
    meta_txt = (
        f"<b>Origem:</b> {html.escape(dados['origem'])} — {dados['qtd_origem']} arquivo(s)<br/>"
        f"<b>Destino:</b> {html.escape(dados['destino'])} — {dados['qtd_destino']} arquivo(s)<br/>"
        f"<b>Método:</b> {metodo} &nbsp;|&nbsp; <b>Tolerância:</b> {dados['tolerancia']:g}s "
        f"&nbsp;|&nbsp; <b>Itens analisados:</b> {total}"
    )
    elementos.append(Paragraph(meta_txt, st_cell))

    # Tabela de itens
    def prio(l):
        p = {"FALTANDO": 0, "TAMANHO_DIFERENTE": 1, "HASH_DIFERENTE": 2,
             "ERRO_LEITURA": 3, "EXTRA": 4, "DATA_DIFERENTE": 5, "OK": 6}
        return (p.get(l["status"], 9), l["caminho"])

    linhas_ord = sorted(linhas, key=prio)
    omitir_ok = total > limite_linhas
    if omitir_ok:
        linhas_ord = [l for l in linhas_ord if l["status"] != "OK"]
        elementos.append(Paragraph(
            f"Lista abaixo: {len(linhas_ord)} item(ns) com problema. "
            f"As {ok} linhas OK foram omitidas no PDF por volume "
            f"(use o relatório CSV ou HTML para a lista completa).", st_sub))

    elementos.append(Spacer(1, 4))
    elementos.append(Paragraph("Itens analisados", st_h2))

    cab = ["Caminho relativo", "Presença", "Status", "Detalhe", "Tam. orig.", "Tam. dest."]
    tabela = [[Paragraph(f"<b>{c}</b>", st_cell) for c in cab]]
    estilo_linhas = []
    for idx, l in enumerate(linhas_ord, start=1):
        cor = CORES.get(l["status"], "#57606a")
        tam_o = formatar_tamanho(l["tam_origem"]) if l["tam_origem"] != "" else "—"
        tam_d = formatar_tamanho(l["tam_destino"]) if l["tam_destino"] != "" else "—"
        tabela.append([
            Paragraph(html.escape(l["caminho"]), st_cell_path),
            Paragraph(l.get("presenca", "—"), st_cell),
            Paragraph(f'<font color="{cor}"><b>{ROTULOS.get(l["status"], l["status"])}</b></font>', st_cell),
            Paragraph(html.escape(l["detalhe"]), st_cell),
            Paragraph(tam_o, st_cell),
            Paragraph(tam_d, st_cell),
        ])

    larg = doc.width
    col_w = [larg * 0.34, larg * 0.10, larg * 0.13, larg * 0.27, larg * 0.08, larg * 0.08]
    t = Table(tabela, colWidths=col_w, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f3f6")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e4e8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(tabela)):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafbfc")))
    t.setStyle(TableStyle(estilo + estilo_linhas))
    elementos.append(t)

    # Erros de leitura
    if dados["erros"]:
        elementos.append(Paragraph("Avisos de leitura", st_h2))
        for c, m in dados["erros"][:200]:
            elementos.append(Paragraph(f"• {html.escape(c)} — {html.escape(m)}", st_cell))

    # Seção da última cópia
    if copia:
        elementos.append(Paragraph("Última cópia realizada", st_h2))
        resumo_cop = (
            f"<b>Data:</b> {html.escape(copia.get('data',''))} &nbsp;|&nbsp; "
            f"<b>Sobrescrever divergentes:</b> {'SIM' if copia.get('sobrescrever') else 'NÃO'}<br/>"
            f"<b>Copiados:</b> {copia.get('copiados',0)} ({formatar_tamanho(copia.get('bytes',0))}) "
            f"&nbsp;|&nbsp; <b>Falhas:</b> {copia.get('falhas',0)} "
            f"&nbsp;|&nbsp; <b>Ignorados:</b> {copia.get('ignorados',0)}"
        )
        elementos.append(Paragraph(resumo_cop, st_cell))
        elementos.append(Spacer(1, 4))

        cab_c = ["Caminho relativo", "Tamanho", "Situação / motivo"]
        tab_c = [[Paragraph(f"<b>{c}</b>", st_cell) for c in cab_c]]
        for a in copia.get("lista_copiados", [])[:limite_linhas]:
            tab_c.append([
                Paragraph(html.escape(a.get("rel", "")), st_cell_path),
                Paragraph(formatar_tamanho(a.get("size", 0)), st_cell),
                Paragraph("COPIADO — " + html.escape(a.get("motivo", "")), st_cell),
            ])
        for rel, err in copia.get("lista_falhas", []):
            tab_c.append([
                Paragraph(html.escape(rel), st_cell_path),
                Paragraph("—", st_cell),
                Paragraph(f'<font color="#cf222e">FALHA — {html.escape(err)}</font>', st_cell),
            ])
        for ig in copia.get("lista_ignorados", []):
            tab_c.append([
                Paragraph(html.escape(ig.get("rel", "")), st_cell_path),
                Paragraph("—", st_cell),
                Paragraph(f'<font color="#9a6700">IGNORADO — {html.escape(ig.get("motivo",""))}</font>', st_cell),
            ])
        if len(tab_c) > 1:
            col_c = [larg * 0.40, larg * 0.12, larg * 0.48]
            tc = Table(tab_c, colWidths=col_c, repeatRows=1)
            tc.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f3f6")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e4e8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            elementos.append(tc)

    doc.build(elementos)


# --------------------------------------------------------------------------- #
# Despacho por formato
# --------------------------------------------------------------------------- #
def gerar(formato, caminho, dados, copia=None):
    """Gera o relatório no formato pedido ('html', 'csv' ou 'pdf')."""
    formato = formato.lower()
    if formato == "html":
        gravar_html(caminho, dados, copia)
    elif formato == "csv":
        gravar_csv(caminho, dados, copia)
    elif formato == "pdf":
        gravar_pdf(caminho, dados, copia)
    else:
        raise ValueError(f"Formato desconhecido: {formato}")


def nome_padrao(formato):
    carimbo = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ext = {"html": "html", "csv": "csv", "pdf": "pdf"}[formato.lower()]
    return f"relatorio_comparacao_{carimbo}.{ext}"
