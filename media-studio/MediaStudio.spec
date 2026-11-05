# -*- mode: python ; coding: utf-8 -*-
"""Receita do Media Studio com tudo embutido, para mandar a outro Mac.

O aplicativo do `criar-media-studio-mac.command` usa o Python da maquina que
o instalou, entao nao roda em outro computador. Este aqui leva o Python junto.

A versao nao fica escrita aqui: e lida do media_studio.py, para nunca
dessincronizar com o rodape da janela.

Gerar com um Python autonomo (o do Homebrew so abriria no macOS 26 em diante):
    uv python install 3.13
    MACOSX_DEPLOYMENT_TARGET=12.0 uv pip install \
        --python-platform aarch64-apple-darwin --only-binary :all: \
        pyinstaller numpy Pillow reportlab certifi
    pyinstaller --noconfirm MediaStudio.spec
"""

import os
import re

_raiz = SPECPATH  # noqa: F821 (o PyInstaller define esta variavel)

VERSAO = "0.0.0"
with open(os.path.join(_raiz, "media_studio.py"), encoding="utf-8") as _f:
    _achado = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _f.read(), re.M)
if _achado:
    VERSAO = _achado.group(1)

# As abas sao importadas pelo nome na hora do clique, e o PyInstaller nao
# enxerga import assim. Por isso os dois pacotes sao varridos aqui: aba nova
# entra sozinha, sem depender de lembrar de listar.
OCULTOS = ['tema', 'pastas', 'atualizador', 'certifi', 'numpy', 'PIL',
           'conversor', 'dados', 'documento', 'pagina_pdf', 'transcritor']
for _pacote in ('abas', 'compartilhado'):
    for _pasta, _subpastas, _arquivos in os.walk(os.path.join(_raiz, _pacote)):
        _subpastas[:] = [s for s in _subpastas if s != '__pycache__']
        _modulo = os.path.relpath(_pasta, _raiz).replace(os.sep, '.')
        OCULTOS.append(_modulo)
        OCULTOS += [_modulo + '.' + a[:-3] for a in _arquivos
                    if a.endswith('.py') and a != '__init__.py']

BINARIOS = [(os.path.join(_raiz, b), '.') for b in ('ffmpeg', 'ffprobe')]
# O trabalhador da transcricao roda num Python separado, entao viaja como
# arquivo solto, e as bibliotecas dele nao entram aqui.
DADOS = [(os.path.join(_raiz, d), '.')
         for d in ('icon.png', 'trabalhador_whisper.py')]

a = Analysis(
    [os.path.join(_raiz, 'media_studio.py')],
    pathex=[_raiz],
    binaries=BINARIOS,
    datas=DADOS,
    hiddenimports=OCULTOS,
    excludes=['pyautogui', 'mss', 'mlx_whisper', 'faster_whisper',
              'sherpa_onnx', 'huggingface_hub'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MediaStudio',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='MediaStudio')
app = BUNDLE(
    coll,
    name='Media Studio.app',
    icon=os.path.join(_raiz, 'icon.icns'),
    bundle_identifier='br.com.avm.mediastudio',
    info_plist={
        'CFBundleShortVersionString': VERSAO,
        'CFBundleVersion': VERSAO,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)
