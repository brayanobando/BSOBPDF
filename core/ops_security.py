"""Seguridad: desbloquear, proteger, censurar y comparar."""
from __future__ import annotations

import difflib
import json
import re
import secrets
from pathlib import Path

import pymupdf

from .utils import (InputFile, Result, ToolError, as_bool, as_float, as_int, hex_to_rgb, normalize_rotation,
                    open_pdf, save_pdf, unique_path)


# ------------------------------------------------------------------ Desbloquear
def unlock(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    files, had_pass = [], 0
    pw = opts.get("password") or ""
    for f in inputs:
        try:
            doc = pymupdf.open(f.path)
        except Exception:
            raise ToolError(f"No se pudo abrir «{f.name}».")
        if doc.needs_pass:
            had_pass += 1
            if not pw:
                raise ToolError(f"«{f.name}» pide contraseña para abrirse. Escríbela en las opciones.")
            if not doc.authenticate(pw):
                raise ToolError(f"La contraseña de «{f.name}» no es correcta.")
        elif doc.is_encrypted:
            had_pass += 1  # solo tenía restricciones (contraseña de propietario)
        dest = unique_path(out, f"{f.stem}_desbloqueado.pdf")
        save_pdf(doc, dest, encryption=pymupdf.PDF_ENCRYPT_NONE)
        files.append(dest)
    msg = ("PDF desbloqueado: ya puedes abrirlo, imprimirlo y copiarlo sin contraseña."
           if had_pass else "Este PDF no tenía contraseña ni restricciones; se entrega una copia sin cambios.")
    return Result(files, msg, zip_name="pdf_desbloqueados.zip")


# ------------------------------------------------------------------ Proteger
def protect(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    pw = opts.get("password") or ""
    if len(pw) < 4:
        raise ToolError("La contraseña debe tener al menos 4 caracteres.")
    if opts.get("password2") is not None and opts.get("password2") != pw:
        raise ToolError("Las contraseñas no coinciden.")
    perms = pymupdf.PDF_PERM_ACCESSIBILITY
    restricted = False
    for key, flag in (("allow_print", pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ),
                      ("allow_copy", pymupdf.PDF_PERM_COPY),
                      ("allow_modify", pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ASSEMBLE),
                      ("allow_annotate", pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM)):
        if as_bool(opts.get(key, True)):
            perms |= flag
        else:
            restricted = True
    owner = opts.get("owner_password") or (secrets.token_urlsafe(18) if restricted else pw)
    files = []
    for f in inputs:
        doc = open_pdf(f, opts.get("current_password"))
        dest = unique_path(out, f"{f.stem}_protegido.pdf")
        save_pdf(doc, dest, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=pw, owner_pw=owner,
                 permissions=perms)
        files.append(dest)
    msg = "PDF protegido con cifrado AES de 256 bits."
    if restricted:
        msg += " Se aplicaron las restricciones elegidas."
    return Result(files, msg, zip_name="pdf_protegidos.zip")


# ------------------------------------------------------------------ Censurar
PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "telefono": r"(?:\+?57[\s-]?)?(?:3\d{2}|60\d)[\s-]?\d{3}[\s-]?\d{4}|\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}",
    "documento": r"\b\d{1,3}(?:\.\d{3}){2,3}\b|\b\d{6,11}\b",
    "fecha": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
    "url": r"https?://\S+|www\.\S+",
    "tarjeta": r"\b(?:\d{4}[\s-]?){3}\d{4}\b",
}


def redact(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    areas = opts.get("areas") or []
    if isinstance(areas, str):
        areas = json.loads(areas or "[]")
    terms = [t.strip() for t in re.split(r"[\n;]", opts.get("terms") or "") if t.strip()]
    pats = [p for p in (opts.get("patterns") or "").split(",") if p in PATTERNS]
    case = as_bool(opts.get("match_case"))
    fill = hex_to_rgb(opts.get("color"), (0, 0, 0))
    if not areas and not terms and not pats:
        raise ToolError("Marca áreas en el documento, escribe palabras o elige qué datos censurar.")
    f = inputs[0]
    doc = open_pdf(f)
    counts = {"areas": 0, "terms": 0, "patterns": 0}
    for page in doc:
        normalize_rotation(page)
        for a in areas:
            if as_int(a.get("page"), -1) == page.number:
                r = pymupdf.Rect(as_float(a["x"], 0), as_float(a["y"], 0),
                                 as_float(a["x"], 0) + as_float(a["w"], 0), as_float(a["y"], 0) + as_float(a["h"], 0))
                page.add_redact_annot(r, fill=fill)
                counts["areas"] += 1
        for t in terms:
            hits = page.search_for(t) if not case else [
                q for q in page.search_for(t) if t in page.get_textbox(q + (-1, -1, 1, 1))]
            for q in hits:
                page.add_redact_annot(q, fill=fill)
                counts["terms"] += 1
        if pats:
            text = page.get_text("text")
            found = set()
            for p in pats:
                for m in re.finditer(PATTERNS[p], text):
                    s = m.group(0).strip()
                    if len(s) >= 4:
                        found.add(s)
            for s in found:
                for q in page.search_for(s):
                    page.add_redact_annot(q, fill=fill)
                    counts["patterns"] += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)
    if as_bool(opts.get("clean_metadata", True)):
        doc.set_metadata({})
        try:
            doc.del_xml_metadata()
        except Exception:
            pass
    total = sum(counts.values())
    if total == 0:
        raise ToolError("No se encontró nada que censurar con esos criterios.")
    dest = unique_path(out, f"{f.stem}_censurado.pdf")
    save_pdf(doc, dest, garbage=4, clean=True)
    return Result([dest], f"Se censuraron {total} elemento(s) de forma permanente: el texto debajo ya no existe.",
                  {"counts": counts})


# ------------------------------------------------------------------ Comparar
def _words(doc: pymupdf.Document):
    out = []
    for page in doc:
        for x0, y0, x1, y1, w, *_ in page.get_text("words", sort=True):
            out.append((w, page.number, pymupdf.Rect(x0, y0, x1, y1)))
    return out


def compare(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    if len(inputs) != 2:
        raise ToolError("Carga exactamente dos PDF: la versión original y la nueva.")
    a, b = open_pdf(inputs[0]), open_pdf(inputs[1])
    for d in (a, b):
        for p in d:
            normalize_rotation(p)
    wa, wb = _words(a), _words(b)
    if not wa and not wb:
        raise ToolError("Ninguno de los dos PDF tiene texto. Si son escaneos, aplica OCR PDF primero.")
    norm = (lambda s: s) if as_bool(opts.get("match_case", True)) else (lambda s: s.lower())
    sm = difflib.SequenceMatcher(None, [norm(w[0]) for w in wa], [norm(w[0]) for w in wb], autojunk=False)
    del_marks: dict[int, list] = {}
    ins_marks: dict[int, list] = {}
    changes = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old = " ".join(w[0] for w in wa[i1:i2])
        new = " ".join(w[0] for w in wb[j1:j2])
        for w in wa[i1:i2]:
            del_marks.setdefault(w[1], []).append(w[2])
        for w in wb[j1:j2]:
            ins_marks.setdefault(w[1], []).append(w[2])
        page_b = wb[j1][1] + 1 if j1 < len(wb) else (wb[-1][1] + 1 if wb else 1)
        page_a = wa[i1][1] + 1 if i1 < len(wa) else (wa[-1][1] + 1 if wa else 1)
        changes.append({"type": {"replace": "cambio", "delete": "eliminado", "insert": "agregado"}[tag],
                        "old": old[:300], "new": new[:300], "page_a": page_a, "page_b": page_b})
    # Informe lado a lado
    report = pymupdf.open()
    gap, head = 24, 36
    red, green = (0.86, 0.15, 0.15), (0.05, 0.6, 0.35)
    for i in range(max(a.page_count, b.page_count)):
        ra = a[i].rect if i < a.page_count else None
        rb = b[i].rect if i < b.page_count else None
        wa_ = ra.width if ra else (rb.width if rb else 595)
        wb_ = rb.width if rb else wa_
        h = max(ra.height if ra else 0, rb.height if rb else 0)
        page = report.new_page(width=wa_ + wb_ + gap * 3, height=h + head + gap)
        page.insert_text((gap, 24), f"Original: {inputs[0].name[:60]} (pág. {i + 1})", fontsize=10, color=(0.3, 0.3, 0.3))
        page.insert_text((gap * 2 + wa_, 24), f"Nueva: {inputs[1].name[:60]} (pág. {i + 1})", fontsize=10, color=(0.3, 0.3, 0.3))
        if ra:
            ta = pymupdf.Rect(gap, head, gap + wa_, head + ra.height)
            page.show_pdf_page(ta, a, i)
            page.draw_rect(ta, color=(0.8, 0.8, 0.8), width=0.5)
            for r in del_marks.get(i, []):
                page.draw_rect(r + (ta.x0, ta.y0, ta.x0, ta.y0), color=red, fill=red, fill_opacity=0.25, width=0.6)
        if rb:
            tb = pymupdf.Rect(gap * 2 + wa_, head, gap * 2 + wa_ + wb_, head + rb.height)
            page.show_pdf_page(tb, b, i)
            page.draw_rect(tb, color=(0.8, 0.8, 0.8), width=0.5)
            for r in ins_marks.get(i, []):
                page.draw_rect(r + (tb.x0, tb.y0, tb.x0, tb.y0), color=green, fill=green, fill_opacity=0.25, width=0.6)
    dest = unique_path(out, f"comparacion_{inputs[0].stem}_vs_{inputs[1].stem}.pdf"[:120])
    save_pdf(report, dest)
    similarity = round(sm.ratio() * 100, 1)
    msg = (f"Los documentos son idénticos en su texto." if not changes else
           (("Se encontró 1 diferencia." if len(changes) == 1 else f"Se encontraron {len(changes)} diferencias.")
            + f" Similitud del texto: {str(similarity).replace('.', ',')} %."))
    return Result([dest], msg, {"changes": len(changes), "similarity": similarity},
                  data={"changes": changes[:500], "report": dest.name})
