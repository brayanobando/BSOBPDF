/* BSOBPDF — página de herramienta: subir, ajustar, procesar y descargar */
(function () {
  "use strict";
  const { $, $$, el, icon, fmtSize, toast, Handoff, postForm, PDF, modal } = U;
  const T = window.TOOL;
  const ACCEPT = T.accept.split(",").map((s) => s.trim());
  const LETTER_COLORS = ["#d9603b", "#2f6fdb", "#1f9d74", "#8a4fd8", "#c2368a", "#b8860b", "#28384f"];
  const S = { files: [], form: null, sel: new Set(), seq: [], url: "", lastResult: null };
  let nextId = 1;
  let mounted = false;

  // ================================================================ utilidades
  const extOf = (name) => "." + (name.split(".").pop() || "").toLowerCase();
  const kindOf = (ext) => ext === ".pdf" ? "pdf" : ([".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"].includes(ext) ? "image" : (ext === ".html" || ext === ".htm" ? "html" : "office"));
  const STAGES = ["st-upload", "st-work", "st-proc", "st-result"];
  function show(id) {
    STAGES.forEach((s) => { $("#" + s).hidden = s !== id; });
    if (id !== "st-work") window.scrollTo({ top: 0 });
  }

  function pagesToString(set) {
    const arr = Array.from(set).sort((a, b) => a - b).map((i) => i + 1);
    const out = [];
    for (let i = 0; i < arr.length; i++) {
      let j = i;
      while (j + 1 < arr.length && arr[j + 1] === arr[j] + 1) j++;
      out.push(j > i ? `${arr[i]}-${arr[j]}` : `${arr[i]}`);
      i = j;
    }
    return out.join(", ");
  }
  function parsePages(str, n) {
    const set = new Set();
    String(str || "").toLowerCase().replace(/\s/g, "").split(/[,;]/).forEach((part) => {
      if (!part) return;
      if (part === "todas") { for (let i = 0; i < n; i++) set.add(i); return; }
      if (part === "impares") { for (let i = 0; i < n; i += 2) set.add(i); return; }
      if (part === "pares") { for (let i = 1; i < n; i += 2) set.add(i); return; }
      const m = part.match(/^(\d*)-(\d*)$/);
      if (m) {
        let a = m[1] ? +m[1] : 1, b = m[2] ? +m[2] : n;
        if (a > b) [a, b] = [b, a];
        for (let p = a; p <= Math.min(b, n); p++) if (p >= 1) set.add(p - 1);
      } else if (/^\d+$/.test(part) && +part >= 1 && +part <= n) set.add(+part - 1);
    });
    return set;
  }

  // ================================================================ archivos
  async function addFiles(list, { replace = false } = {}) {
    const arr = Array.from(list || []);
    if (!arr.length) return;
    const ok = [], bad = [];
    arr.forEach((f) => (ACCEPT.includes(extOf(f.name)) ? ok : bad).push(f));
    if (bad.length) toast(`${bad.map((f) => f.name).join(", ")}: formato no admitido aquí. Se aceptan ${ACCEPT.map((a) => a.slice(1).toUpperCase()).join(", ")}.`, "error", 8000);
    if (!ok.length) return;
    const single = !T.multiple && !["compare", "organize"].includes(T.ui);
    if (single || replace) S.files = [];
    const take = single ? ok.slice(0, 1) : ok;
    for (const f of take) {
      const item = { id: nextId++, file: f, name: f.name, size: f.size, ext: extOf(f.name), kind: kindOf(extOf(f.name)), pdf: null, pages: 0, locked: false, thumbs: {} };
      if (item.kind === "pdf") {
        try {
          item.pdf = await PDF.open(f);
          item.pages = item.pdf.numPages;
        } catch (e) {
          if (e && e.name === "PasswordException") item.locked = true;
          else { toast(`«${f.name}» no parece un PDF válido. Prueba con Reparar PDF.`, "error", 8000); if (T.key !== "repair") continue; }
        }
      }
      S.files.push(item);
      if (T.ui === "organize" && item.pdf) for (let p = 0; p < item.pages; p++) S.seq.push({ f: item.id, p, r: 0 });
    }
    if (T.ui === "compare" && S.files.length > 2) S.files = S.files.slice(-2);
    if (S.files.length && T.ui !== "editor") {
      const locked = S.files.find((f) => f.locked);
      if (locked && !["unlock", "repair"].includes(T.key)) toast(`«${locked.name}» tiene contraseña. Desbloquéalo primero con Desbloquear PDF.`, "error", 9000);
    }
    enterWork();
  }

  function pickFiles(opts) {
    const inp = $("#file-input");
    inp.onchange = () => { addFiles(inp.files, opts); inp.value = ""; };
    inp.click();
  }

  // ================================================================ panel lateral
  function buildSidebar(aside, { top = null, extraBody = null, note = null, onAction = null } = {}) {
    aside.replaceChildren();
    const body = el("div.sidebar-body");
    if (top) body.append(top);
    if (T.options.length) {
      const formBox = el("div", { style: { display: "grid", gap: "20px" } });
      const prev = S.form ? S.form.values : undefined;
      S.form = Options.render(formBox, T.options, { values: prev, pageCount: (S.files[0] && S.files[0].pages) || 1, onChange: onOptionChange });
      body.append(formBox);
    } else if (!S.form) {
      S.form = { values: {}, files: {}, validate: () => null, setInput() {}, setPageCount() {} };
    }
    if (extraBody) body.append(extraBody);
    const btn = el("button.btn.btn-primary.btn-xl", { type: "button", id: "action-btn", onclick: () => (onAction ? onAction() : submit()) }, [T.action]);
    aside.append(
      el("div.sidebar-head", {}, [el("h2", { text: T.name }), el("p", { text: sideHint() })]),
      body,
      el("div.sidebar-foot", {}, [btn, note ? el("p.foot-note", { text: note }) : null]),
    );
    return { body, btn };
  }

  function sideHint() {
    const n = S.files.length;
    switch (T.key) {
      case "merge": return n < 2 ? "Agrega al menos otro PDF para unirlos." : "Arrastra los archivos para cambiar el orden.";
      case "remove-pages": return "Haz clic en las páginas que quieres eliminar.";
      case "extract-pages": return "Haz clic en las páginas que quieres extraer.";
      case "rotate": return "Haz clic en una página para girarla 90°, o gira todo con los botones.";
      case "organize": return "Arrastra las páginas para ordenarlas. Pasa el cursor para girar, borrar o insertar.";
      case "compare": return "La primera es la versión original; la segunda, la nueva.";
      case "edit": return "Agrega texto, imágenes, formas o dibujos sobre las páginas.";
      case "sign": return "Crea tu firma y colócala donde la necesites. Arrástrala para moverla.";
      case "redact": return "Lo que marques se borrará para siempre del documento.";
      case "crop": return "El recuadro marca lo que se conserva.";
      case "forms": return "Rellena los campos sobre el documento o crea campos nuevos.";
      default: return n > 1 ? `${n} archivos listos.` : "Revisa las opciones y continúa.";
    }
  }

  function onOptionChange(name, value) {
    if (T.ui === "pages") {
      if (name === "pages") { S.sel = parsePages(value, S.files[0].pages); paintSelection(); }
      if (["mode", "ranges", "every"].includes(name)) paintSelection();
    }
  }

  // ================================================================ espacio de trabajo
  function enterWork() {
    if (T.ui === "editor") { if (window.EditorUI) { show("st-work"); EditorUI.mount($("#st-work"), API); } return; }
    if (T.ui === "scan") { show("st-work"); if (!mounted && window.ScanUI) { mounted = true; ScanUI.mount($("#st-work"), API); } else if (window.ScanUI) ScanUI.refresh(); return; }
    if (!S.files.length && T.ui !== "html") { show("st-upload"); return; }
    show("st-work");
    const stage = $("#st-work");
    stage.className = "stage work-stage";
    stage.replaceChildren();
    const main = el("div.work-main");
    const aside = el("aside.sidebar", { "aria-label": "Opciones" });
    stage.append(main, aside);
    const ui = { files: renderFiles, pages: renderPages, rotate: renderRotate, organize: renderOrganize, compare: renderCompare, html: renderHtml }[T.ui] || renderFiles;
    ui(main, aside);
  }

  function fab(main) {
    if (!T.multiple && !["compare", "organize"].includes(T.ui)) return;
    main.classList.add("ui-has-fab");
    const b = el("button.fab-add", { type: "button", "aria-label": "Agregar más archivos", title: "Agregar más archivos", onclick: () => pickFiles() }, [icon("plus"), el("span.count", { text: S.files.length })]);
    main.append(b);
  }

  // ---------------------------------------------------------------- miniaturas
  function thumbFor(item, box, maxW = 150, maxH = 190) {
    box.replaceChildren();
    if (item.locked) { box.append(el("div.lock", {}, [icon("lock"), "Protegido"])); return; }
    if (item.kind === "image") { box.append(el("img", { src: item.url || (item.url = URL.createObjectURL(item.file)), alt: "" })); return; }
    if (item.kind !== "pdf" || !item.pdf) { box.append(el("span.ext", { text: item.ext.slice(1).toUpperCase() })); return; }
    if (item.thumbs.cover) { box.append(item.thumbs.cover); return; }
    PDF.render(item.pdf, 1, maxW, maxH).then((c) => { item.thumbs.cover = c; box.replaceChildren(c); }).catch(() => box.append(el("span.ext", { text: "PDF" })));
  }
  function pageThumb(item, i, box, rot = 0) {
    const key = "p" + i;
    const put = (c) => { box.replaceChildren(c); c.style.transform = rot ? rotTransform(c, rot) : ""; };
    if (item.thumbs[key]) { put(item.thumbs[key]); return; }
    box.replaceChildren(el("span.hint", { text: "…" }));
    PDF.render(item.pdf, i + 1, 120, 160).then((c) => { item.thumbs[key] = c; put(c); });
  }
  function rotTransform(c, rot) {
    const w = parseFloat(c.style.width), h = parseFloat(c.style.height);
    const q = ((rot % 360) + 360) % 360;
    const s = q % 180 ? Math.min(160 / w, 120 / h, 1) : 1;
    return `rotate(${q}deg) scale(${s})`;
  }

  // ---------------------------------------------------------------- UI: lista de archivos
  function renderFiles(main, aside) {
    const head = el("div.work-head", {}, [
      el("h2", { text: S.files.length === 1 ? "1 archivo" : `${S.files.length} archivos` }),
      el("span.meta", { text: fmtSize(S.files.reduce((a, f) => a + f.size, 0)) }),
      el("span.spacer"),
    ]);
    if (T.sortable && S.files.length > 1) {
      head.append(
        el("button.btn.btn-sm", { type: "button", onclick: () => { S.files.sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true })); enterWork(); } }, [icon("arrow-down-a-z"), "Ordenar por nombre"]),
        el("button.btn.btn-sm", { type: "button", onclick: () => { S.files.reverse(); enterWork(); } }, [icon("arrow-up-down"), "Invertir"]),
      );
    }
    const grid = el("div.file-grid");
    S.files.forEach((item, idx) => {
      const thumb = el("div.fthumb");
      const meta = item.locked ? "Con contraseña" : item.pages ? `${item.pages} pág. · ${fmtSize(item.size)}` : fmtSize(item.size);
      const card = el("div.fcard", { draggable: T.sortable ? "true" : null, dataset: { id: item.id } }, [
        thumb,
        T.sortable ? el("span.order-n", { text: idx + 1 }) : null,
        el("div.fname", { title: item.name, text: item.name }),
        el("div.fmeta", { text: meta }),
        el("div.fcard-actions", {}, [el("button", { type: "button", "aria-label": `Quitar ${item.name}`, title: "Quitar", onclick: () => removeFile(item.id) }, [icon("x")])]),
      ]);
      thumbFor(item, thumb);
      if (T.sortable) makeSortable(card, grid, () => S.files, (arr) => { S.files = arr; enterWork(); });
      grid.append(card);
    });
    main.append(head, grid);
    fab(main);
    const note = T.key === "merge" && S.files.length < 2 ? "Necesitas al menos 2 archivos." : null;
    const { btn } = buildSidebar(aside, { note });
    if (S.files.length < (T.min_files || 1)) btn.disabled = true;
  }

  function removeFile(id) {
    S.files = S.files.filter((f) => f.id !== id);
    S.seq = S.seq.filter((s) => s.f !== id);
    if (!S.files.length) { show("st-upload"); return; }
    enterWork();
  }

  /** Arrastrar y soltar para ordenar tarjetas (archivos o páginas). */
  function makeSortable(card, grid, getArr, setArr, keyOf = (x) => String(x.id)) {
    card.addEventListener("dragstart", (e) => { card.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/bsob", card.dataset.id); });
    card.addEventListener("dragend", () => { card.classList.remove("dragging"); $$(".drop-before,.drop-after", grid).forEach((c) => c.classList.remove("drop-before", "drop-after")); });
    card.addEventListener("dragover", (e) => {
      if (!e.dataTransfer.types.includes("text/bsob")) return;
      e.preventDefault();
      const r = card.getBoundingClientRect();
      const after = e.clientX > r.left + r.width / 2;
      card.classList.toggle("drop-after", after); card.classList.toggle("drop-before", !after);
    });
    card.addEventListener("dragleave", () => card.classList.remove("drop-before", "drop-after"));
    card.addEventListener("drop", (e) => {
      const from = e.dataTransfer.getData("text/bsob");
      if (!from) return;
      e.preventDefault(); e.stopPropagation();
      const after = card.classList.contains("drop-after");
      const arr = getArr().slice();
      const fi = arr.findIndex((x) => keyOf(x) === from);
      if (fi < 0) return;
      const [moved] = arr.splice(fi, 1);
      let ti = arr.findIndex((x) => keyOf(x) === card.dataset.id);
      if (ti < 0) ti = arr.length; else if (after) ti += 1;
      arr.splice(ti, 0, moved);
      setArr(arr);
    });
  }

  // ---------------------------------------------------------------- UI: páginas (dividir, eliminar, extraer)
  let pageCards = [];
  function renderPages(main, aside) {
    const item = S.files[0];
    if (!item.pdf) { renderFiles(main, aside); return; }
    main.append(el("div.work-head", {}, [el("h2", { text: item.name }), el("span.meta", { text: `${item.pages} páginas` })]));
    const grid = el("div.page-grid");
    pageCards = [];
    for (let i = 0; i < item.pages; i++) {
      const box = el("div.pthumb");
      const card = el("div.pcard" + (T.key === "remove-pages" ? ".mode-remove" : ""), { tabindex: 0, role: "button", "aria-pressed": "false", "aria-label": `Página ${i + 1}` }, [box, el("div.pnum", {}, [el("span.tag"), `${i + 1}`])]);
      card.addEventListener("click", () => togglePage(i));
      card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); togglePage(i); } });
      pageThumb(item, i, box);
      grid.append(card);
      pageCards.push(card);
    }
    main.append(grid);
    buildSidebar(aside);
    S.form.setPageCount(item.pages);
    if (S.form.values.pages) S.sel = parsePages(S.form.values.pages, item.pages);
    paintSelection();
  }
  function selectable() { return T.key !== "split" || S.form.values.mode === "seleccion"; }
  function togglePage(i) {
    if (!selectable()) return;
    S.sel.has(i) ? S.sel.delete(i) : S.sel.add(i);
    S.form.setInput("pages", pagesToString(S.sel));
    paintSelection();
  }
  function paintSelection() {
    const n = S.files[0] ? S.files[0].pages : 0;
    const groups = new Array(n).fill(-1);
    if (T.key === "split") {
      const v = S.form.values;
      if (v.mode === "rangos") (v.ranges || []).forEach((r, gi) => { for (let p = Math.max(1, r.from); p <= Math.min(n, r.to); p++) if (groups[p - 1] < 0) groups[p - 1] = gi; });
      if (v.mode === "fijo") { const k = Math.max(1, +v.every || 1); for (let p = 0; p < n; p++) groups[p] = Math.floor(p / k); }
      if (v.mode === "todas") for (let p = 0; p < n; p++) groups[p] = p;
    }
    pageCards.forEach((c, i) => {
      const on = selectable() && S.sel.has(i);
      c.classList.toggle("is-selected", on);
      c.setAttribute("aria-pressed", String(on));
      const tag = c.querySelector(".tag");
      if (groups[i] >= 0) { tag.style.background = Options.RANGE_COLORS[groups[i] % Options.RANGE_COLORS.length]; tag.textContent = groups[i] + 1; tag.hidden = false; }
      else tag.hidden = true;
      c.style.cursor = selectable() ? "pointer" : "default";
    });
  }

  // ---------------------------------------------------------------- UI: rotar
  function renderRotate(main, aside) {
    S.files.forEach((item) => { if (!item.rot) item.rot = new Array(item.pages || 0).fill(0); });
    const total = S.files.reduce((a, f) => a + (f.pages || 0), 0);
    main.append(el("div.work-head", {}, [el("h2", { text: S.files.length > 1 ? `${S.files.length} archivos` : S.files[0].name }), el("span.meta", { text: `${total} páginas` })]));
    S.files.forEach((item, fi) => {
      if (!item.pdf) return;
      const grid = el("div.page-grid");
      for (let i = 0; i < item.pages; i++) {
        const box = el("div.pthumb");
        const card = el("div.pcard", { tabindex: 0, role: "button", "aria-label": `Girar página ${i + 1}` }, [box, el("div.pnum", { text: `${i + 1}` }),
          el("div.p-actions", {}, [
            el("button", { type: "button", "aria-label": "Girar a la izquierda", onclick: (e) => { e.stopPropagation(); spin(item, i, -90, box); } }, [icon("rotate-ccw")]),
            el("button", { type: "button", "aria-label": "Girar a la derecha", onclick: (e) => { e.stopPropagation(); spin(item, i, 90, box); } }, [icon("rotate-cw")]),
          ])]);
        card.addEventListener("click", () => spin(item, i, 90, box));
        card.addEventListener("keydown", (e) => { if (e.key === "Enter") spin(item, i, 90, box); });
        pageThumb(item, i, box, item.rot[i]);
        grid.append(card);
      }
      main.append(el("div.file-group", {}, [
        S.files.length > 1 ? el("h3", {}, [el("span.letter", { style: { background: LETTER_COLORS[fi % 7] }, text: String.fromCharCode(65 + fi) }), item.name,
          el("button.btn.btn-ghost.btn-sm", { type: "button", "aria-label": `Quitar ${item.name}`, onclick: () => removeFile(item.id) }, [icon("x")])]) : null,
        grid]));
    });
    fab(main);
    const all = (d) => () => { S.files.forEach((f) => { f.rot = f.rot.map((r) => r + d); }); enterWork(); };
    const top = el("div.field", {}, [el("div.field-label", { text: "Todas las páginas" }), el("div.segmented", {}, [
      el("button", { type: "button", onclick: all(-90) }, [icon("rotate-ccw"), " Izquierda"]),
      el("button", { type: "button", onclick: all(90) }, [icon("rotate-cw"), " Derecha"]),
    ]), el("button.btn.btn-sm.btn-ghost", { type: "button", onclick: () => { S.files.forEach((f) => { f.rot = f.rot.map(() => 0); }); enterWork(); } }, [icon("refresh-cw"), "Restablecer"])]);
    buildSidebar(aside, { top });
  }
  function spin(item, i, d, box) {
    item.rot[i] = (item.rot[i] || 0) + d;
    const c = box.querySelector("canvas");
    if (c) c.style.transform = rotTransform(c, item.rot[i]);
  }

  // ---------------------------------------------------------------- UI: organizar
  function renderOrganize(main, aside) {
    main.append(el("div.work-head", {}, [el("h2", { text: `${S.seq.length} páginas` }), el("span.meta", { text: S.files.length > 1 ? `de ${S.files.length} archivos` : S.files[0].name })]));
    const grid = el("div.page-grid");
    S.seq.forEach((s, idx) => {
      if (!s.key) s.key = "k" + Math.random().toString(36).slice(2, 9);
      const fi = S.files.findIndex((f) => f.id === s.f);
      const item = S.files[fi];
      const box = el("div.pthumb");
      const actions = el("div.p-actions", {}, [
        el("button", { type: "button", "aria-label": "Girar", title: "Girar", onclick: (e) => { e.stopPropagation(); s.r = (s.r || 0) + 90; const c = box.querySelector("canvas"); if (c) c.style.transform = rotTransform(c, s.r); } }, [icon("rotate-cw")]),
        el("button", { type: "button", "aria-label": "Insertar página en blanco después", title: "Página en blanco después", onclick: (e) => { e.stopPropagation(); S.seq.splice(idx + 1, 0, { blank: true }); enterWork(); } }, [icon("file-plus-2")]),
        el("button", { type: "button", "aria-label": "Eliminar página", title: "Eliminar", onclick: (e) => { e.stopPropagation(); S.seq.splice(idx, 1); enterWork(); } }, [icon("trash-2")]),
      ]);
      const label = s.blank ? el("div.pnum", { text: "En blanco" }) : el("div.pnum", {}, [S.files.length > 1 ? el("span.letter", { style: { background: LETTER_COLORS[fi % 7] }, text: String.fromCharCode(65 + fi) }) : null, `${s.p + 1}`]);
      const card = el("div.pcard" + (s.blank ? ".blank" : ""), { draggable: "true", dataset: { id: s.key } }, [box, label, actions]);
      if (s.blank) box.append(el("div", { text: "Página en blanco" }));
      else if (item) pageThumb(item, s.p, box, s.r || 0);
      makeSortable(card, grid, () => S.seq, (arr) => { S.seq = arr; enterWork(); }, (x) => x.key);
      grid.append(card);
    });
    main.append(grid);
    fab(main);
    const top = el("div", { style: { display: "grid", gap: "8px" } }, [
      el("button.btn", { type: "button", onclick: () => pickFiles() }, [icon("file-plus-2"), "Agregar otro PDF"]),
      el("button.btn", { type: "button", onclick: () => { S.seq.push({ blank: true }); enterWork(); } }, [icon("plus"), "Página en blanco al final"]),
      el("button.btn", { type: "button", onclick: () => { S.seq.reverse(); enterWork(); } }, [icon("arrow-up-down"), "Invertir el orden"]),
      el("button.btn.btn-ghost", { type: "button", onclick: () => { S.seq = []; S.files.forEach((f) => { for (let p = 0; p < f.pages; p++) S.seq.push({ f: f.id, p, r: 0 }); }); enterWork(); } }, [icon("refresh-cw"), "Restablecer"]),
    ]);
    buildSidebar(aside, { top });
  }

  // ---------------------------------------------------------------- UI: comparar
  function renderCompare(main, aside) {
    main.append(el("div.work-head", {}, [el("h2", { text: "Elige las dos versiones" }), el("span.spacer"),
      S.files.length === 2 ? el("button.btn.btn-sm", { type: "button", onclick: () => { S.files.reverse(); enterWork(); } }, [icon("arrow-left-right"), "Intercambiar"]) : null]));
    const grid = el("div.file-grid", { style: { gridTemplateColumns: "repeat(2, minmax(0, 260px))" } });
    ["Original", "Versión nueva"].forEach((label, i) => {
      const item = S.files[i];
      const thumb = el("div.fthumb");
      if (item) thumbFor(item, thumb);
      else thumb.append(el("button.btn.btn-primary", { type: "button", onclick: () => pickFiles() }, [icon("upload"), "Elegir PDF"]));
      grid.append(el("div.fcard", {}, [thumb, el("span.slot-label", { text: label }),
        el("div.fname", { text: item ? item.name : "Falta este archivo" }),
        el("div.fmeta", { text: item ? `${item.pages} pág.` : "Arrástralo aquí o elígelo" }),
        item ? el("div.fcard-actions", {}, [el("button", { type: "button", "aria-label": "Quitar", onclick: () => removeFile(item.id) }, [icon("x")])]) : null]));
    });
    main.append(grid);
    const { btn } = buildSidebar(aside);
    btn.disabled = S.files.length !== 2;
  }

  // ---------------------------------------------------------------- UI: HTML a PDF
  function renderHtml(main, aside) {
    const item = S.files[0];
    const label = item ? item.name : S.url;
    main.append(el("div.work-head", {}, [el("h2", { text: "Página a convertir" })]),
      el("div.fcard", { style: { maxWidth: "560px", flexDirection: "row", alignItems: "center", gap: "14px", padding: "16px" } }, [
        el("span.sheet.cat-convertir", {}, [icon(item ? "file-code" : "globe")]),
        el("div", { style: { minWidth: 0, flex: 1 } }, [el("div.fname", { text: label }), el("div.fmeta", { style: { marginTop: "2px" }, text: item ? fmtSize(item.size) : "Se descargará y convertirá en este equipo." })]),
        el("button.btn.btn-sm", { type: "button", onclick: () => { S.files = []; S.url = ""; show("st-upload"); } }, ["Cambiar"])]));
    buildSidebar(aside);
  }

  // ================================================================ enviar
  async function submit(extra = {}, overrideFiles = null) {
    const err = S.form && S.form.validate();
    if (err) { toast(err, "error"); return; }
    if (T.key === "protect" && S.form.values.password !== S.form.values.password2) { toast("Las contraseñas no coinciden.", "error"); return; }
    const fd = new FormData();
    const files = overrideFiles || S.files.map((f) => f.file);
    files.forEach((f) => fd.append("files", f, f.name));
    const options = Object.assign({}, S.form ? S.form.values : {}, extra);
    if (T.ui === "rotate") options.rotations = S.files.map((f) => (f.rot || []).map((r) => ((r % 360) + 360) % 360));
    if (T.ui === "organize") {
      const idx = Object.fromEntries(S.files.map((f, i) => [f.id, i]));
      options.sequence = S.seq.map((s) => s.blank ? { blank: true } : { f: idx[s.f], p: s.p, r: ((s.r || 0) % 360 + 360) % 360 });
    }
    if (T.ui === "html" && !files.length) options.url = S.url;
    if (S.form && S.form.files) Object.entries(S.form.files).forEach(([k, f]) => fd.append(k, f, f.name));
    fd.append("options", JSON.stringify(options));

    show("st-proc");
    const bar = $("#proc-bar"), fill = bar.firstElementChild;
    bar.classList.remove("indeterminate"); fill.style.width = "0";
    $("#proc-title").textContent = files.length ? "Subiendo archivos…" : "Preparando…";
    $("#proc-sub").textContent = "No cierres esta pestaña.";
    const onProgress = (p, done) => {
      fill.style.width = Math.round(p * 100) + "%";
      if (done || p >= 1) {
        bar.classList.add("indeterminate");
        $("#proc-title").textContent = `${T.action}…`;
        $("#proc-sub").textContent = ["ocr", "translate", "summarize", "word-to-pdf", "ppt-to-pdf", "excel-to-pdf", "html-to-pdf"].includes(T.key)
          ? "Esto puede tardar un poco según el tamaño del documento." : "Casi listo.";
      }
    };
    if (!files.length) onProgress(1, true);
    const res = await postForm(`/api/procesar/${T.slug}`, fd, onProgress);
    if (!res.ok) {
      show("st-work");
      toast(res.error || "No se pudo procesar el archivo.", "error", 10000);
      return;
    }
    S.lastResult = res;
    renderResult(res);
  }

  // ================================================================ resultado
  function mdToHtml(md) {
    const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>").replace(/`([^`]+)`/g, "<code>$1</code>");
    const lines = md.split(/\r?\n/);
    let html = "", list = null, para = [], table = [];
    const flushPara = () => { if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; } };
    const flushList = () => { if (list) { html += `</${list}>`; list = null; } };
    const flushTable = () => {
      if (!table.length) return;
      const rows = table.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
      html += "<table>" + rows.map((r, i) => "<tr>" + r.replace(/^\s*\||\|\s*$/g, "").split("|").map((c) => i === 0 ? `<th>${inline(c.trim())}</th>` : `<td>${inline(c.trim())}</td>`).join("") + "</tr>").join("") + "</table>";
      table = [];
    };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (/^\s*\|.*\|\s*$/.test(line)) { flushPara(); flushList(); table.push(line); continue; } else flushTable();
      let m;
      if ((m = line.match(/^(#{1,6})\s+(.*)$/))) { flushPara(); flushList(); const l = Math.min(m[1].length + 1, 4); html += `<h${l}>${inline(m[2])}</h${l}>`; continue; }
      if ((m = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/))) { flushPara(); const t = m[1] ? "ol" : "ul"; if (list !== t) { flushList(); html += `<${t}>`; list = t; } html += `<li>${inline(m[2])}</li>`; continue; }
      if (!line.trim()) { flushPara(); flushList(); continue; }
      flushList(); para.push(line.trim());
    }
    flushPara(); flushList(); flushTable();
    return html;
  }

  function renderResult(res) {
    const box = $("#st-result");
    box.replaceChildren();
    const dl = res.download;
    box.append(el("span.sheet.lg.cat-" + T.category, {}, [icon("check")]));
    box.lastChild.style.marginBottom = "20px";
    box.append(el("h1", { text: T.done }), el("p.result-msg", { text: res.message }));
    const actions = el("div.result-actions", {}, [
      el("a.btn.btn-primary.btn-xl", { href: dl.url, download: dl.name }, [icon("download"), dl.name.endsWith(".zip") ? "Descargar ZIP" : "Descargar"]),
      el("button.btn", { type: "button", onclick: () => enterWork() }, [icon("undo-2"), "Volver a editar"]),
      el("a.btn.btn-ghost", { href: location.pathname }, [icon("refresh-cw"), "Empezar de nuevo"]),
    ]);
    if (dl.name.toLowerCase().endsWith(".pdf")) actions.insertBefore(el("a.btn", { href: dl.url + "?ver=1", target: "_blank", rel: "noopener" }, [icon("eye"), "Ver"]), actions.children[1]);
    box.append(actions, el("p.result-file", { text: `${dl.name} · ${dl.size_h}` }));

    if (res.files.length > 1) {
      box.append(el("div.result-files", {}, res.files.map((f) => el("a", { href: f.url, download: f.name }, [el("span", { text: f.name }), el("span", { text: f.size_h })]))));
    }
    // Comprimir: barra de ahorro
    if (T.key === "compress" && res.stats && res.stats.before) {
      const pct = res.stats.percent;
      box.append(el("div.savings", {}, [
        el("div.big", { text: `-${pct}%` }),
        el("div.bar", { style: { marginTop: "12px" } }, [el("div", { style: { width: `${100 - pct}%` } })]),
        el("div.labels", {}, [el("span", { text: `Ahora: ${fmtSize(res.stats.after)}` }), el("span", { text: `Antes: ${fmtSize(res.stats.before)}` })]),
      ]));
    }
    // Resumen
    if (res.data && res.data.summary) {
      const copy = el("button.btn.btn-sm", { type: "button", onclick: () => { navigator.clipboard.writeText(res.data.summary).then(() => toast("Resumen copiado.")); } }, [icon("copy"), "Copiar"]);
      box.append(el("div.text-result", {}, [el("div.tr-head", {}, [el("h2", { text: "Resumen" }), copy]), el("div.md", { html: mdToHtml(res.data.summary) })]));
    }
    // Markdown
    if (res.data && res.data.markdown) {
      const rendered = el("div.md", { html: mdToHtml(res.data.markdown) });
      const raw = el("pre.md-raw", { text: res.data.markdown, hidden: true });
      const toggle = el("div.segmented", { role: "radiogroup", "aria-label": "Vista" }, [
        el("button", { type: "button", role: "radio", "aria-checked": "true", text: "Vista previa" }),
        el("button", { type: "button", role: "radio", "aria-checked": "false", text: "Código" })]);
      toggle.querySelectorAll("button").forEach((b, i) => b.addEventListener("click", () => {
        toggle.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", "false")); b.setAttribute("aria-checked", "true");
        rendered.hidden = i === 1; raw.hidden = i === 0;
      }));
      box.append(el("div.text-result", {}, [el("div.tr-head", {}, [el("h2", { text: "Markdown" }), toggle,
        el("button.btn.btn-sm", { type: "button", onclick: () => navigator.clipboard.writeText(res.data.markdown).then(() => toast("Markdown copiado.")) }, [icon("copy"), "Copiar"])]), rendered, raw]));
    }
    // Comparación
    if (res.data && res.data.changes) {
      const list = el("div.changes");
      if (!res.data.changes.length) list.append(el("p.empty-note", { text: "No hay diferencias de texto entre las dos versiones." }));
      res.data.changes.forEach((c) => {
        list.append(el("div.change", {}, [
          el("div.where", { text: `${c.type === "agregado" ? "Agregado" : c.type === "eliminado" ? "Eliminado" : "Cambio"}, pág. ${c.page_b}` }),
          el("div", {}, [c.old ? el("del", { text: c.old }) : null, c.old && c.new ? " " : null, c.new ? el("ins", { text: c.new }) : null])]));
      });
      const view = el("div.report-view");
      box.append(el("div.text-result", {}, [el("div.tr-head", {}, [el("h2", { text: "Diferencias" })]), list]), view);
      fetch(dl.url).then((r) => r.blob()).then(async (b) => {
        const pdf = await PDF.open(new File([b], "r.pdf"));
        const w = Math.min(1200, view.clientWidth || 1000);
        for (let i = 1; i <= Math.min(pdf.numPages, 30); i++) view.append(await PDF.render(pdf, i, w, 5000));
        view.querySelectorAll("canvas").forEach((c) => { c.style.width = "100%"; c.style.height = "auto"; });
      });
    }
    // Continuar con otra herramienta
    if (dl.name.toLowerCase().endsWith(".pdf") && T.key !== "compare") {
      const next = (window.NEXT_TOOLS || []).filter((t) => t.slug !== T.slug).slice(0, 7);
      box.append(el("div.continue", {}, [el("h2", { text: "Continuar con este PDF" }), el("div.continue-list", {}, next.map((t) =>
        el("button", { type: "button", onclick: async () => {
          const blob = await (await fetch(dl.url)).blob();
          const id = await Handoff.put([new File([blob], dl.name, { type: "application/pdf" })]);
          location.href = `/${t.slug}?h=${id}`;
        } }, [el("span.sheet.sm.cat-" + t.category, {}, [icon(t.icon)]), t.name])))]));
    }
    show("st-result");
  }

  // ================================================================ arranque
  const API = { T, S, show, addFiles, pickFiles, buildSidebar, submit, enterWork, removeFile, PDF };
  window.ToolApp = API;

  document.addEventListener("DOMContentLoaded", async () => {
    $$("[data-pick]").forEach((b) => b.addEventListener("click", () => pickFiles()));
    const fi = $("#file-input");
    fi.onchange = () => { addFiles(fi.files); fi.value = ""; };
    const urlForm = $("#url-form");
    if (urlForm) urlForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = $("#url-input").value.trim();
      if (!v) { toast("Escribe la dirección de la página web.", "error"); return; }
      S.url = v; S.files = []; enterWork();
    });
    // Aviso si falta un programa
    if (T.needs && window.ENGINE && window.ENGINE[T.needs] === false) {
      const note = $("#engine-note");
      note.hidden = false;
      note.lastElementChild.innerHTML = T.needs === "office"
        ? 'Para esta herramienta hace falta <b>LibreOffice</b> (gratis) o <b>Microsoft Office</b> en este equipo. <a href="/estado">Ver cómo instalarlo</a>.'
        : 'El OCR necesita <b>Tesseract</b> con el idioma español. <a href="/estado">Ver cómo instalarlo</a>.';
    }
    // Arrastrar y soltar en toda la página
    const overlay = $("#drop-overlay");
    let depth = 0;
    const canDrop = () => !$("#st-upload").hidden || (!$("#st-work").hidden && T.ui !== "editor");
    document.addEventListener("dragenter", (e) => { if (e.dataTransfer.types.includes("Files") && canDrop()) { depth++; overlay.hidden = false; } });
    document.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; overlay.hidden = true; } });
    document.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); });
    document.addEventListener("drop", (e) => {
      depth = 0; overlay.hidden = true;
      if (!e.dataTransfer.files.length) return;
      e.preventDefault();
      if (canDrop() || T.ui === "editor") addFiles(e.dataTransfer.files, { replace: T.ui === "editor" });
    });
    // Archivos traídos desde otra página (portada o «Continuar con»)
    const h = new URLSearchParams(location.search).get("h");
    if (h) {
      const files = await Handoff.take(h);
      history.replaceState(null, "", location.pathname);
      if (files.length) { addFiles(files); return; }
    }
    if (T.ui === "scan") enterWork();
  });
})();
