/* BSOBPDF — editor visual sobre las páginas: editar, firmar, censurar, recortar y formularios.
   Todas las coordenadas se guardan en puntos PDF (1/72 pulgada) de la página tal como se ve. */
(function () {
  "use strict";
  const { $, $$, el, icon, toast, PDF, modal, store } = U;
  let A, T, S, MODE;
  const SWATCHES = ["#1d232b", "#c0392b", "#0b6b55", "#2f6fdb", "#8a4fd8", "#e67e22", "#ffffff"];
  const FONT_CSS = { helv: "Helvetica, Arial, sans-serif", times: "'Times New Roman', Times, serif", courier: "'Courier New', Courier, monospace" };

  const E = {
    item: null, pages: [], objects: [], selected: null, tool: "select", zoom: 1, baseScale: 1,
    current: 0, history: [], fields: [], values: {}, observer: null, nextId: 1,
    props: { color: "#1d232b", stroke: "#c0392b", fill: "", width: 2, size: 14, font: "helv", bold: false, italic: false, underline: false, opacity: 1 },
  };
  let dom = {};

  // ================================================================ montaje
  async function mount(stage, api) {
    A = api; T = api.T; S = api.S;
    MODE = { edit: "edit", sign: "sign", redact: "redact", crop: "crop", forms: "forms" }[T.key];
    const item = S.files[0];
    if (!item) { A.show("st-upload"); return; }
    if (E.item === item && dom.main) { A.show("st-work"); return; }
    if (item.locked) { toast("Este PDF tiene contraseña. Desbloquéalo primero con Desbloquear PDF.", "error", 9000); S.files = []; A.show("st-upload"); return; }
    if (!item.pdf) { toast("No se pudo leer este PDF. Prueba con Reparar PDF.", "error"); S.files = []; A.show("st-upload"); return; }
    Object.assign(E, { item, pages: [], objects: [], selected: null, history: [], fields: [], values: {}, current: 0, zoom: 1 });
    E.tool = { redact: "redact", forms: "select" }[MODE] || "select";

    stage.className = "stage editor-stage";
    stage.replaceChildren();
    dom.thumbs = el("nav.ed-thumbs", { "aria-label": "Páginas" });
    dom.toolbar = el("div.ed-toolbar", { role: "toolbar", "aria-label": "Herramientas" });
    dom.pagesBox = el("div.ed-pages");
    dom.main = el("div.ed-main", {}, [dom.toolbar, dom.pagesBox]);
    dom.side = el("aside.ed-side.sidebar", { "aria-label": "Opciones" });
    stage.append(dom.thumbs, dom.main, dom.side);

    buildToolbar();
    await buildPages();
    buildSide();
    if (MODE === "crop") initCrop();
    if (MODE === "forms") loadFields();
    document.addEventListener("keydown", onKey);
    dom.main.addEventListener("pointerdown", (e) => { if (e.target === dom.main || e.target === dom.pagesBox) select(null); });
  }

  // ================================================================ barra de herramientas
  const TOOLS = {
    edit: [["select", "mouse-pointer-2", "Mover"], ["text", "type", "Texto"], ["image", "image", "Imagen"], "|",
      ["rect", "square", "Rectángulo"], ["ellipse", "circle", "Elipse"], ["line", "minus", "Línea"], ["arrow", "move", "Flecha"], ["draw", "pen-tool", "Dibujar"], "|",
      ["highlight", "highlighter", "Resaltar"], ["whiteout", "eraser", "Tapar"]],
    sign: [["select", "mouse-pointer-2", "Mover"], ["text", "type", "Texto"]],
    redact: [["select", "mouse-pointer-2", "Mover"], ["redact", "square-dashed", "Marcar área"]],
    crop: [],
    forms: [["select", "mouse-pointer-2", "Rellenar"], ["field-text", "text-cursor-input", "Campo de texto"], ["field-check", "check", "Casilla"], ["field-combo", "list-ordered", "Lista"]],
  };
  function buildToolbar() {
    dom.toolbar.replaceChildren();
    (TOOLS[MODE] || []).forEach((t) => {
      if (t === "|") { dom.toolbar.append(el("span.sep")); return; }
      const [id, ic, label] = t;
      const b = el("button.tb", { type: "button", "aria-pressed": String(E.tool === id), dataset: { tool: id }, title: label }, [icon(ic), label]);
      b.addEventListener("click", () => {
        if (id === "image") { pickImage(); return; }
        setTool(id);
      });
      dom.toolbar.append(b);
    });
    const pct = el("span", { text: "100%" });
    dom.zoomLabel = pct;
    dom.toolbar.append(el("div.zoom", {}, [
      el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Alejar", onclick: () => setZoom(E.zoom / 1.2) }, [icon("zoom-out")]), pct,
      el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Acercar", onclick: () => setZoom(E.zoom * 1.2) }, [icon("zoom-in")])]));
  }
  function setTool(id) {
    E.tool = id;
    $$(".tb", dom.toolbar).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tool === id)));
    E.pages.forEach((p) => {
      p.layer.classList.toggle("tool-active", id !== "select" && id !== "text");
      p.layer.classList.toggle("tool-text", id === "text");
    });
    if (id !== "select") select(null);
    refreshProps();
  }

  // ================================================================ páginas
  async function buildPages() {
    const pdf = E.item.pdf;
    const avail = Math.max(320, (dom.main.clientWidth || 800) - 64);
    dom.pagesBox.replaceChildren();
    dom.thumbs.replaceChildren();
    E.pages = [];
    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n);
      const vp = page.getViewport({ scale: 1, rotation: page.rotate });
      const info = { n, idx: n - 1, page, wPt: vp.width, hPt: vp.height, rendered: 0 };
      E.pages.push(info);
    }
    const maxW = Math.max(...E.pages.map((p) => p.wPt));
    E.baseScale = Math.min(avail / maxW, 1.6);
    E.pages.forEach((p) => {
      p.canvas = el("canvas");
      p.layer = el("div.ed-layer");
      p.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      p.svg.setAttribute("class", "ed-svg");
      p.wrap = el("div.ed-page", { dataset: { idx: p.idx } }, [el("span.pno", { text: `Página ${p.n}` }), p.canvas, p.svg, p.layer]);
      dom.pagesBox.append(p.wrap);
      p.layer.addEventListener("pointerdown", (e) => onLayerDown(e, p));
      // miniatura
      const tb = el("button", { type: "button", "aria-label": `Ir a la página ${p.n}`, onclick: () => p.wrap.scrollIntoView({ behavior: "smooth", block: "start" }) }, [el("span.hint", { text: "…" }), `${p.n}`]);
      dom.thumbs.append(tb);
      p.thumbBtn = tb;
      PDF.render(E.item.pdf, p.n, 96, 130).then((c) => tb.firstChild.replaceWith(c));
    });
    sizePages();
    // Dibujar solo las páginas visibles y saber cuál es la actual
    if (E.observer) E.observer.disconnect();
    const ratios = new Map();
    E.observer = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        const p = E.pages[+en.target.dataset.idx];
        ratios.set(p.idx, en.intersectionRatio);
        if (en.isIntersecting) drawPage(p);
      });
      let best = E.current, bestR = -1;
      ratios.forEach((r, i) => { if (r > bestR) { bestR = r; best = i; } });
      setCurrent(best);
    }, { root: dom.main, threshold: [0, 0.25, 0.5, 0.75, 1] });
    E.pages.forEach((p) => E.observer.observe(p.wrap));
  }
  function scale() { return E.baseScale * E.zoom; }
  function sizePages() {
    const s = scale();
    E.pages.forEach((p) => {
      p.wrap.style.width = p.wPt * s + "px";
      p.wrap.style.height = p.hPt * s + "px";
      p.canvas.style.width = p.wPt * s + "px";
      p.canvas.style.height = p.hPt * s + "px";
      p.svg.setAttribute("viewBox", `0 0 ${p.wPt} ${p.hPt}`);
    });
    if (dom.zoomLabel) dom.zoomLabel.textContent = Math.round(E.zoom * 100) + "%";
  }
  async function drawPage(p) {
    const s = scale();
    if (p.rendered === s || p.rendering) return;
    p.rendering = true;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const vp = p.page.getViewport({ scale: s * dpr, rotation: p.page.rotate });
    const c = document.createElement("canvas");
    c.width = Math.floor(vp.width); c.height = Math.floor(vp.height);
    c.style.width = p.wPt * s + "px"; c.style.height = p.hPt * s + "px";
    try { await p.page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise; } catch (e) { /* página dañada */ }
    p.canvas.replaceWith(c);
    p.canvas = c;
    p.rendered = s;
    p.rendering = false;
    if (scale() !== s) drawPage(p);
  }
  function setZoom(z) {
    E.zoom = Math.max(0.4, Math.min(3, z));
    sizePages();
    E.pages.forEach((p) => { p.rendered = 0; });
    E.pages.forEach((p) => { const r = p.wrap.getBoundingClientRect(), m = dom.main.getBoundingClientRect(); if (r.bottom > m.top && r.top < m.bottom) drawPage(p); });
    renderAll();
  }
  function setCurrent(i) {
    E.current = i;
    E.pages.forEach((p) => p.thumbBtn && p.thumbBtn.setAttribute("aria-current", String(p.idx === i)));
    if (dom.cropPageLabel) dom.cropPageLabel.textContent = `Página ${i + 1}`;
  }

  // ================================================================ objetos
  const isBox = (t) => !["line", "arrow", "draw"].includes(t);
  function newObj(o) {
    const base = { id: E.nextId++, opacity: E.props.opacity };
    return Object.assign(base, o);
  }
  function commit() {
    E.history.push(JSON.stringify(E.objects.map(stripDom)));
    if (E.history.length > 60) E.history.shift();
  }
  function stripDom(o) { const c = Object.assign({}, o); delete c.node; return c; }
  function undo() {
    if (!E.history.length) return;
    const snap = JSON.parse(E.history.pop());
    E.objects.forEach((o) => o.node && o.node.remove());
    E.objects = snap;
    E.selected = null;
    renderAll();
    refreshProps();
  }
  function addObject(o, { selectIt = true } = {}) {
    commit();
    E.objects.push(o);
    renderObject(o);
    if (selectIt) select(o);
    updateCounts();
    return o;
  }
  function removeObject(o) {
    if (!o || o.type === "crop") return;
    commit();
    o.node && o.node.remove();
    E.objects = E.objects.filter((x) => x !== o);
    if (E.selected === o) E.selected = null;
    refreshProps(); updateCounts();
  }
  function renderAll() { E.objects.forEach(renderObject); }

  function renderObject(o) {
    const p = E.pages[o.page];
    if (!p) return;
    const s = scale();
    if (!isBox(o.type)) {
      let node = o.node;
      if (!node) {
        node = document.createElementNS("http://www.w3.org/2000/svg", o.type === "draw" ? "polyline" : "g");
        node.classList.add("shape");
        node.addEventListener("pointerdown", (e) => { if (E.tool !== "select") return; e.stopPropagation(); select(o); startMove(e, o); });
        p.svg.append(node);
        o.node = node;
      }
      node.setAttribute("opacity", o.opacity ?? 1);
      if (o.type === "draw") {
        node.setAttribute("points", o.points.map((q) => q.join(",")).join(" "));
        Object.entries({ fill: "none", stroke: o.stroke, "stroke-width": o.width, "stroke-linecap": "round", "stroke-linejoin": "round" }).forEach(([k, v]) => node.setAttribute(k, v));
      } else {
        const [a, b] = o.points;
        let inner = `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${o.stroke}" stroke-width="${o.width}" stroke-linecap="round"/>`;
        if (o.type === "arrow") {
          const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), L = Math.max(8, o.width * 4);
          [2.6, -2.6].forEach((d) => { inner += `<line x1="${b[0]}" y1="${b[1]}" x2="${b[0] + L * Math.cos(ang + d)}" y2="${b[1] + L * Math.sin(ang + d)}" stroke="${o.stroke}" stroke-width="${o.width}" stroke-linecap="round"/>`; });
        }
        inner += `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="transparent" stroke-width="${Math.max(10, o.width + 8)}"/>`;
        node.innerHTML = inner;
      }
      node.classList.toggle("selected", E.selected === o);
      return;
    }
    let node = o.node;
    if (!node) {
      node = el("div.obj.obj-" + (o.type.startsWith("field") ? "field" : o.type), { dataset: { id: o.id } });
      if (o.type === "text") {
        const t = el("div.txt", { spellcheck: "false" });
        t.textContent = o.text || "";
        t.addEventListener("dblclick", () => editText(o));
        t.addEventListener("input", () => { o.text = t.innerText.replace(/\n$/, ""); measure(o); });
        t.addEventListener("blur", () => { t.contentEditable = "false"; if (!o.text || !o.text.trim()) removeObject(o); });
        node.append(t);
      }
      if (o.type === "image") node.append(el("img", { src: o.data, alt: "" }));
      if (o.type.startsWith("field")) node.append(el("span", { text: o.name }));
      ["nw", "ne", "sw", "se"].forEach((h) => {
        const hd = el("span.h." + h);
        hd.addEventListener("pointerdown", (e) => { e.stopPropagation(); startResize(e, o, h); });
        node.append(hd);
      });
      if (o.type !== "crop") node.append(el("button.del", { type: "button", "aria-label": "Eliminar", title: "Eliminar (Supr)", onpointerdown: (e) => e.stopPropagation(), onclick: () => removeObject(o) }, [icon("trash-2")]));
      node.addEventListener("pointerdown", (e) => {
        if (o.type === "text" && node.firstChild.isContentEditable) return;
        if (E.tool !== "select" && o.type !== "crop") return;
        e.stopPropagation();
        select(o);
        startMove(e, o);
      });
      p.layer.append(node);
      o.node = node;
    }
    Object.assign(node.style, { left: o.x * s + "px", top: o.y * s + "px", opacity: o.opacity ?? 1 });
    if (o.type === "text") {
      const t = node.firstChild;
      Object.assign(t.style, {
        fontFamily: FONT_CSS[o.font] || FONT_CSS.helv, fontSize: o.size * s + "px", color: o.color,
        fontWeight: o.bold ? "700" : "400", fontStyle: o.italic ? "italic" : "normal", textDecoration: o.underline ? "underline" : "none",
      });
      node.style.width = node.style.height = "";
      requestAnimationFrame(() => measure(o));
    } else {
      node.style.width = o.w * s + "px";
      node.style.height = o.h * s + "px";
    }
    if (o.type === "rect" || o.type === "ellipse") {
      Object.assign(node.style, {
        border: o.stroke ? `${Math.max(1, o.width * s)}px solid ${o.stroke}` : "none",
        background: o.fill || "transparent", borderRadius: o.type === "ellipse" ? "50%" : "0",
      });
    }
    if (o.type === "highlight") node.style.background = (o.fill || "#ffe14d") + "88";
    if (o.type.startsWith("field") && node.firstChild) node.firstChild.textContent = o.name;
    node.classList.toggle("selected", E.selected === o);
  }
  function measure(o) {
    if (!o.node) return;
    const s = scale();
    o.w = o.node.offsetWidth / s;
    o.h = o.node.offsetHeight / s;
  }
  function editText(o) {
    const t = o.node.firstChild;
    t.contentEditable = "true";
    t.focus();
    const r = document.createRange(); r.selectNodeContents(t); r.collapse(false);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
  }
  function select(o) {
    const prev = E.selected;
    E.selected = o;
    if (prev && prev.node) { prev.node.classList.remove("selected"); }
    if (o && o.node) o.node.classList.add("selected");
    refreshProps();
  }

  // ---------------------------------------------------------------- arrastrar y redimensionar
  function pt(e, p) {
    const r = p.wrap.getBoundingClientRect(), s = scale();
    return [Math.max(0, Math.min(p.wPt, (e.clientX - r.left) / s)), Math.max(0, Math.min(p.hPt, (e.clientY - r.top) / s))];
  }
  function startMove(e, o) {
    const p = E.pages[o.page];
    const start = pt(e, p);
    const orig = JSON.parse(JSON.stringify({ x: o.x, y: o.y, points: o.points }));
    let moved = false;
    const mv = (ev) => {
      const q = pt(ev, p);
      const dx = q[0] - start[0], dy = q[1] - start[1];
      if (!moved && Math.abs(dx) + Math.abs(dy) < 1) return;
      if (!moved) { commit(); moved = true; }
      if (isBox(o.type)) {
        o.x = Math.max(0, Math.min(p.wPt - o.w, orig.x + dx));
        o.y = Math.max(0, Math.min(p.hPt - o.h, orig.y + dy));
      } else {
        o.points = orig.points.map(([x, y]) => [x + dx, y + dy]);
        bbox(o);
      }
      renderObject(o);
    };
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); if (o.type === "crop") syncCrop(); };
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", up);
  }
  function startResize(e, o, h) {
    const p = E.pages[o.page];
    commit();
    const o0 = { x: o.x, y: o.y, w: o.w, h: o.h };
    const keep = o.type === "image" ? o0.h / o0.w : null;
    const mv = (ev) => {
      const [qx, qy] = pt(ev, p);
      let x0 = o0.x, y0 = o0.y, x1 = o0.x + o0.w, y1 = o0.y + o0.h;
      if (h.includes("w")) x0 = Math.min(qx, x1 - 6); else x1 = Math.max(qx, x0 + 6);
      if (h.includes("n")) y0 = Math.min(qy, y1 - 6); else y1 = Math.max(qy, y0 + 6);
      if (keep) { const w = x1 - x0; const hh = w * keep; if (h.includes("n")) y0 = y1 - hh; else y1 = y0 + hh; }
      if (o.type === "text") {
        // en texto, el tamaño de la esquina cambia el tamaño de letra
        const ratio = (y1 - y0) / o0.h;
        o.size = Math.max(4, Math.round(o.size * ratio * 10) / 10);
        o0.h = y1 - y0; o.x = x0; o.y = y0;
      } else { Object.assign(o, { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }); }
      renderObject(o);
      if (o.type === "text") refreshProps();
    };
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); if (o.type === "crop") syncCrop(); };
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", up);
  }
  function bbox(o) {
    const xs = o.points.map((q) => q[0]), ys = o.points.map((q) => q[1]);
    o.x = Math.min(...xs); o.y = Math.min(...ys); o.w = Math.max(...xs) - o.x; o.h = Math.max(...ys) - o.y;
  }

  // ---------------------------------------------------------------- crear con el ratón
  function onLayerDown(e, p) {
    if (e.button !== 0) return;
    const tool = E.tool;
    const [x, y] = pt(e, p);
    setCurrent(p.idx);
    if (tool === "select") { if (e.target === p.layer) select(null); return; }
    e.preventDefault();
    const P = E.props;
    if (tool === "text") {
      const o = addObject(newObj({ page: p.idx, type: "text", x, y: Math.max(0, y - P.size * 0.6), text: "", size: P.size, font: P.font, color: P.color, bold: P.bold, italic: P.italic, underline: P.underline }));
      setTool("select");
      editText(o);
      setTimeout(() => { if (o.node && document.activeElement !== o.node.firstChild) editText(o); }, 30);
      return;
    }
    if (tool === "draw") {
      const o = addObject(newObj({ page: p.idx, type: "draw", points: [[x, y]], stroke: P.stroke, width: P.width }), { selectIt: false });
      const mv = (ev) => { o.points.push(pt(ev, p)); renderObject(o); };
      const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); if (o.points.length < 2) { removeObject(o); E.history.pop(); } else bbox(o); };
      window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
      return;
    }
    if (tool === "line" || tool === "arrow") {
      const o = addObject(newObj({ page: p.idx, type: tool, points: [[x, y], [x, y]], stroke: P.stroke, width: P.width }), { selectIt: false });
      const mv = (ev) => { o.points[1] = pt(ev, p); renderObject(o); };
      const up = () => {
        window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
        const [a, b] = o.points;
        if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 4) o.points[1] = [a[0] + 80, a[1]];
        bbox(o); renderObject(o); select(o);
      };
      window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
      return;
    }
    // Herramientas de rectángulo
    const defaults = {
      rect: { stroke: P.stroke, fill: P.fill, width: P.width }, ellipse: { stroke: P.stroke, fill: P.fill, width: P.width },
      highlight: { fill: "#ffe14d" }, whiteout: { fill: "#ffffff" }, redact: {},
      "field-text": { name: fieldName("texto") }, "field-check": { name: fieldName("casilla") }, "field-combo": { name: fieldName("lista"), options: "Opción 1, Opción 2" },
    }[tool];
    if (!defaults) return;
    const o = addObject(newObj(Object.assign({ page: p.idx, type: tool, x, y, w: 1, h: 1 }, defaults)), { selectIt: false });
    const mv = (ev) => {
      const [qx, qy] = pt(ev, p);
      Object.assign(o, { x: Math.min(x, qx), y: Math.min(y, qy), w: Math.abs(qx - x), h: Math.abs(qy - y) });
      renderObject(o);
    };
    const up = () => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
      if (o.w < 5 || o.h < 5) {
        const def = { "field-check": [14, 14], "field-text": [160, 20], "field-combo": [140, 20], highlight: [140, 16], redact: [140, 18] }[tool] || [120, 70];
        Object.assign(o, { w: def[0], h: def[1], x: Math.min(x, p.wPt - def[0]), y: Math.min(y, p.hPt - def[1]) });
      }
      if (tool === "field-check") { o.h = o.w = Math.max(10, Math.min(o.w, o.h)); }
      renderObject(o); select(o);
      if (!["redact", "highlight"].includes(tool)) setTool("select");
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  }
  function fieldName(base) {
    let i = 1;
    const used = new Set(E.objects.filter((o) => o.name).map((o) => o.name).concat(E.fields.map((f) => f.name)));
    while (used.has(`${base}_${i}`)) i++;
    return `${base}_${i}`;
  }

  // ---------------------------------------------------------------- imágenes
  function readImage(file) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => { const img = new Image(); img.onload = () => resolve({ data: fr.result, w: img.naturalWidth, h: img.naturalHeight }); img.onerror = reject; img.src = fr.result; };
      fr.onerror = reject;
      fr.readAsDataURL(file);
    });
  }
  function pickImage() {
    const inp = el("input", { type: "file", accept: "image/*" });
    inp.addEventListener("change", async () => {
      const f = inp.files[0];
      if (!f) return;
      try { const im = await readImage(f); placeImage(im.data, im.w, im.h, 200); }
      catch (e) { toast("No se pudo leer esa imagen.", "error"); }
    });
    inp.click();
  }
  function placeImage(data, w, h, targetW, page = E.current) {
    const p = E.pages[page];
    const W = Math.min(targetW, p.wPt * 0.8), H = W * h / w;
    const visibleY = visibleCenterY(p);
    return addObject(newObj({ page, type: "image", data, x: (p.wPt - W) / 2, y: Math.max(0, Math.min(p.hPt - H, visibleY - H / 2)), w: W, h: H }));
  }
  function visibleCenterY(p) {
    const r = p.wrap.getBoundingClientRect(), m = dom.main.getBoundingClientRect();
    const cy = (Math.max(r.top, m.top) + Math.min(r.bottom, m.bottom)) / 2;
    return Math.max(0, Math.min(p.hPt, (cy - r.top) / scale()));
  }

  // ================================================================ panel lateral
  function buildSide() {
    const top = el("div", { style: { display: "grid", gap: "18px" } });
    dom.props = el("div", { style: { display: "grid", gap: "16px" } });
    if (MODE === "edit") {
      top.append(el("p.hint", { text: "Elige una herramienta arriba y haz clic o arrastra sobre la página. Doble clic en un texto para cambiarlo. Ctrl+Z deshace." }), dom.props);
    } else if (MODE === "sign") {
      top.append(signPanel(), dom.props);
    } else if (MODE === "redact") {
      dom.count = el("p.empty-note", { text: "Dibuja rectángulos sobre lo que quieras tapar, o usa las opciones de abajo para buscar texto." });
      top.append(dom.count);
    } else if (MODE === "crop") {
      dom.cropPageLabel = el("b", { text: "Página 1" });
      top.append(el("p.hint", { text: "Arrastra el recuadro y sus esquinas para elegir el área que se conserva." }),
        el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } }, [
          el("button.btn.btn-sm", { type: "button", onclick: () => moveCropTo(E.current) }, [icon("crop"), "Llevar el recuadro a la página visible"]),
          el("button.btn.btn-sm.btn-ghost", { type: "button", onclick: () => resetCrop() }, [icon("refresh-cw"), "Restablecer"])]));
    } else if (MODE === "forms") {
      dom.count = el("p.empty-note", { text: "Buscando campos del formulario…" });
      top.append(dom.count, dom.props);
    }
    const res = A.buildSidebar(dom.side, { top, onAction: send });
    dom.actionBtn = res.btn;
    refreshProps();
  }

  // ---------------------------------------------------------------- propiedades del objeto
  function refreshProps() {
    if (!dom.props) return;
    dom.props.replaceChildren();
    const o = E.selected;
    const t = o ? o.type : E.tool;
    const P = o || E.props;
    const setP = (k, v) => {
      if (o) { commit(); o[k] = v; renderObject(o); } else E.props[k] = v;
      if (!o || ["font", "size", "color", "stroke", "fill", "width", "bold", "italic", "underline"].includes(k)) E.props[k] = v;
    };
    const colorRow = (label, key, allowNone) => {
      const row = el("div.color-row");
      const mark = () => row.querySelectorAll(".swatch").forEach((s) => s.setAttribute("aria-checked", String((s.dataset.c || "") === (P[key] || ""))));
      if (allowNone) row.append(el("button.swatch", { type: "button", dataset: { c: "" }, "aria-label": "Sin color", title: "Sin relleno", style: { background: "repeating-linear-gradient(45deg,#fff 0 4px,#e5484d 4px 6px)" }, onclick: () => { setP(key, ""); mark(); } }));
      SWATCHES.forEach((c) => row.append(el("button.swatch", { type: "button", dataset: { c }, "aria-label": c, style: { background: c }, onclick: () => { setP(key, c); mark(); } })));
      const pick = el("input", { type: "color", value: P[key] || "#000000", "aria-label": "Otro color" });
      pick.addEventListener("input", () => { setP(key, pick.value); mark(); });
      row.append(pick); mark();
      return el("div.field", {}, [el("div.field-label", { text: label }), row]);
    };
    const num = (label, key, min, max, step = 1) => {
      const i = el("input.input", { type: "number", min, max, step, value: P[key] });
      i.addEventListener("change", () => setP(key, Number(i.value)));
      return el("div.field", {}, [el("label", { text: label }), i]);
    };
    const opacity = () => {
      const out = el("output", { text: Math.round((P.opacity ?? 1) * 100) + "%" });
      const r = el("input", { type: "range", min: 0.1, max: 1, step: 0.05, value: P.opacity ?? 1 });
      r.addEventListener("input", () => { out.textContent = Math.round(r.value * 100) + "%"; if (o) { o.opacity = Number(r.value); renderObject(o); } else E.props.opacity = Number(r.value); });
      return el("div.field", {}, [el("div.field-label", { text: "Opacidad" }), el("div.range-row", {}, [r, out])]);
    };

    if (MODE === "forms") { formsProps(o); return; }
    if (MODE === "redact" || MODE === "crop") return;

    if (t === "text") {
      const fam = el("div.segmented", { role: "radiogroup", "aria-label": "Fuente" });
      [["helv", "Sans"], ["times", "Serif"], ["courier", "Mono"]].forEach(([v, l]) => {
        const b = el("button", { type: "button", role: "radio", "aria-checked": String(P.font === v), text: l, style: { fontFamily: FONT_CSS[v] } });
        b.addEventListener("click", () => { fam.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", "false")); b.setAttribute("aria-checked", "true"); setP("font", v); });
        fam.append(b);
      });
      const tog = el("div.toggle-row");
      [["bold", "N", "Negrita", { fontWeight: 800 }], ["italic", "I", "Cursiva", { fontStyle: "italic" }], ["underline", "S", "Subrayado", { textDecoration: "underline" }]].forEach(([k, l, title, st]) => {
        const b = el("button", { type: "button", title, "aria-label": title, "aria-pressed": String(!!P[k]), text: l, style: st });
        b.addEventListener("click", () => { const v = !(b.getAttribute("aria-pressed") === "true"); b.setAttribute("aria-pressed", String(v)); setP(k, v); });
        tog.append(b);
      });
      dom.props.append(el("div.field", {}, [el("div.field-label", { text: "Texto" }), fam]), el("div.prop-grid", {}, [num("Tamaño (pt)", "size", 4, 200, 0.5), el("div.field", {}, [el("div.field-label", { text: "Estilo" }), tog])]), colorRow("Color", "color"), opacity());
    } else if (["rect", "ellipse"].includes(t)) {
      dom.props.append(colorRow("Borde", "stroke", true), colorRow("Relleno", "fill", true), num("Grosor del borde", "width", 0, 30, 0.5), opacity());
    } else if (["line", "arrow", "draw"].includes(t)) {
      dom.props.append(colorRow("Color", "stroke"), num("Grosor", "width", 0.5, 30, 0.5), opacity());
    } else if (t === "highlight") {
      dom.props.append(colorRow("Color del resaltado", "fill"));
    } else if (t === "image") {
      dom.props.append(opacity());
    } else if (MODE === "edit" && !o) {
      dom.props.append(el("p.empty-note", { text: "Selecciona un elemento para cambiar su color, tamaño u opacidad." }));
    }
    if (o && MODE === "sign") {
      dom.props.append(el("button.btn", { type: "button", onclick: () => repeatAll(o) }, [icon("copy"), "Repetir en todas las páginas"]));
    }
    if (o) dom.props.append(el("button.btn.btn-ghost.btn-danger", { type: "button", onclick: () => removeObject(o) }, [icon("trash-2"), "Eliminar elemento"]));
  }

  function repeatAll(o) {
    commit();
    E.pages.forEach((p) => {
      if (p.idx === o.page) return;
      const c = stripDom(o);
      c.id = E.nextId++; c.page = p.idx;
      c.x = Math.min(c.x, p.wPt - (c.w || 10)); c.y = Math.min(c.y, p.hPt - (c.h || 10));
      E.objects.push(c); renderObject(c);
    });
    toast(`Copiado en ${E.pages.length - 1} página(s) más.`);
    updateCounts();
  }

  function updateCounts() {
    if (MODE === "redact" && dom.count) {
      const n = E.objects.filter((o) => o.type === "redact").length;
      dom.count.textContent = n ? `${n} área(s) marcada(s) para censurar.` : "Dibuja rectángulos sobre lo que quieras tapar, o usa las opciones de abajo para buscar texto.";
    }
  }

  // ================================================================ firma
  function signPanel() {
    const box = el("div", { style: { display: "grid", gap: "14px" } });
    const draw = () => {
      box.replaceChildren();
      const sigs = store.get("firmas", {});
      const slot = (key, label, desc) => {
        const has = sigs[key];
        const b = el("button.sig-slot", { type: "button" }, [
          el("span.prev", {}, [has ? el("img", { src: has, alt: "" }) : el("span", { text: "Sin crear" })]),
          el("span", {}, [el("b", { text: label }), el("small", { text: has ? "Clic para colocarla" : desc })])]);
        b.addEventListener("click", async () => {
          if (!has) { signatureDialog(key, label, () => { draw(); placeSig(key); }); return; }
          placeSig(key);
        });
        const edit = has ? el("button.btn.btn-ghost.btn-sm", { type: "button", onclick: () => signatureDialog(key, label, draw) }, [icon("pencil-line"), "Cambiar"]) : null;
        return el("div", { style: { display: "grid", gap: "4px" } }, [b, edit]);
      };
      const name = store.get("nombre", "");
      box.append(el("div.field-label", { text: "Tus firmas" }), el("div.sig-slots", {}, [slot("firma", "Firma", "Dibújala, escríbela o súbela"), slot("iniciales", "Iniciales", "Para rubricar cada página")]),
        el("div.field-label", { text: "Agregar datos" }),
        el("div.quick-fields", {}, [
          el("button.btn.btn-sm", { type: "button", onclick: () => quickText(name || "Tu nombre") }, [icon("user-round"), "Nombre"]),
          el("button.btn.btn-sm", { type: "button", onclick: () => quickText(new Date().toLocaleDateString("es-CO")) }, [icon("calendar"), "Fecha"]),
          el("button.btn.btn-sm", { type: "button", onclick: () => quickText("Texto") }, [icon("type"), "Texto"]),
          el("button.btn.btn-sm", { type: "button", onclick: () => quickText("✓", 18) }, [icon("check"), "Visto"]),
        ]),
        el("p.hint", { text: "Las firmas se guardan solo en este navegador para la próxima vez." }));
    };
    draw();
    return box;
  }
  function placeSig(key) {
    const data = store.get("firmas", {})[key];
    if (!data) return;
    const img = new Image();
    img.onload = () => placeImage(data, img.naturalWidth, img.naturalHeight, key === "firma" ? 170 : 70);
    img.src = data;
  }
  function quickText(text, size) {
    const p = E.pages[E.current];
    const sz = size || E.props.size;
    const n = E.objects.filter((x) => x.page === p.idx).length;
    const o = addObject(newObj({ page: p.idx, type: "text", x: p.wPt * 0.35, y: Math.min(p.hPt - sz * 2, visibleCenterY(p) + 40 + (n % 5) * sz * 1.6), text, size: sz, font: E.props.font, color: E.props.color, bold: false, italic: false }));
    return o;
  }

  function signatureDialog(key, label, done) {
    let mode = "dibujar", penColor = "#1d232b", font = "Firma Dancing";
    const tabs = el("div.tabs", { role: "tablist" });
    const panel = el("div");
    const colors = () => el("div.sig-colors", {}, [el("span.field-label", { text: "Color" }), ...["#1d232b", "#1a3fb0", "#b42318"].map((c) => {
      const b = el("button.swatch", { type: "button", "aria-label": c, "aria-checked": String(c === penColor), style: { background: c } });
      b.addEventListener("click", () => { penColor = c; b.parentElement.querySelectorAll(".swatch").forEach((x) => x.setAttribute("aria-checked", String(x === b))); if (mode === "escribir") renderType(); });
      return b;
    })]);
    let pad, ctx, typed, fileData = null, fileNoBg = null, removeBg = true;
    const renderType = () => panel.querySelectorAll(".sig-fonts button").forEach((b) => { b.style.color = penColor; });
    const tabsDef = [["dibujar", "Dibujar"], ["escribir", "Escribir"], ["subir", "Subir imagen"]];
    const showTab = (m) => {
      mode = m;
      tabs.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.m === m)));
      panel.replaceChildren();
      if (m === "dibujar") {
        pad = el("canvas.sig-pad", { width: 1200, height: 440 });
        ctx = pad.getContext("2d");
        ctx.lineCap = ctx.lineJoin = "round";
        let last = null;
        const pos = (e) => { const r = pad.getBoundingClientRect(); return [(e.clientX - r.left) * pad.width / r.width, (e.clientY - r.top) * pad.height / r.height]; };
        pad.addEventListener("pointerdown", (e) => { pad.setPointerCapture(e.pointerId); last = pos(e); });
        pad.addEventListener("pointermove", (e) => {
          if (!last) return;
          const q = pos(e);
          ctx.strokeStyle = penColor; ctx.lineWidth = 7 * (e.pressure && e.pointerType === "pen" ? 0.5 + e.pressure : 1);
          ctx.beginPath(); ctx.moveTo(last[0], last[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
          last = q; pad.dataset.dirty = "1";
        });
        pad.addEventListener("pointerup", () => { last = null; });
        panel.append(pad, el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "10px" } }, [colors(),
          el("button.btn.btn-sm.btn-ghost", { type: "button", onclick: () => { ctx.clearRect(0, 0, pad.width, pad.height); delete pad.dataset.dirty; } }, [icon("eraser"), "Borrar"])]));
      } else if (m === "escribir") {
        typed = el("input.input.sig-type-input", { type: "text", value: store.get("nombre", ""), placeholder: key === "iniciales" ? "Tus iniciales" : "Tu nombre completo" });
        const fonts = el("div.sig-fonts", { role: "radiogroup", "aria-label": "Estilo" });
        const upd = () => fonts.querySelectorAll("button").forEach((b) => { b.textContent = typed.value || "Tu firma"; });
        ["Firma Dancing", "Firma Vibes", "Firma Sacramento"].forEach((f) => {
          const b = el("button", { type: "button", role: "radio", "aria-checked": String(f === font), style: { fontFamily: `'${f}', cursive`, color: penColor } });
          b.addEventListener("click", () => { font = f; fonts.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b))); });
          fonts.append(b);
        });
        typed.addEventListener("input", upd); upd();
        panel.append(el("div", { style: { display: "grid", gap: "12px" } }, [typed, fonts, colors()]));
      } else {
        const inp = el("input", { type: "file", accept: "image/*" });
        const prev = el("img", { alt: "", style: { maxHeight: "160px", margin: "10px auto", display: "none" } });
        const chk = el("input", { type: "checkbox", checked: true, id: "sig-bg" });
        chk.addEventListener("change", () => { removeBg = chk.checked; });
        inp.addEventListener("change", async () => {
          const f = inp.files[0]; if (!f) return;
          const im = await readImage(f);
          fileData = im.data; prev.src = im.data; prev.style.display = "block";
          const img = new Image();
          img.onload = () => { fileNoBg = whiteToAlpha(img); };
          img.src = im.data;
        });
        panel.append(el("div", { style: { display: "grid", gap: "10px" } }, [inp, prev, el("label.check", { for: "sig-bg" }, [chk, el("span", { text: "Quitar el fondo blanco (recomendado para fotos de una firma en papel)" })])]));
      }
    };
    tabsDef.forEach(([m, l]) => { const b = el("button", { type: "button", role: "tab", dataset: { m }, text: l }); b.addEventListener("click", () => showTab(m)); tabs.append(b); });
    showTab("dibujar");
    document.fonts && document.fonts.load("40px 'Firma Dancing'");

    modal({
      title: `Crear ${label.toLowerCase()}`, body: el("div", { style: { display: "grid", gap: "14px" } }, [tabs, panel]),
      actions: [{ label: "Cancelar" }, { label: "Guardar y colocar", primary: true, onClick: () => {
        const out = produce();
        if (!out) { toast(mode === "dibujar" ? "Dibuja tu firma en el recuadro." : mode === "escribir" ? "Escribe tu nombre." : "Elige una imagen.", "error"); return false; }
        const sigs = store.get("firmas", {}); sigs[key] = out; store.set("firmas", sigs);
        if (mode === "escribir" && typed.value) store.set("nombre", typed.value);
        sessionSig[key] = out;
        done && done();
      } }],
    });
    function produce() {
      let c;
      if (mode === "dibujar") { if (!pad.dataset.dirty) return null; c = pad; }
      else if (mode === "escribir") {
        if (!typed.value.trim()) return null;
        c = document.createElement("canvas"); c.width = 1600; c.height = 400;
        const g = c.getContext("2d");
        g.font = `140px '${font}', cursive`; g.fillStyle = penColor; g.textBaseline = "middle";
        g.fillText(typed.value.trim(), 40, 210);
      } else {
        if (!fileData) return null;
        return removeBg && fileNoBg ? fileNoBg : fileData;
      }
      return trim(c);
    }
  }
  const sessionSig = {};
  // Si el navegador no guarda en localStorage, usamos la firma de esta sesión
  const _get = store.get;
  store.get = (k, d) => { const v = _get(k, d); if (k === "firmas") return Object.assign({}, sessionSig, v || {}); return v; };

  function trim(canvas) {
    const g = canvas.getContext("2d");
    const { width: w, height: h } = canvas;
    const data = g.getImageData(0, 0, w, h).data;
    let x0 = w, y0 = h, x1 = 0, y1 = 0;
    for (let y = 0; y < h; y += 2) for (let x = 0; x < w; x += 2) {
      if (data[(y * w + x) * 4 + 3] > 10) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    }
    if (x1 <= x0 || y1 <= y0) return null;
    const pad = 8;
    x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(w, x1 + pad); y1 = Math.min(h, y1 + pad);
    const out = document.createElement("canvas"); out.width = x1 - x0; out.height = y1 - y0;
    out.getContext("2d").drawImage(canvas, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
    return out.toDataURL("image/png");
  }
  function whiteToAlpha(img) {
    const c = document.createElement("canvas");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    const g = c.getContext("2d"); g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height);
    for (let i = 0; i < d.data.length; i += 4) {
      const lum = 0.299 * d.data[i] + 0.587 * d.data[i + 1] + 0.114 * d.data[i + 2];
      if (lum > 200) d.data[i + 3] = 0; else if (lum > 150) d.data[i + 3] = Math.round(255 * (200 - lum) / 50);
    }
    g.putImageData(d, 0, 0);
    return trim(c) || c.toDataURL("image/png");
  }

  // ================================================================ recortar
  function initCrop() {
    const p = E.pages[0];
    E.objects.push(newObj({ page: 0, type: "crop", x: p.wPt * 0.06, y: p.hPt * 0.06, w: p.wPt * 0.88, h: p.hPt * 0.88 }));
    p.wrap.classList.add("clip");
    renderAll();
    syncCrop();
  }
  function cropObj() { return E.objects.find((o) => o.type === "crop"); }
  function moveCropTo(idx) {
    const o = cropObj(), from = E.pages[o.page], to = E.pages[idx];
    from.wrap.classList.remove("clip"); to.wrap.classList.add("clip");
    const fx = o.x / from.wPt, fy = o.y / from.hPt, fw = o.w / from.wPt, fh = o.h / from.hPt;
    o.node.remove(); o.node = null;
    Object.assign(o, { page: idx, x: fx * to.wPt, y: fy * to.hPt, w: fw * to.wPt, h: fh * to.hPt });
    renderObject(o); syncCrop();
  }
  function resetCrop() {
    const o = cropObj(), p = E.pages[o.page];
    Object.assign(o, { x: p.wPt * 0.06, y: p.hPt * 0.06, w: p.wPt * 0.88, h: p.hPt * 0.88 });
    renderObject(o); syncCrop();
  }
  function syncCrop() { /* el recuadro se envía al procesar */ }

  // ================================================================ formularios
  async function loadFields() {
    const fd = new FormData();
    fd.append("files", E.item.file, E.item.name);
    let j;
    try { j = await (await fetch("/api/formularios/campos", { method: "POST", body: fd })).json(); }
    catch (e) { j = { ok: false, error: "No se pudo leer el formulario." }; }
    if (!j.ok) { dom.count.textContent = j.error; return; }
    E.fields = j.fields;
    dom.count.textContent = j.fields.length
      ? `Se encontraron ${j.fields.length} campo(s). Escribe directamente sobre el documento.`
      : "Este PDF no tiene campos. Usa las herramientas de arriba para crear campos de texto, casillas o listas.";
    renderFields();
    refreshProps();
  }
  function renderFields() {
    const s = scale();
    E.fields.forEach((f) => {
      const p = E.pages[f.page];
      if (!p) return;
      let node = f.node;
      if (!node) {
        if (f.type === "checkbox" || f.type === "radio") {
          node = el("input.form-input", { type: f.type, name: f.type === "radio" ? "r_" + f.name : null, "aria-label": f.label || f.name, checked: !!f.value, disabled: f.readonly });
          node.addEventListener("change", () => {
            if (f.type === "radio") E.fields.filter((x) => x.name === f.name).forEach((x) => { E.values[x.xref] = x.node.checked; });
            else E.values[f.xref] = node.checked;
          });
        } else if (f.type === "combobox" || f.type === "listbox") {
          node = el("select.form-input", { "aria-label": f.label || f.name, disabled: f.readonly }, (f.options || []).map((o) => el("option", { value: o, text: o, selected: o === f.value })));
          node.addEventListener("change", () => { E.values[f.xref] = node.value; });
        } else {
          node = f.multiline ? el("textarea.form-input", { "aria-label": f.label || f.name, readonly: f.readonly }) : el("input.form-input", { type: "text", "aria-label": f.label || f.name, readonly: f.readonly });
          node.value = f.value || "";
          node.addEventListener("input", () => { E.values[f.xref] = node.value; });
        }
        node.title = f.label || f.name;
        node.addEventListener("pointerdown", (e) => e.stopPropagation());
        p.layer.append(node);
        f.node = node;
      }
      Object.assign(node.style, { left: f.x * s + "px", top: f.y * s + "px", width: f.w * s + "px", height: f.h * s + "px", fontSize: Math.max(9, Math.min(f.h * 0.65, 14) * s) + "px" });
    });
  }
  function formsProps(o) {
    if (o && o.type.startsWith("field")) {
      const name = el("input.input", { type: "text", value: o.name });
      name.addEventListener("input", () => { o.name = name.value.trim() || o.name; renderObject(o); });
      const parts = [el("div.field", {}, [el("label", { text: "Nombre del campo nuevo" }), name])];
      if (o.type === "field-combo") {
        const ops = el("input.input", { type: "text", value: o.options || "" });
        ops.addEventListener("input", () => { o.options = ops.value; });
        parts.push(el("div.field", {}, [el("label", { text: "Opciones (separadas por comas)" }), ops]));
      }
      parts.push(el("button.btn.btn-ghost.btn-danger", { type: "button", onclick: () => removeObject(o) }, [icon("trash-2"), "Quitar campo"]));
      dom.props.append(...parts);
    } else {
      const n = E.objects.filter((x) => x.type.startsWith("field")).length;
      if (n) dom.props.append(el("p.hint", { text: `${n} campo(s) nuevo(s) se agregarán al guardar.` }));
    }
  }

  // ================================================================ teclado
  function onKey(e) {
    if ($("#st-work").hidden) return;
    const editing = document.activeElement && (document.activeElement.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName));
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !editing) { e.preventDefault(); undo(); return; }
    if (editing) { if (e.key === "Escape") document.activeElement.blur(); return; }
    if ((e.key === "Delete" || e.key === "Backspace") && E.selected) { e.preventDefault(); removeObject(E.selected); }
    if (e.key === "Escape") { select(null); setTool(TOOLS[MODE] && TOOLS[MODE][0] ? TOOLS[MODE][0][0] : "select"); }
    if (E.selected && E.selected.type !== "crop" && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key) && isBox(E.selected.type)) {
      e.preventDefault();
      const d = e.shiftKey ? 10 : 1, o = E.selected;
      if (e.key === "ArrowLeft") o.x -= d; if (e.key === "ArrowRight") o.x += d; if (e.key === "ArrowUp") o.y -= d; if (e.key === "ArrowDown") o.y += d;
      renderObject(o);
    }
  }

  // ================================================================ enviar
  function send() {
    if (document.activeElement && document.activeElement.isContentEditable) document.activeElement.blur();
    const objs = E.objects.map(stripDom);
    let extra = {};
    if (MODE === "edit" || MODE === "sign") {
      const list = objs.filter((o) => !(o.type === "text" && !(o.text || "").trim()));
      if (!list.length) { toast(MODE === "sign" ? "Coloca tu firma en el documento." : "Agrega al menos un elemento al documento.", "error"); return; }
      extra.objects = list.map((o) => {
        const c = { page: o.page, type: o.type, x: o.x, y: o.y, w: o.w, h: o.h, opacity: o.opacity };
        if (o.type === "text") Object.assign(c, { text: o.text, size: o.size, font: o.font, color: o.color, bold: o.bold, italic: o.italic, underline: o.underline });
        if (o.type === "image") c.data = o.data;
        if (["rect", "ellipse"].includes(o.type)) Object.assign(c, { stroke: o.stroke, fill: o.fill, width: o.width });
        if (["line", "arrow", "draw"].includes(o.type)) Object.assign(c, { stroke: o.stroke, width: o.width, points: o.points });
        if (["highlight", "whiteout"].includes(o.type)) c.fill = o.fill;
        return c;
      });
    } else if (MODE === "redact") {
      extra.areas = objs.filter((o) => o.type === "redact").map((o) => ({ page: o.page, x: o.x, y: o.y, w: o.w, h: o.h }));
      const v = S.form.values;
      if (!extra.areas.length && !(v.terms || "").trim() && !v.patterns) { toast("Marca áreas en el documento, escribe palabras o elige qué datos censurar.", "error"); return; }
    } else if (MODE === "crop") {
      const o = cropObj();
      extra.box = { x: o.x, y: o.y, w: o.w, h: o.h };
      extra.page = o.page;
    } else if (MODE === "forms") {
      extra.values = E.values;
      extra.new_fields = objs.filter((o) => o.type.startsWith("field")).map((o) => ({
        page: o.page, x: o.x, y: o.y, w: o.w, h: o.h, name: o.name,
        type: o.type === "field-check" ? "checkbox" : o.type === "field-combo" ? "combobox" : "text", options: o.options,
      }));
      if (!Object.keys(extra.values).length && !extra.new_fields.length && !S.form.values.flatten) { toast("Rellena algún campo o crea campos nuevos antes de guardar.", "error"); return; }
    }
    A.submit(extra);
  }

  // Ajustar al cambiar el tamaño de la ventana
  let rt;
  window.addEventListener("resize", () => {
    clearTimeout(rt);
    rt = setTimeout(() => {
      if (!dom.main || !E.pages.length) return;
      const avail = Math.max(320, dom.main.clientWidth - 64);
      const maxW = Math.max(...E.pages.map((p) => p.wPt));
      const nb = Math.min(avail / maxW, 1.6);
      if (Math.abs(nb - E.baseScale) > 0.02) { E.baseScale = nb; setZoom(E.zoom); renderFields(); }
    }, 200);
  });
  const _setZoom = setZoom;
  setZoom = function (z) { _setZoom(z); renderFields(); }; // eslint-disable-line no-func-assign

  window.EditorUI = { mount };
})();
