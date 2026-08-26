# -*- mode: python ; coding: utf-8 -*-
"""Receita de empacotamento do Video Studio (usada no Mac).

Existe por um motivo so: buildar por flags soltas do PyInstaller nunca
preenche a versao do bundle, e o Finder acaba mostrando "0.0.0" em
Informacoes (Cmd+I). A versao so entra no Info.plist quando o build sai de
um .spec, como este.

A versao NAO fica escrita aqui: e lida do proprio estudio_video.py, para
nunca dessincronizar com o rodape da janela.
"""

import os
import re

VERSAO = "0.0.0"
try:
    _fonte = open("estudio_video.py", encoding="utf-8").read()
    _achado = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _fonte, re.M)
    if _achado:
        VERSAO = _achado.group(1)
except Exception:
    pass

# O programa nao e um arquivo so: `estudio_video.py` monta cada aba com
# __import__ no momento em que a pessoa clica nela. Import feito assim, por
# nome montado em tempo de execucao, o PyInstaller nao enxerga sozinho --
# entao cada modulo do pacote `abas` precisa ser listado a mao aqui, senao o
# app abre e todas as abas falham.
#
# O pacote `compartilhado` entra pelo mesmo motivo: as abas "Cortar e
# dividir" e "Extrair audio" sao arquivos finos que so chamam a tela real
# la de dentro (`from compartilhado import cortar_dividir`), e o motor de
# download tambem mora ali. Sem estas linhas, essas abas quebram no app
# empacotado.
OCULTOS = [
    'tema',
    'pastas',
    'atualizador',
    'certifi',
    'abas',
    'abas.baixar',
    'abas.cortar',
    'abas.quadros',
    'abas.audio',
    'compartilhado',
    'compartilhado.cortar_dividir',
    'compartilhado.extrair_audio',
    'compartilhado.motor_download',
]

# Os motores de audio/video e o icone da janela viajam junto.
BINARIOS = [(b, '.') for b in ('ffmpeg', 'ffprobe') if os.path.exists(b)]
DADOS = [(d, '.') for d in ('icon.png', 'icon.icns') if os.path.exists(d)]
# Rede de seguranca: alem dos hiddenimports, os arquivos do pacote `abas`
# tambem entram como dados, para o caso de o import por nome cair no disco.
DADOS += [(os.path.join('abas', f), 'abas')
          for f in ('__init__.py', 'baixar.py', 'cortar.py', 'quadros.py',
                    'audio.py')
          if os.path.exists(os.path.join('abas', f))]
# Mesma rede de seguranca para o pacote `compartilhado` (as telas que dois
# estudios usam). `medir_abas.py` fica de fora de proposito: e ferramenta de
# conferencia, nao faz parte do programa.
DADOS += [(os.path.join('compartilhado', f), 'compartilhado')
          for f in ('__init__.py', 'cortar_dividir.py', 'extrair_audio.py',
                    'motor_download.py')
          if os.path.exists(os.path.join('compartilhado', f))]


a = Analysis(
    ['estudio_video.py'],
    pathex=['.'],
    binaries=BINARIOS,
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
    name='VideoStudio',
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
    name='VideoStudio.app',
    icon='icon.icns',
    bundle_identifier=None,
    info_plist={
        'CFBundleShortVersionString': VERSAO,
        'CFBundleVersion': VERSAO,
        'NSHighResolutionCapable': True,
    },
)
