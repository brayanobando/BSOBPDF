/* Portada: filtros por categoría y «suelta un archivo para ver qué puedes hacer» */
(function () {
  "use strict";
  const { $, $$, el, icon, Handoff } = U;

  // ---------------------------------------------------------------- filtros
  const chips = $$(".filters [data-filter]");
  const cards = $$("#tool-grid .tool-card");
  function applyFilter(f) {
    chips.forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.filter === f)));
    cards.forEach((c) => { c.hidden = !(f === "todas" || c.dataset.cat === f); });
    U.store.set("filtro", f);
  }
  chips.forEach((c) => c.addEventListener("click", () => applyFilter(c.dataset.filter)));
  const saved = U.store.get("filtro", "todas");
  if (chips.some((c) => c.dataset.filter === saved)) applyFilter(saved);

  // ---------------------------------------------------------------- hoja para soltar archivos
  const sheet = $("#dropsheet"), input = $("#ds-input"), results = $("#ds-results");
  if (!sheet) return;

  function toolsFor(file) {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    return window.TOOL_INDEX.filter((slug) => {
      const m = window.TOOL_META[slug];
      return m.accept.split(",").includes(ext) && slug !== "comparar-pdf" && slug !== "escanear-a-pdf";
    });
  }

  async function show(files) {
    const file = files[0];
    if (!file) return;
    const matches = toolsFor(file);
    results.replaceChildren();
    results.hidden = false;
    results.append(el("div.ds-file", {}, [icon("file-text"), file.name + (files.length > 1 ? ` y ${files.length - 1} más` : "")]));
    if (!matches.length) {
      results.append(el("p", { text: "Ninguna herramienta acepta este tipo de archivo. Prueba con PDF, Word, Excel, PowerPoint, imágenes o HTML." }));
      return;
    }
    const list = el("div.ds-tools");
    matches.forEach((slug) => {
      const m = window.TOOL_META[slug];
      list.append(el("button.chip", { type: "button", onclick: async (e) => {
        e.stopPropagation();
        const id = await Handoff.put(files);
        location.href = `/${slug}?h=${id}`;
      } }, [m.name]));
    });
    results.append(list);
  }

  sheet.addEventListener("click", (e) => { if (!e.target.closest(".chip")) input.click(); });
  sheet.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => show(Array.from(input.files)));
  ["dragenter", "dragover"].forEach((ev) => sheet.addEventListener(ev, (e) => { e.preventDefault(); sheet.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((ev) => sheet.addEventListener(ev, () => sheet.classList.remove("is-over")));
  sheet.addEventListener("drop", (e) => { e.preventDefault(); show(Array.from(e.dataTransfer.files)); });
  // Soltar en cualquier parte de la portada también funciona
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => { if (!sheet.contains(e.target)) { e.preventDefault(); show(Array.from(e.dataTransfer.files)); sheet.scrollIntoView({ behavior: "smooth", block: "center" }); } });
})();
