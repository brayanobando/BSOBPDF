"""Catálogo de herramientas de BSOBPDF: textos, categorías, archivos aceptados, opciones y operación."""
from __future__ import annotations

from . import ops_ai, ops_convert, ops_edit, ops_optimize, ops_organize, ops_security

PDF = ".pdf"
IMAGES = ".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.gif"
WORD = ".doc,.docx,.odt,.rtf,.txt"
PPT = ".ppt,.pptx,.pps,.ppsx,.odp"
EXCEL = ".xls,.xlsx,.xlsm,.ods,.csv"

CATEGORIES = [
    {"id": "organizar", "name": "Organizar", "color": "#D9603B"},
    {"id": "optimizar", "name": "Optimizar", "color": "#1F9D74"},
    {"id": "convertir", "name": "Convertir", "color": "#2F6FDB"},
    {"id": "editar", "name": "Editar", "color": "#8A4FD8"},
    {"id": "seguridad", "name": "Seguridad", "color": "#28384F"},
    {"id": "inteligencia", "name": "Inteligencia", "color": "#C2368A"},
]

PAGES_HELP = "Ejemplo: 1-3, 5, 8-10. También «impares», «pares» o «todas»."

LANG_CHOICES = [
    {"value": "es", "label": "Español"}, {"value": "en", "label": "Inglés"},
    {"value": "pt", "label": "Portugués"}, {"value": "fr", "label": "Francés"},
    {"value": "it", "label": "Italiano"}, {"value": "de", "label": "Alemán"},
    {"value": "zh-CN", "label": "Chino"}, {"value": "ja", "label": "Japonés"},
    {"value": "ko", "label": "Coreano"}, {"value": "ru", "label": "Ruso"},
    {"value": "ar", "label": "Árabe"}, {"value": "nl", "label": "Neerlandés"},
    {"value": "ca", "label": "Catalán"},
]

POS6 = [{"value": v, "label": l} for v, l in (("tl", "Arriba izquierda"), ("tc", "Arriba centro"), ("tr", "Arriba derecha"),
                                               ("bl", "Abajo izquierda"), ("bc", "Abajo centro"), ("br", "Abajo derecha"))]


def T(slug, key, name, card, subtitle, category, icon, op, *, accept=PDF, multiple=True, min_files=1,
      max_files=None, ui="files", action=None, options=None, workflow=False, sortable=False, needs=None,
      done=None, output="pdf", badge=None):
    return dict(slug=slug, key=key, name=name, card=card, subtitle=subtitle, category=category, icon=icon,
                op=op, accept=accept, multiple=multiple, min_files=min_files, max_files=max_files, ui=ui,
                action=action or name, options=options or [], workflow=workflow, sortable=sortable,
                needs=needs, done=done or "Listo", output=output, badge=badge)


TOOLS = [
    # ================================================================ ORGANIZAR
    T("unir-pdf", "merge", "Unir PDF", "Combina varios PDF en uno, en el orden que elijas.",
      "Junta varios PDF en un solo documento. Arrástralos para cambiar el orden.",
      "organizar", "combine", ops_organize.merge, min_files=2, sortable=True, workflow=True,
      action="Unir PDF", done="Tus PDF se unieron",
      options=[{"name": "bookmarks", "type": "checkbox", "label": "Crear un marcador por cada archivo", "default": True}]),
    T("dividir-pdf", "split", "Dividir PDF", "Separa un PDF por rangos o página por página.",
      "Separa un PDF en varios archivos: por rangos, cada cierto número de páginas o página por página.",
      "organizar", "scissors", ops_organize.split, multiple=False, ui="pages", action="Dividir PDF",
      done="Tu PDF se dividió", options=[
          {"name": "mode", "type": "cards", "label": "Modo", "default": "rangos", "choices": [
              {"value": "rangos", "label": "Rangos personalizados", "desc": "Tú decides dónde empieza y termina cada parte"},
              {"value": "fijo", "label": "Cada N páginas", "desc": "Partes del mismo tamaño"},
              {"value": "todas", "label": "Todas las páginas", "desc": "Un PDF por cada página"},
              {"value": "seleccion", "label": "Elegir páginas", "desc": "Haz clic en las páginas que quieres separar"}]},
          {"name": "ranges", "type": "ranges", "label": "Rangos", "show_if": {"mode": ["rangos"]}},
          {"name": "merge_ranges", "type": "checkbox", "label": "Unir todos los rangos en un solo PDF", "show_if": {"mode": ["rangos"]}},
          {"name": "every", "type": "number", "label": "Páginas por archivo", "default": 2, "min": 1, "show_if": {"mode": ["fijo"]}},
          {"name": "pages", "type": "pages", "label": "Páginas seleccionadas", "help": PAGES_HELP, "show_if": {"mode": ["seleccion"]}},
          {"name": "merge_selected", "type": "checkbox", "label": "Unir las páginas elegidas en un solo PDF", "show_if": {"mode": ["seleccion"]}},
      ]),
    T("eliminar-paginas", "remove-pages", "Eliminar páginas", "Quita las páginas que sobran de un PDF.",
      "Haz clic en las páginas que quieres quitar y descarga el PDF sin ellas.",
      "organizar", "file-minus", ops_organize.remove_pages, multiple=False, ui="pages", workflow=True,
      action="Eliminar páginas", done="Se eliminaron las páginas",
      options=[{"name": "pages", "type": "pages", "label": "Páginas a eliminar", "help": PAGES_HELP}]),
    T("extraer-paginas", "extract-pages", "Extraer páginas", "Saca las páginas que necesitas a un PDF nuevo.",
      "Elige páginas y guárdalas como un PDF nuevo, o como un PDF por página.",
      "organizar", "file-output", ops_organize.extract_pages, multiple=False, ui="pages", workflow=True,
      action="Extraer páginas", done="Páginas extraídas",
      options=[{"name": "pages", "type": "pages", "label": "Páginas a extraer", "help": PAGES_HELP},
               {"name": "separate", "type": "checkbox", "label": "Un PDF por cada página"}]),
    T("organizar-pdf", "organize", "Organizar PDF", "Reordena, gira, borra o agrega páginas.",
      "Arrastra las páginas para ordenarlas, gíralas, bórralas o inserta páginas en blanco. Puedes mezclar varios PDF.",
      "organizar", "layout-grid", ops_organize.organize, ui="organize", action="Guardar cambios",
      done="Tu PDF quedó organizado"),
    T("escanear-a-pdf", "scan", "Escanear a PDF", "Usa la cámara del celular o del PC para escanear documentos.",
      "Toma fotos de tus documentos con la cámara del computador o con tu celular y conviértelas en un PDF limpio.",
      "organizar", "scan-line", ops_organize.scan_to_pdf, accept=IMAGES, ui="scan", action="Crear PDF",
      done="Tu escaneo está listo", options=[
          {"name": "filter", "type": "segmented", "label": "Acabado", "default": "mejorado", "choices": [
              {"value": "original", "label": "Original"}, {"value": "mejorado", "label": "Color"},
              {"value": "gris", "label": "Gris"}, {"value": "documento", "label": "B/N"}]},
          {"name": "autocrop", "type": "checkbox", "label": "Detectar la hoja y enderezarla", "default": True},
          {"name": "page_size", "type": "segmented", "label": "Tamaño de página", "default": "a4", "choices": [
              {"value": "a4", "label": "A4"}, {"value": "carta", "label": "Carta"}, {"value": "ajustar", "label": "Ajustar"}]},
          {"name": "margin", "type": "hidden", "default": "pequeno"},
      ]),

    # ================================================================ OPTIMIZAR
    T("comprimir-pdf", "compress", "Comprimir PDF", "Reduce el peso del PDF manteniendo la mejor calidad posible.",
      "Reduce el tamaño de tus PDF para enviarlos por correo o subirlos a plataformas con límite de peso.",
      "optimizar", "minimize-2", ops_optimize.compress, workflow=True, action="Comprimir PDF",
      done="Tu PDF se comprimió", options=[
          {"name": "level", "type": "cards", "label": "Nivel de compresión", "default": "recomendada", "choices": [
              {"value": "extrema", "label": "Extrema", "desc": "Menor peso, menor calidad"},
              {"value": "recomendada", "label": "Recomendada", "desc": "Buena calidad, buen ahorro"},
              {"value": "baja", "label": "Baja", "desc": "Alta calidad, menos ahorro"}]},
          {"name": "grayscale", "type": "checkbox", "label": "Convertir imágenes a escala de grises"},
      ]),
    T("reparar-pdf", "repair", "Reparar PDF", "Recupera datos de PDF dañados o que no abren bien.",
      "Reconstruye PDF dañados o corruptos y recupera todas las páginas que se puedan leer.",
      "optimizar", "wrench", ops_optimize.repair, workflow=True, action="Reparar PDF", done="PDF reparado"),
    T("ocr-pdf", "ocr", "OCR PDF", "Convierte escaneos en PDF con texto que se puede buscar y copiar.",
      "Reconoce el texto de documentos escaneados para que puedas buscarlo, seleccionarlo y copiarlo.",
      "optimizar", "scan-text", ops_optimize.ocr, workflow=True, action="Aplicar OCR", needs="ocr",
      done="OCR completado", options=[
          {"name": "language", "type": "select", "label": "Idioma del documento", "default": "spa+eng", "choices": [
              {"value": "spa+eng", "label": "Español + inglés"}, {"value": "spa", "label": "Español"},
              {"value": "eng", "label": "Inglés"}, {"value": "por", "label": "Portugués"},
              {"value": "fra", "label": "Francés"}]},
          {"name": "dpi", "type": "segmented", "label": "Precisión", "default": "300", "choices": [
              {"value": "200", "label": "Rápida"}, {"value": "300", "label": "Normal"}, {"value": "400", "label": "Alta"}]},
          {"name": "skip_text", "type": "checkbox", "label": "Saltar páginas que ya tienen texto", "default": True},
      ]),

    # ================================================================ CONVERTIR A PDF
    T("jpg-a-pdf", "jpg-to-pdf", "JPG a PDF", "Convierte imágenes JPG, PNG y más en PDF.",
      "Convierte tus imágenes en PDF. Ajusta la orientación, el tamaño de página y los márgenes.",
      "convertir", "image", ops_convert.images_to_pdf, accept=IMAGES, sortable=True, action="Convertir a PDF",
      done="Tus imágenes ahora son PDF", options=[
          {"name": "orientation", "type": "segmented", "label": "Orientación", "default": "auto", "choices": [
              {"value": "auto", "label": "Auto"}, {"value": "vertical", "label": "Vertical"}, {"value": "horizontal", "label": "Horizontal"}]},
          {"name": "page_size", "type": "segmented", "label": "Tamaño de página", "default": "ajustar", "choices": [
              {"value": "ajustar", "label": "Ajustar a la imagen"}, {"value": "a4", "label": "A4"}, {"value": "carta", "label": "Carta"}]},
          {"name": "margin", "type": "segmented", "label": "Margen", "default": "ninguno", "choices": [
              {"value": "ninguno", "label": "Sin margen"}, {"value": "pequeno", "label": "Pequeño"}, {"value": "grande", "label": "Grande"}]},
          {"name": "merge", "type": "checkbox", "label": "Unir todas las imágenes en un solo PDF", "default": True},
      ]),
    T("word-a-pdf", "word-to-pdf", "Word a PDF", "Convierte documentos DOC y DOCX a PDF.",
      "Convierte documentos de Word (DOC, DOCX, ODT, RTF) a PDF conservando el formato.",
      "convertir", "file-text", ops_convert.word_to_pdf, accept=WORD, needs="office", action="Convertir a PDF",
      done="Tu documento ahora es PDF",
      options=[{"name": "merge", "type": "checkbox", "label": "Unir todos en un solo PDF"}]),
    T("powerpoint-a-pdf", "ppt-to-pdf", "PowerPoint a PDF", "Convierte presentaciones PPT y PPTX a PDF.",
      "Convierte tus presentaciones (PPT, PPTX, ODP) a PDF, una diapositiva por página.",
      "convertir", "presentation", ops_convert.ppt_to_pdf, accept=PPT, needs="office", action="Convertir a PDF",
      done="Tu presentación ahora es PDF",
      options=[{"name": "merge", "type": "checkbox", "label": "Unir todas en un solo PDF"}]),
    T("excel-a-pdf", "excel-to-pdf", "Excel a PDF", "Convierte hojas de cálculo a PDF.",
      "Convierte libros de Excel (XLS, XLSX, ODS, CSV) a PDF.",
      "convertir", "sheet", ops_convert.excel_to_pdf, accept=EXCEL, needs="office", action="Convertir a PDF",
      done="Tu hoja de cálculo ahora es PDF",
      options=[{"name": "merge", "type": "checkbox", "label": "Unir todas en un solo PDF"}]),
    T("html-a-pdf", "html-to-pdf", "HTML a PDF", "Convierte una página web en PDF con solo pegar su dirección.",
      "Pega la dirección de una página web (o sube un archivo HTML) y guárdala como PDF.",
      "convertir", "globe", ops_convert.html_to_pdf, accept=".html,.htm", multiple=False, min_files=0,
      ui="html", action="Convertir a PDF", done="La página web ahora es PDF", options=[
          {"name": "page_size", "type": "segmented", "label": "Tamaño de página", "default": "a4", "choices": [
              {"value": "a4", "label": "A4"}, {"value": "carta", "label": "Carta"}, {"value": "oficio", "label": "Oficio"}]},
          {"name": "orientation", "type": "segmented", "label": "Orientación", "default": "vertical", "choices": [
              {"value": "vertical", "label": "Vertical"}, {"value": "horizontal", "label": "Horizontal"}]},
          {"name": "margin", "type": "segmented", "label": "Margen", "default": "pequeno", "choices": [
              {"value": "ninguno", "label": "Sin margen"}, {"value": "pequeno", "label": "Pequeño"}, {"value": "grande", "label": "Grande"}]},
          {"name": "viewport", "type": "segmented", "label": "Ancho de pantalla", "default": "1280", "choices": [
              {"value": "390", "label": "Celular"}, {"value": "1024", "label": "Tableta"}, {"value": "1280", "label": "Escritorio"}]},
          {"name": "one_page", "type": "checkbox", "label": "Toda la página web en una sola hoja larga"},
      ]),

    # ================================================================ CONVERTIR DESDE PDF
    T("pdf-a-jpg", "pdf-to-jpg", "PDF a JPG", "Convierte cada página en imagen o extrae las imágenes del PDF.",
      "Convierte cada página del PDF en una imagen JPG o PNG, o extrae todas las imágenes que contiene.",
      "convertir", "file-image", ops_convert.pdf_to_images, action="Convertir a imágenes",
      done="Tus imágenes están listas", output="images", options=[
          {"name": "mode", "type": "cards", "label": "Qué quieres obtener", "default": "paginas", "choices": [
              {"value": "paginas", "label": "Página a imagen", "desc": "Cada página se convierte en una imagen"},
              {"value": "imagenes", "label": "Extraer imágenes", "desc": "Saca las fotos incrustadas en el PDF"}]},
          {"name": "format", "type": "segmented", "label": "Formato", "default": "jpg", "choices": [
              {"value": "jpg", "label": "JPG"}, {"value": "png", "label": "PNG"}]},
          {"name": "dpi", "type": "segmented", "label": "Calidad", "default": "150", "show_if": {"mode": ["paginas"]}, "choices": [
              {"value": "96", "label": "Baja"}, {"value": "150", "label": "Normal"}, {"value": "300", "label": "Alta"}]},
          {"name": "pages", "type": "pages", "label": "Páginas", "help": "Déjalo vacío para convertir todas.", "show_if": {"mode": ["paginas"]}},
      ]),
    T("pdf-a-word", "pdf-to-word", "PDF a Word", "Convierte PDF en documentos de Word editables.",
      "Convierte tus PDF en documentos DOCX editables, conservando textos, tablas e imágenes.",
      "convertir", "file-type", ops_convert.pdf_to_word, action="Convertir a Word", done="Tu PDF ahora es Word",
      output="docx"),
    T("pdf-a-powerpoint", "pdf-to-ppt", "PDF a PowerPoint", "Convierte PDF en presentaciones PPTX editables.",
      "Convierte cada página en una diapositiva de PowerPoint con el texto editable.",
      "convertir", "presentation", ops_convert.pdf_to_ppt, action="Convertir a PowerPoint",
      done="Tu PDF ahora es PowerPoint", output="pptx", options=[
          {"name": "mode", "type": "cards", "label": "Tipo de conversión", "default": "editable", "choices": [
              {"value": "editable", "label": "Texto editable", "desc": "El texto queda en cuadros que puedes cambiar"},
              {"value": "imagen", "label": "Idéntico", "desc": "Cada diapositiva es una imagen exacta de la página"}]}]),
    T("pdf-a-excel", "pdf-to-excel", "PDF a Excel", "Saca las tablas de un PDF a una hoja de cálculo.",
      "Detecta las tablas de tus PDF y las pasa a Excel, con los números listos para calcular.",
      "convertir", "file-spreadsheet", ops_convert.pdf_to_excel, action="Convertir a Excel",
      done="Tu PDF ahora es Excel", output="xlsx", options=[
          {"name": "layout", "type": "cards", "label": "Organización", "default": "por_pagina", "choices": [
              {"value": "por_pagina", "label": "Una hoja por página", "desc": "Cada página del PDF en su propia hoja"},
              {"value": "por_tabla", "label": "Una hoja por tabla", "desc": "Cada tabla detectada por separado"},
              {"value": "una_hoja", "label": "Todo en una hoja", "desc": "Todas las tablas, una debajo de otra"}]},
          {"name": "tables_only", "type": "checkbox", "label": "Solo tablas (ignorar el resto del texto)"},
      ]),
    T("pdf-a-pdfa", "pdf-to-pdfa", "PDF a PDF/A", "Convierte PDF al estándar de archivo a largo plazo.",
      "Convierte tus PDF a PDF/A, el formato ISO para archivar documentos por largo tiempo (exigido en muchos trámites).",
      "convertir", "archive", ops_convert.pdf_to_pdfa, workflow=True, action="Convertir a PDF/A",
      done="Tu PDF ahora es PDF/A", options=[
          {"name": "level", "type": "segmented", "label": "Nivel de conformidad", "default": "2b", "choices": [
              {"value": "1b", "label": "PDF/A-1b"}, {"value": "2b", "label": "PDF/A-2b"}, {"value": "3b", "label": "PDF/A-3b"}]}]),

    # ================================================================ EDITAR
    T("rotar-pdf", "rotate", "Rotar PDF", "Gira páginas sueltas o documentos completos.",
      "Gira todas las páginas o solo las que elijas. Pasa el cursor sobre una página para girarla.",
      "editar", "rotate-cw", ops_edit.rotate, ui="rotate", workflow=True, action="Rotar PDF",
      done="Tu PDF quedó rotado", options=[
          {"name": "angle", "type": "segmented", "label": "Giro (en flujos de trabajo)", "default": "90", "workflow_only": True, "choices": [
              {"value": "90", "label": "90° derecha"}, {"value": "180", "label": "180°"}, {"value": "270", "label": "90° izquierda"}]},
          {"name": "pages", "type": "pages", "label": "Páginas", "workflow_only": True, "help": "Vacío = todas"}]),
    T("numerar-paginas", "page-numbers", "Números de página", "Agrega números de página con la posición y el estilo que quieras.",
      "Numera las páginas de tu PDF. Elige posición, formato, tipografía y desde qué página empezar.",
      "editar", "hash", ops_edit.page_numbers, workflow=True, action="Agregar números",
      done="Tu PDF ya tiene números de página", options=[
          {"name": "position", "type": "position6", "label": "Posición", "default": "bc", "choices": POS6},
          {"name": "mode", "type": "segmented", "label": "Modo", "default": "una", "choices": [
              {"value": "una", "label": "Una cara"}, {"value": "enfrentadas", "label": "Páginas enfrentadas"}]},
          {"name": "margin", "type": "segmented", "label": "Margen", "default": "recomendado", "choices": [
              {"value": "pequeno", "label": "Pequeño"}, {"value": "recomendado", "label": "Normal"}, {"value": "grande", "label": "Grande"}]},
          {"name": "format", "type": "select", "label": "Texto", "default": "n", "choices": [
              {"value": "n", "label": "1"}, {"value": "pagina_n", "label": "Página 1"},
              {"value": "pagina_n_de_total", "label": "Página 1 de 10"}, {"value": "n_de_total", "label": "1 / 10"},
              {"value": "custom", "label": "Personalizado…"}]},
          {"name": "custom_text", "type": "text", "label": "Texto personalizado", "default": "Folio {n}",
           "help": "Usa {n} para el número y {total} para el total.", "show_if": {"format": ["custom"]}},
          {"name": "first_number", "type": "number", "label": "Primer número", "default": 1, "min": 0},
          {"name": "pages", "type": "pages", "label": "Páginas a numerar", "help": "Vacío = todas. Ejemplo: 2- para saltar la portada."},
          {"name": "font", "type": "segmented", "label": "Fuente", "default": "helv", "choices": [
              {"value": "helv", "label": "Sans"}, {"value": "times", "label": "Serif"}, {"value": "courier", "label": "Mono"}]},
          {"name": "font_size", "type": "number", "label": "Tamaño", "default": 11, "min": 5, "max": 72},
          {"name": "bold", "type": "checkbox", "label": "Negrita"},
          {"name": "color", "type": "color", "label": "Color", "default": "#1d232b"},
      ]),
    T("marca-de-agua", "watermark", "Marca de agua", "Estampa un texto o una imagen sobre tu PDF.",
      "Pon un texto o un logo encima (o debajo) del contenido de tu PDF. Elige posición, transparencia y giro.",
      "editar", "stamp", ops_edit.watermark, workflow=True, action="Aplicar marca de agua",
      done="Marca de agua aplicada", options=[
          {"name": "type", "type": "segmented", "label": "Tipo", "default": "texto", "choices": [
              {"value": "texto", "label": "Texto"}, {"value": "imagen", "label": "Imagen"}]},
          {"name": "text", "type": "textarea", "label": "Texto", "default": "CONFIDENCIAL", "show_if": {"type": ["texto"]}},
          {"name": "watermark_image", "type": "file", "label": "Imagen (PNG o JPG)", "accept": IMAGES, "show_if": {"type": ["imagen"]}},
          {"name": "image_scale", "type": "range", "label": "Tamaño de la imagen", "default": 0.35, "min": 0.05, "max": 1, "step": 0.05,
           "format": "percent", "show_if": {"type": ["imagen"]}},
          {"name": "font", "type": "segmented", "label": "Fuente", "default": "helv", "show_if": {"type": ["texto"]}, "choices": [
              {"value": "helv", "label": "Sans"}, {"value": "times", "label": "Serif"}, {"value": "courier", "label": "Mono"}]},
          {"name": "font_size", "type": "number", "label": "Tamaño del texto", "default": 54, "min": 6, "max": 300, "show_if": {"type": ["texto"]}},
          {"name": "bold", "type": "checkbox", "label": "Negrita", "default": True, "show_if": {"type": ["texto"]}},
          {"name": "color", "type": "color", "label": "Color", "default": "#c0392b", "show_if": {"type": ["texto"]}},
          {"name": "position", "type": "position9", "label": "Posición", "default": "mc"},
          {"name": "mosaic", "type": "checkbox", "label": "Repetir en mosaico por toda la página"},
          {"name": "opacity", "type": "range", "label": "Transparencia", "default": 0.3, "min": 0.05, "max": 1, "step": 0.05, "format": "percent"},
          {"name": "rotation", "type": "segmented", "label": "Giro", "default": "45", "choices": [
              {"value": "0", "label": "0°"}, {"value": "45", "label": "45°"}, {"value": "90", "label": "90°"}, {"value": "315", "label": "-45°"}]},
          {"name": "layer", "type": "segmented", "label": "Capa", "default": "encima", "choices": [
              {"value": "encima", "label": "Encima del contenido"}, {"value": "debajo", "label": "Debajo del contenido"}]},
          {"name": "pages", "type": "pages", "label": "Páginas", "help": "Vacío = todas."},
      ]),
    T("recortar-pdf", "crop", "Recortar PDF", "Recorta márgenes o deja solo el área que te interesa.",
      "Dibuja el área que quieres conservar y aplícala a una página o a todo el documento. También puede quitar márgenes blancos automáticamente.",
      "editar", "crop", ops_edit.crop, multiple=False, ui="editor", workflow=True, action="Recortar PDF",
      done="Tu PDF quedó recortado", options=[
          {"name": "auto", "type": "checkbox", "label": "Quitar márgenes blancos automáticamente"},
          {"name": "padding", "type": "number", "label": "Espacio alrededor del contenido (pt)", "default": 10, "min": 0, "show_if": {"auto": [True]}},
          {"name": "scope", "type": "segmented", "label": "Aplicar a", "default": "todas", "choices": [
              {"value": "todas", "label": "Todas las páginas"}, {"value": "actual", "label": "Solo esta página"}]},
      ]),
    T("editar-pdf", "edit", "Editar PDF", "Agrega texto, imágenes, formas, dibujos y resaltados.",
      "Escribe sobre tu PDF, inserta imágenes, dibuja formas y flechas, resalta o tapa contenido.",
      "editar", "pencil-line", ops_edit.edit, multiple=False, ui="editor", action="Guardar PDF",
      done="Tus cambios quedaron guardados"),
    T("formularios-pdf", "forms", "Formularios PDF", "Rellena formularios o crea campos nuevos.",
      "Detecta los campos de un formulario PDF para rellenarlos, o crea campos de texto y casillas nuevas.",
      "editar", "text-cursor-input", ops_edit.forms, multiple=False, ui="editor", action="Guardar formulario",
      done="Tu formulario está listo", badge="Nuevo", options=[
          {"name": "flatten", "type": "checkbox", "label": "Fijar respuestas (los campos ya no se podrán editar)"}]),

    # ================================================================ SEGURIDAD
    T("desbloquear-pdf", "unlock", "Desbloquear PDF", "Quita la contraseña y las restricciones de un PDF.",
      "Elimina la contraseña y las restricciones de impresión o copia de tus PDF (necesitas conocer la contraseña).",
      "seguridad", "lock-open", ops_security.unlock, workflow=True, action="Desbloquear PDF",
      done="Tu PDF quedó desbloqueado", options=[
          {"name": "password", "type": "password", "label": "Contraseña del PDF",
           "help": "Solo hace falta si el PDF pide contraseña para abrirse."}]),
    T("proteger-pdf", "protect", "Proteger PDF", "Cifra tu PDF con contraseña.",
      "Protege tu PDF con contraseña y cifrado AES de 256 bits. Opcionalmente, bloquea la impresión o la copia.",
      "seguridad", "lock", ops_security.protect, workflow=True, action="Proteger PDF",
      done="Tu PDF quedó protegido", options=[
          {"name": "password", "type": "password", "label": "Contraseña", "required": True},
          {"name": "password2", "type": "password", "label": "Repite la contraseña", "required": True},
          {"name": "allow_print", "type": "checkbox", "label": "Permitir imprimir", "default": True},
          {"name": "allow_copy", "type": "checkbox", "label": "Permitir copiar texto", "default": True},
          {"name": "allow_modify", "type": "checkbox", "label": "Permitir modificar", "default": True},
          {"name": "allow_annotate", "type": "checkbox", "label": "Permitir comentar y rellenar", "default": True},
      ]),
    T("firmar-pdf", "sign", "Firmar PDF", "Firma tú mismo un documento: dibuja, escribe o sube tu firma.",
      "Crea tu firma (dibujada, escrita o desde una imagen) y colócala donde la necesites, junto con iniciales, nombre o fecha.",
      "seguridad", "signature", ops_edit.sign, multiple=False, ui="editor", action="Firmar PDF",
      done="Tu documento quedó firmado"),
    T("censurar-pdf", "redact", "Censurar PDF", "Elimina para siempre texto y gráficos sensibles.",
      "Tapa y borra de forma definitiva datos sensibles: marca áreas, busca palabras o detecta correos, teléfonos y documentos.",
      "seguridad", "eraser", ops_security.redact, multiple=False, ui="editor", workflow=True,
      action="Censurar PDF", done="Tu PDF quedó censurado", options=[
          {"name": "terms", "type": "textarea", "label": "Palabras o frases a censurar", "help": "Una por línea."},
          {"name": "patterns", "type": "multicheck", "label": "Detectar automáticamente", "choices": [
              {"value": "email", "label": "Correos"}, {"value": "telefono", "label": "Teléfonos"},
              {"value": "documento", "label": "Cédulas y números de documento"}, {"value": "fecha", "label": "Fechas"},
              {"value": "url", "label": "Enlaces"}, {"value": "tarjeta", "label": "Tarjetas bancarias"}]},
          {"name": "color", "type": "color", "label": "Color de la censura", "default": "#000000"},
          {"name": "clean_metadata", "type": "checkbox", "label": "Borrar también los metadatos (autor, título…)", "default": True},
      ]),
    T("comparar-pdf", "compare", "Comparar PDF", "Encuentra las diferencias entre dos versiones de un documento.",
      "Carga la versión original y la nueva: verás lado a lado lo que se eliminó y lo que se agregó.",
      "seguridad", "git-compare", ops_security.compare, min_files=2, max_files=2, ui="compare",
      action="Comparar", done="Comparación lista", options=[
          {"name": "match_case", "type": "checkbox", "label": "Distinguir mayúsculas y minúsculas", "default": True}]),

    # ================================================================ INTELIGENCIA
    T("resumir-pdf", "summarize", "Resumir con IA", "Obtén las ideas clave de un documento en segundos.",
      "Resume documentos largos con inteligencia artificial que corre en tu propio equipo (Ollama).",
      "inteligencia", "sparkles", ops_ai.summarize, multiple=False, action="Resumir", done="Tu resumen está listo",
      badge="IA", options=[
          {"name": "engine", "type": "cards", "label": "Motor", "default": "ollama", "choices": [
              {"value": "ollama", "label": "IA local (Ollama)", "desc": "Redacta un resumen nuevo, sin internet"},
              {"value": "extractivo", "label": "Sin IA", "desc": "Elige las frases más importantes del texto"}]},
          {"name": "model", "type": "model", "label": "Modelo", "show_if": {"engine": ["ollama"]}},
          {"name": "length", "type": "segmented", "label": "Extensión", "default": "medio", "choices": [
              {"value": "corto", "label": "Corto"}, {"value": "medio", "label": "Medio"}, {"value": "largo", "label": "Detallado"}]},
          {"name": "language", "type": "select", "label": "Idioma del resumen", "default": "es", "choices": LANG_CHOICES,
           "show_if": {"engine": ["ollama"]}},
      ]),
    T("traducir-pdf", "translate", "Traducir PDF", "Traduce tu PDF conservando el diseño original.",
      "Traduce el texto de tu PDF a otro idioma y lo coloca en el mismo lugar, sin perder imágenes ni diseño.",
      "inteligencia", "languages", ops_ai.translate, multiple=False, workflow=True, action="Traducir PDF",
      done="Tu PDF quedó traducido", badge="IA", options=[
          {"name": "target", "type": "select", "label": "Traducir al", "default": "en", "choices": LANG_CHOICES},
          {"name": "engine", "type": "cards", "label": "Motor de traducción", "default": "google", "choices": [
              {"value": "google", "label": "En línea", "desc": "Google Translate, rápido y preciso (requiere internet)"},
              {"value": "ollama", "label": "IA local (Ollama)", "desc": "Sin internet; la calidad depende del modelo"}]},
          {"name": "model", "type": "model", "label": "Modelo", "show_if": {"engine": ["ollama"]}},
      ]),
    T("pdf-a-markdown", "markdown", "PDF a Markdown", "Convierte PDF a Markdown con títulos, tablas y listas.",
      "Convierte tus PDF a Markdown limpio, ideal para notas, wikis o para dárselo a una IA.",
      "inteligencia", "file-code", ops_convert.pdf_to_markdown, action="Convertir a Markdown",
      done="Tu Markdown está listo", output="md", badge="Nuevo", options=[
          {"name": "images", "type": "checkbox", "label": "Incluir las imágenes (descarga en ZIP)"},
          {"name": "ocr", "type": "checkbox", "label": "Leer con OCR las páginas escaneadas (más lento)"}]),
]

BY_SLUG = {t["slug"]: t for t in TOOLS}
BY_KEY = {t["key"]: t for t in TOOLS}

# Sugerencias para «Continuar con…» según el tipo de resultado
NEXT = {
    "pdf": ["comprimir-pdf", "unir-pdf", "proteger-pdf", "firmar-pdf", "numerar-paginas", "marca-de-agua", "pdf-a-word", "dividir-pdf"],
}


def public(tool: dict) -> dict:
    """Versión serializable (sin la función) para enviar al navegador."""
    return {k: v for k, v in tool.items() if k != "op"}
