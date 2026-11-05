"""Trabalhador da transcricao: o pedaco que roda DENTRO do motor do Whisper.

Este arquivo nao e importado pelo Media Studio. Ele e executado como um
programa a parte, pelo Python do motor (o ambiente proprio que a aba
"Transcrever" monta uma vez, em Application Support), e conversa com a aba
so por texto: cada linha que ele escreve na saida e um recado em JSON.

    {"tipo": "duracao", "s": 1834.2}
    {"tipo": "trecho", "ini": 12.4, "fim": 17.9, "texto": "Bom dia."}
    {"tipo": "pronto", "idioma": "pt", "segmentos": [...]}
    {"tipo": "erro", "msg": "..."}

e, na separacao de quem fala:

    {"tipo": "separando", "fracao": 0.42}
    {"tipo": "pronto", "turnos": [[0.0, 7.2, 1], [7.7, 15.6, 0], ...]}

Por que um programa separado, e nao uma funcao da aba:

- o motor e o modelo pesam mais de 2 GB e nao cabem dentro do aplicativo;
  ficam numa pasta do usuario e sobrevivem a reinstalacao do Media Studio;
- a janela nunca trava, nem quando o Whisper ocupa a placa de video inteira;
- Cancelar e encerrar este processo, que larga a memoria na hora.

Dois motores, escolhidos pela aba conforme o computador:

- "mlx": Mac com chip Apple (M1 em diante). Usa a placa de video do Mac e e,
  medido aqui, seis vezes mais rapido que o outro (4,5 min de audio em 31 s
  num M1 Pro, contra 185 s).
- "faster": qualquer outro computador (Mac Intel, Windows). Usa so o
  processador.

A separacao de quem fala (diarizacao) e outro trabalho, num processo
proprio: o Whisper ocupa a placa de video e ela, o processador, entao os dois
rodam ao mesmo tempo. Ela usa o sherpa-onnx, que nao precisa do PyTorch, com
dois modelos pequenos: um acha onde ha voz e onde ela troca, o outro tira a
"impressao digital" de cada voz para juntar os trechos da mesma pessoa.

Uso:
    python trabalhador_whisper.py baixar <repositorio> <pasta destino> [arquivo]
    python trabalhador_whisper.py transcrever <arquivo .json com as opcoes>
    python trabalhador_whisper.py separar <arquivo .json com as opcoes>

So depende do que o motor instalou; nada do Media Studio entra aqui.
"""

import json
import os
import re
import subprocess
import sys

TAXA = 16000   # o Whisper so ouve audio mono a 16 kHz

# Frases que o Whisper "ouve" em trecho de silencio porque foram muito
# repetidas nos videos legendados com que ele aprendeu. Saem so quando sao a
# fala INTEIRA do trecho, nunca do meio de uma fala de verdade.
ALUCINACOES = [
    "legendas pela comunidade amara.org",
    "legenda adriana zanotto",
    "legendado por",
    "obrigado por assistir",
    "obrigada por assistir",
    "inscreva-se no canal",
    "e nao se esqueca de se inscrever no canal",
    "sous-titres realises par la communaute d'amara.org",
    "subtitles by the amara.org community",
]

_SAIDA = sys.stdout


def avisar(**recado):
    _SAIDA.write(json.dumps(recado, ensure_ascii=False) + "\n")
    _SAIDA.flush()


# ---------------------------------------------------------------- baixar

def baixar(repositorio, destino, arquivo=None):
    """Baixa o modelo para `destino`. Retoma de onde parou, se cair.

    Com `arquivo`, baixa so ele: o repositorio dos modelos de voz guarda
    duas dezenas de modelos, e so um interessa.
    """
    from huggingface_hub import snapshot_download
    os.makedirs(destino, exist_ok=True)
    snapshot_download(repo_id=repositorio, local_dir=destino,
                      allow_patterns=[arquivo] if arquivo else None)
    if arquivo and not os.path.isfile(os.path.join(destino, arquivo)):
        raise ValueError("O arquivo %s nao veio do repositorio %s."
                         % (arquivo, repositorio))
    # A marca so e gravada no fim: modelo pela metade nunca passa por pronto.
    with open(os.path.join(destino, ".completo"), "w") as f:
        f.write(repositorio)
    avisar(tipo="pronto")


# ---------------------------------------------------------------- audio

def carregar_audio(arquivo, ffmpeg):
    """Le qualquer audio ou video e devolve o som no formato do Whisper.

    E o ffmpeg que abre o arquivo (MP3, M4A, WAV, MP4, MOV...), pega so a
    faixa de som, junta os canais e reduz para 16 kHz. Os dois motores
    recebem o audio ja pronto, e assim nenhum depende de biblioteca propria
    para abrir arquivo.
    """
    import numpy as np
    comando = [ffmpeg, "-nostdin", "-loglevel", "error", "-i", arquivo,
               "-vn", "-ac", "1", "-ar", str(TAXA), "-f", "f32le", "-"]
    proc = subprocess.run(comando, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        erro = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        detalhe = erro[-1] if erro else "sem resposta do ffmpeg"
        raise ValueError("Este arquivo nao tem som, ou nao pude abrir: %s"
                         % detalhe)
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def _normalizar(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[\s.!?…]+$", "", re.sub(r"\s+", " ", t)).strip()


def _alucinacao(texto):
    t = _normalizar(texto)
    return any(t == a or t.startswith(a) and len(t) < len(a) + 25
               for a in ALUCINACOES)


# A mesma palavra (ou ate quatro palavras) repetida quatro vezes ou mais em
# seguida: "tentou, tentou, tentou, tentou...". E o outro vicio conhecido do
# Whisper, quando ele "trava" num trecho de silencio ou de ruido.
_LOOP = re.compile(r"\b(\w+(?:[\s,]+\w+){0,3}?)(?:[\s,.!?…-]+\1\b){3,}",
                   re.IGNORECASE)


def _compressao(texto):
    """Quanto o texto encolhe compactado. Fala de verdade fica abaixo de 2,4;
    texto em loop encolhe muito mais (e o mesmo teste que o Whisper usa)."""
    import zlib
    bruto = texto.encode("utf-8")
    return len(bruto) / max(1, len(zlib.compress(bruto)))


def _desenrolar(texto):
    """Tira a repeticao em loop. Devolve "" se nao sobrar fala de verdade."""
    if len(texto) < 40 or _compressao(texto) <= 2.4:
        return texto
    curto = _LOOP.sub(r"\1", texto).strip()
    if _compressao(curto) > 2.4 or len(curto.split()) < 2:
        return ""
    return curto


def _limpar(segmentos):
    saida = []
    for s in segmentos:
        texto = _desenrolar((s["texto"] or "").strip())
        if not texto or _alucinacao(texto):
            continue
        saida.append({"ini": round(float(s["ini"]), 2),
                      "fim": round(float(s["fim"]), 2), "texto": texto})
    return saida


# ---------------------------------------------------------------- motores

class _LinhasDoMlx:
    """Recebe o que o mlx-whisper imprime e devolve como recado.

    Com `verbose=True` ele imprime cada trecho assim que termina de ouvir:

        [00:12.400 --> 00:17.900] Bom dia.

    E isso que deixa a aba mostrar o texto saindo e a barra andando enquanto
    ele trabalha, em vez de ficar muda ate o fim de uma entrevista de uma
    hora. O resto do que ele imprime e ignorado.
    """

    _LINHA = re.compile(r"^\[([\d:.]+) --> ([\d:.]+)\]\s?(.*)$")

    def __init__(self):
        self.resto = ""

    @staticmethod
    def _segundos(marca):
        partes = [float(p) for p in marca.split(":")]
        total = 0.0
        for p in partes:
            total = total * 60 + p
        return total

    def write(self, texto):
        self.resto += texto
        while "\n" in self.resto:
            linha, self.resto = self.resto.split("\n", 1)
            m = self._LINHA.match(linha.strip())
            if m:
                avisar(tipo="trecho", ini=self._segundos(m.group(1)),
                       fim=self._segundos(m.group(2)),
                       texto=m.group(3).strip())
        return len(texto)

    def flush(self):
        pass


def transcrever_mlx(audio, opcoes):
    import mlx_whisper
    # Os recados continuam saindo pela saida de verdade (guardada em _SAIDA
    # quando o arquivo carregou); so o que o mlx imprime passa pelo filtro.
    real = sys.stdout
    sys.stdout = _LinhasDoMlx()
    try:
        r = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=opcoes["modelo"],
            language=opcoes.get("idioma") or None,
            initial_prompt=opcoes.get("prompt") or None,
            # Sem isto, numa gravacao longa um erro de um trecho contamina o
            # seguinte e o Whisper entra em loop. Medido aqui com 4,5 min de
            # audio: com o padrao saiu "tentou, tentou, tentou..." no fim e
            # levou 24 s; assim saiu limpo, igual em toda rodada, em 11 s.
            condition_on_previous_text=False,
            verbose=True,
        )
    finally:
        sys.stdout = real
    segmentos = [{"ini": s["start"], "fim": s["end"], "texto": s["text"]}
                 for s in r.get("segments", [])]
    return r.get("language") or opcoes.get("idioma") or "", segmentos


def transcrever_faster(audio, opcoes):
    from faster_whisper import WhisperModel
    modelo = WhisperModel(opcoes["modelo"], device="cpu",
                          compute_type="int8",
                          cpu_threads=max(1, (os.cpu_count() or 2)))
    pedacos, info = modelo.transcribe(
        audio,
        language=opcoes.get("idioma") or None,
        initial_prompt=opcoes.get("prompt") or None,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
    )
    segmentos = []
    for s in pedacos:
        avisar(tipo="trecho", ini=s.start, fim=s.end, texto=s.text.strip())
        segmentos.append({"ini": s.start, "fim": s.end, "texto": s.text})
    return info.language or "", segmentos


def transcrever(arquivo_opcoes):
    with open(arquivo_opcoes, "r", encoding="utf-8") as f:
        opcoes = json.load(f)

    audio = carregar_audio(opcoes["arquivo"], opcoes["ffmpeg"])
    duracao = len(audio) / float(TAXA)
    avisar(tipo="duracao", s=round(duracao, 2))
    if duracao < 0.3:
        raise ValueError("O som deste arquivo e curto demais para transcrever.")

    if opcoes["motor"] == "mlx":
        idioma, segmentos = transcrever_mlx(audio, opcoes)
    else:
        idioma, segmentos = transcrever_faster(audio, opcoes)

    avisar(tipo="pronto", idioma=idioma, duracao=round(duracao, 2),
           segmentos=_limpar(segmentos))


# ---------------------------------------------------------------- separar

# A separacao tem duas etapas, e o numero de pessoas sai da segunda:
#
# 1. O sherpa-onnx acha ONDE ha voz e onde ela troca (os turnos). Ele tambem
#    agrupa os turnos por pessoa, mas por um limiar fixo, e nenhum limiar
#    acertou todas as gravacoes de teste: a voz "do meio" de tres (uma mulher
#    de voz grave entre outra mulher e um homem) se misturava com as outras,
#    e baixando o limiar uma gravacao real de 4 pessoas saia com 5. Por isso
#    o agrupamento dele e usado so como palpite, com o limiar baixo
#    (LIMIAR_TURNOS), que prefere partir uma pessoa em duas a juntar duas.
# 2. Aqui, cada turno (em pedacos de ate PEDACO segundos) ganha a
#    "impressao digital" da voz, e os pedacos sao agrupados de novo para 2,
#    3... ate 10 pessoas. Fica o numero em que os grupos saem mais bem
#    separados entre si (a medida chama "silhueta"). Depois, dois grupos com
#    impressoes muito parecidas (MESMA_PESSOA) viram um so: e assim que uma
#    pessoa falando sozinha nao sai partida em duas.
#
# Medido aqui (M1 Pro) em 11 gravacoes, 4 sinteticas e 7 de gente de verdade,
# com 1, 2, 3 e 4 pessoas: todas sairam com o numero certo. Entre grupos de
# uma mesma pessoa a semelhanca deu de 0,83 a 0,94; entre pessoas diferentes,
# no maximo 0,63. A velocidade e de uns 20 vezes a do audio (9 min em 34 s),
# e no Mac com chip Apple isso corre ao lado do Whisper.
#
# JANELA: o modelo que acha as trocas olha 10 s de cada vez, e a janela anda
# 25% disso a cada passo. O padrao (10%) e quatro vezes mais lento; 50% erra
# o comeco de cada fala em 1 a 2 s.
JANELA = 0.25
LIMIAR_TURNOS = 0.5
PEDACO = 8.0           # turno maior que isto e ouvido em partes
PEDACO_MINIMO = 1.0    # menos que isto nao da impressao digital confiavel
MAXIMO_PESSOAS = 10
MESMA_PESSOA = 0.75


def separar(arquivo_opcoes):
    """Diz em que horarios cada voz fala, sem saber o nome de ninguem.

    Devolve os turnos [ini, fim, numero da voz], em ordem de horario. O
    numero e so um rotulo (0, 1, 2...): quem casa cada turno com o texto do
    Whisper e a aba, e e ela que numera os Palestrantes na ordem em que
    aparecem.
    """
    with open(arquivo_opcoes, "r", encoding="utf-8") as f:
        opcoes = json.load(f)
    import numpy as np
    import sherpa_onnx

    audio = carregar_audio(opcoes["arquivo"], opcoes["ffmpeg"])
    nucleos = max(1, min(4, os.cpu_count() or 1))
    voz = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
        model=opcoes["voz"], num_threads=nucleos)
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=opcoes["segmentacao"], window_shift_ratio=JANELA),
            num_threads=nucleos),
        embedding=voz,
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=-1, threshold=LIMIAR_TURNOS),
        min_duration_on=0.3, min_duration_off=0.5)
    if not config.validate():
        raise ValueError("Os modelos que separam quem fala estao incompletos. "
                         "Clique em Preparar de novo.")

    ultimo = [-1]

    def andamento(fracao):
        # Um recado por ponto percentual, e nao um por pedaco: numa hora de
        # audio sao milhares de pedacos.
        pct = int(100 * fracao)
        if pct != ultimo[0]:
            ultimo[0] = pct
            avisar(tipo="separando", fracao=round(pct / 100.0, 2))

    # 1. Os turnos. Achar os turnos e o grosso do tempo: 85% da barra.
    separador = sherpa_onnx.OfflineSpeakerDiarization(config)
    turnos = [(float(t.start), float(t.end), int(t.speaker)) for t in
              separador.process(
                  audio, callback=lambda f, t: andamento(
                      0.85 * f / max(1, t)) or 0).sort_by_start_time()]

    # 2. A impressao digital de cada pedaco.
    pedacos = []
    for ini, fim, palpite in turnos:
        n = max(1, int(np.ceil((fim - ini) / PEDACO)))
        passo = (fim - ini) / n
        pedacos.extend((ini + i * passo, ini + (i + 1) * passo, palpite)
                       for i in range(n))
    extrator = sherpa_onnx.SpeakerEmbeddingExtractor(voz)
    medidos, impressoes = [], []
    for i, (ini, fim, _palpite) in enumerate(pedacos):
        if fim - ini >= PEDACO_MINIMO:
            fluxo = extrator.create_stream()
            fluxo.accept_waveform(TAXA, audio[int(ini * TAXA):int(fim * TAXA)])
            fluxo.input_finished()
            v = np.array(extrator.compute(fluxo), dtype=np.float64)
            norma = np.linalg.norm(v)
            if norma > 0:
                medidos.append(i)
                impressoes.append(v / norma)
        andamento(0.85 + 0.13 * (i + 1) / max(1, len(pedacos)))

    grupo = _agrupar(np.array(impressoes),
                     np.array([pedacos[i][1] - pedacos[i][0] for i in medidos]))
    rotulo = dict(zip(medidos, grupo))

    # Pedaco curto demais para medir fica com o grupo em que o palpite do
    # sherpa mais caiu; sem palpite medido, com o pedaco medido mais perto.
    votos = {}
    for i, g in rotulo.items():
        p = pedacos[i]
        votos.setdefault(p[2], {}).setdefault(g, 0.0)
        votos[p[2]][g] += p[1] - p[0]
    saida = []
    for i, (ini, fim, palpite) in enumerate(pedacos):
        if i in rotulo:
            g = rotulo[i]
        elif palpite in votos:
            g = max(votos[palpite], key=votos[palpite].get)
        elif rotulo:
            meio = (ini + fim) / 2
            g = rotulo[min(rotulo, key=lambda j: abs(
                (pedacos[j][0] + pedacos[j][1]) / 2 - meio))]
        else:
            g = palpite
        if saida and saida[-1][2] == g and ini - saida[-1][1] < 0.05:
            saida[-1][1] = round(fim, 2)
        else:
            saida.append([round(ini, 2), round(fim, 2), int(g)])
    andamento(1.0)
    avisar(tipo="pronto", turnos=saida)


def _agrupar(impressoes, pesos):
    """Agrupa as impressoes por pessoa e devolve o grupo de cada uma.

    Tenta de 2 a MAXIMO_PESSOAS grupos e fica com o que sai mais bem separado
    (a silhueta, ponderada pelo tempo de fala); depois junta os grupos que
    sao a mesma pessoa. A semente e fixa: o mesmo audio da sempre o mesmo
    resultado.
    """
    import numpy as np
    n = len(impressoes)
    if n == 0:
        return []
    if n == 1:
        return [0]
    sorteio = np.random.default_rng(0)
    distancia = 1.0 - impressoes @ impressoes.T
    melhor_nota, melhor = -2.0, np.zeros(n, dtype=int)
    if n == 2:
        melhor = np.array([0, 1])
    for k in range(2, min(MAXIMO_PESSOAS, n - 1) + 1):
        for _tentativa in range(8):
            grupos = _kmeans(impressoes, pesos, k, sorteio)
            nota = _silhueta(distancia, pesos, grupos, k)
            if nota > melhor_nota:
                melhor_nota, melhor = nota, grupos

    # Junta, um par por vez, os dois grupos mais parecidos enquanto forem
    # parecidos demais para serem pessoas diferentes.
    grupos = list(melhor)
    while True:
        presentes = sorted(set(grupos))
        if len(presentes) < 2:
            break
        centros = []
        for g in presentes:
            sel = np.array(grupos) == g
            c = (impressoes[sel] * pesos[sel, None]).sum(0)
            centros.append(c / max(np.linalg.norm(c), 1e-9))
        semelhanca = np.array(centros) @ np.array(centros).T
        np.fill_diagonal(semelhanca, -1.0)
        a, b = np.unravel_index(int(np.argmax(semelhanca)), semelhanca.shape)
        if semelhanca[a, b] <= MESMA_PESSOA:
            break
        grupos = [presentes[a] if g == presentes[b] else g for g in grupos]
    return [int(g) for g in grupos]


def _kmeans(impressoes, pesos, k, sorteio, voltas=50):
    """k-medias na esfera (semelhanca de cosseno), com inicio k-means++."""
    import numpy as np
    centros = [impressoes[sorteio.choice(len(impressoes), p=pesos / pesos.sum())]]
    for _ in range(1, k):
        longe = np.clip(1.0 - np.max(impressoes @ np.array(centros).T, axis=1),
                        0.0, None) * pesos
        if longe.sum() <= 0:
            break
        centros.append(impressoes[sorteio.choice(len(impressoes),
                                                 p=longe / longe.sum())])
    centros = np.array(centros)
    grupos = np.argmax(impressoes @ centros.T, axis=1)
    for _ in range(voltas):
        novos = []
        for j in range(len(centros)):
            sel = grupos == j
            c = (impressoes[sel] * pesos[sel, None]).sum(0) if sel.any() \
                else centros[j]
            novos.append(c / max(np.linalg.norm(c), 1e-9))
        centros = np.array(novos)
        de_novo = np.argmax(impressoes @ centros.T, axis=1)
        if np.array_equal(de_novo, grupos):
            break
        grupos = de_novo
    return grupos


def _silhueta(distancia, pesos, grupos, k):
    """O quanto cada pedaco esta mais perto do proprio grupo que do vizinho.

    Vai de -1 a 1; quanto maior, mais bem separados os grupos. Ponderada
    pelo tempo de cada pedaco, para uma tosse nao pesar como uma resposta.
    """
    import numpy as np
    n = len(grupos)
    linhas = np.arange(n)
    dono = np.eye(k)[grupos] * pesos[:, None]
    soma = distancia @ dono
    peso_grupo = dono.sum(0)
    if (peso_grupo > 0).sum() < 2:
        return -1.0
    resto = peso_grupo[grupos] - pesos
    a = np.where(resto > 0, soma[linhas, grupos] / np.maximum(resto, 1e-9), 0.0)
    media = soma / np.maximum(peso_grupo, 1e-9)
    media[linhas, grupos] = np.inf
    media[:, peso_grupo == 0] = np.inf
    b = media.min(axis=1)
    s = np.where(resto > 0, (b - a) / np.maximum(np.maximum(a, b), 1e-9), 0.0)
    return float((s * pesos).sum() / pesos.sum())


def main():
    # Nunca sair procurando nada na internet durante a transcricao: o modelo
    # ja esta na pasta, e e isso que garante funcionar desconectado.
    if len(sys.argv) >= 2 and sys.argv[1] in ("transcrever", "separar"):
        os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    try:
        if len(sys.argv) in (4, 5) and sys.argv[1] == "baixar":
            baixar(*sys.argv[2:])
        elif len(sys.argv) == 3 and sys.argv[1] == "transcrever":
            transcrever(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == "separar":
            separar(sys.argv[2])
        else:
            avisar(tipo="erro", msg="uso errado do trabalhador: %r" % sys.argv)
            return 2
    except ValueError as e:
        avisar(tipo="erro", msg=str(e))
        return 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        avisar(tipo="erro", msg="%s: %s" % (type(e).__name__, e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
