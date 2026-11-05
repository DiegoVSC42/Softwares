"""
Atualizador automático (módulo compartilhado)
=============================================

Este arquivo é copiado para dentro da pasta de cada programa e importado
pelo arquivo principal. Ele faz o programa conferir sozinho, ao abrir, se
existe versão nova publicada no repositório `DiegoVSC42/Softwares` e, se o
usuário aceitar, baixar e trocar o próprio programa, reabrindo já na
versão nova.

Como usar no arquivo principal do programa:

    import atualizador
    ...
    raiz = Tk()
    App(raiz)
    atualizador.iniciar(raiz, "comparador-planilhas", APP_VERSION,
                        "Comparador de Planilhas")
    raiz.mainloop()

Como ele descobre a versão publicada:

    https://github.com/DiegoVSC42/Softwares/releases/download/<subpasta>/versao.json

Esse arquivo é gerado automaticamente pelo workflow do GitHub Actions a
cada publicação, e tem este formato:

    {
      "versao": "1.2.0",
      "windows": "ComparadorPlanilhas.exe",
      "mac_arm": "ComparadorPlanilhas-mac.zip",
      "mac_intel": "ComparadorPlanilhas-mac-intel.zip",
      "obrigatoria": false,
      "notas": "texto opcional mostrado na janela"
    }

Regras de segurança deste módulo:

- Ele só age quando o programa está empacotado (.exe ou .app). Rodando a
  partir do código-fonte, ele não faz nada.
- Qualquer falha (sem internet, arquivo ausente, pasta sem permissão de
  escrita) é engolida: o programa abre normalmente, como se o atualizador
  não existisse. Atualização nunca pode impedir o uso do software.
- Nada é tocado na interface fora da thread principal do Tkinter.
"""
import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

# O import precisa ficar aqui, no nível do módulo, para o PyInstaller
# enxergar o certifi e embutir a cadeia de certificados no executável.
try:
    import certifi
except Exception:  # pragma: no cover - ambiente sem certifi
    certifi = None

REPOSITORIO = "DiegoVSC42/Softwares"
URL_BASE = "https://github.com/%s/releases/download" % REPOSITORIO
TEMPO_LIMITE = 12          # segundos de espera por resposta da internet
ATRASO_PADRAO = 900        # milissegundos após abrir a janela

# Paleta escura padrão dos programas (ver CLAUDE.md).
COR_PAINEL = "#161b22"
COR_TEXTO = "#e6edf3"
COR_APOIO = "#a8b3bf"


# ------------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------------
def _log(mensagem):
    try:
        sys.stderr.write("[atualizador] %s\n" % mensagem)
    except Exception:
        pass


def _contexto_ssl():
    """Contexto HTTPS com a cadeia de certificados do certifi, quando houver.

    O Python embutido pelo PyInstaller não herda os certificados do sistema
    no Windows, o que provoca CERTIFICATE_VERIFY_FAILED mesmo com a internet
    funcionando.
    """
    try:
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        return None


def _abrir(url):
    pedido = urllib.request.Request(
        url,
        headers={
            "User-Agent": "atualizador-softwares",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    return urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE,
                                  context=_contexto_ssl())


def _versao_tupla(texto):
    """'1.10.2' -> (1, 10, 2). Partes não numéricas viram 0."""
    partes = []
    for pedaco in str(texto or "0").strip().lstrip("vV").split("."):
        digitos = "".join(c for c in pedaco if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:4])


def _chave_plataforma():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac_arm" if platform.machine().lower() in ("arm64", "aarch64") else "mac_intel"
    return None


def _alvo_instalado():
    """Caminho do que precisa ser trocado: o .app no Mac, o .exe no Windows.

    Devolve None quando o programa está rodando a partir do código-fonte
    (nesse caso não há nada para atualizar).
    """
    if not getattr(sys, "frozen", False):
        return None
    executavel = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for candidato in [executavel] + list(executavel.parents):
            if candidato.suffix == ".app":
                return candidato
        return None
    return executavel


def _limpar_restos(alvo):
    """Apaga a versão anterior deixada para trás pela última atualização."""
    try:
        antigo = alvo.parent / (alvo.name + ".old")
        if antigo.is_dir():
            shutil.rmtree(antigo, ignore_errors=True)
        elif antigo.exists():
            antigo.unlink()
    except Exception as erro:
        _log("nao consegui limpar a versao anterior: %s" % erro)


# ------------------------------------------------------------------
# Ponto de entrada
# ------------------------------------------------------------------
def iniciar(janela, subpasta, versao_atual, nome_amigavel=None,
            atraso_ms=ATRASO_PADRAO):
    """Agenda a conferência de versão pouco depois de a janela aparecer.

    janela        -- a janela principal do Tkinter (Tk ou subclasse)
    subpasta      -- nome da pasta do software no repositório, que também é
                     a tag do Release (ex.: "comparador-planilhas")
    versao_atual  -- a constante VERSION / APP_VERSION do programa
    nome_amigavel -- nome mostrado nas mensagens (ex.: "Extrair Quadros")
    """
    try:
        alvo = _alvo_instalado()
        if alvo is None:
            return
        _limpar_restos(alvo)
        nome = nome_amigavel or subpasta
        janela.after(
            atraso_ms,
            lambda: threading.Thread(
                target=_conferir,
                args=(janela, subpasta, versao_atual, nome, alvo),
                daemon=True,
            ).start(),
        )
    except Exception:
        _log(traceback.format_exc())


def _conferir(janela, subpasta, versao_atual, nome, alvo):
    """Roda em thread: baixa o versao.json e compara com a versão local."""
    try:
        chave = _chave_plataforma()
        if not chave:
            return
        url = "%s/%s/versao.json" % (URL_BASE, subpasta)
        with _abrir(url) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        remota = str(dados.get("versao") or "").strip()
        arquivo = str(dados.get(chave) or "").strip()
        if not remota or not arquivo:
            return
        if _versao_tupla(remota) <= _versao_tupla(versao_atual):
            return
        url_arquivo = "%s/%s/%s" % (URL_BASE, subpasta, arquivo)
        janela.after(0, lambda: _perguntar(janela, nome, versao_atual, remota,
                                           dados, url_arquivo, alvo))
    except Exception as erro:
        _log("conferencia falhou: %s" % erro)


def _perguntar(janela, nome, versao_atual, remota, dados, url_arquivo, alvo):
    try:
        notas = str(dados.get("notas") or "").strip()
        texto = (
            "Existe uma versão nova do %s.\n\n"
            "Instalada: %s\nDisponível: %s\n\n" % (nome, versao_atual, remota)
        )
        if notas:
            texto += "%s\n\n" % notas
        texto += ("Atualizar agora? O programa baixa a versão nova, se "
                  "substitui e reabre sozinho.")
        if messagebox.askyesno("Atualização disponível", texto, parent=janela):
            _JanelaAtualizacao(janela, nome, remota, url_arquivo, alvo)
    except Exception:
        _log(traceback.format_exc())


# ------------------------------------------------------------------
# Janela de progresso do download
# ------------------------------------------------------------------
class _JanelaAtualizacao:
    def __init__(self, pai, nome, versao, url, alvo):
        self.pai = pai
        self.alvo = alvo
        self.url = url
        self.cancelado = False

        self.topo = tk.Toplevel(pai)
        self.topo.title("Atualizando")
        self.topo.configure(bg=COR_PAINEL)
        self.topo.resizable(False, False)
        self.topo.transient(pai)
        self.topo.protocol("WM_DELETE_WINDOW", self._cancelar)

        quadro = tk.Frame(self.topo, bg=COR_PAINEL, padx=24, pady=20)
        quadro.pack(fill="both", expand=True)

        tk.Label(quadro, text="Baixando %s v%s" % (nome, versao),
                 bg=COR_PAINEL, fg=COR_TEXTO,
                 font=("Helvetica", 13)).pack(anchor="w")

        self.barra = ttk.Progressbar(quadro, length=360, mode="determinate",
                                     maximum=100)
        self.barra.pack(fill="x", pady=(14, 8))

        self.rotulo = tk.Label(quadro, text="Conectando...", bg=COR_PAINEL,
                               fg=COR_APOIO, font=("Helvetica", 11))
        self.rotulo.pack(anchor="w")

        # ttk, e nao tk.Button: no Mac o botao do Tk puro ignora a cor de
        # fundo, e o texto claro sumia em cima do botao branco.
        self.botao = ttk.Button(quadro, text="Cancelar",
                                command=self._cancelar)
        self.botao.pack(anchor="e", pady=(14, 0))

        self.topo.update_idletasks()
        try:
            x = pai.winfo_rootx() + (pai.winfo_width() - self.topo.winfo_width()) // 2
            y = pai.winfo_rooty() + 120
            self.topo.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        except Exception:
            pass
        try:
            self.topo.grab_set()
        except Exception:
            pass

        threading.Thread(target=self._trabalhar, daemon=True).start()

    # -- interface (sempre na thread principal) --
    def _cancelar(self):
        self.cancelado = True
        self.rotulo.configure(text="Cancelando...")

    def _progresso(self, baixado, total):
        if not self.topo.winfo_exists():
            return
        if total:
            self.barra.configure(value=baixado * 100.0 / total)
            self.rotulo.configure(text="%.1f MB de %.1f MB" %
                                  (baixado / 1048576.0, total / 1048576.0))
        else:
            self.rotulo.configure(text="%.1f MB baixados" % (baixado / 1048576.0))

    def _etapa(self, texto):
        if self.topo.winfo_exists():
            self.rotulo.configure(text=texto)

    def _fechar(self):
        try:
            self.topo.grab_release()
        except Exception:
            pass
        try:
            self.topo.destroy()
        except Exception:
            pass

    def _falhar(self, mensagem):
        self._fechar()
        messagebox.showwarning(
            "Não foi possível atualizar",
            "A atualização não pôde ser concluída e o programa continua "
            "funcionando na versão atual.\n\nDetalhe: %s\n\n"
            "Você pode baixar a versão nova manualmente na página de "
            "downloads do repositório." % mensagem,
            parent=self.pai,
        )

    # -- trabalho pesado (thread) --
    def _trabalhar(self):
        pasta = None
        try:
            pasta = Path(tempfile.mkdtemp(prefix="atualizacao_"))
            destino = pasta / Path(self.url).name
            with _abrir(self.url) as resposta:
                total = int(resposta.headers.get("Content-Length") or 0)
                baixado = 0
                with open(destino, "wb") as saida:
                    while True:
                        if self.cancelado:
                            raise RuntimeError("cancelado pelo usuário")
                        pedaco = resposta.read(262144)
                        if not pedaco:
                            break
                        saida.write(pedaco)
                        baixado += len(pedaco)
                        self.pai.after(0, self._progresso, baixado, total)
            if destino.stat().st_size < 1024:
                raise RuntimeError("arquivo baixado veio vazio")

            self.pai.after(0, self._etapa, "Instalando...")
            if sys.platform == "darwin":
                _instalar_mac(destino, self.alvo, pasta)
            else:
                _instalar_windows(destino, self.alvo)
        except Exception as erro:
            _log(traceback.format_exc())
            if pasta:
                shutil.rmtree(pasta, ignore_errors=True)
            if self.cancelado:
                self.pai.after(0, self._fechar)
            else:
                self.pai.after(0, self._falhar, str(erro))


# ------------------------------------------------------------------
# Troca do programa e reabertura
# ------------------------------------------------------------------
def _instalar_mac(caminho_zip, alvo, pasta):
    """Descompacta o .zip, troca o .app e reabre o programa."""
    extraido = pasta / "novo"
    extraido.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/ditto", "-x", "-k", str(caminho_zip),
                    str(extraido)], check=True)
    encontrados = sorted(extraido.glob("*.app"))
    if not encontrados:
        encontrados = sorted(extraido.glob("*/*.app"))
    if not encontrados:
        raise RuntimeError("o pacote baixado não tinha um aplicativo dentro")
    novo = encontrados[0]

    # O download feito pelo próprio programa não recebe a marca de
    # quarentena do navegador, mas tiramos por garantia.
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine",
                    str(novo)], check=False)

    antigo = alvo.parent / (alvo.name + ".old")
    if antigo.exists():
        shutil.rmtree(antigo, ignore_errors=True)
    os.rename(alvo, antigo)
    try:
        subprocess.run(["/usr/bin/ditto", str(novo), str(alvo)], check=True)
    except Exception:
        if not alvo.exists():
            os.rename(antigo, alvo)
        raise

    script = pasta / "reabrir.sh"
    script.write_text(
        '#!/bin/sh\n'
        'sleep 2\n'
        'rm -rf "$1"\n'
        '/usr/bin/open "$2"\n'
        'sleep 3\n'
        'rm -rf "$3"\n',
        encoding="utf-8",
    )
    subprocess.Popen(["/bin/sh", str(script), str(antigo), str(alvo),
                      str(pasta)], start_new_session=True)
    os._exit(0)


def _instalar_windows(caminho_exe, alvo):
    """Troca o .exe (renomeando o que está rodando) e reabre o programa."""
    antigo = alvo.parent / (alvo.name + ".old")
    if antigo.exists():
        try:
            antigo.unlink()
        except Exception:
            pass
    os.replace(str(alvo), str(antigo))
    try:
        shutil.move(str(caminho_exe), str(alvo))
    except Exception:
        os.replace(str(antigo), str(alvo))
        raise

    bat = Path(tempfile.gettempdir()) / ("reabrir_%s.bat" % os.getpid())
    bat.write_text(
        "@echo off\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        "del /q %1 >nul 2>&1\r\n"
        "start \"\" %2\r\n",
        encoding="ascii",
    )
    separado = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen(["cmd", "/c", str(bat), str(antigo), str(alvo)],
                     creationflags=separado, close_fds=True)
    os._exit(0)
