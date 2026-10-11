"""Detección de programas externos opcionales (LibreOffice, Office, Tesseract, Ghostscript,
navegador para HTML→PDF y Ollama). Todo es opcional: si falta algo, solo esa herramienta avisa."""
from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path

import requests

IS_WIN = platform.system() == "Windows"

OLLAMA_URL = os.environ.get("BSOBPDF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("BSOBPDF_OLLAMA_MODEL", "")


def _first_existing(paths) -> str | None:
    for p in paths:
        for hit in sorted(glob.glob(p), reverse=True):
            if os.path.isfile(hit):
                return hit
    return None


def _pf_dirs() -> list[str]:
    dirs = [os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", "")]
    return [d for d in dirs if d]


# ------------------------------------------------------------------ LibreOffice
@lru_cache(maxsize=1)
def soffice_path() -> str | None:
    env = os.environ.get("BSOBPDF_SOFFICE")
    if env and os.path.isfile(env):
        return env
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    if IS_WIN:
        cands = []
        for d in _pf_dirs():
            cands += [os.path.join(d, "LibreOffice", "program", "soffice.exe"),
                      os.path.join(d, "LibreOffice*", "program", "soffice.exe")]
        return _first_existing(cands)
    return _first_existing(["/Applications/LibreOffice.app/Contents/MacOS/soffice",
                            "/opt/libreoffice*/program/soffice"])


# ------------------------------------------------------------------ Microsoft Office (COM)
@lru_cache(maxsize=1)
def ms_office_available() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg  # noqa: F401
        import win32com.client  # noqa: F401
    except Exception:
        return False
    try:
        import winreg
        for prog in ("Word.Application", "Excel.Application", "PowerPoint.Application"):
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog).Close()
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ Tesseract (datos de idioma para OCR)
@lru_cache(maxsize=1)
def tessdata_dir() -> str | None:
    cands = [os.environ.get("BSOBPDF_TESSDATA"), os.environ.get("TESSDATA_PREFIX")]
    if IS_WIN:
        for d in _pf_dirs():
            cands.append(os.path.join(d, "Tesseract-OCR", "tessdata"))
            cands.append(os.path.join(d, "Programs", "Tesseract-OCR", "tessdata"))
    else:
        cands += glob.glob("/usr/share/tesseract-ocr/*/tessdata") + [
            "/usr/share/tessdata", "/usr/local/share/tessdata", "/opt/homebrew/share/tessdata"]
    for c in cands:
        if c and os.path.isdir(c) and glob.glob(os.path.join(c, "*.traineddata")):
            return c
    return None


def ocr_languages() -> list[str]:
    d = tessdata_dir()
    if not d:
        return []
    return sorted(Path(p).stem for p in glob.glob(os.path.join(d, "*.traineddata")) if Path(p).stem != "osd")


# ------------------------------------------------------------------ Ghostscript (PDF/A estricto)
@lru_cache(maxsize=1)
def ghostscript_path() -> str | None:
    for name in ("gswin64c", "gswin32c", "gs"):
        p = shutil.which(name)
        if p:
            return p
    if IS_WIN:
        cands = []
        for d in _pf_dirs():
            cands += [os.path.join(d, "gs", "gs*", "bin", "gswin64c.exe"),
                      os.path.join(d, "gs", "gs*", "bin", "gswin32c.exe")]
        return _first_existing(cands)
    return None


# ------------------------------------------------------------------ Navegador (HTML → PDF)
@lru_cache(maxsize=1)
def browser_path() -> str | None:
    env = os.environ.get("BSOBPDF_BROWSER")
    if env and os.path.isfile(env):
        return env
    if IS_WIN:
        cands = []
        for d in _pf_dirs():
            cands += [os.path.join(d, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(d, "Google", "Chrome", "Application", "chrome.exe"),
                      os.path.join(d, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
        return _first_existing(cands)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    return _first_existing(["/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"])


# ------------------------------------------------------------------ Ollama (IA local)
_ollama_cache: dict = {"t": 0.0, "models": None}


def ollama_models(force: bool = False) -> list[str] | None:
    """Lista de modelos de Ollama o None si Ollama no responde."""
    now = time.time()
    if not force and now - _ollama_cache["t"] < 20:
        return _ollama_cache["models"]
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        # Los modelos de embeddings no sirven para chatear
        models = [m for m in models if "embed" not in m.lower()]
    except Exception:
        models = None
    _ollama_cache.update(t=now, models=models)
    return models


def default_ollama_model() -> str | None:
    models = ollama_models() or []
    if OLLAMA_MODEL and (OLLAMA_MODEL in models or not models):
        return OLLAMA_MODEL
    if not models:
        return None
    # Preferimos modelos de instrucción medianos si existen
    for pref in ("qwen3:4b", "qwen2.5:3b", "llama3.2", "gemma3", "qwen3", "qwen2.5", "mistral", "phi"):
        for m in models:
            if m.startswith(pref):
                return m
    return models[0]


def run(cmd: list[str], timeout: int = 300, cwd: str | None = None) -> subprocess.CompletedProcess:
    kw = {}
    if IS_WIN:
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd, **kw)


def status() -> dict:
    """Estado de cada motor para la página /estado y los avisos de cada herramienta."""
    import pymupdf

    langs = ocr_languages()
    models = ollama_models(force=True)
    return {
        "pymupdf": {"ok": True, "detail": f"PyMuPDF {pymupdf.VersionBind}"},
        "office": {
            "ok": bool(soffice_path() or ms_office_available()),
            "detail": (f"LibreOffice: {soffice_path()}" if soffice_path() else
                       "Microsoft Office (automatización COM)" if ms_office_available() else
                       "No se encontró LibreOffice ni Microsoft Office."),
        },
        "ocr": {
            "ok": bool(langs),
            "detail": (f"Tesseract — idiomas: {', '.join(langs)}" if langs else
                       "No se encontraron los datos de Tesseract (tessdata)."),
            "langs": langs,
        },
        "pdfa": {
            "ok": True,
            "strict": bool(ghostscript_path()),
            "detail": (f"Ghostscript: {ghostscript_path()}" if ghostscript_path() else
                       "Sin Ghostscript: se genera PDF/A en modo básico."),
        },
        "html": {
            "ok": True,
            "detail": (f"Navegador: {browser_path()}" if browser_path() else
                       "Sin navegador Chromium/Edge: se usa el conversor básico."),
        },
        "ollama": {
            "ok": models is not None and len(models) > 0,
            "detail": (f"Ollama en {OLLAMA_URL} — modelos: {', '.join(models)}" if models else
                       f"Ollama no responde en {OLLAMA_URL}." if models is None else
                       "Ollama responde pero no tiene modelos descargados."),
            "models": models or [],
            "default": default_ollama_model(),
        },
    }
