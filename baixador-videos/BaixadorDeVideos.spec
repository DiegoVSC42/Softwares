# -*- mode: python ; coding: utf-8 -*-
#
# Spec usado apenas nos builds de Mac (local e nuvem) para o app carregar a
# versão certa no Info.plist — sem isso, o Finder sempre mostra "0.0.0" em
# Informações, porque o PyInstaller não preenche esse campo sozinho quando
# builda direto do .py (só via este arquivo .spec). O Windows não usa este
# arquivo: o .exe não tem esse conceito de versão de bundle.
#
# A versão é lida automaticamente de APP_VERSION em baixador_videos.py — não
# precisa editar aqui quando a versão do programa mudar.

import re

with open('baixador_videos.py', encoding='utf-8') as _f:
    _m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _f.read(), re.MULTILINE)
VERSAO = _m.group(1) if _m else '0.0.0'

a = Analysis(
    ['baixador_videos.py'],
    pathex=[],
    binaries=[('ffmpeg', '.')],
    datas=[],
    # certifi explicito (alem do hook automatico do PyInstaller): garante
    # que o cacert.pem entre no bundle, senao o app empacotado falha ao
    # baixar o motor com "unable to get local issuer certificate".
    hiddenimports=['certifi'],
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
    name='BaixadorDeVideos',
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
    name='BaixadorDeVideos.app',
    icon='icon.icns',
    bundle_identifier=None,
    info_plist={
        'CFBundleShortVersionString': VERSAO,
        'CFBundleVersion': VERSAO,
        'NSHighResolutionCapable': True,
    },
)
