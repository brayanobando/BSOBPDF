"""Optimizar PDF: comprimir, reparar y OCR."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pymupdf

from . import engines
from .utils import (InputFile, Result, ToolError, as_bool, as_int, human_size, open_pdf, save_pdf,
                    unique_path)

LEVELS = {
    # nivel: (umbral dpi, dpi destino, calidad JPEG)
    "extrema": (100, 72, 40),
    "recomendada": (170, 150, 65),
    "baja": (260, 220, 82),
}


# ------------------------------------------------------------------ Comprimir
def compress(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    level = opts.get("level", "recomendada")
    thr, target, quality = LEVELS.get(level, LEVELS["recomendada"])
    gray = as_bool(opts.get("grayscale", False))
    files, before_total, after_total = [], 0, 0
    per_file = []
    for f in inputs:
        before = f.path.stat().st_size
        doc = open_pdf(f)
        try:
            doc.rewrite_images(dpi_threshold=thr, dpi_target=target, quality=quality,
                               lossy=True, lossless=True, bitonal=True, color=True, gray=True,
                               set_to_gray=gray)
        except Exception:
            pass
        try:
            doc.subset_fonts()
        except Exception:
            pass
        if level == "extrema":
            try:
                doc.scrub(metadata=False, xml_metadata=True, thumbnails=True, javascript=True,
                          attached_files=False, embedded_files=False, clean_pages=True,
                          hidden_text=False, redactions=False, remove_links=False, reset_fields=False,
                          reset_responses=False)
            except Exception:
                pass
        dest = unique_path(out, f"{f.stem}_comprimido.pdf")
        save_pdf(doc, dest, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                 clean=True, use_objstms=1, compression_effort=0)
        doc.close()
        after = dest.stat().st_size
        if after >= before:
            # No logramos reducirlo: entregamos el original (nunca más grande)
            shutil.copyfile(f.path, dest)
            after = before
        before_total += before
        after_total += after
        per_file.append({"name": f.name, "before": before, "after": after})
        files.append(dest)
    saved = before_total - after_total
    pct = round(100 * saved / before_total) if before_total else 0
    msg = (f"Tu PDF ahora pesa {human_size(after_total)} (antes {human_size(before_total)}): {pct}% menos."
           if saved > 0 else
           "Este PDF ya estaba optimizado: no se pudo reducir más sin perder calidad.")
    return Result(files, msg, {"before": before_total, "after": after_total, "percent": pct, "files": per_file},
                  zip_name="pdf_comprimidos.zip")


# ------------------------------------------------------------------ Reparar
def _salvage_bytes(raw: bytes) -> bytes:
    """Recorta basura antes del encabezado %PDF y después del último %%EOF."""
    start = raw.find(b"%PDF")
    if start > 0:
        raw = raw[start:]
    end = raw.rfind(b"%%EOF")
    if end != -1:
        raw = raw[:end + 5]
    return raw


def repair(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    files, notes = [], []
    for f in inputs:
        pymupdf.TOOLS.reset_mupdf_warnings()
        raw = f.path.read_bytes()
        doc = None
        for attempt in (raw, _salvage_bytes(raw)):
            try:
                doc = pymupdf.open(stream=attempt, filetype="pdf")
                if doc.page_count > 0:
                    break
            except Exception:
                doc = None
        if doc is None or doc.page_count == 0:
            raise ToolError(f"«{f.name}» está demasiado dañado: no se pudo recuperar ninguna página.")
        if doc.needs_pass:
            raise ToolError(f"«{f.name}» tiene contraseña. Desbloquéalo antes de repararlo.")
        # Reconstruimos página por página: las que fallen se omiten
        fixed = pymupdf.open()
        bad = []
        for i in range(doc.page_count):
            try:
                fixed.insert_pdf(doc, from_page=i, to_page=i)
                fixed[-1].get_text("text")  # fuerza el análisis del contenido
            except Exception:
                bad.append(i + 1)
        if fixed.page_count == 0:
            raise ToolError(f"No se pudo recuperar ninguna página de «{f.name}».")
        try:
            fixed.set_metadata(doc.metadata or {})
        except Exception:
            pass
        dest = unique_path(out, f"{f.stem}_reparado.pdf")
        save_pdf(fixed, dest, garbage=4, clean=True)
        warnings = pymupdf.TOOLS.mupdf_warnings()
        n_warn = len([w for w in warnings.splitlines() if w.strip()]) if warnings else 0
        notes.append({"name": f.name, "pages": fixed.page_count, "skipped": bad, "warnings": n_warn})
        files.append(dest)
    msg = "PDF reparado y reconstruido."
    if any(n["skipped"] for n in notes):
        msg += " Algunas páginas estaban irrecuperables y se omitieron."
    elif any(n["warnings"] for n in notes):
        msg += " Se corrigieron errores internos de la estructura."
    else:
        msg += " No se encontraron daños graves."
    return Result(files, msg, {"files": notes}, zip_name="pdf_reparados.zip")


# ------------------------------------------------------------------ OCR
def _ocr_lang(requested: str) -> str:
    avail = engines.ocr_languages()
    if not avail:
        raise ToolError("El OCR necesita Tesseract instalado. Revisa la página Estado para ver cómo instalarlo.")
    langs = [l for l in re.split(r"[+,\s]+", requested or "spa+eng") if l]
    ok = [l for l in langs if l in avail]
    if not ok:
        ok = ["eng"] if "eng" in avail else [avail[0]]
    return "+".join(ok)


def ocr(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    lang = _ocr_lang(opts.get("language", "spa+eng"))
    dpi = as_int(opts.get("dpi"), 300)
    skip_text = as_bool(opts.get("skip_text", True))
    tess = engines.tessdata_dir()
    files, words_total, pages_done = [], 0, 0
    for f in inputs:
        doc = open_pdf(f)
        for page in doc:
            if skip_text and len(page.get_text("text").strip()) > 20:
                continue
            try:
                tp = page.get_textpage_ocr(language=lang, dpi=dpi, full=True, tessdata=tess)
            except Exception as e:
                raise ToolError(f"Tesseract no pudo procesar la página {page.number + 1}: {e}")
            words = page.get_text("words", textpage=tp)
            pages_done += 1
            if not words:
                continue
            # Capa de texto invisible (render_mode=3) alineada con cada palabra reconocida
            tw = pymupdf.TextWriter(page.rect)
            font = pymupdf.Font("helv")
            for x0, y0, x1, y1, word, *_ in words:
                w = font.text_length(word, fontsize=1)
                h = y1 - y0
                if w <= 0 or h <= 0:
                    continue
                size = min((x1 - x0) / w, h * 1.3)
                if size < 1:
                    continue
                try:
                    tw.append((x0, y1 - 0.18 * h), word, font=font, fontsize=size)
                    words_total += 1
                except Exception:
                    continue
            tw.write_text(page, render_mode=3, overlay=True)
        dest = unique_path(out, f"{f.stem}_ocr.pdf")
        save_pdf(doc, dest, garbage=3, deflate=True)
        files.append(dest)
    if pages_done == 0:
        msg = "Todas las páginas ya tenían texto seleccionable: no fue necesario aplicar OCR."
    else:
        msg = f"OCR aplicado a {pages_done} página(s): se reconocieron {words_total} palabras. Ahora puedes buscar y copiar el texto."
    return Result(files, msg, {"pages": pages_done, "words": words_total, "language": lang},
                  zip_name="pdf_ocr.zip")
