# -*- mode: python ; coding: utf-8 -*-
"""Receita de empacotamento do Image Studio (usada no Mac).

Existe por um motivo so: buildar por flags soltas do PyInstaller nunca
preenche a versao do bundle, e o Finder acaba mostrando "0.0.0" em
Informacoes (Cmd+I). A versao so entra no Info.plist quando o build sai de
um .spec, como este.

A versao NAO fica escrita aqui: e lida do proprio estudio_imagem.py, para
nunca dessincronizar com o rodape da janela.
"""

import os
import re

VERSAO = "0.0.0"
try:
    _fonte = open("estudio_imagem.py", encoding="utf-8").read()
    _achado = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _fonte, re.M)
    if _achado:
        VERSAO = _achado.group(1)
except Exception:
    pass

# O programa nao e um arquivo so: `estudio_imagem.py` monta cada aba com
# __import__ no momento em que a pessoa clica nela. Import feito assim, por
# nome montado em tempo de execucao, o PyInstaller nao enxerga sozinho --
# entao cada modulo do pacote `abas` precisa ser listado a mao aqui, senao o
# app abre e todas as abas falham.
#
# Pillow (PIL) e numpy sao o motor deste estudio: PIL abre, corta,
# redimensiona e grava as imagens, e o numpy acha a area preenchida do PNG
# na aba Figurinhas. Este programa NAO usa ffmpeg.
OCULTOS = [
    'tema',
    'pastas',
    'atualizador',
    'certifi',
    'abas',
    'abas.comprimir',
    'abas.redimensionar',
    'abas.figurinhas',
    'abas.printshot',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageOps',
    'PIL.ImageTk',
    'PIL.ImageGrab',
    'PIL.ImageStat',
    'numpy',
]

# Este estudio nao carrega motor externo (nada de ffmpeg): so o icone da
# janela viaja junto.
DADOS = [(d, '.') for d in ('icon.png', 'icon.icns') if os.path.exists(d)]
# Rede de seguranca: alem dos hiddenimports, os arquivos do pacote `abas`
# tambem entram como dados, para o caso de o import por nome cair no disco.
# `medir_abas.py` fica de fora de proposito: e ferramenta de conferencia,
# nao faz parte do programa.
DADOS += [(os.path.join('abas', f), 'abas')
          for f in ('__init__.py', 'comprimir.py', 'redimensionar.py',
                    'figurinhas.py', 'printshot.py')
          if os.path.exists(os.path.join('abas', f))]


a = Analysis(
    ['estudio_imagem.py'],
    pathex=['.'],
    binaries=[],
    datas=DADOS,
    hiddenimports=OCULTOS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ImageStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.icns'],
)
app = BUNDLE(
    exe,
    name='ImageStudio.app',
    icon='icon.icns',
    bundle_identifier=None,
    info_plist={
        'CFBundleShortVersionString': VERSAO,
        'CFBundleVersion': VERSAO,
        'NSHighResolutionCapable': True,
    },
)
