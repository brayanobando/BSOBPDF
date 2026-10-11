"""Pruebas de BSOBPDF: ejecuta cada herramienta con archivos de ejemplo generados al vuelo.

    pip install pytest
    pytest -q

Las herramientas que dependen de programas externos (LibreOffice, Tesseract, internet)
se saltan automáticamente si no están disponibles.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BSOBPDF_NO_BROWSER", "1")

import pymupdf  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import app as bsob  # noqa: E402
from core import engines  # noqa: E402


# ------------------------------------------------------------------ archivos de ejemplo
@pytest.fixture(scope="session")
def fx(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("fx")
    doc = pymupdf.open()
    for i in range(4):
        p = doc.new_page()
        p.insert_text((72, 80), f"Informe de prueba - Pagina {i + 1}", fontsize=18)
        p.insert_textbox(pymupdf.Rect(72, 100, 520, 260),
                         "Texto de ejemplo con correo prueba@ejemplo.com y telefono 312 456 7890. " * 3, fontsize=11)
        for r, row in enumerate([["Ciudad", "Cantidad"], ["Mocoa", "1.250"], ["Pasto", "980"]]):
            for c, val in enumerate(row):
                rect = pymupdf.Rect(72 + c * 150, 300 + r * 24, 72 + (c + 1) * 150, 324 + r * 24)
                p.draw_rect(rect, color=(0, 0, 0), width=0.7)
                p.insert_text((rect.x0 + 6, rect.y1 - 7), val, fontsize=10)
    doc.save(d / "a.pdf")
    v2 = pymupdf.open(d / "a.pdf")
    v2[1].insert_text((72, 700), "Linea agregada en la version nueva", fontsize=12)
    v2.save(d / "b.pdf")
    pymupdf.open(d / "a.pdf").save(d / "clave.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="x")
    f = pymupdf.open()
    pg = f.new_page()
    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_name = "nombre"
    w.rect = pymupdf.Rect(100, 100, 300, 120)
    pg.add_widget(w)
    f.save(d / "form.pdf")
    im = Image.new("RGB", (800, 1100), (245, 245, 240))
    ImageDraw.Draw(im).rectangle((100, 100, 700, 1000), outline=(0, 0, 0), width=8)
    im.save(d / "foto.jpg")
    (d / "pagina.html").write_text("<h1>Hola</h1><p>Prueba de HTML a PDF.</p>", encoding="utf-8")
    return d


@pytest.fixture(scope="session")
def client():
    return bsob.app.test_client()


def run(client, fx, slug, files, opts=None, extra=None):
    data = {"options": json.dumps(opts or {}), "files": [(open(fx / f, "rb"), f) for f in files]}
    for k, f in (extra or {}).items():
        data[k] = (open(fx / f, "rb"), f)
    r = client.post(f"/api/procesar/{slug}", data=data, content_type="multipart/form-data")
    return r.get_json()


def ok(j):
    assert j["ok"], j.get("error")
    return j


# ------------------------------------------------------------------ páginas
@pytest.mark.parametrize("path", ["/", "/flujos", "/estado", "/unir-pdf", "/editar-pdf", "/escanear-a-pdf"])
def test_paginas(client, path):
    assert client.get(path).status_code == 200


def test_404(client):
    assert client.get("/no-existe").status_code == 404


# ------------------------------------------------------------------ herramientas
CASOS = [
    ("unir-pdf", ["a.pdf", "b.pdf"], {}),
    ("dividir-pdf", ["a.pdf"], {"mode": "rangos", "ranges": [{"from": 1, "to": 2}, {"from": 3, "to": 4}]}),
    ("dividir-pdf", ["a.pdf"], {"mode": "todas"}),
    ("eliminar-paginas", ["a.pdf"], {"pages": "2"}),
    ("extraer-paginas", ["a.pdf"], {"pages": "1,3"}),
    ("organizar-pdf", ["a.pdf"], {"sequence": [{"f": 0, "p": 2}, {"blank": True}, {"f": 0, "p": 0, "r": 90}]}),
    ("escanear-a-pdf", ["foto.jpg"], {"filter": "documento"}),
    ("comprimir-pdf", ["a.pdf"], {"level": "extrema"}),
    ("reparar-pdf", ["a.pdf"], {}),
    ("jpg-a-pdf", ["foto.jpg"], {"page_size": "a4"}),
    ("html-a-pdf", ["pagina.html"], {}),
    ("pdf-a-jpg", ["a.pdf"], {"mode": "paginas", "pages": "1"}),
    ("pdf-a-word", ["a.pdf"], {}),
    ("pdf-a-powerpoint", ["a.pdf"], {}),
    ("pdf-a-excel", ["a.pdf"], {}),
    ("pdf-a-pdfa", ["a.pdf"], {}),
    ("rotar-pdf", ["a.pdf"], {"rotations": [[90, 0, 180, 0]]}),
    ("numerar-paginas", ["a.pdf"], {"format": "pagina_n_de_total"}),
    ("marca-de-agua", ["a.pdf"], {"text": "BORRADOR", "mosaic": True}),
    ("recortar-pdf", ["a.pdf"], {"auto": True}),
    ("editar-pdf", ["a.pdf"], {"objects": [{"page": 0, "type": "text", "x": 80, "y": 600, "w": 200, "h": 20, "text": "Hola", "size": 12}]}),
    ("formularios-pdf", ["form.pdf"], {"new_fields": [{"page": 0, "type": "checkbox", "x": 100, "y": 150, "w": 14, "h": 14}]}),
    ("desbloquear-pdf", ["clave.pdf"], {"password": "1234"}),
    ("proteger-pdf", ["a.pdf"], {"password": "secreta", "password2": "secreta"}),
    ("censurar-pdf", ["a.pdf"], {"patterns": "email,telefono"}),
    ("comparar-pdf", ["a.pdf", "b.pdf"], {}),
    ("resumir-pdf", ["a.pdf"], {"engine": "extractivo"}),
    ("pdf-a-markdown", ["a.pdf"], {}),
]


@pytest.mark.parametrize("slug,files,opts", CASOS, ids=[c[0] + "-" + str(i) for i, c in enumerate(CASOS)])
def test_herramienta(client, fx, slug, files, opts):
    j = ok(run(client, fx, slug, files, opts))
    data = client.get(j["download"]["url"]).data
    assert len(data) > 0


def test_firmar_con_imagen(client, fx):
    png = io.BytesIO()
    Image.new("RGBA", (300, 100), (0, 0, 120, 255)).save(png, "PNG")
    data = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    ok(run(client, fx, "firmar-pdf", ["a.pdf"], {"objects": [{"page": 0, "type": "image", "x": 300, "y": 650, "w": 150, "h": 50, "data": data}]}))


def test_marca_de_agua_imagen(client, fx):
    ok(run(client, fx, "marca-de-agua", ["a.pdf"], {"type": "imagen"}, extra={"watermark_image": "foto.jpg"}))


def test_contrasena_incorrecta(client, fx):
    j = run(client, fx, "desbloquear-pdf", ["clave.pdf"], {"password": "mala"})
    assert not j["ok"] and "contraseña" in j["error"]


def test_formato_no_admitido(client, fx):
    j = run(client, fx, "unir-pdf", ["foto.jpg", "a.pdf"])
    assert not j["ok"]


def test_campos_de_formulario(client, fx):
    r = client.post("/api/formularios/campos", data={"files": [(open(fx / "form.pdf", "rb"), "form.pdf")]},
                    content_type="multipart/form-data").get_json()
    assert r["ok"] and r["fields"][0]["name"] == "nombre"


def test_flujo(client, fx):
    steps = [{"tool": "unir-pdf", "options": {}}, {"tool": "numerar-paginas", "options": {}},
             {"tool": "comprimir-pdf", "options": {}}, {"tool": "proteger-pdf", "options": {"password": "abcd", "password2": "abcd"}}]
    r = client.post("/api/flujo", data={"steps": json.dumps(steps), "files": [(open(fx / "a.pdf", "rb"), "a.pdf"), (open(fx / "b.pdf", "rb"), "b.pdf")]},
                    content_type="multipart/form-data").get_json()
    assert r["ok"], r.get("error")
    assert len(r["data"]["log"]) == 4


@pytest.mark.skipif(not (engines.soffice_path() or engines.ms_office_available()), reason="Sin LibreOffice ni Microsoft Office")
def test_office_a_pdf(client, fx, tmp_path):
    from docx import Document
    d = Document()
    d.add_paragraph("Documento de prueba")
    d.save(fx / "carta.docx")
    ok(run(client, fx, "word-a-pdf", ["carta.docx"]))


@pytest.mark.skipif(not engines.ocr_languages(), reason="Sin Tesseract")
def test_ocr(client, fx):
    src = pymupdf.open(fx / "a.pdf")
    pix = src[0].get_pixmap(dpi=150)
    s = pymupdf.open()
    pg = s.new_page(width=src[0].rect.width, height=src[0].rect.height)
    pg.insert_image(pg.rect, pixmap=pix)
    s.save(fx / "escaneado.pdf")
    j = ok(run(client, fx, "ocr-pdf", ["escaneado.pdf"], {"language": "eng"}))
    out = pymupdf.open("pdf", client.get(j["download"]["url"]).data)
    assert "Informe" in out[0].get_text()
