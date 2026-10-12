# Guía para desarrolladores

Esta guía explica cómo está construido BSOBPDF, cómo agregar herramientas nuevas y cómo probar los cambios. Para instalarlo y usarlo, mira el [README](../README.md).

## Índice

1. [Preparar el entorno](#preparar-el-entorno)
2. [Recorrido de una petición](#recorrido-de-una-petición)
3. [El catálogo de herramientas](#el-catálogo-de-herramientas)
4. [Opciones: tipos de campo](#opciones-tipos-de-campo)
5. [Contrato de una operación](#contrato-de-una-operación)
6. [Ejemplo: agregar una herramienta](#ejemplo-agregar-una-herramienta)
7. [La interfaz (JavaScript)](#la-interfaz-javascript)
8. [Referencia de la API](#referencia-de-la-api)
9. [Motores externos](#motores-externos)
10. [Pruebas](#pruebas)
11. [Compilar el instalador de Windows](#compilar-el-instalador-de-windows)
12. [Convenciones](#convenciones)

---

## Preparar el entorno

```bash
git clone https://github.com/brayanobando/BSOBPDF.git
cd BSOBPDF
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest
BSOBPDF_NO_BROWSER=1 python app.py  # Windows (cmd): set BSOBPDF_NO_BROWSER=1 && python app.py
```

Abre `http://127.0.0.1:5000`. Los cambios en plantillas y archivos estáticos se ven al recargar; los cambios en Python requieren reiniciar `app.py`.

Para depurar con el servidor de desarrollo de Flask (recarga automática y trazas en el navegador):

```bash
flask --app app run --debug --port 5000
```

---

## Recorrido de una petición

1. El navegador carga `/<slug>` (por ejemplo `/unir-pdf`). `app.py` busca la herramienta en `core/registry.py` y renderiza `templates/tool.html` con su definición en `window.TOOL`.
2. `static/js/tool.js` arma la interfaz según `TOOL.ui` y `static/js/options.js` dibuja el panel de opciones a partir de `TOOL.options`.
3. Al pulsar el botón principal, el navegador envía un `POST /api/procesar/<slug>` (multipart) con:
   - `files`: los archivos, en el orden elegido;
   - `options`: un JSON con los valores de las opciones (más datos de la interfaz, como `objects` del editor o `sequence` de Organizar);
   - campos de archivo adicionales (por ejemplo `watermark_image`).
4. `app.py` crea una carpeta de trabajo (`core/jobs.py`), guarda las entradas con nombres seguros, valida extensiones y cantidad, y llama a la función de la herramienta.
5. La función escribe sus resultados en `out/` y devuelve un `Result`. Si hay varios archivos, `app.py` los empaqueta en un ZIP.
6. La respuesta JSON incluye el enlace de descarga (`/descargar/<job>/<archivo>`), el mensaje para el usuario, estadísticas y datos extra (resumen, cambios, markdown).
7. Las carpetas de trabajo se borran solas después de `BSOBPDF_MAX_AGE` segundos.

PyMuPDF no es seguro entre hilos, así que `app.py` ejecuta las operaciones de a una con `OPS_LOCK`. Waitress sigue atendiendo páginas y descargas mientras tanto.

---

## El catálogo de herramientas

Cada herramienta se declara una vez en `core/registry.py` con la función `T(...)`:

```python
T("comprimir-pdf",            # slug: la dirección /comprimir-pdf
  "compress",                 # key: identificador interno
  "Comprimir PDF",            # nombre visible
  "Reduce el peso del PDF…",  # texto de la tarjeta en la portada
  "Reduce el tamaño de tus PDF para enviarlos…",  # subtítulo de la página
  "optimizar",                # categoría
  "minimize-2",               # icono (nombre de Lucide incluido en static/icons/icons.json)
  ops_optimize.compress,      # función que hace el trabajo
  workflow=True,              # ¿se puede usar en flujos de trabajo?
  action="Comprimir PDF",     # texto del botón principal
  done="Tu PDF se comprimió", # título de la pantalla final
  options=[ ... ])            # panel de opciones (ver abajo)
```

Parámetros opcionales de `T`:

| Parámetro | Por defecto | Significado |
|---|---|---|
| `accept` | `".pdf"` | Extensiones aceptadas, separadas por comas |
| `multiple` | `True` | Si acepta varios archivos |
| `min_files` / `max_files` | `1` / sin límite | Cantidad de archivos |
| `ui` | `"files"` | Interfaz: `files`, `pages`, `rotate`, `organize`, `compare`, `html`, `editor`, `scan` |
| `sortable` | `False` | Permite ordenar los archivos arrastrándolos |
| `needs` | `None` | Motor externo requerido: `"office"` u `"ocr"` (muestra un aviso si falta) |
| `output` | `"pdf"` | Tipo de resultado (informativo) |
| `badge` | `None` | Etiqueta en la tarjeta («Nuevo», «IA») |

La portada, el menú, el pie de página y la página de flujos se generan solos a partir de `TOOLS`.

---

## Opciones: tipos de campo

Cada opción es un diccionario. Campos comunes: `name`, `type`, `label`, `default`, `help`, `show_if` (por ejemplo `{"mode": ["rangos"]}` para mostrarla solo con ese valor), `required` y `workflow_only`.

| `type` | Se ve como | Valor enviado |
|---|---|---|
| `cards` | Tarjetas grandes con título y descripción (`choices` con `desc`) | `value` elegido |
| `segmented` | Botones en fila | `value` elegido |
| `select` | Lista desplegable | `value` elegido |
| `text`, `password`, `textarea` | Campo de texto | Texto |
| `number` | Número (`min`, `max`, `step`) | Número |
| `range` | Deslizador (`format: "percent"` lo muestra en %) | Número |
| `color` | Muestras de color y selector | `#rrggbb` |
| `checkbox` | Casilla | `true` / `false` |
| `multicheck` | Varias casillas | Valores separados por comas |
| `position6`, `position9` | Cuadrícula de posiciones | `tl`, `tc`, `tr`, `ml`, `mc`, `mr`, `bl`, `bc`, `br` |
| `pages` | Campo de páginas (se sincroniza con los clics en miniaturas) | Texto como `1-3, 5` |
| `ranges` | Lista de rangos con colores | `[{"from": 1, "to": 3}, …]` |
| `file` | Selector de archivo | Se envía como archivo adicional con ese `name` |
| `model` | Lista de modelos de Ollama | Nombre del modelo |
| `hidden` | No se muestra | `default` |

---

## Contrato de una operación

```python
from pathlib import Path
from core.utils import InputFile, Result, ToolError

def mi_herramienta(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    ...
```

- `inputs`: archivos subidos. `f.path` es la ruta en disco y `f.name` el nombre original (`f.stem` da un nombre base seguro para los resultados).
- `opts`: valores de las opciones. Los archivos adicionales llegan como `InputFile` con la clave del campo.
- `out`: carpeta donde debes escribir los resultados. Usa `unique_path(out, "nombre.pdf")` para no sobrescribir.
- Devuelve `Result(files=[...], message="…", stats={...}, data={...}, zip_name="….zip")`.
- Para errores que el usuario debe ver, lanza `ToolError("mensaje claro en español")`; se muestra tal cual y responde con HTTP 400. Cualquier otra excepción se registra en la consola y responde con HTTP 500.

Utilidades en `core/utils.py`:

| Función | Uso |
|---|---|
| `open_pdf(f, password=None)` | Abre un PDF con mensajes de error amigables (contraseña, archivo dañado, sin páginas) |
| `save_pdf(doc, path, **kw)` | Guarda con compresión por defecto |
| `parse_pages("1-3, 5", n)` | Convierte rangos en índices base 0 (admite `todas`, `pares`, `impares`) |
| `normalize_rotation(page)` | Deja la página con rotación 0 sin cambiar su aspecto, para trabajar en coordenadas visibles |
| `font_for(familia, negrita, cursiva)` | Nombre de fuente base-14 de PyMuPDF |
| `image_bytes_for_pdf(datos, opacidad, giro)` | Prepara una imagen para insertarla |
| `as_bool`, `as_int`, `as_float`, `hex_to_rgb` | Conversión segura de opciones |

---

## Ejemplo: agregar una herramienta

Vamos a crear «Quitar comentarios», que elimina todas las anotaciones de un PDF.

**1. La operación**, en `core/ops_edit.py`:

```python
def remove_annotations(inputs: list[InputFile], opts: dict, out: Path) -> Result:
    files, total = [], 0
    for f in inputs:
        doc = open_pdf(f)
        for page in doc:
            annot = page.first_annot
            while annot:
                annot = page.delete_annot(annot)  # devuelve la siguiente
                total += 1
        dest = unique_path(out, f"{f.stem}_sin_comentarios.pdf")
        save_pdf(doc, dest)
        files.append(dest)
    return Result(files, f"Se quitaron {total} comentario(s).", zip_name="sin_comentarios.zip")
```

**2. El registro**, en la lista `TOOLS` de `core/registry.py`:

```python
T("quitar-comentarios", "remove-annots", "Quitar comentarios",
  "Elimina notas, resaltados y comentarios de un PDF.",
  "Deja tu PDF limpio quitando todas las anotaciones.",
  "editar", "eraser", ops_edit.remove_annotations,
  workflow=True, action="Quitar comentarios", done="Comentarios eliminados"),
```

**3. Una prueba**, en `tests/test_herramientas.py`, agregando a `CASOS`:

```python
("quitar-comentarios", ["a.pdf"], {}),
```

Reinicia `app.py`: la herramienta ya aparece en la portada, el menú, el pie de página y los flujos de trabajo.

---

## La interfaz (JavaScript)

Sin frameworks ni compilación: archivos JavaScript simples cargados por las plantillas.

| Archivo | Responsabilidad |
|---|---|
| `static/js/core.js` | Utilidades (`U.el`, `U.icon`, `U.toast`, `U.modal`), envío con progreso (`U.postForm`), PDF.js (`U.PDF`), almacenamiento local seguro (`U.store`) y traspaso de archivos entre páginas con IndexedDB (`U.Handoff`) |
| `static/js/options.js` | `Options.render(contenedor, esquema, opciones)` dibuja el panel de opciones y expone `values`, `files`, `validate()` |
| `static/js/tool.js` | Controlador de la página de herramienta: etapas (subir, trabajar, procesar, resultado) e interfaces `files`, `pages`, `rotate`, `organize`, `compare` y `html` |
| `static/js/editor.js` | Editor visual para `editar`, `firmar`, `censurar`, `recortar` y `formularios` |
| `static/js/scan.js` | Cámara del PC, sesión con el celular por QR y modo celular |
| `static/js/workflows.js` | Constructor de flujos (guardados en `localStorage`) |
| `static/js/index.js` | Filtros de la portada y «suelta un archivo» |

**Coordenadas del editor.** Todos los objetos se guardan en **puntos PDF** (1/72 de pulgada) relativos a la página tal como se ve, con origen arriba a la izquierda. En el servidor, `normalize_rotation()` quita la rotación de la página antes de dibujar, así coinciden aunque la página tenga `/Rotate`. Un objeto del editor se ve así:

```json
{"page": 0, "type": "text", "x": 72, "y": 600, "w": 180, "h": 17,
 "text": "Hola", "size": 14, "font": "helv", "color": "#1d232b", "bold": false}
```

Tipos: `text`, `image` (con `data` en base64), `rect`, `ellipse`, `line`, `arrow`, `draw` (con `points`), `highlight` y `whiteout`.

**Traspaso de archivos.** La portada («suelta un archivo») y «Continuar con» guardan los archivos en IndexedDB y abren `/<slug>?h=<id>`; la página destino los recupera y los carga.

---

## Referencia de la API

| Método y ruta | Entrada | Respuesta |
|---|---|---|
| `GET /` , `/<slug>`, `/flujos`, `/estado` | | Páginas HTML |
| `POST /api/procesar/<slug>` | multipart: `files[]`, `options` (JSON), archivos extra | `{ok, job, download, files, message, stats, data, seconds}` |
| `POST /api/flujo` | multipart: `files[]`, `steps` (JSON: `[{tool, options}]`) | Igual que procesar, con `data.log` |
| `POST /api/formularios/campos` | multipart: `files` (un PDF) | `{ok, fields: [{xref, page, name, type, value, x, y, w, h, options}], pages}` |
| `GET /descargar/<job>/<archivo>` | `?ver=1` para abrir en el navegador | El archivo |
| `GET /api/estado` | | Estado de motores externos |
| `GET /api/ollama/modelos` | | `{ok, models, default}` |
| `POST /api/escaneo/nueva` | | `{sid, url, qr}` (QR en SVG) |
| `POST /api/escaneo/<sid>` | multipart: `files[]` (fotos) | `{ok, added, total}` |
| `GET /api/escaneo/<sid>` | | `{files: [{name, url}]}` |

En caso de error: `{"ok": false, "error": "mensaje"}` con HTTP 400 (error del usuario), 404, 413 (demasiado grande) o 500.

Ejemplo con `curl`:

```bash
curl -F "files=@a.pdf" -F "files=@b.pdf" -F 'options={"bookmarks": true}' \
     http://127.0.0.1:5000/api/procesar/unir-pdf
```

---

## Motores externos

`core/engines.py` detecta cada programa buscando en el `PATH`, en las carpetas de instalación habituales de Windows (`Program Files`) y en variables de entorno (`BSOBPDF_SOFFICE`, `BSOBPDF_TESSDATA`, `BSOBPDF_BROWSER`). La página `/estado` muestra el resultado.

| Motor | Uso | Orden de preferencia |
|---|---|---|
| Office a PDF | Word, PowerPoint, Excel | Microsoft Office (COM, solo Windows), luego LibreOffice (`BSOBPDF_OFFICE_ENGINE=lo` invierte el orden) |
| Tesseract | OCR con la integración de PyMuPDF | Necesita la carpeta `tessdata` con los idiomas |
| Ghostscript | PDF/A estricto | Si no está, PDF/A básico con XMP y perfil sRGB |
| HTML a PDF | Playwright con Edge o Chrome instalados, luego el navegador por línea de comandos, luego `pymupdf.Story` | |
| Ollama | Resumir y traducir | `BSOBPDF_OLLAMA_URL`, `BSOBPDF_OLLAMA_MODEL` |

---

## Pruebas

```bash
pip install pytest
pytest -q
```

`tests/test_herramientas.py` genera PDF, imágenes y formularios de ejemplo al vuelo y ejecuta cada herramienta a través de la API. Las pruebas de Office y OCR se saltan solas si falta el programa.

Para probar la interfaz a mano, carga PDF reales con páginas giradas, formularios, contraseñas y escaneos: son los casos que más diferencias producen.

---

## Compilar el instalador de Windows

El programa de escritorio tiene tres piezas:

| Archivo | Qué hace |
|---|---|
| `escritorio.py` | Punto de entrada del `.exe`. Arranca Waitress en segundo plano, abre BSOBPDF en una ventana de Edge o Chrome en modo aplicación (`--app`, con su propio perfil en `%LOCALAPPDATA%\BSOBPDF\ventana`) y termina cuando se cierra la ventana. Si ya hay una instancia abierta, solo abre otra ventana. Escribe su registro en `%LOCALAPPDATA%\BSOBPDF\bsobpdf.log`. |
| `empaquetado/BSOBPDF.spec` | Receta de PyInstaller: incluye `templates/`, `static/` y los datos de PyMuPDF, PyMuPDF4LLM, pdf2docx, python-docx, python-pptx y onnxruntime. Excluye Playwright (en el programa instalado, HTML a PDF usa Edge directamente). |
| `empaquetado/BSOBPDF.iss` | Instalador de Inno Setup en español: instalación por usuario sin permisos de administrador, accesos directos, licencia y desinstalador. |

**Compilación automática.** El flujo `.github/workflows/instalador-windows.yml` se ejecuta en Windows cada vez que cambia el código en `main`: instala las dependencias, compila con PyInstaller, ejecuta `BSOBPDF.exe --prueba` (19 herramientas y las páginas principales), crea el instalador, lo instala en silencio, prueba el programa instalado y lo desinstala. El instalador queda como artefacto en la pestaña **Actions**. Cuando publicas una versión en **Releases** (por ejemplo `v1.1.0`), el mismo flujo adjunta `BSOBPDF-Setup-1.1.0.exe` a esa versión.

**Compilación manual en tu PC con Windows:**

```powershell
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean empaquetado/BSOBPDF.spec      # crea dist\BSOBPDF\BSOBPDF.exe
dist\BSOBPDF\BSOBPDF.exe --prueba=prueba.txt; type prueba.txt  # prueba rápida
# Instala Inno Setup 6 (https://jrsoftware.org/isinfo.php) y luego:
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 empaquetado\BSOBPDF.iss
# Resultado: dist\BSOBPDF-Setup-1.0.0.exe
```

Para publicar una versión nueva: cambia `VERSION` en `app.py` (y `empaquetado/version_info.txt`), sube los cambios y crea la versión en Releases con la etiqueta `vX.Y.Z`.

---

## Convenciones

- **Textos en español** neutro, en minúscula inicial salvo nombres propios, con verbos claros («Unir PDF», «Descargar»). El botón y el mensaje final usan el mismo verbo.
- **Errores** con `ToolError`: dicen qué pasó y cómo resolverlo, sin disculpas.
- **Nombres de salida**: `<nombre original>_<acción>.pdf` (por ejemplo `informe_comprimido.pdf`).
- **Nunca** modificar el archivo de entrada; escribir siempre en `out/`.
- **Sin dependencias de internet** en la interfaz: fuentes, iconos y PDF.js van incluidos.
- Antes de un pull request, ejecuta `pytest -q`.
