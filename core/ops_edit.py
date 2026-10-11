"""Editar PDF: rotar, numerar, marca de agua, recortar, editor visual, firmar y formularios."""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

import pymupdf

from .utils import (InputFile, Result, ToolError, as_bool, as_float, as_int, font_for, hex_to_rgb,
                    image_bytes_for_pdf, normalize_rotation, open_pdf, parse_pages, save_pdf, unique_path)


def _json(v, default):
    if v is None or v == "":
        return default
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return default


# Distancia (en em) desde el borde superior de la línea hasta la línea base, con interlineado 1.2,
# igual que el editor del navegador (Arial/Times/Courier).
BASELINE = {"helv": 0.947, "tiro": 0.938, "cour": 0.866}


def _family(font: str) -> str:
    f = (font or "helv").lower()
    if f in ("times", "serif", "tiro"):
        return "tiro"
    if f in ("courier", "mono", "cour"):
        return "cour"
    return "helv"


# ------------------------------------------------------------------ Rotar
def rotate(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    angle = as_int(opts.get("angle"), 90)
    per_page = _json(opts.get("rotations"), None)  # [[delta por página] por archivo]
    files = []
    for fi, f in enumerate(inputs):
        doc = open_pdf(f)
        deltas = per_page[fi] if per_page and fi < len(per_page) else None
        pages = parse_pages(opts.get("pages"), doc.page_count)
        for i, page in enumerate(doc):
            d = (as_int(deltas[i], 0) if deltas and i < len(deltas) else (angle if i in pages else 0)) % 360
            if d:
                page.set_rotation((page.rotation + d) % 360)
        dest = unique_path(out, f"{f.stem}_rotado.pdf")
        save_pdf(doc, dest)
        files.append(dest)
    return Result(files, "Páginas rotadas.", zip_name="pdf_rotados.zip")


# ------------------------------------------------------------------ Números de página
MARGIN_PT = {"pequeno": 18, "recomendado": 30, "grande": 50}
FORMATS = {
    "n": "{n}",
    "pagina_n": "Página {n}",
    "pagina_n_de_total": "Página {n} de {total}",
    "n_de_total": "{n} / {total}",
}


def page_numbers(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    pos = opts.get("position", "bc")
    margin = MARGIN_PT.get(opts.get("margin", "recomendado"), 30)
    first = as_int(opts.get("first_number"), 1)
    size = as_float(opts.get("font_size"), 11)
    color = hex_to_rgb(opts.get("color"), (0, 0, 0))
    fontname = font_for(opts.get("font", "helv"), as_bool(opts.get("bold")))
    tpl = opts.get("custom_text") if opts.get("format") == "custom" else FORMATS.get(opts.get("format", "n"), "{n}")
    tpl = tpl or "{n}"
    facing = opts.get("mode") == "enfrentadas"
    files = []
    for f in inputs:
        doc = open_pdf(f)
        pages = parse_pages(opts.get("pages"), doc.page_count)
        total = first + len(pages) - 1
        for k, i in enumerate(pages):
            page = doc[i]
            normalize_rotation(page)
            num = first + k
            text = tpl.replace("{n}", str(num)).replace("{total}", str(total))
            tw = pymupdf.get_text_length(text, fontname=fontname, fontsize=size)
            r = page.rect
            v, h = pos[0], pos[1]
            if facing and num % 2 == 0 and h in "lr":
                h = "r" if h == "l" else "l"
            x = {"l": r.x0 + margin, "c": r.x0 + (r.width - tw) / 2, "r": r.x1 - margin - tw}[h]
            y = r.y0 + margin + size * 0.8 if v == "t" else r.y1 - margin
            page.insert_text((x, y), text, fontsize=size, fontname=fontname, color=color)
        dest = unique_path(out, f"{f.stem}_numerado.pdf")
        save_pdf(doc, dest)
        files.append(dest)
    return Result(files, "Números de página agregados.", zip_name="pdf_numerados.zip")


# ------------------------------------------------------------------ Marca de agua
GRID = {"t": 0.12, "m": 0.5, "b": 0.88, "l": 0.15, "c": 0.5, "r": 0.85}


def watermark(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    kind = opts.get("type", "texto")
    pos = opts.get("position", "mc")
    mosaic = as_bool(opts.get("mosaic"))
    opacity = max(0.05, min(1.0, as_float(opts.get("opacity"), 0.35)))
    angle = as_float(opts.get("rotation"), 45)
    overlay = opts.get("layer", "encima") != "debajo"
    files = []

    img_file: InputFile | None = opts.get("watermark_image")
    img_cache: dict = {}
    if kind == "imagen":
        if not isinstance(img_file, InputFile):
            raise ToolError("Elige la imagen que se usará como marca de agua.")
        raw = img_file.path.read_bytes()
        img_data = image_bytes_for_pdf(raw, opacity=opacity, rotate=angle)
        from PIL import Image
        import io as _io
        iw, ih = Image.open(_io.BytesIO(img_data)).size
        img_cache["data"], img_cache["ratio"] = img_data, ih / iw
    else:
        text = (opts.get("text") or "").strip()
        if not text:
            raise ToolError("Escribe el texto de la marca de agua.")
        size = as_float(opts.get("font_size"), 48)
        fontname = font_for(opts.get("font", "helv"), as_bool(opts.get("bold", True)))
        color = hex_to_rgb(opts.get("color"), (0.8, 0.1, 0.1))

    def place_text(page, cx, cy):
        lines = text.split("\n")
        lh = size * 1.2
        for li, line in enumerate(lines):
            tw = pymupdf.get_text_length(line, fontname=fontname, fontsize=size)
            oy = (li - (len(lines) - 1) / 2) * lh
            origin = pymupdf.Point(cx - tw / 2, cy + oy + size * 0.35)
            page.insert_text(origin, line, fontsize=size, fontname=fontname, color=color,
                             fill_opacity=opacity, overlay=overlay,
                             morph=(pymupdf.Point(cx, cy), pymupdf.Matrix(-angle)))

    def place_image(page, cx, cy):
        scale = as_float(opts.get("image_scale"), 0.35)
        w = page.rect.width * scale
        h = w * img_cache["ratio"]
        rect = pymupdf.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        page.insert_image(rect, stream=img_cache["data"], overlay=overlay, keep_proportion=True)

    place = place_image if kind == "imagen" else place_text
    for f in inputs:
        doc = open_pdf(f)
        for i in parse_pages(opts.get("pages"), doc.page_count):
            page = doc[i]
            normalize_rotation(page)
            r = page.rect
            if mosaic:
                step_x = r.width / 3
                step_y = r.height / 4
                for yi in range(4):
                    for xi in range(3):
                        off = step_x / 2 if yi % 2 else 0
                        place(page, r.x0 + step_x * (xi + 0.5) + off - step_x / 4, r.y0 + step_y * (yi + 0.5))
            else:
                place(page, r.x0 + r.width * GRID[pos[1]], r.y0 + r.height * GRID[pos[0]])
        dest = unique_path(out, f"{f.stem}_marca_de_agua.pdf")
        save_pdf(doc, dest)
        files.append(dest)
    return Result(files, "Marca de agua aplicada.", zip_name="pdf_marca_agua.zip")


# ------------------------------------------------------------------ Recortar
def _content_bbox(page: pymupdf.Page) -> pymupdf.Rect | None:
    r = pymupdf.Rect()
    for kind, bbox in page.get_bboxlog():
        b = pymupdf.Rect(bbox)
        if kind.startswith("ignore") or b.is_empty or b.is_infinite:
            continue
        if b.width >= page.rect.width * 0.98 and b.height >= page.rect.height * 0.98 and kind == "fill-path":
            continue  # fondo de página completo
        r |= b
    r &= page.rect
    return None if r.is_empty else r


def crop(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    auto = as_bool(opts.get("auto"))
    box = _json(opts.get("box"), None)
    scope = opts.get("scope", "todas")
    ref_page = as_int(opts.get("page"), 0)
    pad = as_float(opts.get("padding"), 10)
    files = []
    for f in inputs:
        doc = open_pdf(f)
        if not auto:
            if not box:
                raise ToolError("Dibuja el área que quieres conservar.")
            ref = doc[min(ref_page, doc.page_count - 1)]
            rw, rh = ref.rect.width, ref.rect.height
            frac = (box["x"] / rw, box["y"] / rh, (box["x"] + box["w"]) / rw, (box["y"] + box["h"]) / rh)
        targets = [min(ref_page, doc.page_count - 1)] if scope == "actual" else range(doc.page_count)
        for i in targets:
            page = doc[i]
            normalize_rotation(page)
            pr = page.rect
            if auto:
                cb = _content_bbox(page)
                if cb is None:
                    continue
                vis = (cb + (-pad, -pad, pad, pad)) & pr
            else:
                vis = pymupdf.Rect(pr.x0 + frac[0] * pr.width, pr.y0 + frac[1] * pr.height,
                                   pr.x0 + frac[2] * pr.width, pr.y0 + frac[3] * pr.height) & pr
            if vis.is_empty or vis.width < 10 or vis.height < 10:
                continue
            cb0 = page.cropbox
            new = pymupdf.Rect(vis.x0 + cb0.x0, vis.y0 + cb0.y0, vis.x1 + cb0.x0, vis.y1 + cb0.y0)
            page.set_cropbox(new & page.mediabox)
        dest = unique_path(out, f"{f.stem}_recortado.pdf")
        save_pdf(doc, dest)
        files.append(dest)
    return Result(files, "PDF recortado.", zip_name="pdf_recortados.zip")


# ------------------------------------------------------------------ Editor visual (editar y firmar)
def _data_url_bytes(s: str) -> bytes:
    if not s:
        raise ToolError("Falta una imagen en el documento.")
    if "," in s:
        s = s.split(",", 1)[1]
    return base64.b64decode(s)


def apply_objects(doc: pymupdf.Document, objects: list[dict]) -> int:
    count = 0
    touched = set()
    for o in objects:
        pi = as_int(o.get("page"), 0)
        if pi < 0 or pi >= doc.page_count:
            continue
        page = doc[pi]
        if pi not in touched:
            normalize_rotation(page)
            touched.add(pi)
        t = o.get("type")
        x, y, w, h = (as_float(o.get(k), 0) for k in ("x", "y", "w", "h"))
        rect = pymupdf.Rect(x, y, x + w, y + h)
        opacity = max(0.0, min(1.0, as_float(o.get("opacity"), 1)))
        stroke = hex_to_rgb(o.get("stroke"), None) if o.get("stroke") else None
        fill = hex_to_rgb(o.get("fill"), None) if o.get("fill") else None
        width = as_float(o.get("width"), 2)
        if t == "text":
            text = str(o.get("text") or "")
            if not text.strip():
                continue
            size = as_float(o.get("size"), 14)
            fam = _family(o.get("font"))
            fontname = font_for(fam, as_bool(o.get("bold")), as_bool(o.get("italic")))
            color = hex_to_rgb(o.get("color"), (0, 0, 0))
            align = o.get("align", "left")
            base = BASELINE.get(fam, 0.94)
            for li, line in enumerate(text.split("\n")):
                tw = pymupdf.get_text_length(line, fontname=fontname, fontsize=size)
                lx = x if align == "left" else (x + (w - tw) / 2 if align == "center" else x + w - tw)
                ly = y + base * size + li * 1.2 * size
                if line:
                    page.insert_text((lx, ly), line, fontsize=size, fontname=fontname, color=color,
                                     fill_opacity=opacity)
                    if as_bool(o.get("underline")):
                        page.draw_line((lx, ly + size * 0.12), (lx + tw, ly + size * 0.12), color=color,
                                       width=max(0.5, size / 18), stroke_opacity=opacity)
        elif t == "image":
            data = image_bytes_for_pdf(_data_url_bytes(o.get("data", "")), opacity=opacity)
            page.insert_image(rect, stream=data, keep_proportion=False)
        elif t == "rect":
            page.draw_rect(rect, color=stroke, fill=fill, width=width if stroke else 0,
                           stroke_opacity=opacity, fill_opacity=opacity)
        elif t == "ellipse":
            page.draw_oval(rect, color=stroke, fill=fill, width=width if stroke else 0,
                           stroke_opacity=opacity, fill_opacity=opacity)
        elif t in ("line", "arrow"):
            pts = o.get("points") or [[x, y], [x + w, y + h]]
            p1, p2 = pymupdf.Point(pts[0]), pymupdf.Point(pts[-1])
            col = stroke or (0, 0, 0)
            page.draw_line(p1, p2, color=col, width=width, stroke_opacity=opacity, lineCap=1)
            if t == "arrow":
                ang = math.atan2(p2.y - p1.y, p2.x - p1.x)
                L = max(8, width * 4)
                for da in (2.6, -2.6):
                    q = pymupdf.Point(p2.x + L * math.cos(ang + da), p2.y + L * math.sin(ang + da))
                    page.draw_line(p2, q, color=col, width=width, stroke_opacity=opacity, lineCap=1)
        elif t == "draw":
            pts = [pymupdf.Point(p) for p in (o.get("points") or [])]
            if len(pts) >= 2:
                page.draw_polyline(pts, color=stroke or (0, 0, 0), width=width, stroke_opacity=opacity,
                                   lineCap=1, lineJoin=1)
        elif t == "highlight":
            annot = page.add_highlight_annot(rect)
            annot.set_colors(stroke=fill or (1, 0.89, 0.3))
            annot.update()
        elif t == "whiteout":
            page.draw_rect(rect, color=None, fill=fill or (1, 1, 1), width=0)
        else:
            continue
        count += 1
    return count


def edit(inputs: list[InputFile], opts: dict, out: Path, suffix: str = "editado") -> Result:
    objects = _json(opts.get("objects"), [])
    if not objects:
        raise ToolError("Agrega al menos un elemento (texto, imagen, forma o firma) al documento.")
    f = inputs[0]
    doc = open_pdf(f)
    n = apply_objects(doc, objects)
    if as_bool(opts.get("flatten")):
        try:
            doc.bake(annots=True, widgets=False)
        except Exception:
            pass
    dest = unique_path(out, f"{f.stem}_{suffix}.pdf")
    save_pdf(doc, dest)
    return Result([dest], f"Se aplicaron {n} cambio(s) al documento.")


def sign(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    objects = _json(opts.get("objects"), [])
    if not any(o.get("type") == "image" for o in objects) and not objects:
        raise ToolError("Coloca tu firma en el documento antes de continuar.")
    res = edit(inputs, opts, out, suffix="firmado")
    res.message = "Documento firmado."
    return res


# ------------------------------------------------------------------ Formularios
WTYPES = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: "text",
    pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: "listbox",
    pymupdf.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    pymupdf.PDF_WIDGET_TYPE_BUTTON: "button",
}


def form_fields(f: InputFile) -> dict:
    doc = open_pdf(f)
    fields = []
    for page in doc:
        rm = page.rotation_matrix
        for w in page.widgets() or []:
            kind = WTYPES.get(w.field_type, "other")
            if kind in ("button", "signature", "other"):
                continue
            r = w.rect * rm
            item = {
                "xref": w.xref, "page": page.number, "name": w.field_name or f"campo_{w.xref}",
                "label": w.field_label or "", "type": kind, "value": w.field_value,
                "x": r.x0, "y": r.y0, "w": r.width, "h": r.height,
                "multiline": bool(w.field_flags & 4096) if kind == "text" else False,
                "readonly": bool(w.field_flags & 1),
            }
            if kind in ("combobox", "listbox"):
                item["options"] = [c if isinstance(c, str) else c[0] for c in (w.choice_values or [])]
            if kind in ("checkbox", "radio"):
                try:
                    item["on"] = w.on_state()
                except Exception:
                    item["on"] = "Yes"
                item["value"] = w.field_value not in (False, "Off", "", None)
            fields.append(item)
    return {"fields": fields, "pages": doc.page_count}


def forms(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    f = inputs[0]
    doc = open_pdf(f)
    values = _json(opts.get("values"), {})
    new_fields = _json(opts.get("new_fields"), [])
    filled = 0
    for page in doc:
        for w in page.widgets() or []:
            key = str(w.xref)
            if key not in values:
                continue
            v = values[key]
            kind = WTYPES.get(w.field_type)
            try:
                if kind == "checkbox":
                    w.field_value = w.on_state() if as_bool(v) else "Off"
                elif kind == "radio":
                    if as_bool(v):
                        w.field_value = w.on_state()
                    else:
                        continue
                else:
                    w.field_value = "" if v is None else str(v)
                w.update()
                filled += 1
            except Exception:
                continue
    created = 0
    for nf in new_fields:
        pi = as_int(nf.get("page"), 0)
        if pi >= doc.page_count:
            continue
        page = doc[pi]
        normalize_rotation(page)
        x, y, w_, h = (as_float(nf.get(k), 0) for k in ("x", "y", "w", "h"))
        wd = pymupdf.Widget()
        kind = nf.get("type", "text")
        wd.rect = pymupdf.Rect(x, y, x + w_, y + h)
        wd.field_name = (nf.get("name") or f"campo_{pi + 1}_{created + 1}").strip()
        wd.border_color = (0.55, 0.6, 0.65)
        wd.border_width = 0.6
        if kind == "checkbox":
            wd.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
            wd.field_value = as_bool(nf.get("value"))
        elif kind == "combobox":
            wd.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
            opts_list = [s.strip() for s in str(nf.get("options") or "").split(",") if s.strip()] or ["Opción 1", "Opción 2"]
            wd.choice_values = opts_list
            wd.field_value = nf.get("value") or opts_list[0]
            wd.text_fontsize = 0
        else:
            wd.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            wd.field_value = nf.get("value") or ""
            wd.text_fontsize = 0
            if h > 30:
                wd.field_flags |= 4096  # multilínea
        wd.fill_color = (0.94, 0.97, 1)
        page.add_widget(wd)
        created += 1
    if as_bool(opts.get("flatten")):
        doc.bake(annots=False, widgets=True)
    dest = unique_path(out, f"{f.stem}_formulario.pdf")
    save_pdf(doc, dest)
    parts = []
    if filled:
        parts.append(f"{filled} campo(s) rellenado(s)")
    if created:
        parts.append(f"{created} campo(s) nuevo(s)")
    msg = ("Formulario listo: " + " y ".join(parts) + ".") if parts else "Formulario guardado."
    if as_bool(opts.get("flatten")):
        msg += " Los campos quedaron fijos (ya no se pueden editar)."
    return Result([dest], msg)
