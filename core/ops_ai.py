"""Inteligencia PDF: resumir y traducir (con Ollama local o servicios en línea)."""
from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf
import requests

from . import engines
from .utils import InputFile, Result, ToolError, as_bool, normalize_rotation, open_pdf, save_pdf, unique_path

LANGS = {
    "es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "it": "italiano",
    "de": "alemán", "zh-CN": "chino simplificado", "ja": "japonés", "ko": "coreano", "ru": "ruso",
    "ar": "árabe", "nl": "neerlandés", "ca": "catalán", "qu": "quechua",
}


# ------------------------------------------------------------------ Ollama
def ollama_chat(prompt: str, system: str = "", model: str | None = None, temperature: float = 0.2,
                timeout: int = 600) -> str:
    model = model or engines.default_ollama_model()
    if not model:
        raise ToolError("Ollama no está disponible. Ábrelo (o instala un modelo con «ollama pull qwen3:4b») "
                        "o elige el motor sin IA.")
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": msgs, "stream": False, "think": False,
            "options": {"temperature": temperature, "num_ctx": 8192}}
    try:
        r = requests.post(f"{engines.OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        if r.status_code == 400 and "think" in r.text.lower():
            body.pop("think")
            r = requests.post(f"{engines.OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
    except requests.ConnectionError:
        raise ToolError(f"No se pudo conectar con Ollama en {engines.OLLAMA_URL}. ¿Está abierto?")
    except requests.HTTPError:
        raise ToolError(f"Ollama respondió con un error: {r.text[:200]}")
    except requests.Timeout:
        raise ToolError("Ollama tardó demasiado en responder. Prueba con un documento más corto o un modelo más pequeño.")
    content = r.json().get("message", {}).get("content", "")
    return re.sub(r"(?s)<think>.*?</think>", "", content).strip()


def _chunks(text: str, size: int = 7000) -> list[str]:
    paras = re.split(r"\n\s*\n", text)
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        while len(p) > size:
            out.append(p[:size])
            p = p[size:]
        cur += p + "\n\n"
    if cur.strip():
        out.append(cur)
    return out


# ------------------------------------------------------------------ Resumen extractivo (sin IA)
STOP = set("""a al algo algunas algunos ante antes como con contra cual cuando de del desde donde durante e el ella ellas
ellos en entre era eran es esa esas ese eso esos esta estaba estas este esto estos fue fueron ha han hasta hay la las le les lo los
mas más me mi mis muy no nos o otra otro para pero por porque que qué se sea ser si sí sin sobre su sus también tanto te tiene
tienen todo todos tu un una uno unos y ya the of and to in is for on that with as are be by this it from or an at was which
""".split())


def extractive_summary(text: str, n: int) -> str:
    seen_s: set[str] = set()
    sentences = []
    for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9])", re.sub(r"\s+", " ", text)):
        s = s.strip()
        key = s.lower()
        if 40 < len(s) < 600 and key not in seen_s:
            seen_s.add(key)
            sentences.append(s)
    if not sentences:
        return text[:1500]
    words = [w for w in re.findall(r"[a-záéíóúñü]{3,}", text.lower()) if w not in STOP]
    freq = Counter(words)
    top = freq.most_common(1)[0][1] if freq else 1
    scored = []
    for i, s in enumerate(sentences):
        ws = [w for w in re.findall(r"[a-záéíóúñü]{3,}", s.lower()) if w not in STOP]
        if not ws:
            continue
        score = sum(freq[w] / top for w in ws) / (len(ws) ** 0.6)
        if i < 3:
            score *= 1.2
        scored.append((score, i, s))
    best = sorted(sorted(scored, reverse=True)[:n], key=lambda t: t[1])
    return "\n".join(f"- {s}" for _, _, s in best)


# ------------------------------------------------------------------ Markdown → HTML mínimo (para el PDF del resumen)
def md_to_html(md: str) -> str:
    out, in_list = [], False
    for line in md.splitlines():
        s = line.rstrip()
        esc = html.escape(s)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", esc)
        m = re.match(r"^(#{1,4})\s+(.*)", esc)
        li = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)", esc)
        if li:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{li.group(1)}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if m:
            lvl = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
        elif esc.strip():
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def text_pdf(title: str, md: str, dest: Path) -> Path:
    css = """
    body { font-family: sans-serif; font-size: 11pt; line-height: 1.45; color: #1d232b; }
    h1 { font-size: 18pt; color: #0b6b55; margin-bottom: 4pt; }
    h2 { font-size: 14pt; margin-top: 12pt; color: #0b6b55; }
    h3, h4 { font-size: 12pt; margin-top: 10pt; }
    p { margin: 0 0 6pt 0; } li { margin-bottom: 4pt; }
    .meta { color: #6b7380; font-size: 9pt; }
    """
    body = f"<h1>{html.escape(title)}</h1><p class='meta'>Generado con BSOBPDF</p>" + md_to_html(md)
    story = pymupdf.Story(html=body, user_css=css)
    writer = pymupdf.DocumentWriter(str(dest))
    rect = pymupdf.paper_rect("a4")
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(rect + (56, 56, -56, -56))
        story.draw(dev)
        writer.end_page()
    writer.close()
    return dest


# ------------------------------------------------------------------ Resumir
LENGTHS = {"corto": ("entre 3 y 5 viñetas breves", 5), "medio": ("entre 6 y 10 viñetas", 9),
           "largo": ("un resumen detallado por secciones con títulos y viñetas", 16)}


def summarize(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    f = inputs[0]
    doc = open_pdf(f)
    text = "\n\n".join(p.get_text("text") for p in doc)
    if len(text.strip()) < 40:
        raise ToolError("Este PDF no tiene texto suficiente para resumir. Si es un escaneo, aplica OCR PDF primero.")
    length = opts.get("length", "medio")
    how, n_sent = LENGTHS.get(length, LENGTHS["medio"])
    lang = LANGS.get(opts.get("language", "es"), "español")
    engine = opts.get("engine", "ollama")
    model = opts.get("model") or None
    if engine == "extractivo":
        # Solo párrafos de prosa: se descartan tablas, encabezados y números sueltos
        prose = []
        for page in doc:
            for b in page.get_text("blocks"):
                t = " ".join(b[4].split())
                words = t.split()
                letters = sum(c.isalpha() for c in t)
                if len(words) >= 8 and letters > 0.6 * len(t.replace(" ", "")):
                    prose.append(t)
        summary = "## Ideas principales\n\n" + extractive_summary("\n\n".join(prose) or text, n_sent)
        used = "resumen extractivo (sin IA)"
    else:
        system = (f"Eres un asistente que resume documentos con precisión. Responde siempre en {lang}, "
                  "en formato Markdown, sin inventar datos que no estén en el texto.")
        parts = _chunks(text)
        if len(parts) == 1:
            summary = ollama_chat(f"Resume el siguiente documento en {how}. Empieza con una frase que diga de qué trata.\n\n"
                                  f"DOCUMENTO:\n{parts[0]}", system, model)
        else:
            partials = [ollama_chat(f"Resume esta parte ({i + 1}/{len(parts)}) de un documento en 4 a 6 viñetas con "
                                    f"los datos clave:\n\n{p}", system, model) for i, p in enumerate(parts)]
            joined = "\n\n".join(partials)
            summary = ollama_chat(f"Estos son resúmenes parciales de un mismo documento. Únelos en {how}, "
                                  f"sin repetir ideas. Empieza con una frase que diga de qué trata.\n\n{joined}",
                                  system, model)
        used = f"Ollama ({model or engines.default_ollama_model()})"
    md_path = unique_path(out, f"{f.stem}_resumen.md")
    md_path.write_text(f"# Resumen de {f.name}\n\n{summary}\n", encoding="utf-8")
    pdf_path = text_pdf(f"Resumen de {f.name}", summary, unique_path(out, f"{f.stem}_resumen.pdf"))
    words = len(text.split())
    return Result([pdf_path, md_path], f"Resumen listo ({used}). El documento original tiene {words:,} palabras.".replace(",", "."),
                  {"words": words}, data={"summary": summary, "engine": used}, zip_name=f"{f.stem}_resumen.zip")


# ------------------------------------------------------------------ Traducir
def _translate_google(texts: list[str], target: str, source: str = "auto") -> list[str]:
    """Traduce en lotes (varias líneas por solicitud) para respetar el límite de Google."""
    try:
        from deep_translator import GoogleTranslator
    except Exception:
        raise ToolError("Falta el paquete deep-translator. Ejecuta de nuevo INICIAR.bat.")
    import time as _time
    from concurrent.futures import ThreadPoolExecutor

    failures = {"n": 0, "last": ""}

    def call(text: str) -> str | None:
        tr = GoogleTranslator(source=source or "auto", target=target)
        for attempt in range(3):
            try:
                return tr.translate(text)
            except Exception as e:  # noqa: BLE001
                failures["last"] = f"{type(e).__name__}: {e}"
                msg = str(e).lower()
                if any(k in msg for k in ("connect", "resolve", "timed out", "max retries", "proxy")):
                    raise ToolError("No hay conexión a internet para el traductor en línea. Usa el motor Ollama (local).")
                _time.sleep(1 + attempt)
        failures["n"] += 1
        return None

    # Agrupamos bloques en lotes de ~4000 caracteres, un bloque por línea
    batches: list[list[int]] = []
    cur, size = [], 0
    for i, t in enumerate(texts):
        t1 = t.replace("\n", " ")
        if cur and size + len(t1) > 4000:
            batches.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(t1) + 1
    if cur:
        batches.append(cur)
    result: list[str] = list(texts)

    def do_batch(idx: list[int]) -> None:
        joined = "\n".join(texts[i].replace("\n", " ")[:4800] for i in idx)
        ans = call(joined)
        if ans is None:
            raise ToolError("El traductor en línea no respondió (puede ser el límite de solicitudes de Google o la conexión). "
                            "Intenta de nuevo en un momento o usa el motor Ollama (local).")
        parts = ans.split("\n")
        if ans and len(parts) == len(idx):
            for i, p in zip(idx, parts):
                result[i] = p.strip() or texts[i]
        else:
            for i in idx:  # el lote no conservó las líneas: uno por uno
                r = call(texts[i][:4800])
                if r:
                    result[i] = r

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(do_batch, batches))
    if failures["n"] and failures["n"] >= max(1, len(batches)):
        raise ToolError("El traductor en línea no respondió (puede ser el límite de solicitudes de Google o la conexión). "
                        "Intenta de nuevo en un momento o usa el motor Ollama (local).")
    return result


def _translate_ollama(texts: list[str], target: str, model: str | None) -> list[str]:
    lang = LANGS.get(target, target)
    system = (f"Eres un traductor profesional. Traduce al {lang} con naturalidad y precisión. "
              "Conserva números, nombres propios, siglas y formato. No agregues explicaciones.")
    out: list[str] = []
    batch: list[str] = []

    def flush():
        if not batch:
            return
        payload = json.dumps(batch, ensure_ascii=False)
        ans = ollama_chat(f"Traduce cada elemento de este arreglo JSON al {lang}. Responde SOLO con un arreglo JSON "
                          f"de la misma longitud ({len(batch)} elementos), en el mismo orden:\n{payload}", system, model)
        m = re.search(r"\[.*\]", ans, re.S)
        res = None
        if m:
            try:
                res = json.loads(m.group(0))
            except Exception:
                res = None
        if not isinstance(res, list) or len(res) != len(batch):
            res = [ollama_chat(f"Traduce al {lang}. Responde solo con la traducción:\n\n{t}", system, model) for t in batch]
        out.extend(str(x) for x in res)
        batch.clear()

    size = 0
    for t in texts:
        if size + len(t) > 2500 or len(batch) >= 15:
            flush()
            size = 0
        batch.append(t)
        size += len(t)
    flush()
    return out


def translate(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    target = opts.get("target", "en")
    engine = opts.get("engine", "google")
    model = opts.get("model") or None
    f = inputs[0]
    doc = open_pdf(f)
    jobs = []  # (page, rect, text, size, color, bold, serif)

    def style(spans):
        sizes = [round(s["size"], 1) for s in spans]
        colors = [s["color"] for s in spans]
        bolds = [bool(s["flags"] & 16) or "bold" in s["font"].lower() for s in spans]
        serif = sum(1 for s in spans if s["flags"] & 4 or "times" in s["font"].lower() or "serif" in s["font"].lower())
        return (Counter(sizes).most_common(1)[0][0], Counter(colors).most_common(1)[0][0],
                sum(bolds) > len(bolds) / 2, serif > len(spans) / 2)

    def segments(line):
        """Parte una línea donde hay huecos grandes (celdas de tabla, columnas).
        Devuelve una lista de segmentos; cada uno es una lista de «pseudo-spans» con texto y bbox."""
        segs, cur, last_x1 = [], None, None
        for s in line["spans"]:
            for ch in s["chars"]:
                c = ch["c"]
                x0, x1 = ch["bbox"][0], ch["bbox"][2]
                if c.strip() and last_x1 is not None and x0 - last_x1 > 1.6 * s["size"]:
                    segs.append(cur)
                    cur = None
                if cur is None:
                    cur = []
                if not cur or cur[-1]["_src"] is not s:
                    cur.append({"_src": s, "text": "", "bbox": list(ch["bbox"]), "size": s["size"],
                                "color": s["color"], "flags": s["flags"], "font": s["font"]})
                ps = cur[-1]
                ps["text"] += c
                ps["bbox"] = [min(ps["bbox"][0], ch["bbox"][0]), min(ps["bbox"][1], ch["bbox"][1]),
                              max(ps["bbox"][2], ch["bbox"][2]), max(ps["bbox"][3], ch["bbox"][3])]
                if c.strip():
                    last_x1 = x1
        if cur:
            segs.append(cur)
        return [[ps for ps in sg if ps["text"].strip()] for sg in segs if any(ps["text"].strip() for ps in sg)]

    for page in doc:
        normalize_rotation(page)
        d = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            lines = [ln for ln in b["lines"] if abs(ln.get("dir", (1, 0))[1]) <= 0.1]
            segs_per_line = [segments(ln) for ln in lines]
            tabular = any(len(sg) > 1 for sg in segs_per_line)
            if not tabular and len(lines) > 1:
                # Varias líneas a la misma altura = celdas o columnas distintas
                ys = sorted(((ln["bbox"][1] + ln["bbox"][3]) / 2, ln["bbox"][3] - ln["bbox"][1]) for ln in lines)
                tabular = any(abs(ys[i + 1][0] - ys[i][0]) < 0.5 * max(ys[i][1], 1) for i in range(len(ys) - 1))
            if tabular:
                # Cada celda se traduce y se coloca por separado
                for sg in segs_per_line:
                    for spans in sg:
                        text = "".join(s["text"] for s in spans).strip()
                        if not re.search(r"[A-Za-zÀ-ÿ]{2,}", text):
                            continue
                        r = pymupdf.Rect(spans[0]["bbox"])
                        for s in spans[1:]:
                            r |= pymupdf.Rect(s["bbox"])
                        jobs.append((page.number, r, text, *style(spans)))
                continue
            texts, spans_all = [], []
            for sg in segs_per_line:
                for spans in sg:
                    texts.append("".join(s["text"] for s in spans).strip())
                    spans_all += spans
            text = re.sub(r"(\w)- (\w)", r"\1\2", " ".join(t for t in texts if t))
            if not spans_all or not re.search(r"[A-Za-zÀ-ÿ]{2,}", text):
                continue
            jobs.append((page.number, pymupdf.Rect(b["bbox"]), text, *style(spans_all)))
    if not jobs:
        raise ToolError("Este PDF no tiene texto para traducir. Si es un escaneo, aplica OCR PDF primero.")
    texts = [j[2] for j in jobs]
    if engine == "ollama":
        translated = _translate_ollama(texts, target, model)
        used = f"Ollama ({model or engines.default_ollama_model()})"
    else:
        translated = _translate_google(texts, target, opts.get("source", "auto"))
        used = "Google Translate"
    # Borramos el texto original (sin tocar imágenes ni gráficos) y escribimos la traducción en su lugar
    by_page: dict[int, list] = {}
    for j, t in zip(jobs, translated):
        by_page.setdefault(j[0], []).append((j, t))
    for pno, items in by_page.items():
        page = doc[pno]
        for (j, _t) in items:
            page.add_redact_annot(j[1], fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        for (j, t) in items:
            _, rect, _, size, color, bold, serif = j
            c = f"#{color:06x}"
            fam = "serif" if serif else "sans-serif"
            css = f"* {{font-family: {fam}; font-size: {size}px; color: {c}; line-height: 1.15; " \
                  f"font-weight: {'bold' if bold else 'normal'}; margin: 0; padding: 0;}}"
            r = pymupdf.Rect(rect.x0, rect.y0 - size * 0.1, rect.x1 + 2, rect.y1 + size * 0.3)
            try:
                page.insert_htmlbox(r, html.escape(t), css=css, scale_low=0.4)
            except Exception:
                page.insert_textbox(r, t, fontsize=size * 0.85, fontname="helv", color=pymupdf.sRGB_to_pdf(color))
    dest = unique_path(out, f"{f.stem}_{target}.pdf")
    save_pdf(doc, dest, garbage=3)
    return Result([dest], f"PDF traducido al {LANGS.get(target, target)} con {used}, conservando el diseño.",
                  {"blocks": len(jobs)})
