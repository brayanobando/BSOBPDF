/* BSOBPDF — constructor y ejecución de flujos de trabajo */
(function () {
  "use strict";
  const { $, el, icon, toast, postForm, fmtSize, store } = U;
  const TOOLS = Object.fromEntries(window.WF_TOOLS.map((t) => [t.slug, t]));
  const TEMPLATES = [
    { name: "Listo para enviar por correo", steps: [{ tool: "comprimir-pdf", options: { level: "recomendada" } }, { tool: "proteger-pdf", options: {} }] },
    { name: "Documento oficial numerado", steps: [{ tool: "unir-pdf", options: {} }, { tool: "numerar-paginas", options: { format: "pagina_n_de_total", position: "br" } }, { tool: "comprimir-pdf", options: {} }] },
    { name: "Archivo a largo plazo", steps: [{ tool: "reparar-pdf", options: {} }, { tool: "ocr-pdf", options: {} }, { tool: "pdf-a-pdfa", options: { level: "2b" } }] },
    { name: "Borrador confidencial", steps: [{ tool: "marca-de-agua", options: { text: "BORRADOR", mosaic: true } }, { tool: "censurar-pdf", options: { patterns: "email,telefono,documento" } }] },
  ];
  let flows = store.get("flujos", []);
  let current = { id: null, name: "", steps: [] };
  let files = [];

  // ---------------------------------------------------------------- lista de flujos
  function drawSaved() {
    const box = $("#wf-saved");
    box.replaceChildren();
    if (!flows.length) box.append(el("p.hint", { text: "Aún no tienes flujos guardados." }));
    flows.forEach((f) => box.append(el("button", { type: "button", "aria-current": String(f.id === current.id), onclick: () => load(f) }, [
      el("span", { text: f.name || "Sin nombre" }), el("small", { text: `${f.steps.length} pasos` })])));
    const tb = $("#wf-templates");
    tb.replaceChildren();
    TEMPLATES.forEach((t) => tb.append(el("button", { type: "button", onclick: () => load({ id: null, name: t.name, steps: JSON.parse(JSON.stringify(t.steps)) }) }, [
      el("span", { text: t.name }), el("small", { text: t.steps.map((s) => TOOLS[s.tool] ? TOOLS[s.tool].name : s.tool).join(" + ") })])));
  }
  function load(f) {
    current = JSON.parse(JSON.stringify(f));
    $("#wf-name").value = current.name || "";
    drawSteps(); drawSaved(); drawRun();
  }

  // ---------------------------------------------------------------- pasos
  function drawSteps() {
    const box = $("#wf-steps");
    box.replaceChildren();
    if (!current.steps.length) box.append(el("p.empty-note", { text: "Agrega el primer paso con los botones de abajo." }));
    current.steps.forEach((st, i) => {
      const t = TOOLS[st.tool];
      if (!t) return;
      const body = el("div.wf-step-body");
      const open = st._open !== false;
      body.hidden = !open;
      const opts = t.options.filter((o) => o.type !== "file" && o.type !== "ranges");
      if (opts.length) Options.render(body, opts, { values: st.options, workflow: true, onChange: (k, v, all) => { st.options = Object.assign({}, all); } });
      else body.append(el("p.hint", { text: "Este paso no tiene opciones." }));
      if (st.tool === "unir-pdf") body.append(el("p.hint", { text: "Solo tiene efecto si cargas varios archivos." }));
      if (st.tool === "recortar-pdf") body.append(el("p.hint", { text: "En un flujo se quitan los márgenes blancos automáticamente." }));
      if (st.tool === "censurar-pdf") body.append(el("p.hint", { text: "En un flujo solo se censuran palabras y datos detectados automáticamente." }));
      const head = el("div.wf-step-head", {}, [
        el("span.n"), el("span.sheet.sm.cat-" + t.category, {}, [icon(t.icon)]), el("b", { text: t.name }),
        el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Subir paso", disabled: i === 0, onclick: () => { move(i, -1); } }, [icon("chevron-left")]),
        el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Bajar paso", disabled: i === current.steps.length - 1, onclick: () => { move(i, 1); } }, [icon("chevron-right")]),
        el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": open ? "Ocultar opciones" : "Mostrar opciones", onclick: () => { st._open = !open; drawSteps(); } }, [icon("settings-2")]),
        el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Quitar paso", onclick: () => { current.steps.splice(i, 1); drawSteps(); } }, [icon("x")]),
      ]);
      head.querySelectorAll(".btn-icon")[0].firstChild.style.transform = "rotate(90deg)";
      head.querySelectorAll(".btn-icon")[1].firstChild.style.transform = "rotate(90deg)";
      box.append(el("div.wf-step", {}, [head, body]));
    });
  }
  function move(i, d) {
    const j = i + d;
    if (j < 0 || j >= current.steps.length) return;
    [current.steps[i], current.steps[j]] = [current.steps[j], current.steps[i]];
    drawSteps();
  }
  function drawAdd() {
    const box = $("#wf-add");
    window.WF_TOOLS.forEach((t) => box.append(el("button", { type: "button", onclick: () => {
      if (current.steps.length >= 12) { toast("Un flujo puede tener como máximo 12 pasos.", "error"); return; }
      const st = { tool: t.slug, options: {} };
      if (t.slug === "unir-pdf") current.steps.unshift(st); else current.steps.push(st);
      drawSteps();
    } }, [el("span.sheet.sm.cat-" + t.category, {}, [icon(t.icon)]), t.name])));
  }

  // ---------------------------------------------------------------- ejecutar
  function drawRun() {
    const box = $("#wf-run");
    box.replaceChildren();
    const inp = el("input", { type: "file", accept: ".pdf", multiple: true, hidden: true });
    inp.addEventListener("change", () => { files = files.concat(Array.from(inp.files)); inp.value = ""; drawRun(); });
    const list = el("div", { style: { display: "grid", gap: "6px" } }, files.map((f, i) => el("div.result-files", { style: { marginTop: 0, width: "100%" } }, [
      el("a", { href: "#", onclick: (e) => { e.preventDefault(); files.splice(i, 1); drawRun(); } }, [el("span", { text: f.name }), el("span", { text: `${fmtSize(f.size)} · quitar` })])])));
    const run = el("button.btn.btn-primary.btn-xl", { type: "button", style: { width: "100%" }, disabled: !files.length || !current.steps.length, onclick: execute }, ["Ejecutar flujo"]);
    box.append(
      el("button.btn", { type: "button", style: { width: "100%" }, onclick: () => inp.click() }, [icon("upload"), files.length ? "Agregar más PDF" : "Elegir archivos PDF"]),
      inp, list,
      el("p.hint", { style: { margin: "8px 0 14px" }, text: !current.steps.length ? "Primero agrega pasos al flujo." : `${current.steps.length} paso(s) se aplicarán en orden.` }),
      run, el("div", { id: "wf-result" }));
  }
  async function execute() {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    fd.append("steps", JSON.stringify(current.steps.map((s) => ({ tool: s.tool, options: s.options || {} }))));
    const out = $("#wf-result");
    out.replaceChildren(el("div.progress.indeterminate", { style: { marginTop: "18px" } }, [el("div")]), el("p.hint", { style: { marginTop: "8px" }, text: "Procesando el flujo…" }));
    const r = await postForm("/api/flujo", fd);
    out.replaceChildren();
    if (!r.ok) { out.append(el("div.error-box", {}, [icon("triangle-alert"), el("span", { text: r.error })])); return; }
    out.append(el("div", { style: { marginTop: "18px", display: "grid", gap: "10px" } }, [
      el("a.btn.btn-primary", { href: r.download.url, download: r.download.name }, [icon("download"), `Descargar ${r.download.name}`]),
      el("ol", { style: { margin: 0, paddingLeft: "20px", fontSize: ".9rem", color: "var(--tinta-2)", display: "grid", gap: "4px" } }, (r.data.log || []).map((l) => el("li", { text: l })))]));
  }

  // ---------------------------------------------------------------- guardar
  $("#wf-new").addEventListener("click", () => load({ id: null, name: "", steps: [] }));
  $("#wf-name").addEventListener("input", (e) => { current.name = e.target.value; });
  $("#wf-save").addEventListener("click", () => {
    if (!current.steps.length) { toast("Agrega al menos un paso.", "error"); return; }
    current.name = $("#wf-name").value.trim() || "Mi flujo";
    if (!current.id) current.id = Date.now().toString(36);
    const clean = { id: current.id, name: current.name, steps: current.steps.map((s) => ({ tool: s.tool, options: s.options || {} })) };
    const i = flows.findIndex((f) => f.id === current.id);
    if (i >= 0) flows[i] = clean; else flows.push(clean);
    store.set("flujos", flows);
    drawSaved();
    toast("Flujo guardado.");
  });
  $("#wf-delete").addEventListener("click", () => {
    if (!current.id) { load({ id: null, name: "", steps: [] }); return; }
    flows = flows.filter((f) => f.id !== current.id);
    store.set("flujos", flows);
    load({ id: null, name: "", steps: [] });
    toast("Flujo borrado.");
  });

  drawAdd();
  load(flows[0] || { id: null, name: TEMPLATES[0].name, steps: JSON.parse(JSON.stringify(TEMPLATES[0].steps)) });
})();
