"""Utilidades compartidas por todas las herramientas."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


class ToolError(Exception):
    """Error con un mensaje pensado para mostrarse tal cual al usuario."""


@dataclass
class InputFile:
    path: Path          # ruta en disco (nombre seguro)
    name: str           # nombre original que eligió el usuario

    @property
    def stem(self) -> str:
        return safe_stem(self.name)

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()


@dataclass
class Result:
    files: list[Path] = field(default_factory=list)
    message: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    zip_name: str | None = None


# ---------------------------------------------------------------- nombres

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_stem(name: str, default: str = "documento") -> str:
    stem = Path(name).stem
    stem = _BAD.sub("_", stem).strip(" .")
    return (stem[:80] or default)


def unique_path(folder: Path, filename: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / filename
    if not p.exists():
        return p
    stem, suf = p.stem, p.suffix
    i = 2
    while True:
        cand = folder / f"{stem} ({i}){suf}"
        if not cand.exists():
            return cand
        i += 1


# ---------------------------------------------------------------- PDF

def open_pdf(inp: InputFile | Path, password: str | None = None) -> pymupdf.Document:
    path = inp.path if isinstance(inp, InputFile) else inp
    name = inp.name if isinstance(inp, InputFile) else path.name
    try:
        doc = pymupdf.open(path)
    except Exception:
        raise ToolError(f"No se pudo abrir «{name}». ¿Es un PDF válido? Prueba primero con Reparar PDF.")
    if not doc.is_pdf:
        # Documentos XPS, EPUB, imágenes… se convierten a PDF en memoria
        try:
            data = doc.convert_to_pdf()
            doc.close()
            doc = pymupdf.open("pdf", data)
        except Exception:
            raise ToolError(f"«{name}» no es un PDF.")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            raise ToolError(
                f"«{name}» está protegido con contraseña. Desbloquéalo primero con Desbloquear PDF"
                + (" (la contraseña escrita no es correcta)." if password else ".")
            )
    if doc.page_count == 0:
        raise ToolError(f"«{name}» no tiene páginas.")
    return doc


def save_pdf(doc: pymupdf.Document, path: Path, **kw) -> Path:
    opts = dict(garbage=3, deflate=True)
    opts.update(kw)
    doc.save(path, **opts)
    return path


def parse_pages(spec: str | None, n: int, default_all: bool = True) -> list[int]:
    """Convierte «1-3, 5, 8-» en índices (base 0). Admite «todas», «impares», «pares», «última»."""
    if spec is None or str(spec).strip() == "":
        return list(range(n)) if default_all else []
    s = str(spec).lower().replace(" ", "")
    if s in ("todas", "all", "*"):
        return list(range(n))
    if s in ("impares", "odd"):
        return list(range(0, n, 2))
    if s in ("pares", "even"):
        return list(range(1, n, 2))
    out: list[int] = []
    for part in re.split(r"[;,]", s):
        if not part:
            continue
        part = part.replace("última", str(n)).replace("ultima", str(n)).replace("fin", str(n))
        m = re.fullmatch(r"(\d*)-(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else n
            if a > b:
                a, b = b, a
            for p in range(a, b + 1):
                if 1 <= p <= n:
                    out.append(p - 1)
        elif part.isdigit():
            p = int(part)
            if 1 <= p <= n:
                out.append(p - 1)
        else:
            raise ToolError(f"No entiendo el rango de páginas «{part}». Usa algo como 1-3, 5, 8-10.")
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "si", "sí", "on", "yes")


def as_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def as_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def hex_to_rgb(h: str | None, default=(0, 0, 0)) -> tuple[float, float, float]:
    if not h:
        return default
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore
    except ValueError:
        return default


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


def zip_files(files: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        used = set()
        for f in files:
            arc = f.name
            i = 2
            while arc in used:
                arc = f"{f.stem} ({i}){f.suffix}"
                i += 1
            used.add(arc)
            z.write(f, arc)
    return dest


def normalize_rotation(page: pymupdf.Page) -> None:
    """Deja la página con /Rotate 0 sin cambiar su aspecto, para trabajar en coordenadas visibles."""
    if page.rotation:
        page.remove_rotation()


def font_for(family: str, bold: bool = False, italic: bool = False) -> str:
    """Nombre de fuente base-14 de PyMuPDF según familia/estilo."""
    family = (family or "helv").lower()
    if family in ("times", "serif", "tiro"):
        return {(False, False): "tiro", (True, False): "tibo", (False, True): "tiit", (True, True): "tibi"}[(bold, italic)]
    if family in ("courier", "mono", "cour"):
        return {(False, False): "cour", (True, False): "cobo", (False, True): "coit", (True, True): "cobi"}[(bold, italic)]
    return {(False, False): "helv", (True, False): "hebo", (False, True): "heit", (True, True): "hebi"}[(bold, italic)]


def image_bytes_for_pdf(data: bytes, opacity: float = 1.0, rotate: float = 0) -> bytes:
    """Prepara una imagen (cualquier formato que lea Pillow) para insertarla en un PDF."""
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if opacity < 1 or rotate or has_alpha:
        im = im.convert("RGBA")
        if opacity < 1:
            a = im.getchannel("A").point(lambda v: int(v * max(0.0, opacity)))
            im.putalpha(a)
        if rotate:
            im = im.rotate(rotate, expand=True, resample=Image.BICUBIC)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return buf.getvalue()
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


OpFunc = Callable[[list[InputFile], dict, Path], Result]
