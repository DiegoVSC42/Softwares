"""Motor de transcricao offline (Whisper) da aba "Transcrever".

Este arquivo NAO tem interface: sao as funcoes que preparam o motor uma vez,
conversam com o trabalhador (`trabalhador_whisper.py`) enquanto ele ouve o
audio, e gravam o resultado no mesmo formato da aba "Limpar transcricao".

Onde as coisas ficam, e por que fora do aplicativo:

    ~/Library/Application Support/MediaStudio/Transcricao/
        python/         so no app empacotado do Mac: o Python que monta o motor
        motor-mlx/      o Python do Whisper, com as bibliotecas (~650 MB)
        modelos/...     o "cerebro" do Whisper, baixado uma vez (~1,6 GB),
                        e os dois modelos que separam quem fala (~46 MB)

O instalador do Media Studio apaga e remonta o aplicativo a cada versao. Se o
motor morasse dentro dele, cada atualizacao baixaria 2 GB de novo. Aqui ele
sobrevive as reinstalacoes, e a internet so e usada na primeira preparacao:
dali em diante, a transcricao roda com o computador desconectado.
"""

import datetime
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request

from compartilhado import legenda
from compartilhado import motor_download

# Motor -> o que o pip instala, em ordem. O mlx-whisper entra SEM as
# dependencias dele de proposito: ele pede o PyTorch (590 MB) so para um
# conversor de modelos que nunca usamos. As que ele usa de verdade vem logo
# depois, e o motor fica com metade do tamanho.
PACOTES = {
    "mlx": [
        ["--no-deps", "mlx-whisper==0.4.3"],
        ["mlx", "numpy", "numba", "scipy", "tiktoken", "more-itertools",
         "tqdm", "huggingface_hub"],
    ],
    "faster": [
        ["faster-whisper>=1.2,<2", "numpy"],
    ],
}

# O modulo que tem de abrir para o motor contar como pronto.
MODULO = {"mlx": "mlx_whisper", "faster": "faster_whisper"}

# O modelo "large-v3-turbo": a mesma qualidade do maior Whisper em portugues,
# com uma fracao do tempo. Um por motor, porque cada um le um formato.
MODELO = {
    "mlx": "mlx-community/whisper-large-v3-turbo",
    "faster": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

# O app empacotado do Mac nao tem um Python solto para montar o motor, e o Mac
# de quem usa pode nao ter nenhum. Por isso ele baixa este, autonomo, uma vez
# so. A versao e fixa e cada arquivo e conferido pelo hash. As duas origens
# servem o mesmo arquivo: a segunda cobre uma falha da primeira.
PYTHON_ORIGENS = (
    "https://releases.astral.sh/github/python-build-standalone/releases/"
    "download/20260901/",
    "https://github.com/astral-sh/python-build-standalone/releases/"
    "download/20260901/",
)
PYTHON_NOME = ("cpython-3.13.15%%2B20260901-%s-apple-darwin-"
               "install_only_stripped.tar.gz")
PYTHON_HASH = {
    "arm64": ("aarch64", "d3904bd6a072246e07aa0bdadee9a14e"
                         "80521e42a943c0848059feb16a2816dc"),
    "x86_64": ("x86_64", "f712a9143c8a5d248438ec7921a0b48d"
                         "548bca4f1337d33c690d28c2d0504137"),
}

# Tamanhos aproximados, so para a barra de progresso e a conta de espaco.
MB_MOTOR = {"mlx": 600, "faster": 250}
MB_MODELO = 1550

# Separar quem fala (opcional, marcado na aba). O sherpa-onnx roda os dois
# modelos que fazem isso SEM o PyTorch, e entra no mesmo ambiente do Whisper,
# nos dois motores. So o pacote pronto para este computador serve: compilar
# do zero levaria meia hora e falharia num Mac sem ferramentas de programador.
PACOTES_SEPARADOR = [
    ["--only-binary", "sherpa-onnx,sherpa-onnx-core", "sherpa-onnx>=1.12,<2"],
]
MODULO_SEPARADOR = "sherpa_onnx"

# Os dois modelos, cada um num repositorio. O primeiro acha onde ha voz e
# onde ela troca (pyannote 3.0); o segundo tira a "impressao digital" de cada
# voz (TitaNet). Escolhidos entre quatro, medindo aqui: foi o que acertou o
# numero de pessoas em todas as gravacoes de teste, inclusive as de gente de
# verdade, sem ser o mais lento.
MODELOS_SEPARADOR = {
    "segmentacao": ("csukuangfj/sherpa-onnx-pyannote-segmentation-3-0",
                    "model.onnx"),
    "voz": ("csukuangfj/speaker-embedding-models",
            "nemo_en_titanet_small.onnx"),
}
MB_SEPARADOR = 95   # ~45 MB do pacote, ~46 MB dos dois modelos

# Nome que a transcricao nasce usando para quem fala. Sem a separacao, o
# Whisper escreve o que foi dito mas nao sabe QUEM disse, e tudo sai em nome
# de um so; a troca e feita na aba Sincronizar. Com ela, cada voz ganha um
# numero, na ordem em que aparece. "Palestrante" e o mesmo nome do TurboScribe.
FALANTE = "Palestrante 1"
NOME_FALANTE = "Palestrante %d"


IDIOMAS = [
    ("Português", "pt"),
    ("Detectar sozinho", ""),
    ("Inglês", "en"),
    ("Espanhol", "es"),
]

_MESES = ["jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.",
          "set.", "out.", "nov.", "dez."]


class Cancelado(Exception):
    """A pessoa clicou em Cancelar."""


# ---------------------------------------------------------------- caminhos

def qual_motor():
    """'mlx' em Mac com chip Apple, 'faster' em qualquer outro computador."""
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return "mlx"
    return "faster"


def pasta_base():
    # A variavel de ambiente existe so para testar sem mexer no motor de
    # verdade; no uso normal ela nao esta definida.
    forcada = os.environ.get("MEDIA_STUDIO_TRANSCRICAO")
    if forcada:
        p = forcada
    elif os.name == "nt":
        raiz = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        p = os.path.join(raiz, "MediaStudio", "Transcricao")
    elif sys.platform == "darwin":
        p = os.path.expanduser(
            "~/Library/Application Support/MediaStudio/Transcricao")
    else:
        p = os.path.expanduser("~/.media-studio/transcricao")
    os.makedirs(p, exist_ok=True)
    return p


def pasta_motor(motor):
    return os.path.join(pasta_base(), "motor-" + motor)


def python_do_motor(motor):
    if os.name == "nt":
        return os.path.join(pasta_motor(motor), "Scripts", "python.exe")
    return os.path.join(pasta_motor(motor), "bin", "python")


def pasta_modelo(motor):
    return os.path.join(pasta_base(), "modelos",
                        MODELO[motor].replace("/", "__"))


def pasta_modelo_separador(chave):
    repositorio, _arquivo = MODELOS_SEPARADOR[chave]
    return os.path.join(pasta_base(), "modelos",
                        repositorio.replace("/", "__"))


def arquivo_modelo_separador(chave):
    return os.path.join(pasta_modelo_separador(chave),
                        MODELOS_SEPARADOR[chave][1])


def caminho_trabalhador():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "trabalhador_whisper.py")


def python_base():
    """O Python que cria o ambiente do motor.

    Rodando pelo codigo-fonte (o caso do aplicativo montado pelo instalador),
    e o proprio Python que abriu a janela: ele ja provou que funciona. Num
    executavel empacotado nao ha Python solto dentro dele, e e preciso achar
    um instalado na maquina.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable
    # No app empacotado do Mac nao se procura Python instalado: num Mac sem
    # as ferramentas de programador, so tocar no /usr/bin/python3 abre uma
    # janela do sistema pedindo para instala-las. `_baixar_python` resolve.
    if sys.platform == "darwin":
        return None
    candidatos = [
        "/opt/homebrew/bin/python3", "/usr/local/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
        shutil.which("python3") or "", shutil.which("python") or "",
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            try:
                ok = subprocess.run(
                    [c, "-c", "import sys, venv; "
                              "sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                    capture_output=True, timeout=20).returncode == 0
            except Exception:
                ok = False
            if ok:
                return c
    return None


def _ambiente():
    """Ambiente limpo para os processos do motor.

    O lancador do aplicativo poe as bibliotecas dele no PYTHONPATH. Se isso
    vazasse para o motor, o Python do motor carregaria o numpy do aplicativo
    em vez do proprio, e quebraria sem explicacao. O ffmpeg entra na frente
    do PATH porque e ele quem abre o audio.
    """
    env = dict(os.environ)
    for chave in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV",
                  "__PYVENV_LAUNCHER__"):
        env.pop(chave, None)
    pasta_ff = motor_download.find_ffmpeg_dir()
    if pasta_ff:
        env["PATH"] = pasta_ff + os.pathsep + env.get("PATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    return env


def _sem_janela():
    """No Windows, impede que cada processo abra uma janela preta."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


# ---------------------------------------------------------------- estado

def _abre(motor, modulo):
    """O Python do motor consegue abrir `modulo`?"""
    py = python_do_motor(motor)
    if not os.path.isfile(py):
        return False
    try:
        return subprocess.run(
            [py, "-I", "-c", "import " + modulo],
            capture_output=True, timeout=120, env=_ambiente(),
            **_sem_janela()).returncode == 0
    except Exception:
        return False


def motor_pronto(motor):
    return _abre(motor, MODULO[motor])


def modelo_pronto(motor):
    return os.path.isfile(os.path.join(pasta_modelo(motor), ".completo"))


def _modelo_separador_pronto(chave):
    return (os.path.isfile(os.path.join(pasta_modelo_separador(chave),
                                        ".completo")) and
            os.path.isfile(arquivo_modelo_separador(chave)))


def separador_pronto(motor):
    """Da para separar quem fala, sem internet?"""
    return (all(_modelo_separador_pronto(c) for c in MODELOS_SEPARADOR) and
            _abre(motor, MODULO_SEPARADOR))


def _tamanho_mb(pasta):
    total = 0
    for raiz, _pastas, arquivos in os.walk(pasta):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                pass
    return total / (1024 * 1024)


def espaco_livre_mb():
    try:
        return shutil.disk_usage(pasta_base()).free / (1024 * 1024)
    except Exception:
        return None


# ---------------------------------------------------------------- execucao

class Execucao:
    """Um processo do motor em andamento, que pode ser cancelado.

    A separacao de quem fala roda num processo ao lado do Whisper, com uma
    execucao "filha": Cancelar encerra os dois, e um erro no Whisper encerra
    so a filha daquele arquivo, sem parar a fila.
    """

    def __init__(self):
        self.proc = None
        self.cancelado = False
        self.filhas = []

    def filha(self):
        f = Execucao()
        f.cancelado = self.cancelado
        self.filhas.append(f)
        return f

    def cancelar(self):
        self.cancelado = True
        for f in list(self.filhas):
            f.cancelar()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def conferir(self):
        if self.cancelado:
            raise Cancelado()


def _rodar(execucao, comando, ao_linha=None, ao_tique=None):
    """Roda `comando`, entregando cada linha da saida a `ao_linha`.

    A saida de erro e lida em paralelo (senao um processo que escreve muito
    nela trava esperando alguem ler) e as ultimas linhas voltam junto, para
    explicar uma falha. `ao_tique` e chamado a cada meio segundo, para quem
    precisa medir progresso por fora (o tamanho da pasta que esta baixando).
    """
    execucao.conferir()
    proc = subprocess.Popen(
        comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, env=_ambiente(), text=True,
        encoding="utf-8", errors="replace", bufsize=1, **_sem_janela())
    execucao.proc = proc
    erros = []

    def ler_erros():
        for linha in proc.stderr:
            erros.append(linha.rstrip())
            del erros[:-60]

    t_erros = threading.Thread(target=ler_erros, daemon=True)
    t_erros.start()

    parar_tique = threading.Event()
    if ao_tique is not None:
        def tique():
            while not parar_tique.wait(0.5):
                try:
                    ao_tique()
                except Exception:
                    pass
        threading.Thread(target=tique, daemon=True).start()

    try:
        for linha in proc.stdout:
            if ao_linha is not None:
                ao_linha(linha.rstrip("\n"))
        proc.wait()
    finally:
        parar_tique.set()
        t_erros.join(timeout=2)
        execucao.proc = None
    execucao.conferir()
    return proc.returncode, erros


# ---------------------------------------------------------------- preparar

def preparar(execucao, avisar):
    """Instala o motor e baixa o modelo, o que faltar. Precisa de internet.

    `avisar(texto, fracao)` recebe o andamento; `fracao` vai de 0 a 1, ou e
    None quando nao da para medir. Levanta RuntimeError com uma explicacao
    em portugues se algo der errado, e Cancelado se a pessoa desistir.
    """
    motor = qual_motor()
    falta_motor = not motor_pronto(motor)
    falta_modelo = not modelo_pronto(motor)
    # A separacao de quem fala entra na mesma preparacao, mesmo que a opcao
    # esteja desmarcada: sao uns 95 MB perto de 2 GB, e assim ela funciona
    # sem internet no dia em que alguem marcar.
    falta_separador = not separador_pronto(motor)
    if not (falta_motor or falta_modelo or falta_separador):
        return

    precisa = ((MB_MOTOR[motor] if falta_motor else 0) +
               (MB_MODELO if falta_modelo else 0) +
               (MB_SEPARADOR if falta_separador else 0) + 500)
    livre = espaco_livre_mb()
    if livre is not None and livre < precisa:
        raise RuntimeError(
            "Falta espaço no disco: preciso de uns %.1f GB livres e há %.1f GB."
            % (precisa / 1024, livre / 1024))

    if falta_motor:
        _instalar_motor(motor, execucao, avisar)
    if falta_modelo:
        _baixar_modelo(motor, execucao, avisar)
    if falta_separador:
        _preparar_separador(motor, execucao, avisar)


def _instalar_motor(motor, execucao, avisar):
    py = python_do_motor(motor)
    if not os.path.isfile(py) or not _python_vivo(py):
        # Ambiente quebrado (o Python que o criou foi atualizado ou
        # removido, por exemplo): recomeca do zero. O modelo nao e tocado.
        shutil.rmtree(pasta_motor(motor), ignore_errors=True)
        base = python_base()
        if not base and sys.platform == "darwin":
            base = _baixar_python(execucao, avisar)
        if not base:
            raise RuntimeError(
                "Não encontrei um Python instalado neste computador para "
                "montar o motor. Instale o Python do site python.org e tente "
                "de novo.")
        avisar("Criando o ambiente do motor...", None)
        codigo, erros = _rodar(execucao, [base, "-m", "venv", pasta_motor(motor)])
        if codigo != 0 or not os.path.isfile(py):
            raise RuntimeError("Não consegui criar o ambiente do motor.\n\n"
                               + "\n".join(erros[-8:]))

    _pip(py, PACOTES[motor], "Instalando o motor",
         "Não consegui instalar o motor.", execucao, avisar)
    if not motor_pronto(motor):
        raise RuntimeError("O motor foi instalado, mas não abriu. "
                           "Tente preparar de novo.")


def _baixar_python(execucao, avisar):
    """Baixa o Python que monta o motor, uma vez so. Devolve o caminho dele."""
    destino = os.path.join(pasta_base(), "python")
    py = os.path.join(destino, "bin", "python3")
    if _python_vivo(py):
        return py
    if platform.machine() not in PYTHON_HASH:
        raise RuntimeError("Este computador não tem um Python que sirva para "
                           "montar o motor.")
    arquitetura, esperado = PYTHON_HASH[platform.machine()]
    pasta = tempfile.mkdtemp(prefix="python-", dir=pasta_base())
    try:
        arquivo = os.path.join(pasta, "python.tar.gz")
        _baixar_pacote_python(PYTHON_NOME % arquitetura, esperado, arquivo,
                              execucao, avisar)
        avisar("Preparando o Python...", None)
        with tarfile.open(arquivo) as pacote:
            pacote.extractall(pasta, filter="data")
        shutil.rmtree(destino, ignore_errors=True)
        os.replace(os.path.join(pasta, "python"), destino)
    except (OSError, tarfile.TarError) as e:
        raise RuntimeError("Não consegui preparar o Python. Tente de novo.\n\n"
                           + str(e))
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    if not _python_vivo(py):
        raise RuntimeError("O Python foi baixado, mas não abriu. Tente "
                           "preparar de novo.")
    return py


def _baixar_pacote_python(nome, esperado, destino, execucao, avisar):
    """Grava o pacote em `destino`, conferido pelo hash, tentando as origens."""
    ultimo = ""
    for origem in PYTHON_ORIGENS:
        try:
            pedido = urllib.request.Request(
                origem + nome, headers={"User-Agent": "MediaStudio"})
            resumo = hashlib.sha256()
            with urllib.request.urlopen(
                    pedido, timeout=60,
                    context=motor_download._contexto_ssl()) as resposta, \
                    open(destino, "wb") as saida:
                total = int(resposta.headers.get("Content-Length") or 0)
                feito = 0
                while True:
                    execucao.conferir()
                    pedaco = resposta.read(262144)
                    if not pedaco:
                        break
                    saida.write(pedaco)
                    resumo.update(pedaco)
                    feito += len(pedaco)
                    if total:
                        avisar("Baixando o Python: %d de %d MB"
                               % (feito / 1048576, total / 1048576),
                               feito / total)
            if resumo.hexdigest() == esperado:
                return
            ultimo = "o arquivo veio diferente do esperado"
        except (OSError, http.client.HTTPException) as e:
            ultimo = str(e)
    raise RuntimeError("Não consegui baixar o Python. Confira a internet e "
                       "tente de novo.\n\n" + ultimo)


def _pip(py, grupos, rotulo, falha, execucao, avisar):
    """Instala os `grupos` de pacotes, um pip por grupo, contando o passo."""
    for i, grupo in enumerate(grupos):
        def linha(texto, i=i):
            # O pip fala ingles; aqui so aproveitamos o nome da peca da vez.
            partes = texto.strip().split()
            if len(partes) >= 2 and partes[0] in ("Collecting", "Downloading"):
                peca = re.sub(r"-\d.*$", "", partes[1].split("/")[-1])
                peca = re.split(r"[=<>!~;\[(]", peca)[0]
                avisar("%s (passo %d de %d): baixando %s..."
                       % (rotulo, i + 1, len(grupos), peca), None)
            elif texto.startswith("Installing collected packages"):
                avisar("%s (passo %d de %d): gravando..."
                       % (rotulo, i + 1, len(grupos)), None)
        codigo, erros = _rodar(
            execucao,
            [py, "-I", "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", "--progress-bar", "off"] + grupo,
            ao_linha=linha)
        if codigo != 0:
            raise RuntimeError(
                falha + " Confira a internet e tente de novo.\n\n"
                + "\n".join(erros[-8:]))


def _python_vivo(py):
    try:
        return subprocess.run([py, "-I", "-c", "pass"], capture_output=True,
                              timeout=30, **_sem_janela()).returncode == 0
    except Exception:
        return False


def _baixar_modelo(motor, execucao, avisar):
    _baixar(motor, MODELO[motor], None, pasta_modelo(motor), MB_MODELO,
            "o modelo do Whisper", execucao, avisar)
    if not modelo_pronto(motor):
        raise RuntimeError("O modelo veio incompleto. Tente preparar de novo.")
    avisar("Modelo pronto.", 1.0)


def _baixar(motor, repositorio, arquivo, destino, mb, oque, execucao, avisar):
    """Baixa `repositorio` (ou so `arquivo` dele) com a barra andando."""
    avisar("Baixando %s..." % oque, 0.0)

    def tique():
        feito = _tamanho_mb(destino)
        avisar("Baixando %s: %d de ~%d MB" % (oque, feito, mb),
               min(0.99, feito / max(1, mb)))

    comando = [python_do_motor(motor), "-I", caminho_trabalhador(), "baixar",
               repositorio, destino]
    if arquivo:
        comando.append(arquivo)
    codigo, erros = _rodar(execucao, comando, ao_tique=tique)
    if codigo != 0 or not os.path.isfile(os.path.join(destino, ".completo")):
        raise RuntimeError(
            "Não consegui baixar %s. Confira a internet e tente de novo: o "
            "que já veio fica guardado, e ele continua de onde parou.\n\n"
            % oque + "\n".join(erros[-6:]))


def _preparar_separador(motor, execucao, avisar):
    """O pacote e os dois modelos que separam quem fala (~95 MB)."""
    if not _abre(motor, MODULO_SEPARADOR):
        _pip(python_do_motor(motor), PACOTES_SEPARADOR,
             "Instalando o separador de vozes",
             "Não consegui instalar o separador de vozes.", execucao, avisar)
        if not _abre(motor, MODULO_SEPARADOR):
            raise RuntimeError("O separador de vozes foi instalado, mas não "
                               "abriu. Tente preparar de novo.")
    tamanhos = {"segmentacao": 6, "voz": 40}
    for chave, (repositorio, arquivo) in MODELOS_SEPARADOR.items():
        if not _modelo_separador_pronto(chave):
            _baixar(motor, repositorio, arquivo, pasta_modelo_separador(chave),
                    tamanhos[chave], "o separador de vozes (%d de 2)"
                    % (list(MODELOS_SEPARADOR).index(chave) + 1),
                    execucao, avisar)
    if not separador_pronto(motor):
        raise RuntimeError("O separador de vozes veio incompleto. Tente "
                           "preparar de novo.")
    avisar("Separador de vozes pronto.", 1.0)


# ---------------------------------------------------------------- transcrever

def transcrever(arquivo, idioma, prompt, execucao, ao_recado, separar=False):
    """Transcreve `arquivo` sem internet. Devolve o recado final do trabalhador.

    `ao_recado(dict)` recebe, enquanto ele trabalha, a duracao do audio e
    cada trecho ouvido. O resultado traz `segmentos` (ini, fim, texto).

    `separar` liga a separacao de quem fala, que descobre sozinha quantas
    pessoas sao. Com ela, cada segmento ganha `falante` (1, 2, 3...) e o
    resultado traz `pessoas`, quantas sairam. Se so a separacao falhar, a
    transcricao nao se perde: sai toda em nome de um so, e o motivo vem em
    `aviso`.
    """
    motor = qual_motor()
    if not (motor_pronto(motor) and modelo_pronto(motor)):
        raise RuntimeError("O motor de transcrição ainda não foi preparado.")
    if separar and not separador_pronto(motor):
        raise RuntimeError("A separação de quem fala ainda não foi preparada.")
    ffmpeg = motor_download.find_ffmpeg_exe()
    if not ffmpeg:
        raise RuntimeError("Não encontrei o ffmpeg, que abre o áudio.")

    opcoes = {
        "arquivo": arquivo, "ffmpeg": ffmpeg, "motor": motor,
        "modelo": pasta_modelo(motor), "idioma": idioma or "",
        "prompt": (prompt or "").strip(),
    }
    separacao = None
    if separar:
        separacao = _Separacao(motor, execucao.filha(), {
            "arquivo": arquivo, "ffmpeg": ffmpeg,
            "segmentacao": arquivo_modelo_separador("segmentacao"),
            "voz": arquivo_modelo_separador("voz"),
        }, ao_recado)
        # No Mac com chip Apple o Whisper usa a placa de video, e a separacao
        # o processador: rodando juntos, ela sai de graca. No outro motor os
        # dois disputariam o processador, entao ela fica para depois.
        if motor == "mlx":
            separacao.comecar()

    try:
        final = _trabalho(motor, "transcrever", opcoes, execucao, ao_recado)
    except BaseException:
        if separacao is not None:
            separacao.parar()
        raise
    if separacao is None:
        return final

    ao_recado({"tipo": "esperando_separacao"})
    turnos, erro = separacao.esperar()
    execucao.conferir()
    if erro:
        final["aviso"] = ("não deu para separar quem fala (%s); saiu tudo em "
                          "nome de %s" % (erro, FALANTE))
    else:
        final["segmentos"], final["pessoas"] = atribuir_falantes(
            final.get("segmentos") or [], turnos)
    return final


def _trabalho(motor, tarefa, opcoes, execucao, ao_recado):
    """Roda uma tarefa do trabalhador e devolve o recado "pronto" dele."""
    fd, caminho_opcoes = tempfile.mkstemp(prefix=tarefa + "-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(opcoes, f, ensure_ascii=False)

    final = {}

    def linha(texto):
        try:
            recado = json.loads(texto)
        except ValueError:
            return
        if recado.get("tipo") in ("pronto", "erro"):
            final.update(recado)
        else:
            ao_recado(recado)

    try:
        codigo, erros = _rodar(
            execucao,
            [python_do_motor(motor), "-I", caminho_trabalhador(),
             tarefa, caminho_opcoes],
            ao_linha=linha)
    finally:
        try:
            os.remove(caminho_opcoes)
        except OSError:
            pass

    if final.get("tipo") == "pronto":
        return final
    if final.get("tipo") == "erro":
        raise RuntimeError(final.get("msg") or "falha no motor")
    raise RuntimeError("O motor parou sem terminar.\n\n" + "\n".join(erros[-6:]))


class _Separacao:
    """A separacao de quem fala de um arquivo, num processo a parte."""

    def __init__(self, motor, execucao, opcoes, ao_recado):
        self.motor = motor
        self.execucao = execucao
        self.opcoes = opcoes
        self.ao_recado = ao_recado
        self.linha = None
        self.turnos = None
        self.erro = None

    def comecar(self):
        self.linha = threading.Thread(target=self._rodar, daemon=True)
        self.linha.start()

    def _rodar(self):
        try:
            final = _trabalho(self.motor, "separar", self.opcoes,
                              self.execucao, self.ao_recado)
            self.turnos = final.get("turnos") or []
        except Cancelado:
            self.erro = "cancelada"
        except Exception as e:
            self.erro = str(e).strip().split("\n")[0] or "falha"

    def parar(self):
        self.execucao.cancelar()
        if self.linha is not None:
            self.linha.join(timeout=6)

    def esperar(self):
        """Espera terminar (ou roda agora, se ainda nao comecou)."""
        if self.linha is None:
            self._rodar()
        else:
            self.linha.join()
        return self.turnos, self.erro


def atribuir_falantes(segmentos, turnos):
    """Diz quem falou cada trecho do Whisper, casando os horarios.

    `turnos` vem da separacao: [ini, fim, voz], em que `voz` e so um rotulo.
    Cada trecho fica com a voz que mais ocupou o tempo dele. (Pedir ao
    Whisper o horario de cada palavra, para partir um trecho em que duas
    pessoas falaram, foi medido e descartado: dobrava o tempo da transcricao
    e quase nunca ha trecho assim, porque o Whisper ja corta na pausa.)

    Devolve (segmentos com `falante`, quantas pessoas), com as pessoas
    numeradas 1, 2, 3... na ordem em que falam pela primeira vez.
    """
    turnos = sorted((float(a), float(b), k) for a, b, k in turnos if b > a)
    if not turnos:
        return [dict(s, falante=1) for s in segmentos], 1 if segmentos else 0

    def quem(ini, fim):
        votos = {}
        for a, b, voz in turnos:
            if a >= fim:
                break
            if b > ini:
                votos[voz] = votos.get(voz, 0.0) + min(b, fim) - max(a, ini)
        if votos:
            return max(votos, key=votos.get)
        # No meio de um silencio (ou de um trecho que o separador nao ouviu):
        # fica com quem estava falando mais perto dali.
        meio = (ini + fim) / 2.0
        return min(turnos, key=lambda t: max(t[0] - meio, meio - t[1], 0.0))[2]

    numero = {}
    saida = []
    for s in segmentos:
        voz = quem(s["ini"], s["fim"])
        if voz not in numero:
            numero[voz] = len(numero) + 1
        saida.append(dict(s, falante=numero[voz]))
    return saida, len(numero)


# ---------------------------------------------------------------- gravar

def data_do_arquivo(caminho):
    """A data da gravacao, no mesmo jeito do TurboScribe: 25 de jul. de 2026, 12:11."""
    try:
        d = datetime.datetime.fromtimestamp(os.path.getmtime(caminho))
    except OSError:
        d = datetime.datetime.now()
    return "%d de %s de %d, %02d:%02d" % (d.day, _MESES[d.month - 1], d.year,
                                         d.hour, d.minute)


def nome_do_falante(numero, nomes=None):
    """O nome escrito pela pessoa, ou "Palestrante N" enquanto nao houver."""
    return ((nomes or {}).get(numero) or "").strip() or NOME_FALANTE % numero


def limpar_nome(texto):
    """O nome como pode entrar no arquivo sem confundir quem le depois.

    A aba Sincronizar so reconhece como nome uma linha curta que nao comeca
    com horario; um nome comprido ou "(0:12) Ana" viraria fala. Por isso:
    sem quebra de linha, sem horario no comeco e no maximo 40 letras.
    """
    t = re.sub(r"\s+", " ", texto or "").strip()
    t = re.sub(r"^\(\s*\d{1,2}:\d{2}(?::\d{2})?\s*\)\s*", "", t)
    return t[:40].strip()


def primeiras_falas(segmentos, tamanho=90):
    """Para cada pessoa, o horario e o comeco do que ela disse primeiro.

    E o que aparece ao lado de cada campo de nome, para a pessoa saber quem
    e quem sem adivinhar. Quando a primeira fala e curtinha ("Bom dia."), ela
    sozinha nao ajuda a reconhecer ninguem: vai junto a primeira fala longa
    da mesma pessoa, com o horario dela. Devolve
    [(numero, segundos, "(0:06) Claro, o programa..."), ...] por numero.
    """
    # Falas seguidas da mesma pessoa formam um turno: [numero, ini, texto].
    turnos = []
    for s in segmentos:
        n = s.get("falante")
        if not n:
            continue
        if turnos and turnos[-1][0] == n:
            turnos[-1][2] += " " + s["texto"].strip()
        else:
            turnos.append([n, s["ini"], s["texto"].strip()])

    def cortar(texto, limite):
        texto = texto.strip()
        if len(texto) <= limite:
            return texto
        return texto[:limite].rsplit(" ", 1)[0] + "..."

    saida = []
    for n in sorted({t[0] for t in turnos}):
        dela = [t for t in turnos if t[0] == n]
        _, ini, texto = dela[0]
        rotulo = "(%s) %s" % (legenda.formatar(ini), cortar(texto, tamanho))
        if len(texto) < 25:
            longa = next((t for t in dela[1:] if len(t[2]) >= 25), None)
            if longa is not None:
                rotulo += "  ·  (%s) %s" % (legenda.formatar(longa[1]),
                                            cortar(longa[2], tamanho))
        saida.append((n, ini, rotulo))
    return saida


def montar_itens(segmentos, falante=FALANTE, pausa=2.0, por_paragrafo=8,
                 nomes=None):
    """Segmentos do Whisper no formato da aba "Limpar transcricao".

        Palestrante 1
        (0:00) Bom dia. (0:06) Claro, o programa atende...

        (0:31) E quantas familias...

        Palestrante 2
        (0:48) Umas trezentas.

    E exatamente o formato que a aba Sincronizar abre. Um bloco novo, com o
    nome, comeca sempre que a pessoa troca (quando a separacao de quem fala
    deu um `falante` a cada segmento; sem ela, tudo sai em nome de
    `falante`). O nome e o que estiver em `nomes` ({numero: "Ana"}), ou
    "Palestrante N". Dois numeros com o mesmo nome viram a mesma pessoa: e
    assim que se junta alguem que o separador partiu em dois. Dentro do
    bloco, um paragrafo novo comeca numa pausa de `pausa` segundos ou a cada
    `por_paragrafo` trechos, para o texto nao virar um bloco so de uma hora.
    """
    itens = []
    bloco, fim_anterior, atual = [], None, None

    def fechar():
        if bloco:
            itens.append((" ".join(bloco), "fala"))
            del bloco[:]

    for s in segmentos:
        numero = s.get("falante")
        nome = nome_do_falante(numero, nomes) if numero else falante
        if nome != atual:
            fechar()
            if itens:
                itens.append(("", "vazio"))
            itens.append((nome, "nome"))
            atual = nome
        elif bloco and (s["ini"] - fim_anterior >= pausa or
                        len(bloco) >= por_paragrafo):
            fechar()
            itens.append(("", "vazio"))
        bloco.append("(%s) %s" % (legenda.formatar(s["ini"]), s["texto"]))
        fim_anterior = s["fim"]
    fechar()
    return itens


def _tempo_srt(t):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def gravar_srt(caminho, segmentos, nomes=None):
    """Legenda .srt, que qualquer editor de video e o YouTube aceitam.

    Com quem fala separado, a legenda diz o nome na troca de pessoa
    ("Ana: Bom dia."), como se faz em legenda de entrevista: repetir o nome
    em toda linha so atrapalharia a leitura.
    """
    blocos = []
    anterior = None
    for i, s in enumerate(segmentos, start=1):
        fim = max(s["fim"], s["ini"] + 0.5)
        texto = s["texto"]
        if s.get("falante"):
            nome = nome_do_falante(s["falante"], nomes)
            if nome != anterior:
                texto = "%s: %s" % (nome, texto)
            anterior = nome
        blocos.append("%d\n%s --> %s\n%s\n" % (
            i, _tempo_srt(s["ini"]), _tempo_srt(fim), texto))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(blocos))
