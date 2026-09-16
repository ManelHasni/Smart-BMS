# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de configuration PyInstaller pour Smart BMS.

Usage (depuis le dossier du projet, sur Windows) :
    pyinstaller build_exe.spec

Le .exe genere se trouve ensuite dans dist/SmartBMS/SmartBMS.exe
(mode --onedir : demarrage plus rapide que --onefile, recommande pour une
appli avec un modele ML embarque).
"""

import sys
from pathlib import Path

block_cipher = None
PROJECT_DIR = Path(SPECPATH)

datas = [
    (str(PROJECT_DIR / "battery_rf_model.pkl"), "."),
    (str(PROJECT_DIR / "battery_scaler.pkl"), "."),
    (str(PROJECT_DIR / "assets"), "assets"),
]

a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "sklearn.ensemble._forest",
        "sklearn.tree._tree",
        "sklearn.neighbors._typedefs",
        "sklearn.utils._typedefs",
        "sklearn.utils._heap",
        "sklearn.utils._sorting",
        "sklearn.utils._vector_sentinel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SmartBMS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # False = pas de console qui s'ouvre derriere le dashboard
    icon=str(PROJECT_DIR / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SmartBMS",
)
