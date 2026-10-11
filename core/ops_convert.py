"""Convertir a PDF y desde PDF."""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
from pathlib import Path

import pymupdf

from . import engines
from .utils import (InputFile, Result, ToolError, as_bool, as_int, image_bytes_for_pdf, open_pdf,
                    parse_pages, save_pdf, unique_path, zip_files)

PAPER = {"a4": "a4", "carta": "letter", "oficio": "legal", "a3": "a3", "a5": "a5"}
MARGINS = {"ninguno": 0, "pequeno": 20, "grande": 50}


# ================================================================== IMÁGENES → PDF
def images_to_pdf(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    from PIL import Image, ImageOps

    if not inputs:
        raise ToolError("Agrega al menos una imagen.")
    orientation = opts.get("orientation", "auto")
    size = opts.get("page_size", "ajustar")
    margin = MARGINS.get(opts.get("margin", "ninguno"), 0)
    merge = as_bool(opts.get("merge", True))

    def add_image(doc: pymupdf.Document, f: InputFile):
        raw = f.path.read_bytes()
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        except Exception:
            raise ToolError(f"«{f.name}» no es una imagen válida.")
        w_px, h_px = im.size
        dpi = im.info.get("dpi", (96, 96))[0] or 96
        if dpi < 30:
            dpi = 96
        iw, ih = w_px * 72 / dpi, h_px * 72 / dpi
        if size == "ajustar":
            pw, ph = iw + 2 * margin, ih + 2 * margin
            # Limitamos a ~A0 para imágenes gigantes
            k = min(1.0, 3370 / max(pw, ph))
            pw, ph = pw * k, ph * k
        else:
            r = pymupdf.paper_rect(PAPER.get(size, "a4"))
            pw, ph = r.width, r.height
            landscape = (orientation == "horizontal") or (orientation == "auto" and w_px > h_px)
            if landscape:
                pw, ph = max(pw, ph), min(pw, ph)
            else:
                pw, ph = min(pw, ph), max(pw, ph)
        page = doc.new_page(width=pw, height=ph)
        box = pymupdf.Rect(margin, margin, pw - margin, ph - margin)
        page.insert_image(box, stream=image_bytes_for_pdf(raw), keep_proportion=True)

    files = []
    if merge:
        doc = pymupdf.open()
        for f in inputs:
            add_image(doc, f)
        dest = unique_path(out, f"{inputs[0].stem}.pdf" if len(inputs) == 1 else "imagenes.pdf")
        save_pdf(doc, dest, garbage=3)
        files.append(dest)
    else:
        for f in inputs:
            doc = pymupdf.open()
            add_image(doc, f)
            dest = unique_path(out, f"{f.stem}.pdf")
            save_pdf(doc, dest, garbage=3)
            files.append(dest)
    return Result(files, f"Se convirtieron {len(inputs)} imagen(es) a PDF.", zip_name="imagenes_pdf.zip")


# ================================================================== OFFICE → PDF
def _soffice_convert(src: Path, workdir: Path) -> Path:
    soffice = engines.soffice_path()
    if not soffice:
        raise ToolError("no-libreoffice")
    profile = workdir / "lo_profile"
    outdir = workdir / "lo_out"
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [soffice, f"-env:UserInstallation={profile.resolve().as_uri()}", "--headless", "--norestore",
           "--nologo", "--convert-to", "pdf", "--outdir", str(outdir), str(src)]
    try:
        engines.run(cmd, timeout=240)
    except Exception as e:
        raise ToolError(f"LibreOffice no respondió: {e}")
    pdf = outdir / (src.stem + ".pdf")
    if not pdf.exists():
        raise ToolError(f"LibreOffice no pudo convertir «{src.name}».")
    return pdf


def _msoffice_convert(src: Path, dest: Path, kind: str) -> Path:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    try:
        s, d = str(src.resolve()), str(dest.resolve())
        if kind == "word":
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            doc = app.Documents.Open(s, ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False)
            doc.ExportAsFixedFormat(d, 17)
            doc.Close(False)
        elif kind == "excel":
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            wb = app.Workbooks.Open(s, ReadOnly=True)
            wb.ExportAsFixedFormat(0, d)
            wb.Close(False)
        else:
            app = win32com.client.DispatchEx("PowerPoint.Application")
            pres = app.Presentations.Open(s, ReadOnly=True, Untitled=False, WithWindow=False)
            pres.SaveAs(d, 32)
            pres.Close()
    finally:
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
    if not dest.exists():
        raise ToolError(f"Microsoft Office no pudo convertir «{src.name}».")
    return dest


def office_to_pdf(inputs: list[InputFile], opts: dict, out: Path, kind: str = "word") -> Result:
    if not (engines.soffice_path() or engines.ms_office_available()):
        raise ToolError("Para convertir documentos de Office se necesita LibreOffice (gratis) o Microsoft Office. "
                        "Revisa la página Estado para instalarlo.")
    prefer = os.environ.get("BSOBPDF_OFFICE_ENGINE", "auto").lower()
    files = []
    for idx, f in enumerate(inputs):
        work = Path(tempfile.mkdtemp(prefix="bsob_office_", dir=out.parent))
        src = work / f"doc_{idx}{f.ext}"
        shutil.copyfile(f.path, src)
        dest = unique_path(out, f"{f.stem}.pdf")
        order = ["ms", "lo"] if prefer in ("auto", "ms") else ["lo", "ms"]
        last_err = None
        for eng in order:
            try:
                if eng == "ms" and engines.ms_office_available():
                    _msoffice_convert(src, dest, kind)
                    break
                if eng == "lo" and engines.soffice_path():
                    shutil.move(str(_soffice_convert(src, work)), dest)
                    break
            except ToolError as e:
                last_err = e
            except Exception as e:  # errores COM, etc.
                last_err = ToolError(f"No se pudo convertir «{f.name}»: {e}")
        shutil.rmtree(work, ignore_errors=True)
        if not dest.exists():
            raise last_err or ToolError(f"No se pudo convertir «{f.name}».")
        files.append(dest)
    if as_bool(opts.get("merge")) and len(files) > 1:
        doc = pymupdf.open()
        for p in files:
            doc.insert_pdf(pymupdf.open(p))
        dest = unique_path(out, "documentos_unidos.pdf")
        save_pdf(doc, dest)
        files = [dest]
    return Result(files, f"Se convirtieron {len(inputs)} archivo(s) a PDF.", zip_name="office_a_pdf.zip")


def word_to_pdf(inputs, opts, out):
    return office_to_pdf(inputs, opts, out, "word")


def excel_to_pdf(inputs, opts, out):
    return office_to_pdf(inputs, opts, out, "excel")


def ppt_to_pdf(inputs, opts, out):
    return office_to_pdf(inputs, opts, out, "powerpoint")


# ================================================================== HTML → PDF
def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ToolError("Escribe la dirección (URL) de la página web.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    if not url.lower().startswith(("http://", "https://", "file://")):
        raise ToolError("La dirección debe empezar por http:// o https://")
    return url


def _html_playwright(url: str, dest: Path, opts: dict) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    size = PAPER.get(opts.get("page_size", "a4"), "a4")
    fmt = {"a4": "A4", "letter": "Letter", "legal": "Legal", "a3": "A3", "a5": "A5"}[size]
    landscape = opts.get("orientation") == "horizontal"
    m = MARGINS.get(opts.get("margin", "pequeno"), 20)
    vw = as_int(opts.get("viewport"), 1280)
    with sync_playwright() as p:
        browser = None
        attempts = [{"channel": "msedge"}, {"channel": "chrome"}, {}]
        if engines.browser_path():
            attempts.append({"executable_path": engines.browser_path()})
        for kw in attempts:
            try:
                browser = p.chromium.launch(headless=True, **kw)
                break
            except Exception:
                continue
        if browser is None:
            return False
        try:
            page = browser.new_page(viewport={"width": vw, "height": 900})
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                page.goto(url, wait_until="load", timeout=45000)
            if as_bool(opts.get("screen_css", True)):
                page.emulate_media(media="screen")
            if as_bool(opts.get("one_page")):
                h = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
                page.pdf(path=str(dest), width=f"{vw}px", height=f"{int(h) + 2}px", print_background=True,
                         page_ranges="1")
            else:
                page.pdf(path=str(dest), format=fmt, landscape=landscape, print_background=True,
                         margin={k: f"{m * 0.3528:.1f}mm" for k in ("top", "right", "bottom", "left")})
        except Exception:
            return False
        finally:
            browser.close()
    return dest.exists()


def _html_cli(url: str, dest: Path, work: Path) -> bool:
    exe = engines.browser_path()
    if not exe:
        return False
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={work / 'chrome_profile'}", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=15000", f"--print-to-pdf={dest}", url]
    if not engines.IS_WIN:
        cmd.insert(1, "--no-sandbox")
    try:
        engines.run(cmd, timeout=120)
    except Exception:
        return False
    return dest.exists() and dest.stat().st_size > 0


def _html_story(html: str, dest: Path, opts: dict) -> bool:
    size = PAPER.get(opts.get("page_size", "a4"), "a4")
    rect = pymupdf.paper_rect(size)
    if opts.get("orientation") == "horizontal":
        rect = pymupdf.Rect(0, 0, rect.height, rect.width)
    m = max(MARGINS.get(opts.get("margin", "pequeno"), 20), 18)
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", "", html)
    story = pymupdf.Story(html=html)
    writer = pymupdf.DocumentWriter(str(dest))
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(rect + (m, m, -m, -m))
        story.draw(dev)
        writer.end_page()
    writer.close()
    return dest.exists()


def html_to_pdf(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    work = Path(tempfile.mkdtemp(prefix="bsob_html_", dir=out.parent))
    if inputs:
        f = inputs[0]
        url = f.path.resolve().as_uri()
        name = f.stem
        html_text = f.path.read_text("utf-8", errors="ignore")
    else:
        url = _normalize_url(opts.get("url", ""))
        name = re.sub(r"^https?://(www\.)?", "", url).split("/")[0] or "pagina"
        html_text = None
    dest = unique_path(out, f"{name}.pdf")
    engine = None
    try:
        if _html_playwright(url, dest, opts):
            engine = "navegador"
        elif _html_cli(url, dest, work):
            engine = "navegador"
        else:
            if html_text is None:
                import requests
                try:
                    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 BSOBPDF"})
                    r.raise_for_status()
                    r.encoding = r.apparent_encoding or r.encoding
                    html_text = r.text
                except Exception as e:
                    raise ToolError(f"No se pudo descargar la página: {e}")
            _html_story(html_text, dest, opts)
            engine = "básico"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not dest.exists():
        raise ToolError("No se pudo convertir la página a PDF.")
    msg = "Página web convertida a PDF."
    if engine == "básico":
        msg += " Se usó el conversor básico (sin estilos avanzados); instala Microsoft Edge o Chrome para un resultado idéntico a la web."
    return Result([dest], msg)


# ================================================================== PDF → IMÁGENES
def pdf_to_images(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    mode = opts.get("mode", "paginas")
    dpi = as_int(opts.get("dpi"), 150)
    fmt = opts.get("format", "jpg")
    quality = 90
    files = []
    for f in inputs:
        doc = open_pdf(f)
        if mode == "imagenes":
            seen = set()
            for page in doc:
                for img in page.get_images(full=True):
                    xref = img[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    try:
                        pix = pymupdf.Pixmap(doc, xref)
                        if pix.n - pix.alpha >= 4:  # CMYK → RGB
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                        if pix.width < 16 or pix.height < 16:
                            continue
                        ext = "png" if (fmt == "png" or pix.alpha) else "jpg"
                        dest = unique_path(out, f"{f.stem}_img_{len(seen):03d}.{ext}")
                        if ext == "jpg":
                            pix.save(dest, jpg_quality=quality)
                        else:
                            pix.save(dest)
                        files.append(dest)
                    except Exception:
                        continue
        else:
            pages = parse_pages(opts.get("pages"), doc.page_count)
            for i in pages:
                pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
                dest = unique_path(out, f"{f.stem}_pag_{i + 1:03d}.{fmt}")
                if fmt == "jpg":
                    pix.save(dest, jpg_quality=quality)
                else:
                    pix.save(dest)
                files.append(dest)
    if not files:
        raise ToolError("Este PDF no contiene imágenes incrustadas. Prueba la opción «Página a imagen».")
    return Result(files, f"Se generaron {len(files)} imagen(es).", zip_name="imagenes.zip")


# ================================================================== PDF → WORD
def _decrypted_copy(f: InputFile, workdir: Path) -> Path:
    doc = open_pdf(f)
    p = workdir / f"plain_{f.path.stem}.pdf"
    doc.save(p, garbage=1)
    doc.close()
    return p


def pdf_to_word(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    try:
        from pdf2docx import Converter
    except Exception:
        raise ToolError("Falta el paquete pdf2docx. Ejecuta de nuevo INICIAR.bat para instalarlo.")
    import logging
    logging.getLogger().setLevel(logging.ERROR)
    files = []
    for f in inputs:
        src = _decrypted_copy(f, f.path.parent)
        doc = pymupdf.open(src)
        has_text = any(p.get_text("text").strip() for p in doc)
        doc.close()
        dest = unique_path(out, f"{f.stem}.docx")
        try:
            cv = Converter(str(src))
            cv.convert(str(dest), start=0, end=None, multi_processing=False)
            cv.close()
        except Exception as e:
            raise ToolError(f"No se pudo convertir «{f.name}» a Word: {e}")
        files.append(dest)
    msg = "PDF convertido a Word (.docx) editable."
    if not has_text:
        msg += " Ojo: el PDF parece escaneado; aplica OCR PDF antes para obtener texto editable."
    return Result(files, msg, zip_name="pdf_a_word.zip")


# ================================================================== PDF → POWERPOINT
def _rgb_from_int(c: int):
    from pptx.dml.color import RGBColor
    return RGBColor((c >> 16) & 255, (c >> 8) & 255, c & 255)


def pdf_to_ppt(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    from pptx import Presentation
    from pptx.util import Emu, Pt

    editable = opts.get("mode", "editable") == "editable"
    dpi = 170
    files = []
    for f in inputs:
        doc = open_pdf(f)
        prs = Presentation()
        first = doc[0].rect
        EMU = 12700
        sw = int(min(max(first.width * EMU, 914400), 51206400))
        sh = int(min(max(first.height * EMU, 914400), 51206400))
        prs.slide_width, prs.slide_height = sw, sh
        blank = prs.slide_layouts[6]
        for page in doc:
            k = min(sw / (page.rect.width * EMU), sh / (page.rect.height * EMU))
            slide = prs.slides.add_slide(blank)
            d = None
            if editable:
                # Fondo = la página sin texto; el texto va en cuadros editables encima
                tmp = pymupdf.open()
                tmp.insert_pdf(doc, from_page=page.number, to_page=page.number)
                tp = tmp[0]
                if tp.rotation:
                    tp.remove_rotation()
                d = tp.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
                for b in d["blocks"]:
                    if b.get("type") == 0:
                        tp.add_redact_annot(pymupdf.Rect(b["bbox"]), fill=False)
                tp.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                    text=pymupdf.PDF_REDACT_TEXT_REMOVE)
                pix = tp.get_pixmap(dpi=dpi, alpha=False)
            else:
                pix = page.get_pixmap(dpi=dpi, alpha=False)
            img = io.BytesIO(pix.tobytes("jpeg", jpg_quality=88))
            slide.shapes.add_picture(img, 0, 0, width=int(page.rect.width * EMU * k), height=int(page.rect.height * EMU * k))
            if not editable:
                continue
            for b in d["blocks"]:
                if b.get("type") != 0:
                    continue
                for line in b["lines"]:
                    spans = [s for s in line["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    if line.get("dir", (1, 0)) != (1, 0) and abs(line["dir"][1]) > 0.1:
                        continue  # texto girado: queda solo en la imagen de fondo
                    r = pymupdf.Rect(line["bbox"])
                    pad = 2
                    box = slide.shapes.add_textbox(Emu(int((r.x0 - pad) * EMU * k)), Emu(int(r.y0 * EMU * k)),
                                                   Emu(int((r.width + 2 * pad + 4) * EMU * k)),
                                                   Emu(int(max(r.height, 4) * EMU * k)))
                    tf = box.text_frame
                    tf.word_wrap = False
                    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                    p = tf.paragraphs[0]
                    for s in line["spans"]:
                        if not s["text"]:
                            continue
                        run = p.add_run()
                        run.text = s["text"]
                        fnt = run.font
                        fnt.size = Pt(max(1, round(s["size"] * k, 1)))
                        fnt.bold = bool(s["flags"] & 16) or "bold" in s["font"].lower()
                        fnt.italic = bool(s["flags"] & 2) or "italic" in s["font"].lower()
                        fnt.color.rgb = _rgb_from_int(s["color"])
                        fname = s["font"].split("+")[-1].split("-")[0].split(",")[0]
                        if fname:
                            fnt.name = fname
        dest = unique_path(out, f"{f.stem}.pptx")
        prs.save(dest)
        files.append(dest)
    return Result(files, "PDF convertido a PowerPoint (.pptx)." + (" El texto quedó editable." if editable else ""),
                  zip_name="pdf_a_powerpoint.zip")


# ================================================================== PDF → EXCEL
_NUM_ES = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")
_NUM_EN = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_NUM_PLAIN = re.compile(r"^-?\d+([.,]\d+)?$")


def _to_cell(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    t = s.replace("$", "").replace("€", "").replace(" ", "").replace(" ", "")
    pct = t.endswith("%")
    if pct:
        t = t[:-1]
    try:
        if _NUM_ES.match(t):
            n = float(t.replace(".", "").replace(",", "."))
        elif _NUM_EN.match(t):
            n = float(t.replace(",", ""))
        elif _NUM_PLAIN.match(t) and not (len(t) > 1 and t.startswith("0") and t[1].isdigit()):
            n = float(t.replace(",", "."))
        else:
            return s
        if pct:
            n /= 100
        return int(n) if n.is_integer() and not pct and abs(n) < 1e15 else n
    except ValueError:
        return s


def _text_rows(page: pymupdf.Page) -> list[list[str]]:
    """Sin tablas detectadas: agrupa palabras en filas y columnas por posición."""
    words = sorted(page.get_text("words"), key=lambda w: (round(w[3] / 3), w[0]))
    rows, current, last_y = [], [], None
    for w in words:
        y = (w[1] + w[3]) / 2
        if last_y is not None and abs(y - last_y) > 3.5:
            rows.append(current)
            current = []
        current.append(w)
        last_y = y if last_y is None else (last_y + y) / 2 if current else y
    if current:
        rows.append(current)
    out = []
    for r in rows:
        r.sort(key=lambda w: w[0])
        cells, cell, last_x = [], [], None
        for w in r:
            gap = w[0] - last_x if last_x is not None else 0
            avg_char = (w[2] - w[0]) / max(len(w[4]), 1)
            if last_x is not None and gap > max(3 * avg_char, 12):
                cells.append(" ".join(cell))
                cell = []
            cell.append(w[4])
            last_x = w[2]
        if cell:
            cells.append(" ".join(cell))
        out.append(cells)
    return out


def pdf_to_excel(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    layout = opts.get("layout", "por_pagina")
    files, total_tables = [], 0
    for f in inputs:
        doc = open_pdf(f)
        wb = Workbook()
        wb.remove(wb.active)
        single = wb.create_sheet("Datos") if layout == "una_hoja" else None
        found_any = False
        for page in doc:
            try:
                tables = page.find_tables().tables
            except Exception:
                tables = []
            blocks: list[list[list]] = []
            if tables:
                found_any = True
                for t in tables:
                    blocks.append(t.extract())
            elif not opts.get("tables_only"):
                rows = _text_rows(page)
                if rows:
                    blocks.append(rows)
            if not blocks:
                continue
            for bi, rows in enumerate(blocks):
                if single is not None:
                    ws = single
                elif layout == "por_tabla":
                    ws = wb.create_sheet(f"P{page.number + 1}-T{bi + 1}"[:31])
                else:
                    name = f"Página {page.number + 1}"
                    ws = wb[name] if name in wb.sheetnames else wb.create_sheet(name)
                start = ws.max_row + (2 if ws.max_row > 1 else 0)
                if ws.max_row == 1 and ws.cell(1, 1).value is None:
                    start = 1
                for ri, row in enumerate(rows):
                    for ci, val in enumerate(row):
                        if isinstance(val, str):
                            val = val.replace("\n", " ").strip()
                        cell = ws.cell(start + ri, ci + 1, _to_cell(val))
                        if ri == 0 and tables:
                            cell.font = Font(bold=True)
                            cell.fill = PatternFill("solid", fgColor="E7F3EE")
                        cell.alignment = Alignment(vertical="top", wrap_text=False)
                total_tables += 1 if tables else 0
        if not wb.sheetnames or all(ws.max_row <= 1 and ws.cell(1, 1).value is None for ws in wb.worksheets):
            raise ToolError(f"No se encontró texto en «{f.name}». Si es un escaneo, aplica OCR PDF primero.")
        for ws in wb.worksheets:
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(8, width + 2), 60)
        dest = unique_path(out, f"{f.stem}.xlsx")
        wb.save(dest)
        files.append(dest)
    msg = (f"Se extrajeron {total_tables} tabla(s) a Excel." if total_tables else
           "No se detectaron tablas con bordes: se exportó el texto organizado en filas y columnas.")
    return Result(files, msg, zip_name="pdf_a_excel.zip")


# ================================================================== PDF → PDF/A
def _srgb_icc() -> bytes:
    from PIL import ImageCms
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _pdfa_ghostscript(src: Path, dest: Path, part: int) -> bool:
    gs = engines.ghostscript_path()
    if not gs:
        return False
    work = dest.parent
    icc = work / "srgb.icc"
    icc.write_bytes(_srgb_icc())
    icc_ps = str(icc.resolve()).replace("\\", "/")
    defps = work / "PDFA_def.ps"
    defps.write_text(f"""%!
/ICCProfile ({icc_ps}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc_PDFA}} /OutputConditionIdentifier (sRGB) /Info (sRGB IEC61966-2.1) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
""", encoding="latin-1")
    cmd = [gs, f"-dPDFA={part}", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE", "-dQUIET",
           f"--permit-file-read={icc_ps}", "-sColorConversionStrategy=RGB", "-sDEVICE=pdfwrite",
           "-dPDFACompatibilityPolicy=1", f"-sOutputFile={dest}", str(defps), str(src)]
    try:
        engines.run(cmd, timeout=300)
    finally:
        icc.unlink(missing_ok=True)
        defps.unlink(missing_ok=True)
    return dest.exists() and dest.stat().st_size > 0


def _pdfa_basic(doc: pymupdf.Document, part: int, conformance: str = "B") -> None:
    """PDF/A en modo básico: metadatos XMP, OutputIntent sRGB, sin cifrado ni JavaScript."""
    import datetime as _dt

    try:
        doc.scrub(attached_files=False, clean_pages=False, embedded_files=True, hidden_text=False,
                  javascript=True, metadata=False, redactions=False, remove_links=False,
                  reset_fields=False, reset_responses=False, thumbnails=False, xml_metadata=True)
    except Exception:
        pass
    meta = doc.metadata or {}
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = (meta.get("title") or "").replace("&", "&amp;").replace("<", "&lt;")
    author = (meta.get("author") or "").replace("&", "&amp;").replace("<", "&lt;")
    xmp = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdfaid:part>{part}</pdfaid:part>
   <pdfaid:conformance>{conformance}</pdfaid:conformance>
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{author}</rdf:li></rdf:Seq></dc:creator>
   <xmp:CreatorTool>BSOBPDF</xmp:CreatorTool>
   <xmp:ModifyDate>{now}</xmp:ModifyDate>
   <xmp:CreateDate>{now}</xmp:CreateDate>
   <pdf:Producer>BSOBPDF (PyMuPDF)</pdf:Producer>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    doc.set_metadata({**{k: v for k, v in meta.items() if k in ("title", "author", "subject", "keywords")},
                      "producer": "BSOBPDF (PyMuPDF)", "creator": "BSOBPDF"})
    doc.set_xml_metadata(xmp)
    icc_xref = doc.get_new_xref()
    doc.update_object(icc_xref, "<< /N 3 >>")
    doc.update_stream(icc_xref, _srgb_icc())
    oi_xref = doc.get_new_xref()
    doc.update_object(oi_xref, f"<< /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (sRGB) "
                               f"/Info (sRGB IEC61966-2.1) /DestOutputProfile {icc_xref} 0 R >>")
    doc.xref_set_key(doc.pdf_catalog(), "OutputIntents", f"[{oi_xref} 0 R]")
    try:
        doc.subset_fonts()
    except Exception:
        pass


def pdf_to_pdfa(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    part = as_int(str(opts.get("level", "2b"))[0], 2)
    files, strict = [], True
    for f in inputs:
        src = _decrypted_copy(f, f.path.parent)
        dest = unique_path(out, f"{f.stem}_PDFA-{part}b.pdf")
        if not _pdfa_ghostscript(src, dest, part):
            strict = False
            doc = pymupdf.open(src)
            _pdfa_basic(doc, part)
            save_pdf(doc, dest, garbage=3, encryption=pymupdf.PDF_ENCRYPT_NONE)
        files.append(dest)
    msg = f"PDF convertido a PDF/A-{part}b para archivo a largo plazo."
    if not strict:
        msg += (" Se usó el modo básico (metadatos XMP y perfil de color sRGB). "
                "Para cumplimiento certificado instala Ghostscript.")
    return Result(files, msg, zip_name="pdfa.zip")


# ================================================================== PDF → MARKDOWN
def pdf_to_markdown(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    try:
        import pymupdf4llm
    except Exception:
        raise ToolError("Falta el paquete pymupdf4llm. Ejecuta de nuevo INICIAR.bat para instalarlo.")
    with_images = as_bool(opts.get("images", False))
    files, preview = [], ""
    for f in inputs:
        doc = open_pdf(f)
        kw = {}
        img_dir = None
        if with_images:
            img_dir = out / f"{f.stem}_imagenes"
            img_dir.mkdir(parents=True, exist_ok=True)
            kw.update(write_images=True, image_path=str(img_dir), image_format="png")
        use_ocr = as_bool(opts.get("ocr")) and bool(engines.tessdata_dir())
        try:
            md = pymupdf4llm.to_markdown(doc, use_ocr=use_ocr, **kw)
        except TypeError:
            md = pymupdf4llm.to_markdown(doc, **kw)
        if with_images and img_dir:
            md = md.replace(str(img_dir).replace("\\", "/") + "/", f"{img_dir.name}/").replace(str(img_dir) + os.sep, f"{img_dir.name}/")
        if not md.strip():
            raise ToolError(f"«{f.name}» no tiene texto extraíble. Si es un escaneo, aplica OCR PDF primero.")
        dest = unique_path(out, f"{f.stem}.md")
        dest.write_text(md, encoding="utf-8")
        if img_dir and any(img_dir.iterdir()):
            z = unique_path(out, f"{f.stem}_markdown.zip")
            import zipfile
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(dest, dest.name)
                for im in img_dir.iterdir():
                    zf.write(im, f"{img_dir.name}/{im.name}")
            dest.unlink()
            shutil.rmtree(img_dir, ignore_errors=True)
            files.append(z)
        else:
            if img_dir:
                shutil.rmtree(img_dir, ignore_errors=True)
            files.append(dest)
        if not preview:
            preview = md[:60000]
    return Result(files, "PDF convertido a Markdown.", data={"markdown": preview}, zip_name="markdown.zip")
