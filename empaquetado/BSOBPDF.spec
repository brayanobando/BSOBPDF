# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para empaquetar BSOBPDF como programa de Windows.

Uso (desde la raíz del proyecto, en Windows):
    pip install -r requirements.txt pyinstaller
    pyinstaller --noconfirm --clean empaquetado/BSOBPDF.spec

Resultado: dist/BSOBPDF/BSOBPDF.exe (carpeta lista para el instalador de Inno Setup).
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(RAIZ, "templates"), "templates"),
    (os.path.join(RAIZ, "static"), "static"),
]
binaries = []
hiddenimports = ["waitress", "app"]

# Paquetes con datos (plantillas, modelos, bibliotecas) que PyInstaller no detecta solo
for paquete in ("pymupdf", "fitz", "pymupdf4llm", "pymupdf_layout", "pdf2docx", "docx", "pptx",
                "deep_translator", "qrcode", "onnxruntime"):
    try:
        d, b, h = collect_all(paquete)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(RAIZ, "escritorio.py")],
    pathex=[RAIZ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["playwright", "pytest", "IPython", "matplotlib", "notebook", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icono = os.path.join(SPECPATH, "bsobpdf.ico")
version = os.path.join(SPECPATH, "version_info.txt")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BSOBPDF",
    console=False,
    icon=icono if sys.platform == "win32" else None,
    version=version if sys.platform == "win32" else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BSOBPDF", upx=False)
