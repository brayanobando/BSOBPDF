"""Organizar PDF: unir, dividir, eliminar, extraer, organizar y escanear."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pymupdf

from .utils import (InputFile, Result, ToolError, as_bool, as_int, open_pdf, parse_pages,
                    save_pdf, unique_path)


def _load_json(v, default):
    if v is None or v == "":
        return default
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return default


# ------------------------------------------------------------------ Unir
def merge(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    pdfs = [f for f in inputs]
    if len(pdfs) < 2:
        raise ToolError("Agrega al menos dos PDF para unirlos.")
    result = pymupdf.open()
    toc = []
    for f in pdfs:
        src = open_pdf(f, opts.get("password"))
        start = result.page_count
        result.insert_pdf(src)
        if as_bool(opts.get("bookmarks", True)):
            toc.append([1, f.stem, start + 1])
            for lvl, title, page, *_ in src.get_toc():
                if page > 0:
                    toc.append([lvl + 1, title, start + page])
        src.close()
    if toc:
        try:
            result.set_toc(toc)
        except Exception:
            pass
    dest = unique_path(out, f"{pdfs[0].stem}_unido.pdf")
    save_pdf(result, dest)
    return Result([dest], f"Se unieron {len(pdfs)} PDF en un documento de {result.page_count} páginas.",
                  {"pages": result.page_count})


# ------------------------------------------------------------------ Dividir
def split(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    mode = opts.get("mode", "rangos")
    files: list[Path] = []
    for f in inputs:
        doc = open_pdf(f)
        n = doc.page_count
        groups: list[tuple[str, list[int]]] = []
        if mode == "rangos":
            ranges = _load_json(opts.get("ranges"), [])
            if not ranges:
                raise ToolError("Agrega al menos un rango de páginas.")
            for r in ranges:
                a = max(1, as_int(r.get("from"), 1))
                b = min(n, as_int(r.get("to"), n))
                if a > n:
                    continue
                if a > b:
                    a, b = b, a
                groups.append((f"{a}-{b}" if a != b else f"{a}", list(range(a - 1, b))))
            if as_bool(opts.get("merge_ranges")):
                pages = [p for _, g in groups for p in g]
                groups = [("rangos", pages)]
        elif mode == "fijo":
            k = max(1, as_int(opts.get("every"), 1))
            for a in range(0, n, k):
                b = min(n, a + k)
                groups.append((f"{a + 1}-{b}" if b - a > 1 else f"{a + 1}", list(range(a, b))))
        elif mode == "todas":
            groups = [(f"{i + 1}", [i]) for i in range(n)]
        elif mode == "seleccion":
            pages = parse_pages(opts.get("pages"), n, default_all=False)
            if not pages:
                raise ToolError("Selecciona las páginas que quieres separar.")
            if as_bool(opts.get("merge_selected")):
                groups = [("seleccion", pages)]
            else:
                groups = [(f"{p + 1}", [p]) for p in pages]
        else:
            raise ToolError("Modo de división desconocido.")
        if not groups:
            raise ToolError(f"«{f.name}» tiene {n} páginas: los rangos indicados quedan fuera del documento.")
        for label, pages in groups:
            part = pymupdf.open()
            for p in pages:
                part.insert_pdf(doc, from_page=p, to_page=p)
            dest = unique_path(out, f"{f.stem}_pag_{label}.pdf")
            save_pdf(part, dest)
            files.append(dest)
        doc.close()
    return Result(files, "Se creó 1 archivo PDF." if len(files) == 1 else f"Se crearon {len(files)} archivos PDF.",
                  zip_name="pdf_divididos.zip")


# ------------------------------------------------------------------ Eliminar / extraer páginas
def remove_pages(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    files = []
    removed_total = 0
    for f in inputs:
        doc = open_pdf(f)
        pages = parse_pages(opts.get("pages"), doc.page_count, default_all=False)
        if not pages:
            raise ToolError("Selecciona las páginas que quieres eliminar.")
        if len(pages) >= doc.page_count:
            raise ToolError("No puedes eliminar todas las páginas: el PDF quedaría vacío.")
        doc.delete_pages(sorted(pages))
        removed_total += len(pages)
        dest = unique_path(out, f"{f.stem}_editado.pdf")
        save_pdf(doc, dest)
        files.append(dest)
    return Result(files, "Se eliminó 1 página." if removed_total == 1 else f"Se eliminaron {removed_total} páginas.")


def extract_pages(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    files = []
    for f in inputs:
        doc = open_pdf(f)
        pages = parse_pages(opts.get("pages"), doc.page_count, default_all=False)
        if not pages:
            raise ToolError("Selecciona las páginas que quieres extraer.")
        if as_bool(opts.get("separate")):
            for p in pages:
                part = pymupdf.open()
                part.insert_pdf(doc, from_page=p, to_page=p)
                dest = unique_path(out, f"{f.stem}_pag_{p + 1}.pdf")
                save_pdf(part, dest)
                files.append(dest)
        else:
            doc.select(pages)
            dest = unique_path(out, f"{f.stem}_extraido.pdf")
            save_pdf(doc, dest)
            files.append(dest)
    return Result(files, "Páginas extraídas.", zip_name="paginas_extraidas.zip")


# ------------------------------------------------------------------ Organizar
def organize(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    """sequence: [{"f": índice de archivo, "p": índice de página, "r": giro extra}, {"blank": true}]"""
    seq = _load_json(opts.get("sequence"), None)
    docs = [open_pdf(f) for f in inputs]
    if not seq:
        seq = [{"f": i, "p": p} for i, d in enumerate(docs) for p in range(d.page_count)]
    result = pymupdf.open()
    last_size = pymupdf.paper_rect("a4")
    for item in seq:
        if item.get("blank"):
            result.new_page(width=last_size.width, height=last_size.height)
            continue
        fi, pi = as_int(item.get("f"), 0), as_int(item.get("p"), 0)
        if fi >= len(docs) or pi >= docs[fi].page_count:
            continue
        src = docs[fi]
        result.insert_pdf(src, from_page=pi, to_page=pi)
        page = result[-1]
        extra = as_int(item.get("r"), 0) % 360
        if extra:
            page.set_rotation((page.rotation + extra) % 360)
        last_size = page.rect
    if result.page_count == 0:
        raise ToolError("El documento quedó sin páginas.")
    dest = unique_path(out, f"{inputs[0].stem}_organizado.pdf")
    save_pdf(result, dest)
    return Result([dest], f"Documento organizado: {result.page_count} páginas.")


# ------------------------------------------------------------------ Escanear (fotos → PDF)
def _enhance(data: bytes, mode: str, autocrop: bool) -> bytes:
    from PIL import Image, ImageOps, ImageFilter, ImageEnhance

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if autocrop:
        im = _autocrop_document(im)
    if mode == "documento":
        g = ImageOps.grayscale(im)
        try:
            import cv2
            import numpy as np
            arr = np.array(g)
            arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
            im = Image.fromarray(arr)
        except Exception:
            g = ImageOps.autocontrast(g, cutoff=2)
            im = g.point(lambda v: 255 if v > 150 else 0)
    elif mode == "gris":
        im = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
    elif mode == "mejorado":
        im = ImageOps.autocontrast(im, cutoff=1)
        im = ImageEnhance.Color(im).enhance(1.15)
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    # Las fotos de celular son enormes: limitamos a ~2400 px por lado
    im.thumbnail((2400, 2400))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _autocrop_document(im):
    """Detecta la hoja en la foto y corrige la perspectiva (si OpenCV está disponible)."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return im
    from PIL import Image

    arr = np.array(im)
    h, w = arr.shape[:2]
    scale = 800 / max(h, w)
    small = cv2.resize(arr, (int(w * scale), int(h * scale)))
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.25 * small.shape[0] * small.shape[1]:
            best = approx.reshape(4, 2).astype("float32") / scale
            break
    if best is None:
        return im
    s = best.sum(axis=1)
    d = np.diff(best, axis=1).ravel()
    tl, br = best[np.argmin(s)], best[np.argmax(s)]
    tr, bl = best[np.argmin(d)], best[np.argmax(d)]
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 100 or height < 100:
        return im
    M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype="float32"),
                                    np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32"))
    warped = cv2.warpPerspective(arr, M, (width, height))
    return Image.fromarray(warped)


def scan_to_pdf(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    from .ops_convert import images_to_pdf

    if not inputs:
        raise ToolError("Toma o agrega al menos una foto.")
    mode = opts.get("filter", "mejorado")
    autocrop = as_bool(opts.get("autocrop", True))
    processed: list[InputFile] = []
    for i, f in enumerate(inputs):
        data = _enhance(f.path.read_bytes(), mode, autocrop)
        p = f.path.with_name(f"scan_{i:03d}.jpg")
        p.write_bytes(data)
        processed.append(InputFile(p, f"escaneo_{i + 1}.jpg"))
    o = dict(opts)
    o.setdefault("page_size", "a4")
    o["merge"] = True
    res = images_to_pdf(processed, o, out)
    final = unique_path(out, "escaneo.pdf")
    res.files[0].rename(final)
    res.files = [final]
    res.message = f"Escaneo listo: {len(inputs)} página(s)."
    return res
