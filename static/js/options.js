/* Renderiza el panel de opciones de una herramienta a partir de su esquema (core/registry.py) */
(function () {
  "use strict";
  const { el, icon } = U;
  const RANGE_COLORS = ["#d9603b", "#2f6fdb", "#1f9d74", "#8a4fd8", "#c2368a", "#b8860b", "#28384f", "#0e8a9a"];
  const SWATCHES = ["#1d232b", "#c0392b", "#0b6b55", "#2f6fdb", "#8a4fd8", "#e67e22", "#7f8c8d"];
  let uid = 0;

  function render(container, schema, opts = {}) {
    const values = Object.assign({}, opts.values || {});
    const files = {};
    const rows = [];
    const ctx = { pageCount: opts.pageCount || 1 };
    const inputs = {};
    const rangeDrawers = [];
    const onChange = opts.onChange || (() => {});

    const visible = (f) => {
      if (!f.show_if) return true;
      return Object.entries(f.show_if).every(([k, allowed]) => allowed.map(String).includes(String(values[k])));
    };
    const refresh = () => rows.forEach(({ f, row }) => { row.hidden = !visible(f); });
    const set = (name, v, silent) => { values[name] = v; refresh(); if (!silent) onChange(name, v, values); };

    schema.forEach((f) => {
      if (f.type === "file" && opts.workflow) return;
      if (f.workflow_only && !opts.workflow) return;
      if (!(f.name in values)) values[f.name] = f.default !== undefined ? f.default : (f.type === "checkbox" ? false : (f.type === "multicheck" ? "" : (f.type === "ranges" ? null : "")));
      if (f.type === "hidden") return;
      const id = "opt-" + f.name + "-" + (++uid);
      const row = el("div.field");
      const label = f.type === "checkbox" ? null : el(f.type === "cards" || f.type === "segmented" || f.type.startsWith("position") || f.type === "multicheck" || f.type === "ranges" ? "div.field-label" : "label", { for: id, id: id + "-l", text: f.label });
      if (label) row.append(label);
      row.append(build(f, id));
      if (f.help) row.append(el("p.help", { text: f.help }));
      rows.push({ f, row });
      container.append(row);
    });
    refresh();

    function build(f, id) {
      const v = values[f.name];
      switch (f.type) {
        case "cards": {
          const wrap = el("div.cards", { role: "radiogroup", "aria-labelledby": id + "-l" });
          f.choices.forEach((c) => {
            const b = el("button.opt-card", { type: "button", role: "radio", "aria-checked": String(String(v) === String(c.value)) }, [el("b", { text: c.label }), c.desc ? el("span", { text: c.desc }) : null]);
            b.addEventListener("click", () => { wrap.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", "false")); b.setAttribute("aria-checked", "true"); set(f.name, c.value); });
            wrap.append(b);
          });
          return wrap;
        }
        case "segmented": {
          const wrap = el("div.segmented", { role: "radiogroup", "aria-labelledby": id + "-l" });
          f.choices.forEach((c) => {
            const b = el("button", { type: "button", role: "radio", "aria-checked": String(String(v) === String(c.value)), text: c.label });
            b.addEventListener("click", () => { wrap.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", "false")); b.setAttribute("aria-checked", "true"); set(f.name, c.value); });
            wrap.append(b);
          });
          return wrap;
        }
        case "select": {
          const s = el("select.select", { id }, f.choices.map((c) => el("option", { value: c.value, text: c.label, selected: String(c.value) === String(v) })));
          s.addEventListener("change", () => set(f.name, s.value));
          return s;
        }
        case "model": {
          const s = el("select.select", { id }, [el("option", { value: "", text: "Cargando modelos…" })]);
          const note = el("p.help");
          fetch("/api/ollama/modelos").then((r) => r.json()).then((j) => {
            s.replaceChildren();
            if (!j.ok || !j.models.length) {
              s.append(el("option", { value: "", text: "Ollama no disponible" }));
              s.disabled = true;
              note.textContent = j.ok ? "Ollama está abierto pero no tiene modelos. Descarga uno con: ollama pull qwen3:4b" : "Abre Ollama para usar la IA local, o elige el otro motor.";
              return;
            }
            j.models.forEach((m) => s.append(el("option", { value: m, text: m, selected: m === j.default })));
            set(f.name, s.value, true);
          }).catch(() => { note.textContent = "No se pudo consultar Ollama."; });
          s.addEventListener("change", () => set(f.name, s.value));
          return el("div", {}, [s, note]);
        }
        case "text": case "password": case "pages": {
          const i = el("input.input", { id, type: f.type === "password" ? "password" : "text", value: v ?? "", placeholder: f.type === "pages" ? "1-3, 5" : (f.placeholder || ""), autocomplete: f.type === "password" ? "new-password" : "off" });
          i.addEventListener("input", () => set(f.name, i.value));
          i._bsobSet = (val) => { i.value = val; values[f.name] = val; };
          inputs[f.name] = i;
          return i;
        }
        case "textarea": {
          const t = el("textarea.textarea", { id, rows: 3 });
          t.value = v ?? "";
          t.addEventListener("input", () => set(f.name, t.value));
          return t;
        }
        case "number": {
          const i = el("input.input", { id, type: "number", value: v, min: f.min, max: f.max, step: f.step || 1 });
          i.addEventListener("input", () => set(f.name, i.value === "" ? "" : Number(i.value)));
          return i;
        }
        case "range": {
          const out = el("output", { for: id });
          const fmt = (x) => f.format === "percent" ? Math.round(x * 100) + "%" : x;
          const i = el("input", { id, type: "range", min: f.min, max: f.max, step: f.step || 1, value: v });
          out.textContent = fmt(v);
          i.addEventListener("input", () => { out.textContent = fmt(Number(i.value)); set(f.name, Number(i.value)); });
          return el("div.range-row", {}, [i, out]);
        }
        case "color": {
          const wrap = el("div.color-row", { role: "radiogroup", "aria-label": f.label });
          const picker = el("input", { id, type: "color", value: v || "#000000", title: "Otro color" });
          const mark = () => wrap.querySelectorAll(".swatch").forEach((s) => s.setAttribute("aria-checked", String(s.dataset.c.toLowerCase() === String(values[f.name]).toLowerCase())));
          SWATCHES.forEach((c) => wrap.append(el("button.swatch", { type: "button", role: "radio", style: { background: c }, dataset: { c }, "aria-label": c, onclick: () => { picker.value = c; set(f.name, c); mark(); } })));
          picker.addEventListener("input", () => { set(f.name, picker.value); mark(); });
          wrap.append(picker);
          mark();
          return wrap;
        }
        case "checkbox": {
          const i = el("input", { id, type: "checkbox", checked: !!v });
          i.addEventListener("change", () => set(f.name, i.checked));
          return el("label.check", { for: id }, [i, el("span", { text: f.label })]);
        }
        case "multicheck": {
          const wrap = el("div.multicheck");
          const cur = new Set(String(v || "").split(",").filter(Boolean));
          f.choices.forEach((c) => {
            const cid = id + "-" + c.value;
            const i = el("input", { id: cid, type: "checkbox", checked: cur.has(c.value) });
            i.addEventListener("change", () => { i.checked ? cur.add(c.value) : cur.delete(c.value); set(f.name, Array.from(cur).join(",")); });
            wrap.append(el("label.check", { for: cid }, [i, el("span", { text: c.label })]));
          });
          return wrap;
        }
        case "position6": case "position9": {
          const nine = f.type === "position9";
          const grid = el("div.posgrid" + (nine ? "" : ".six"), { role: "radiogroup", "aria-labelledby": id + "-l" });
          const cells = nine ? ["tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br"] : ["tl", "tc", "tr", null, "bl", "bc", "br"];
          const names = { tl: "Arriba izquierda", tc: "Arriba centro", tr: "Arriba derecha", ml: "Centro izquierda", mc: "Centro", mr: "Centro derecha", bl: "Abajo izquierda", bc: "Abajo centro", br: "Abajo derecha" };
          cells.forEach((c) => {
            if (!c) { grid.append(el("div.gap", { text: "página" })); return; }
            const b = el("button", { type: "button", role: "radio", "aria-label": names[c], title: names[c], "aria-checked": String(v === c) });
            b.addEventListener("click", () => { grid.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", "false")); b.setAttribute("aria-checked", "true"); set(f.name, c); });
            grid.append(b);
          });
          return grid;
        }
        case "file": {
          const inp = el("input", { type: "file", accept: f.accept || "", id, hidden: true });
          const prev = el("img", { alt: "", hidden: true });
          const name = el("span", { text: "Ninguna imagen elegida" });
          const btn = el("button.btn.btn-sm", { type: "button", onclick: () => inp.click() }, [icon("image"), "Elegir"]);
          inp.addEventListener("change", () => {
            const file = inp.files[0];
            if (!file) return;
            files[f.name] = file;
            name.textContent = file.name;
            prev.src = URL.createObjectURL(file);
            prev.hidden = false;
            onChange(f.name, file, values);
          });
          return el("div.opt-file", {}, [prev, name, btn, inp]);
        }
        case "ranges": {
          const list = el("div.ranges-list");
          const draw = () => {
            list.replaceChildren();
            (values[f.name] || []).forEach((r, i) => {
              const a = el("input.input", { type: "number", min: 1, max: ctx.pageCount, value: r.from, "aria-label": `Rango ${i + 1}: desde` });
              const b = el("input.input", { type: "number", min: 1, max: ctx.pageCount, value: r.to, "aria-label": `Rango ${i + 1}: hasta` });
              a.addEventListener("input", () => { r.from = Number(a.value); set(f.name, values[f.name]); });
              b.addEventListener("input", () => { r.to = Number(b.value); set(f.name, values[f.name]); });
              const del = el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Quitar rango", disabled: values[f.name].length < 2, onclick: () => { values[f.name].splice(i, 1); draw(); set(f.name, values[f.name]); } }, [icon("x")]);
              list.append(el("div.range-item", {}, [el("span.tag", { style: { background: RANGE_COLORS[i % RANGE_COLORS.length] }, text: i + 1 }), a, el("span", { text: "a" }), b, del]));
            });
            list.append(el("button.btn.btn-sm", { type: "button", onclick: () => {
              const last = values[f.name][values[f.name].length - 1];
              const start = last ? Math.min(last.to + 1, ctx.pageCount) : 1;
              values[f.name].push({ from: start, to: ctx.pageCount });
              draw(); set(f.name, values[f.name]);
            } }, [icon("plus"), "Agregar rango"]));
          };
          if (!values[f.name]) values[f.name] = [{ from: 1, to: ctx.pageCount }];
          rangeDrawers.push(() => { if (values[f.name].length === 1 && values[f.name][0].from === 1) values[f.name][0].to = ctx.pageCount; draw(); });
          draw();
          return list;
        }
        default:
          return el("span", { text: f.type });
      }
    }

    return {
      values, files, set,
      setInput(name, val) { if (inputs[name]) inputs[name]._bsobSet(val); refresh(); },
      setPageCount(n) { ctx.pageCount = n; rangeDrawers.forEach((d) => d()); },
      validate() {
        for (const { f, row } of rows) {
          if (row.hidden) continue;
          if (f.required && !values[f.name]) return `Completa el campo «${f.label}».`;
          if (f.type === "file" && values.type === "imagen" && !files[f.name]) return `Elige la imagen para «${f.label}».`;
        }
        return null;
      },
    };
  }
  window.Options = { render, RANGE_COLORS };
})();
