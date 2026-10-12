"""BSOBPDF como programa de escritorio.

Arranca el servidor en segundo plano y abre BSOBPDF en una ventana propia (Microsoft Edge o
Chrome en modo aplicación, sin barra de direcciones). Al cerrar la ventana, el programa termina.
Es el punto de entrada del instalador para Windows (ver empaquetado/).

    python escritorio.py              abre el programa
    python escritorio.py --prueba     prueba automática sin ventanas (la usa la compilación)
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

NOMBRE = "BSOBPDF"
DATOS = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / NOMBRE
REGISTRO = DATOS / "bsobpdf.log"
PUERTO_ARCHIVO = DATOS / "puerto.txt"


def preparar_registro() -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    try:
        if REGISTRO.exists() and REGISTRO.stat().st_size > 2_000_000:
            REGISTRO.unlink()
    except OSError:
        pass
    logging.basicConfig(filename=str(REGISTRO), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s  %(levelname)s  %(message)s")


def responde(puerto: int) -> bool:
    """¿Hay un BSOBPDF escuchando en ese puerto?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/ping", timeout=0.8) as r:
            return b"bsobpdf" in r.read()
    except Exception:
        return False


def instancia_abierta() -> int | None:
    try:
        puerto = int(PUERTO_ARCHIVO.read_text().strip())
    except Exception:
        return None
    return puerto if responde(puerto) else None


def abrir_ventana(url: str) -> subprocess.Popen | None:
    """Abre BSOBPDF en una ventana de navegador en modo aplicación."""
    from core import engines

    exe = engines.browser_path()
    if not exe:
        return None
    perfil = DATOS / "ventana"
    args = [exe, f"--app={url}", f"--user-data-dir={perfil}", "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate,msEdgeSidebarV2", "--window-size=1320,880", "--lang=es"]
    try:
        return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        logging.exception("No se pudo abrir la ventana")
        return None


def ventana_alternativa(url: str) -> None:
    """Si no hay Edge ni Chrome: abre el navegador predeterminado y muestra una ventanita para cerrar."""
    webbrowser.open(url)
    try:
        import tkinter as tk

        raiz = tk.Tk()
        raiz.title(NOMBRE)
        raiz.geometry("380x150")
        raiz.resizable(False, False)
        tk.Label(raiz, text="BSOBPDF está abierto en tu navegador.", font=("Segoe UI", 11)).pack(pady=(22, 4))
        tk.Label(raiz, text=url, fg="#0b6b55").pack()
        fila = tk.Frame(raiz)
        fila.pack(pady=16)
        tk.Button(fila, text="Abrir de nuevo", command=lambda: webbrowser.open(url)).pack(side="left", padx=6)
        tk.Button(fila, text="Cerrar BSOBPDF", command=raiz.destroy).pack(side="left", padx=6)
        raiz.mainloop()
    except Exception:
        # Sin interfaz gráfica: seguimos funcionando hasta que cierren el proceso
        while True:
            time.sleep(3600)


def mostrar_error(texto: str) -> None:
    logging.error(texto)
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(NOMBRE, texto)
        raiz.destroy()
    except Exception:
        print(texto, file=sys.stderr)


def iniciar_servidor(bsob, puerto: int):
    from waitress import create_server

    servidor = create_server(bsob.app, host=bsob.HOST, port=puerto, threads=8,
                             max_request_body_size=bsob.app.config["MAX_CONTENT_LENGTH"], channel_timeout=900)
    threading.Thread(target=servidor.run, name="servidor", daemon=True).start()
    return servidor


def main() -> int:
    multiprocessing.freeze_support()
    preparar_registro()
    args = sys.argv[1:]
    if args and args[0].startswith("--prueba"):
        destino = args[0].split("=", 1)[1] if "=" in args[0] else str(DATOS / "prueba.txt")
        return prueba(Path(destino))

    abierta = instancia_abierta()
    if abierta:
        # Ya está funcionando: solo abrimos otra ventana
        url = f"http://127.0.0.1:{abierta}"
        if not abrir_ventana(url):
            webbrowser.open(url)
        return 0

    try:
        os.environ.setdefault("BSOBPDF_NO_BROWSER", "1")
        import app as bsob

        puerto = bsob._free_port(int(os.environ.get("BSOBPDF_PORT", "5000")))
        bsob.PORT = puerto
        servidor = iniciar_servidor(bsob, puerto)
    except Exception:
        mostrar_error("BSOBPDF no pudo iniciar.\n\n" + traceback.format_exc(limit=3) + f"\nRegistro: {REGISTRO}")
        return 1

    url = f"http://127.0.0.1:{puerto}"
    for _ in range(100):
        if responde(puerto):
            break
        time.sleep(0.2)
    PUERTO_ARCHIVO.write_text(str(puerto))
    logging.info("BSOBPDF funcionando en %s", url)

    inicio = time.time()
    proceso = abrir_ventana(url)
    if proceso is not None:
        proceso.wait()
        if time.time() - inicio < 4:
            # El navegador entregó la ventana a otro proceso y salió enseguida
            ventana_alternativa(url)
    else:
        ventana_alternativa(url)

    servidor.close()
    try:
        PUERTO_ARCHIVO.unlink()
    except OSError:
        pass
    logging.info("BSOBPDF cerrado")
    return 0


# ---------------------------------------------------------------------------- prueba automática
def prueba(destino: Path) -> int:
    """Ejecuta varias herramientas con archivos generados al vuelo y escribe el resultado en `destino`."""
    lineas: list[str] = []
    errores = 0

    def anotar(ok: bool, texto: str) -> None:
        nonlocal errores
        if not ok:
            errores += 1
        lineas.append(("OK    " if ok else "FALLO ") + texto)

    try:
        import io
        import json

        import pymupdf
        from PIL import Image, ImageDraw

        os.environ.setdefault("BSOBPDF_NO_BROWSER", "1")
        import app as bsob

        anotar(True, f"Python {sys.version.split()[0]}, PyMuPDF {pymupdf.VersionBind}, base {bsob.BASE}")
        cliente = bsob.app.test_client()

        doc = pymupdf.open()
        for i in range(3):
            p = doc.new_page()
            p.insert_text((72, 80), f"Prueba BSOBPDF - pagina {i + 1}", fontsize=18)
            p.insert_textbox(pymupdf.Rect(72, 100, 520, 220), "Texto de prueba con correo prueba@ejemplo.com. " * 4, fontsize=11)
            for r, fila in enumerate([["Ciudad", "Cantidad"], ["Mocoa", "1.250"], ["Pasto", "980"]]):
                for c, valor in enumerate(fila):
                    rect = pymupdf.Rect(72 + c * 150, 260 + r * 24, 72 + (c + 1) * 150, 284 + r * 24)
                    p.draw_rect(rect, color=(0, 0, 0), width=0.7)
                    p.insert_text((rect.x0 + 6, rect.y1 - 7), valor, fontsize=10)
        pdf = doc.tobytes()
        foto = io.BytesIO()
        im = Image.new("RGB", (800, 1100), (240, 240, 235))
        ImageDraw.Draw(im).rectangle((100, 100, 700, 1000), outline=(0, 0, 0), width=8)
        im.save(foto, "JPEG")
        html = "<h1>Hola</h1><p>Prueba de HTML a PDF.</p>".encode()

        casos = [
            ("unir-pdf", [(pdf, "a.pdf"), (pdf, "b.pdf")], {}),
            ("dividir-pdf", [(pdf, "a.pdf")], {"mode": "todas"}),
            ("comprimir-pdf", [(pdf, "a.pdf")], {}),
            ("rotar-pdf", [(pdf, "a.pdf")], {"rotations": [[90, 0, 0]]}),
            ("numerar-paginas", [(pdf, "a.pdf")], {}),
            ("marca-de-agua", [(pdf, "a.pdf")], {"text": "BORRADOR"}),
            ("proteger-pdf", [(pdf, "a.pdf")], {"password": "abcd", "password2": "abcd"}),
            ("censurar-pdf", [(pdf, "a.pdf")], {"patterns": "email"}),
            ("pdf-a-jpg", [(pdf, "a.pdf")], {"pages": "1"}),
            ("pdf-a-word", [(pdf, "a.pdf")], {}),
            ("pdf-a-powerpoint", [(pdf, "a.pdf")], {}),
            ("pdf-a-excel", [(pdf, "a.pdf")], {}),
            ("pdf-a-pdfa", [(pdf, "a.pdf")], {}),
            ("pdf-a-markdown", [(pdf, "a.pdf")], {}),
            ("resumir-pdf", [(pdf, "a.pdf")], {"engine": "extractivo"}),
            ("comparar-pdf", [(pdf, "a.pdf"), (pdf, "b.pdf")], {}),
            ("escanear-a-pdf", [(foto.getvalue(), "foto.jpg")], {}),
            ("jpg-a-pdf", [(foto.getvalue(), "foto.jpg")], {}),
            ("html-a-pdf", [(html, "pagina.html")], {}),
        ]
        for slug, archivos, opciones in casos:
            datos = {"options": json.dumps(opciones),
                     "files": [(io.BytesIO(b), nombre) for b, nombre in archivos]}
            t0 = time.time()
            r = cliente.post(f"/api/procesar/{slug}", data=datos, content_type="multipart/form-data").get_json()
            if r and r.get("ok"):
                tam = len(cliente.get(r["download"]["url"]).data)
                anotar(tam > 0, f"{slug}: {r['message']} ({tam} bytes, {time.time() - t0:.1f} s)")
            else:
                anotar(False, f"{slug}: {(r or {}).get('error')}")

        for ruta in ("/", "/estado", "/flujos", "/editar-pdf", "/static/css/styles.css",
                     "/static/vendor/pdfjs/pdf.worker.min.js", "/static/fonts/atkinson-hyperlegible-latin-400-normal.woff2"):
            codigo = cliente.get(ruta).status_code
            anotar(codigo == 200, f"GET {ruta} -> {codigo}")

        # Servidor real (Waitress) en un puerto libre
        puerto = bsob._free_port(5600)
        servidor = iniciar_servidor(bsob, puerto)
        listo = any(responde(puerto) or time.sleep(0.2) for _ in range(50))
        anotar(bool(listo), f"servidor Waitress en el puerto {puerto}")
        servidor.close()

        from core import engines
        lineas.append(f"INFO  navegador: {engines.browser_path()}")
        lineas.append(f"INFO  office: {engines.soffice_path() or engines.ms_office_available()}")
    except Exception:
        anotar(False, "excepción:\n" + traceback.format_exc())

    lineas.append(f"RESULTADO: {'TODO BIEN' if errores == 0 else f'{errores} fallo(s)'}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
