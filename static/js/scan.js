/* BSOBPDF — Escanear a PDF: cámara del computador o del celular (por código QR) */
(function () {
  "use strict";
  const { $, $$, el, icon, toast, postForm } = U;
  let A, S, dom = {}, stream = null, session = null, poll = null, seen = new Set();

  function mount(stage, api) {
    A = api; S = api.S;
    const sid = new URLSearchParams(location.search).get("sesion");
    if (sid) { phoneMode(stage, sid); return; }
    stage.className = "stage work-stage";
    stage.replaceChildren();
    const main = el("div.work-main");
    dom.aside = el("aside.sidebar", { "aria-label": "Opciones" });
    stage.append(main, dom.aside);

    // Cámara del computador
    dom.video = el("video", { autoplay: true, playsinline: true, muted: true, hidden: true });
    dom.camBtn = el("button.btn.btn-primary", { type: "button", onclick: startCamera }, [icon("camera"), "Encender la cámara"]);
    dom.shotBtn = el("button.btn.btn-primary", { type: "button", hidden: true, onclick: capture }, [icon("camera"), "Capturar página"]);
    const camPanel = el("div.scan-panel", {}, [
      el("h3", {}, [icon("laptop"), "Con este computador"]),
      el("p.hint", { text: "Pon la hoja frente a la cámara, con buena luz, y captura cada página." }),
      dom.video, el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap" } }, [dom.camBtn, dom.shotBtn,
        el("button.btn", { type: "button", onclick: () => A.pickFiles() }, [icon("image"), "Subir fotos"])]),
    ]);
    // Celular
    dom.qr = el("div.qr", {}, [el("span.hint", { text: "Generando código…" })]);
    dom.qrUrl = el("p.qr-url");
    dom.phoneStatus = el("p.hint", { text: "Esperando fotos del celular…" });
    const phonePanel = el("div.scan-panel", {}, [
      el("h3", {}, [icon("smartphone"), "Con tu celular"]),
      el("div.qr-box", {}, [dom.qr, el("div", { style: { display: "grid", gap: "8px" } }, [
        el("p", { text: "Escanea el código con la cámara del celular. El celular debe estar en la misma red Wi‑Fi que este computador." }),
        dom.qrUrl, dom.phoneStatus])]),
    ]);
    dom.grid = el("div.file-grid");
    dom.head = el("div.work-head");
    main.append(el("div.scan-panels", {}, [camPanel, phonePanel]), dom.head, dom.grid);
    newSession();
    refresh();
  }

  function refresh() {
    if (!dom.grid) return;
    dom.head.replaceChildren(el("h2", { text: S.files.length ? `${S.files.length} página(s) escaneada(s)` : "Aún no hay páginas" }),
      el("span.meta", { text: S.files.length ? "Arrastra para ordenar" : "Captura o recibe fotos para empezar" }));
    dom.grid.replaceChildren();
    S.files.forEach((item, idx) => {
      if (!item.url) item.url = URL.createObjectURL(item.file);
      const card = el("div.fcard", { draggable: "true", dataset: { id: item.id } }, [
        el("div.fthumb", {}, [el("img", { src: item.url, alt: `Página ${idx + 1}` })]),
        el("span.order-n", { text: idx + 1 }),
        el("div.fname", { text: `Página ${idx + 1}` }),
        el("div.fcard-actions", {}, [el("button", { type: "button", "aria-label": "Quitar", onclick: () => { S.files.splice(idx, 1); refresh(); } }, [icon("x")])]),
      ]);
      card.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/bsob", String(item.id)));
      card.addEventListener("dragover", (e) => e.preventDefault());
      card.addEventListener("drop", (e) => {
        e.preventDefault();
        const from = S.files.findIndex((f) => String(f.id) === e.dataTransfer.getData("text/bsob"));
        if (from < 0) return;
        const [m] = S.files.splice(from, 1);
        S.files.splice(idx, 0, m);
        refresh();
      });
      dom.grid.append(card);
    });
    const { btn } = A.buildSidebar(dom.aside);
    btn.disabled = !S.files.length;
  }

  // ---------------------------------------------------------------- cámara del PC
  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Este navegador no permite usar la cámara aquí. Usa «Subir fotos» o el celular.", "error", 8000);
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false });
      dom.video.srcObject = stream;
      dom.video.hidden = false; dom.camBtn.hidden = true; dom.shotBtn.hidden = false;
    } catch (e) {
      toast("No se pudo encender la cámara. Revisa el permiso del navegador o si otra aplicación la está usando.", "error", 8000);
    }
  }
  function capture() {
    const v = dom.video;
    if (!v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    c.toBlob((b) => {
      A.addFiles([new File([b], `camara_${Date.now()}.jpg`, { type: "image/jpeg" })]);
      v.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: 250 });
    }, "image/jpeg", 0.92);
  }

  // ---------------------------------------------------------------- sesión con el celular
  async function newSession() {
    try {
      const j = await (await fetch("/api/escaneo/nueva", { method: "POST" })).json();
      session = j.sid;
      dom.qr.innerHTML = j.qr;
      dom.qrUrl.textContent = j.url;
      if (j.local) dom.phoneStatus.textContent = "No se detectó la red local: abre BSOBPDF en el celular escribiendo la dirección de tu PC.";
      poll = setInterval(checkPhone, 2000);
    } catch (e) {
      dom.qr.replaceChildren(el("span.hint", { text: "No disponible" }));
    }
  }
  async function checkPhone() {
    if (!session || document.hidden) return;
    try {
      const j = await (await fetch(`/api/escaneo/${session}`)).json();
      const fresh = (j.files || []).filter((f) => !seen.has(f.name));
      if (!fresh.length) return;
      fresh.forEach((f) => seen.add(f.name));
      const files = await Promise.all(fresh.map(async (f) => new File([await (await fetch(f.url)).blob()], f.name, { type: "image/jpeg" })));
      dom.phoneStatus.textContent = `Recibidas ${seen.size} foto(s) del celular.`;
      A.addFiles(files);
    } catch (e) { /* reintenta en el siguiente ciclo */ }
  }

  // ---------------------------------------------------------------- modo celular
  function phoneMode(stage, sid) {
    $("#st-upload").hidden = true;
    stage.className = "stage";
    stage.hidden = false;
    const shots = el("div.phone-shots");
    const status = el("p", { text: "Toma una foto de cada página. Aparecerán en tu computador." });
    const cam = el("input", { type: "file", accept: "image/*", capture: "environment", hidden: true });
    const gal = el("input", { type: "file", accept: "image/*", multiple: true, hidden: true });
    let sent = 0;
    const local = [];
    const send = async (files) => {
      if (!files.length) return;
      const fd = new FormData();
      Array.from(files).forEach((f) => { fd.append("files", f, f.name || "foto.jpg"); local.push(f); shots.append(el("img", { src: URL.createObjectURL(f), alt: "" })); });
      status.textContent = "Enviando…";
      const r = await postForm(`/api/escaneo/${sid}`, fd);
      if (r.ok) { sent += r.added; status.textContent = `${sent} foto(s) enviadas a tu computador.`; }
      else status.textContent = r.error || "No se pudo enviar. Revisa la conexión Wi‑Fi.";
    };
    cam.addEventListener("change", () => { send(cam.files); cam.value = ""; });
    gal.addEventListener("change", () => { send(gal.files); gal.value = ""; });
    stage.replaceChildren(el("div.phone-mode", {}, [
      el("span.sheet.lg.cat-organizar", { style: { margin: "0 auto" } }, [icon("scan-line")]),
      el("h1", { text: "Escanear con el celular", style: { fontSize: "2rem" } }),
      status,
      el("button.btn.btn-primary.btn-xl", { type: "button", onclick: () => cam.click() }, [icon("camera"), "Tomar foto"]),
      el("button.btn", { type: "button", onclick: () => gal.click() }, [icon("image"), "Elegir de la galería"]),
      shots,
      el("button.btn.btn-ghost", { type: "button", onclick: () => {
        if (!local.length) { toast("Primero toma alguna foto.", "error"); return; }
        history.replaceState(null, "", location.pathname);
        A.addFiles(local.splice(0)).then(() => { dom.grid = null; mountLocal(stage); });
      } }, ["Crear el PDF en este celular"]),
      cam, gal,
    ]));
  }
  function mountLocal(stage) { mount(stage, A); }

  window.ScanUI = { mount, refresh };
})();
