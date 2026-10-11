/* BSOBPDF — utilidades compartidas por todas las páginas */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /** Crea un elemento: el("button.btn.btn-primary", {type:"button", onclick}, ["Texto"]) */
  function el(spec, attrs = {}, children = []) {
    const [tag, ...classes] = spec.split(".");
    const node = document.createElement(tag || "div");
    if (classes.length) node.className = classes.join(" ");
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "html") node.innerHTML = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
      else if (k === "dataset") Object.assign(node.dataset, v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of [].concat(children)) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function icon(name, cls = "ico") {
    const svg = (window.BSOB && BSOB.icons[name]) || "";
    const tpl = document.createElement("template");
    tpl.innerHTML = svg.trim();
    const node = tpl.content.firstElementChild || document.createElement("span");
    if (cls !== "ico") node.setAttribute("class", cls);
    return node;
  }

  function fmtSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1).replace(".", ",") + " KB";
    return (n / 1048576).toFixed(1).replace(".", ",") + " MB";
  }

  function toast(msg, type = "info", ms = 5000) {
    const zone = $("#toasts");
    if (!zone) return alert(msg);
    const t = el("div.toast" + (type === "error" ? ".error" : ""), {}, [
      icon(type === "error" ? "triangle-alert" : "circle-check"), el("span", { text: msg })]);
    zone.append(t);
    setTimeout(() => t.remove(), ms);
  }

  /* ---------------------------------------------------------- traspaso de archivos entre páginas (IndexedDB) */
  const Handoff = {
    _db() {
      return new Promise((resolve, reject) => {
        const req = indexedDB.open("bsobpdf", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("handoff");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    },
    async put(files) {
      const db = await this._db();
      const id = Math.random().toString(36).slice(2, 10);
      const items = await Promise.all(files.map(async (f) => ({ name: f.name, type: f.type, data: await f.arrayBuffer() })));
      await new Promise((res, rej) => {
        const tx = db.transaction("handoff", "readwrite");
        tx.objectStore("handoff").put(items, id);
        tx.oncomplete = res; tx.onerror = () => rej(tx.error);
      });
      return id;
    },
    async take(id) {
      try {
        const db = await this._db();
        const items = await new Promise((res, rej) => {
          const tx = db.transaction("handoff", "readwrite");
          const st = tx.objectStore("handoff");
          const r = st.get(id);
          r.onsuccess = () => { st.delete(id); res(r.result || []); };
          r.onerror = () => rej(r.error);
        });
        return items.map((it) => new File([it.data], it.name, { type: it.type }));
      } catch (e) { return []; }
    },
  };

  /* ---------------------------------------------------------- envío con progreso */
  function postForm(url, form, onProgress) {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
      xhr.upload.onload = () => onProgress && onProgress(1, true);
      xhr.onload = () => {
        const body = xhr.response || {};
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else resolve({ ok: false, error: body.error || `El servidor respondió con el error ${xhr.status}.` });
      };
      xhr.onerror = () => resolve({ ok: false, error: "No se pudo conectar con BSOBPDF. ¿Sigue abierta la ventana del programa?" });
      xhr.send(form);
    });
  }

  /* ---------------------------------------------------------- PDF.js */
  const PDF = {
    ready: false,
    init() {
      if (this.ready || !window.pdfjsLib) return !!window.pdfjsLib;
      pdfjsLib.GlobalWorkerOptions.workerSrc = BSOB.static + "vendor/pdfjs/pdf.worker.min.js";
      this.ready = true;
      return true;
    },
    async open(file, password) {
      this.init();
      const data = new Uint8Array(await file.arrayBuffer());
      const task = pdfjsLib.getDocument({ data, password, isEvalSupported: false, disableFontFace: false });
      return task.promise;
    },
    _queue: Promise.resolve(),
    /** Dibuja una página en un canvas que quepa en maxW × maxH (en píxeles CSS). */
    render(pdf, pageNo, maxW, maxH, extraRotation = 0) {
      const job = async () => {
        const page = await pdf.getPage(pageNo);
        const base = page.getViewport({ scale: 1, rotation: (page.rotate + extraRotation) % 360 });
        const scale = Math.min(maxW / base.width, maxH / base.height);
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const vp = page.getViewport({ scale: scale * dpr, rotation: (page.rotate + extraRotation) % 360 });
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(vp.width); canvas.height = Math.floor(vp.height);
        canvas.style.width = Math.floor(vp.width / dpr) + "px";
        canvas.style.height = Math.floor(vp.height / dpr) + "px";
        await page.render({ canvasContext: canvas.getContext("2d"), viewport: vp }).promise;
        return canvas;
      };
      const p = this._queue.then(job, job);
      this._queue = p.catch(() => {});
      return p;
    },
  };

  /* ---------------------------------------------------------- diálogo modal */
  function modal({ title, body, actions = [], onClose, wide = false }) {
    const close = () => { back.remove(); document.removeEventListener("keydown", onKey); onClose && onClose(); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    const box = el("div.modal", { role: "dialog", "aria-modal": "true", "aria-label": title, style: wide ? { width: "min(820px,100%)" } : {} }, [
      el("div.modal-head", {}, [el("h2", { text: title }),
        el("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": "Cerrar", onclick: close }, [icon("x")])]),
      el("div.modal-body", {}, [body]),
      actions.length ? el("div.modal-foot", {}, actions.map((a) => el("button.btn" + (a.primary ? ".btn-primary" : ""), {
        type: "button", onclick: () => { if (a.onClick && a.onClick() === false) return; close(); } }, [a.label]))) : null,
    ]);
    const back = el("div.modal-back", { onclick: (e) => { if (e.target === back) close(); } }, [box]);
    document.body.append(back);
    document.addEventListener("keydown", onKey);
    setTimeout(() => { const f = box.querySelector("input, textarea, button:not(.btn-ghost)"); f && f.focus(); }, 30);
    return { close, box };
  }

  /* ---------------------------------------------------------- almacenamiento local seguro */
  const store = {
    get(k, d = null) { try { const v = localStorage.getItem("bsob:" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("bsob:" + k, JSON.stringify(v)); } catch (e) { /* sin almacenamiento */ } },
  };

  /* ---------------------------------------------------------- cabecera */
  document.addEventListener("DOMContentLoaded", () => {
    const btn = $("#mega-btn"), mega = $("#mega");
    if (btn && mega) {
      btn.addEventListener("click", () => {
        const open = mega.hidden;
        mega.hidden = !open;
        btn.setAttribute("aria-expanded", String(open));
      });
      document.addEventListener("click", (e) => {
        if (!mega.hidden && !mega.contains(e.target) && !btn.contains(e.target)) { mega.hidden = true; btn.setAttribute("aria-expanded", "false"); }
      });
      document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !mega.hidden) { mega.hidden = true; btn.setAttribute("aria-expanded", "false"); btn.focus(); } });
    }
    const mb = $("#menu-btn"), nav = $("#main-nav");
    if (mb && nav) mb.addEventListener("click", () => { nav.classList.toggle("open"); mb.setAttribute("aria-expanded", String(nav.classList.contains("open"))); });
  });

  window.U = { $, $$, el, icon, fmtSize, toast, Handoff, postForm, PDF, modal, store };
})();
