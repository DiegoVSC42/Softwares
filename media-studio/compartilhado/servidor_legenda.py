# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/servidor_legenda.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O servidor local que sustenta a aba "Sincronizar com video".

POR QUE UM SERVIDOR, E NAO UMA TELA DO TKINTER

O Tkinter nao toca video. Ele nem tenta: nao ha widget de video, nao ha som, e
as saidas usuais (decodificar quadro a quadro com o ffmpeg) entregam imagem
muda e travada, justamente o contrario do que esta aba precisa. E para
CONFERIR QUEM ESTA FALANDO e preciso OUVIR: sem audio, a aba nao serviria para
nada.

Entao o video toca onde ele toca bem, que e o navegador que a pessoa ja tem
instalado: imagem, som, adiantar, atrasar, velocidade, tudo nativo e sem
instalar nada. Este arquivo e a ponte. Ele sobe um servidor minusculo, so em
127.0.0.1 (ninguem de fora da maquina alcanca), entrega o editor e o video, e
recebe de volta a legenda corrigida para gravar em .docx e .txt.

O que ele serve:

    GET  /            o editor (a tela de trabalho)
    GET  /vivo        batida de coracao: diz que o programa ainda esta aberto
    GET  /dados.json  legenda, falantes e configuracao
    GET  /video       o arquivo de video, com suporte a RANGE
    GET  /rascunho    o trabalho salvo sozinho, se houver
    POST /rascunho    guarda o trabalho em andamento
    POST /salvar      grava o .docx e o .txt na pasta escolhida
    POST /mostrar     abre a pasta dos arquivos salvos no Finder

RANGE e a peca que nao pode faltar: sem ela o navegador so consegue tocar do
comeco, e clicar numa fala no meio da entrevista nao levaria a lugar nenhum. E
exatamente por isso que o servidor nao e o `SimpleHTTPRequestHandler` de
prateleira, que ignora Range.

Cada sessao nasce com um TOKEN aleatorio na URL. Sem ele o servidor responde
403. E o que impede que qualquer pagina aberta no navegador fique cutucando a
porta e lendo o video da entrevista.
"""

import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from compartilhado import editor_legenda
from compartilhado import legenda as legenda_mod
from documento import gravar_paragrafos, gravar_texto

# Formatos que o navegador toca sem conversao. O resto abre a imagem preta e
# o usuario acha que o programa quebrou, entao a aba avisa antes.
TOCAVEIS = {".mp4", ".m4v", ".mov", ".webm", ".ogv", ".ogg"}

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")

# Quando o navegador pede "do minuto tal ate o fim", nao despejamos o arquivo
# inteiro numa resposta so: mandamos uma JANELA e deixamos ele pedir o resto se
# precisar. Numa entrevista de tres horas, a resposta unica seria de gigabytes,
# e cada pulo no video deixaria essa torneira aberta escoando a toa.
JANELA = 24 * 1024 * 1024


def preparado_para_pular(caminho):
    """Diz se um MP4/MOV esta pronto para pular para o meio (faststart).

    Num arquivo de video, o indice ("moov") pode estar no comeco ou no fim. Se
    estiver no FIM, o navegador precisa baixar o arquivo quase inteiro antes de
    conseguir pular para o minuto 36 - e a espera parece eternidade, mesmo com o
    arquivo no proprio disco.

    Devolve True (pronto), False (indice no fim) ou None (nao da para saber, o
    que inclui formatos que nao sao MP4/MOV).
    """
    if os.path.splitext(caminho)[1].lower() not in (".mp4", ".m4v", ".mov"):
        return None
    try:
        with open(caminho, "rb") as f:
            fim = os.path.getsize(caminho)
            pos = 0
            while pos < fim:
                f.seek(pos)
                cabeca = f.read(8)
                if len(cabeca) < 8:
                    return None
                tamanho = int.from_bytes(cabeca[:4], "big")
                tipo = cabeca[4:8]
                if tamanho == 1:                      # caixa grande: 64 bits
                    tamanho = int.from_bytes(f.read(8), "big")
                elif tamanho == 0:                    # vai ate o fim
                    tamanho = fim - pos
                if tipo == b"moov":
                    return True                       # indice antes dos dados
                if tipo == b"mdat":
                    return False                      # dados antes do indice
                if tamanho < 8:
                    return None
                pos += tamanho
    except Exception:
        return None
    return None


def nome_seguro(nome, padrao):
    """Devolve um nome de arquivo que nao machuca ninguem.

    O nome vem da tela, e a tela e o navegador: barra, "..", nome vazio ou
    gigante nao podem virar caminho de arquivo. Aqui isso e podado antes de
    chegar perto do disco.
    """
    nome = (nome or "").strip()
    for ruim in ("/", "\\", ":", "\n", "\r", "\t", "\x00"):
        nome = nome.replace(ruim, " ")
    nome = nome.strip(" .")
    nome = " ".join(nome.split())
    if not nome:
        return padrao
    return nome[:120]


class Sessao:
    """Tudo o que uma sessao de sincronizacao precisa saber."""

    def __init__(self, video, titulo, data, segmentos, falantes, saida, nome):
        self.video = video
        self.titulo = titulo
        self.data = data
        self.segmentos = segmentos
        self.falantes = falantes
        self.saida = saida
        self.nome = nome                    # nome do arquivo de saida, sem ext
        self.token = secrets.token_urlsafe(16)
        self.salvos = []                    # caminhos gravados na ultima vez

    @property
    def arquivo_rascunho(self):
        return os.path.join(self.saida, ".%s-sincronizacao.json" % self.nome)


class _Handler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"
    server_version = "TranscriptStudio"
    # Sem o algoritmo de Nagle: cada pedaco do video sai na hora, em vez de
    # esperar o pacote encher. E o que deixa o pulo no video responder rapido.
    disable_nagle_algorithm = True

    # O servidor nao escreve no terminal: a janela do programa e que conta o
    # que esta acontecendo.
    def log_message(self, *args):
        pass

    # ----------------------------------------------------------------- apoio

    @property
    def sessao(self):
        return self.server.sessao

    def _caminho(self):
        parte = self.path.split("?", 1)
        return parte[0], (parte[1] if len(parte) > 1 else "")

    def _autorizado(self, consulta):
        alvo = "t=" + self.sessao.token
        if alvo in consulta:
            return True
        return self.headers.get("X-Token") == self.sessao.token

    def _responder(self, corpo, tipo="text/html; charset=utf-8", codigo=200):
        if isinstance(corpo, str):
            corpo = corpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, dados, codigo=200):
        self._responder(json.dumps(dados, ensure_ascii=False),
                        "application/json; charset=utf-8", codigo)

    # ------------------------------------------------------------------- GET

    def do_GET(self):
        caminho, consulta = self._caminho()
        if not self._autorizado(consulta):
            self._responder("Sessao nao reconhecida.", "text/plain; charset=utf-8", 403)
            return

        if caminho in ("/", "/index.html"):
            self._responder(editor_legenda.pagina(self.sessao.token))
        elif caminho == "/vivo":
            # Batida de coracao: e por ela que a tela do navegador percebe que
            # o programa foi fechado. Quando esta chamada para de responder, a
            # tela avisa a pessoa e fecha a janela do video, para nao ficar um
            # video tocando sozinho na outra tela sem nada por tras.
            self._json({"ok": True})
        elif caminho == "/dados.json":
            self._json(self._dados())
        elif caminho == "/rascunho":
            self._json(self._ler_rascunho())
        elif caminho == "/video":
            self._servir_video()
        else:
            self._responder("Nao encontrado.", "text/plain; charset=utf-8", 404)

    def _dados(self):
        s = self.sessao
        return {
            "titulo": s.titulo,
            "arquivo": s.nome + " (falantes conferidos)",
            "data": s.data,
            "video": os.path.basename(s.video),
            "nome": s.nome,
            "saida": s.saida,
            "falantes": s.falantes,
            "segmentos": s.segmentos,
            "tem_rascunho": os.path.exists(s.arquivo_rascunho),
        }

    def _ler_rascunho(self):
        try:
            with open(self.sessao.arquivo_rascunho, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ------------------------------------------------------- video com Range

    def _servir_video(self):
        caminho = self.sessao.video
        try:
            tamanho = os.path.getsize(caminho)
        except OSError:
            self._responder("Video nao encontrado.", "text/plain; charset=utf-8", 404)
            return

        tipo = mimetypes.guess_type(caminho)[0] or "video/mp4"
        faixa = self.headers.get("Range")
        inicio, fim = 0, tamanho - 1
        parcial = False

        if faixa:
            m = _RANGE.search(faixa)
            if m:
                a, b = m.group(1), m.group(2)
                if a:
                    inicio = int(a)
                    if b:
                        fim = min(int(b), tamanho - 1)
                    else:
                        # "do byte X ate o fim": responde so uma janela.
                        fim = min(inicio + JANELA - 1, tamanho - 1)
                elif b:                       # bytes=-500 (ultimos 500)
                    inicio = max(0, tamanho - int(b))
                parcial = True
        if inicio >= tamanho:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % tamanho)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        total = fim - inicio + 1
        self.send_response(206 if parcial else 200)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(total))
        if parcial:
            self.send_header("Content-Range",
                             "bytes %d-%d/%d" % (inicio, fim, tamanho))
        self.end_headers()

        try:
            with open(caminho, "rb") as arquivo:
                arquivo.seek(inicio)
                restante = total
                while restante > 0:
                    pedaco = arquivo.read(min(512 * 1024, restante))
                    if not pedaco:
                        break
                    self.wfile.write(pedaco)
                    restante -= len(pedaco)
        except (BrokenPipeError, ConnectionResetError):
            # O navegador cortou a conexao porque a pessoa pulou para outro
            # ponto do video. E o comportamento normal, nao e erro.
            pass

    # ------------------------------------------------------------------ POST

    def do_POST(self):
        caminho, consulta = self._caminho()
        if not self._autorizado(consulta):
            self._json({"ok": False, "erro": "Sessao nao reconhecida."}, 403)
            return

        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho).decode("utf-8") or "{}")
        except Exception:
            self._json({"ok": False, "erro": "Nao entendi o que chegou."}, 400)
            return

        if caminho == "/rascunho":
            self._json(self._gravar_rascunho(corpo))
        elif caminho == "/salvar":
            self._json(self._salvar(corpo))
        elif caminho == "/mostrar":
            self._json(self._mostrar())
        else:
            self._json({"ok": False, "erro": "Nao encontrado."}, 404)

    def _gravar_rascunho(self, corpo):
        try:
            with open(self.sessao.arquivo_rascunho, "w", encoding="utf-8") as f:
                json.dump(corpo, f, ensure_ascii=False)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def _mostrar(self):
        """Mostra no Finder o que acabou de ser gravado.

        So abre arquivo que ESTE programa gravou nesta sessao: a pagina pede,
        mas quem escolhe o caminho e o Python, nunca o navegador.
        """
        alvo = self.sessao.salvos[0] if self.sessao.salvos else self.sessao.saida
        try:
            _revelar(alvo)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def _salvar(self, corpo):
        s = self.sessao
        segmentos = corpo.get("segmentos") or []
        if not segmentos:
            return {"ok": False, "erro": "Nao chegou nenhuma fala para gravar."}

        deslocamento = float(corpo.get("deslocamento") or 0)
        if not corpo.get("gravar_ajuste"):
            deslocamento = 0.0

        # Titulo e nome do arquivo podem ter sido trocados na tela.
        titulo = corpo.get("titulo")
        titulo = s.titulo if titulo is None else str(titulo).strip()
        arquivo = nome_seguro(corpo.get("arquivo"),
                              s.nome + " (falantes conferidos)")

        itens = legenda_mod.montar_itens(segmentos, deslocamento=deslocamento)
        base = os.path.join(s.saida, arquivo)
        caminhos = []
        try:
            if corpo.get("docx", True):
                alvo = base + ".docx"
                gravar_paragrafos(alvo, itens, titulo, s.data)
                caminhos.append(alvo)
            if corpo.get("txt", True):
                alvo = base + ".txt"
                gravar_texto(alvo, itens, titulo, s.data)
                caminhos.append(alvo)
        except Exception as e:
            return {"ok": False, "erro": str(e)}

        s.salvos = caminhos
        automatico = bool(corpo.get("auto"))

        # Num salvamento a MAO, o rascunho perde a razao de existir. No
        # automatico ele fica: e o que guarda a selecao e o ajuste fino para
        # a tela voltar exatamente como estava se o navegador fechar.
        if not automatico:
            try:
                os.remove(s.arquivo_rascunho)
            except OSError:
                pass

        aviso = getattr(self.server, "aviso", None)
        if callable(aviso):
            try:
                aviso(("auto", caminhos) if automatico else caminhos)
            except Exception:
                pass
        return {"ok": True, "caminhos": caminhos, "auto": automatico}


def _revelar(caminho):
    """Abre o Finder (ou o Explorer) já com o arquivo selecionado."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", caminho])
    elif os.name == "nt":
        subprocess.Popen(["explorer", "/select,", caminho])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(caminho)])


class Servidor:
    """Sobe, entrega a URL e desce. Nada alem disso."""

    def __init__(self, sessao, aviso=None):
        self.sessao = sessao
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.http.sessao = sessao
        self.http.aviso = aviso
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever,
                                       daemon=True)
        self.thread.start()

    @property
    def url(self):
        porta = self.http.server_address[1]
        return "http://127.0.0.1:%d/?t=%s" % (porta, self.sessao.token)

    def parar(self):
        try:
            self.http.shutdown()
        except Exception:
            pass
        try:
            self.http.server_close()
        except Exception:
            pass
