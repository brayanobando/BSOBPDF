"""BSOBPDF — todas las herramientas PDF en tu propio equipo.

Ejecuta:  python app.py      (o usa INICIAR.bat en Windows)
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import socket
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from pathlib import Path

# En Windows el registro a veces asocia .js a text/plain y el navegador bloquea los scripts
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for  # noqa: E402
from markupsafe import Markup  # noqa: E402

from core import engines, jobs  # noqa: E402
from core.ops_edit import form_fields  # noqa: E402
from core.registry import BY_SLUG, CATEGORIES, NEXT, TOOLS, public  # noqa: E402
from core.utils import InputFile, ToolError, human_size, safe_stem, unique_path, zip_files  # noqa: E402
from core.workflow import run_workflow  # noqa: E402

BASE = Path(__file__).resolve().parent
VERSION = "1.0"
PORT = int(os.environ.get("BSOBPDF_PORT", "5000"))
HOST = os.environ.get("BSOBPDF_HOST", "0.0.0.0")

app = Flask(__name__, static_folder=str(BASE / "static"), template_folder=str(BASE / "templates"))
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("BSOBPDF_MAX_MB", "500")) * 1024 * 1024
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False
log = logging.getLogger("bsobpdf")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

# PyMuPDF no es seguro entre hilos: procesamos un trabajo a la vez
OPS_LOCK = threading.Lock()

# ------------------------------------------------------------------ iconos SVG (Lucide, licencia ISC)
_ICONS: dict[str, str] = json.loads((BASE / "static" / "icons" / "icons.json").read_text("utf-8"))


def icon(name: str, cls: str = "ico") -> Markup:
    svg = _ICONS.get(name, "")
    return Markup(svg.replace("<svg", f'<svg class="{cls}" aria-hidden="true" focusable="false"', 1))


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


_ICONS_JSON: dict[str, str] = {}


def icons_json() -> dict[str, str]:
    """Todos los iconos para el JavaScript (se arman una vez)."""
    if not _ICONS_JSON:
        for name in _ICONS:
            _ICONS_JSON[name] = str(icon(name))
    return _ICONS_JSON


@app.context_processor
def inject():
    cats = {c["id"]: c for c in CATEGORIES}
    return dict(icon=icon, TOOLS=TOOLS, CATEGORIES=CATEGORIES, CATS=cats, VERSION=VERSION,
                icons_json=icons_json())


@app.before_request
def _cleanup():
    jobs.cleanup()


# ================================================================== PÁGINAS
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/flujos")
def workflows_page():
    wf_tools = [public(t) for t in TOOLS if t["workflow"]]
    return render_template("workflows.html", wf_tools=wf_tools)


@app.get("/estado")
def status_page():
    return render_template("status.html", st=engines.status(), lan=f"http://{lan_ip()}:{PORT}",
                           python=sys.version.split()[0], work=str(jobs.WORK))


@app.get("/<slug>")
def tool_page(slug):
    tool = BY_SLUG.get(slug)
    if not tool:
        abort(404)
    related = [BY_SLUG[s] for s in NEXT["pdf"] if s in BY_SLUG and s != slug][:6]
    same_cat = [t for t in TOOLS if t["category"] == tool["category"] and t["slug"] != slug]
    st = {"office": True, "ocr": True}
    if tool.get("needs") == "office":
        st["office"] = bool(engines.soffice_path() or engines.ms_office_available())
    if tool.get("needs") == "ocr":
        st["ocr"] = bool(engines.ocr_languages())
    return render_template("tool.html", tool=tool, tool_json=public(tool), related=related, same_cat=same_cat,
                           next_tools=[public(BY_SLUG[s]) for s in NEXT["pdf"] if s in BY_SLUG],
                           engines_status=st)


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error="Ruta no encontrada."), 404
    return render_template("404.html"), 404


@app.errorhandler(413)
def too_large(_e):
    return jsonify(ok=False, error=f"Los archivos superan el límite de {app.config['MAX_CONTENT_LENGTH'] // 1048576} MB."), 413


# ================================================================== API
def _save_uploads(d: Path, tool: dict | None) -> tuple[list[InputFile], dict]:
    files = request.files.getlist("files")
    inputs: list[InputFile] = []
    accept = [a.strip() for a in (tool["accept"].split(",") if tool else [".pdf"])]
    for i, fs in enumerate(files):
        name = fs.filename or f"archivo_{i + 1}"
        ext = Path(name).suffix.lower()
        if tool and ext not in accept:
            raise ToolError(f"«{name}» no se puede usar aquí. Formatos aceptados: {', '.join(a.upper().lstrip('.') for a in accept)}.")
        p = d / "in" / f"in_{i:03d}{ext}"
        fs.save(p)
        if p.stat().st_size == 0:
            raise ToolError(f"«{name}» está vacío.")
        inputs.append(InputFile(p, name))
    extras = {}
    for key in request.files:
        if key == "files":
            continue
        fs = request.files[key]
        if fs and fs.filename:
            p = d / "in" / f"extra_{safe_stem(key)}{Path(fs.filename).suffix.lower()}"
            fs.save(p)
            extras[key] = InputFile(p, fs.filename)
    return inputs, extras


def _package(jid: str, d: Path, res, base_name: str) -> dict:
    out = d / "out"
    files = [f for f in res.files if f.exists()]
    if not files:
        raise ToolError("La herramienta no produjo ningún archivo.")
    # Todo lo que se entrega debe quedar dentro de out/
    for i, f in enumerate(files):
        if f.parent != out:
            dest = unique_path(out, f.name)
            shutil.copyfile(f, dest)
            files[i] = dest
    if len(files) == 1:
        main = files[0]
    else:
        main = zip_files(files, unique_path(out, res.zip_name or f"{base_name}.zip"))
    def info(p: Path):
        return {"name": p.name, "size": p.stat().st_size, "size_h": human_size(p.stat().st_size),
                "url": url_for("download", jid=jid, name=p.name)}
    return {"ok": True, "job": jid, "download": info(main), "files": [info(f) for f in files],
            "message": res.message, "stats": res.stats, "data": res.data}


@app.post("/api/procesar/<slug>")
def process(slug):
    tool = BY_SLUG.get(slug)
    if not tool:
        return jsonify(ok=False, error="Herramienta desconocida."), 404
    jid, d = jobs.new_job()
    t0 = time.time()
    try:
        inputs, extras = _save_uploads(d, tool)
        try:
            opts = json.loads(request.form.get("options") or "{}")
        except json.JSONDecodeError:
            opts = {}
        opts.update(extras)
        if len(inputs) < tool["min_files"]:
            n = tool["min_files"]
            raise ToolError("Agrega un archivo para continuar." if n == 1 else f"Agrega al menos {n} archivos.")
        if tool["max_files"] and len(inputs) > tool["max_files"]:
            raise ToolError(f"Esta herramienta acepta como máximo {tool['max_files']} archivos.")
        if not tool["multiple"] and len(inputs) > 1:
            inputs = inputs[:1]
        with OPS_LOCK:
            res = tool["op"](inputs, opts, d / "out")
        payload = _package(jid, d, res, tool["key"])
        payload["seconds"] = round(time.time() - t0, 1)
        log.info("✔ %s en %.1fs", tool["name"], time.time() - t0)
        return jsonify(payload)
    except ToolError as e:
        shutil.rmtree(d, ignore_errors=True)
        return jsonify(ok=False, error=str(e)), 400
    except Exception as e:  # noqa: BLE001
        log.error("✘ %s\n%s", tool["name"], traceback.format_exc())
        shutil.rmtree(d, ignore_errors=True)
        return jsonify(ok=False, error=f"Ocurrió un error inesperado al procesar el archivo: {e}"), 500


@app.post("/api/flujo")
def workflow_api():
    jid, d = jobs.new_job()
    try:
        inputs, _ = _save_uploads(d, {"accept": ".pdf"})
        if not inputs:
            raise ToolError("Agrega al menos un PDF.")
        steps = json.loads(request.form.get("steps") or "[]")
        with OPS_LOCK:
            res = run_workflow(inputs, steps, d / "work")
        return jsonify(_package(jid, d, res, "flujo"))
    except ToolError as e:
        shutil.rmtree(d, ignore_errors=True)
        return jsonify(ok=False, error=str(e)), 400
    except Exception as e:  # noqa: BLE001
        log.error("✘ flujo\n%s", traceback.format_exc())
        shutil.rmtree(d, ignore_errors=True)
        return jsonify(ok=False, error=f"Ocurrió un error inesperado: {e}"), 500


@app.post("/api/formularios/campos")
def form_fields_api():
    jid, d = jobs.new_job()
    try:
        inputs, _ = _save_uploads(d, {"accept": ".pdf"})
        if not inputs:
            raise ToolError("Agrega un PDF.")
        with OPS_LOCK:
            data = form_fields(inputs[0])
        return jsonify(ok=True, **data)
    except ToolError as e:
        return jsonify(ok=False, error=str(e)), 400
    finally:
        shutil.rmtree(d, ignore_errors=True)


@app.get("/descargar/<jid>/<path:name>")
def download(jid, name):
    d = jobs.job_dir(jid)
    if not d:
        abort(404)
    out = (d / "out").resolve()
    p = (out / name).resolve()
    if out not in p.parents or not p.is_file():
        abort(404)
    inline = request.args.get("ver") == "1"
    return send_file(p, as_attachment=not inline, download_name=p.name)


@app.get("/api/ping")
def ping():
    return jsonify(app="bsobpdf", version=VERSION)


@app.get("/api/estado")
def status_api():
    return jsonify(engines.status())


@app.get("/api/ollama/modelos")
def ollama_models_api():
    models = engines.ollama_models(force=True)
    return jsonify(ok=models is not None, models=models or [], default=engines.default_ollama_model())


# ------------------------------------------------------------------ Escaneo desde el celular
SCANS: dict[str, dict] = {}


@app.post("/api/escaneo/nueva")
def scan_new():
    import qrcode
    import qrcode.image.svg

    sid = uuid.uuid4().hex[:10]
    jid, d = jobs.new_job()
    SCANS[sid] = {"dir": d / "out", "files": [], "t": time.time()}
    host = request.host.split(":")[0]
    if host in ("127.0.0.1", "localhost", "::1"):
        host = lan_ip()
    url = f"http://{host}:{PORT}/escanear-a-pdf?sesion={sid}"
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    svg = img.to_string(encoding="unicode")
    return jsonify(ok=True, sid=sid, url=url, qr=svg, local=host.startswith("127."))


@app.post("/api/escaneo/<sid>")
def scan_upload(sid):
    s = SCANS.get(sid)
    if not s:
        return jsonify(ok=False, error="La sesión de escaneo expiró. Vuelve a escanear el código QR."), 404
    added = 0
    for fs in request.files.getlist("files"):
        ext = Path(fs.filename or "foto.jpg").suffix.lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp"):
            continue
        name = f"foto_{len(s['files']) + 1:03d}{ext}"
        fs.save(s["dir"] / name)
        s["files"].append(name)
        added += 1
    s["t"] = time.time()
    return jsonify(ok=True, added=added, total=len(s["files"]))


@app.get("/api/escaneo/<sid>")
def scan_list(sid):
    s = SCANS.get(sid)
    if not s:
        return jsonify(ok=False, files=[]), 404
    return jsonify(ok=True, files=[{"name": n, "url": url_for("scan_file", sid=sid, name=n)} for n in s["files"]])


@app.get("/api/escaneo/<sid>/<name>")
def scan_file(sid, name):
    s = SCANS.get(sid)
    if not s or name not in s["files"]:
        abort(404)
    return send_file(s["dir"] / name)


# ================================================================== ARRANQUE
def _free_port(start: int) -> int:
    """Usa el puerto pedido o el siguiente libre (por si otro programa ya ocupa el 5000)."""
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if not engines.IS_WIN:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0" if HOST == "0.0.0.0" else HOST, port))
                return port
            except OSError:
                continue
    return start


def main():
    global PORT
    PORT = _free_port(PORT)
    url_local = f"http://127.0.0.1:{PORT}"
    lines = [f"BSOBPDF {VERSION} está funcionando", "",
             f"En este equipo:   {url_local}"]
    if HOST == "0.0.0.0":
        lines.append(f"Desde el celular: http://{lan_ip()}:{PORT}")
    lines += ["", "Para cerrarlo, cierra esta ventana."]
    w = max(len(x) for x in lines) + 4
    print("\n  ┌" + "─" * w + "┐")
    for x in lines:
        print("  │  " + x.ljust(w - 2) + "│")
    print("  └" + "─" * w + "┘\n")
    if os.environ.get("BSOBPDF_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url_local)).start()
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=8, max_request_body_size=app.config["MAX_CONTENT_LENGTH"],
              channel_timeout=900)
    except ImportError:
        app.run(host=HOST, port=PORT, threaded=True)


if __name__ == "__main__":
    main()
