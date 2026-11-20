// Reportes de difusiones: gráficos con carga diferida, clic en barras para filtrar, filas clicables.
(function () {
  "use strict";

  const seleccion = {}; // parámetro -> Set de valores elegidos (sentido, tipo, nota, motivo)
  let urlRespondieron = null;

  function crear(etiqueta, clase, texto) {
    const el = document.createElement(etiqueta);
    if (clase) el.className = clase;
    if (texto) el.textContent = texto;
    return el;
  }

  async function cargarGrafico(tarjeta) {
    const lugar = tarjeta.querySelector(".lugar");
    try {
      const r = await fetch(tarjeta.dataset.url, { headers: { "X-Requested-With": "fetch" } });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      lugar.innerHTML = "";
      if (d.vacio) {
        lugar.appendChild(crear("div", "aviso", d.vacio));
        return;
      }
      if (d.subtitulo) lugar.appendChild(crear("p", "suave", d.subtitulo));
      const div = crear("div", "grafico");
      lugar.appendChild(div);
      const layout = Object.assign({}, d.fig.layout, { autosize: true });
      delete layout.width;
      await Plotly.newPlot(div, d.fig.data, layout, { displaylogo: false, responsive: true,
        modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] });
      lugar.appendChild(crear("p", "explicacion", d.explicacion));
      if (d.parametro) {
        div.on("plotly_click", (ev) => {
          const p = ev.points && ev.points[0];
          if (!p) return;
          const valor = String(d.eje === "x" ? p.x : p.y);
          const set = (seleccion[d.parametro] = seleccion[d.parametro] || new Set());
          set.has(valor) ? set.delete(valor) : set.add(valor);
          actualizarRespondieron();
        });
      }
    } catch (e) {
      lugar.innerHTML = "";
      lugar.appendChild(crear("div", "aviso error", "No se pudo cargar el gráfico (" + e.message + ")."));
    }
  }

  async function actualizarRespondieron() {
    const caja = document.getElementById("respondieron");
    if (!caja || !urlRespondieron) return;
    const params = new URLSearchParams();
    let hay = false;
    for (const [k, set] of Object.entries(seleccion)) for (const v of set) { params.append(k, v); hay = true; }
    const ayuda = document.getElementById("respondieron-ayuda");
    if (!hay) { caja.innerHTML = ""; if (ayuda) ayuda.hidden = false; return; }
    if (ayuda) ayuda.hidden = true;
    caja.innerHTML = '<div class="esqueleto" style="height:220px"></div>';
    const r = await fetch(urlRespondieron + "&" + params.toString());
    caja.innerHTML = await r.text();
    const quitar = caja.querySelector("[data-quitar]");
    if (quitar) quitar.addEventListener("click", () => {
      for (const k of Object.keys(seleccion)) delete seleccion[k];
      actualizarRespondieron();
    });
  }

  const QUIETO = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Red de partículas (como el hero de bridge4digital.com): nodos azules unidos por líneas finas.
  function particulas(contenedor) {
    const lienzo = document.createElement("canvas");
    lienzo.className = "particulas";
    lienzo.setAttribute("aria-hidden", "true");
    contenedor.prepend(lienzo);
    const ctx = lienzo.getContext("2d");
    let ancho = 0, alto = 0, nodos = [], visible = true;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    function medir() {
      ancho = contenedor.clientWidth; alto = contenedor.clientHeight;
      lienzo.width = ancho * dpr; lienzo.height = alto * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.max(14, Math.min(60, Math.round(ancho * alto / 9000)));
      nodos = Array.from({ length: n }, () => ({
        x: ancho * (0.45 + Math.random() * 0.55), y: Math.random() * alto,
        vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25, r: 1.2 + Math.random() * 1.6,
      }));
    }
    function dibujar() {
      ctx.clearRect(0, 0, ancho, alto);
      for (let i = 0; i < nodos.length; i++) {
        const a = nodos[i];
        for (let j = i + 1; j < nodos.length; j++) {
          const b = nodos[j], d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 120) {
            ctx.strokeStyle = `rgba(15,69,249,${0.22 * (1 - d / 120)})`;
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      for (const a of nodos) {
        ctx.fillStyle = "rgba(15,69,249,.55)";
        ctx.beginPath(); ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2); ctx.fill();
      }
    }
    function paso() {
      if (visible) {
        for (const a of nodos) {
          a.x += a.vx; a.y += a.vy;
          if (a.x < 0 || a.x > ancho) a.vx *= -1;
          if (a.y < 0 || a.y > alto) a.vy *= -1;
        }
        dibujar();
      }
      if (!QUIETO) requestAnimationFrame(paso);
    }
    medir(); dibujar();
    if (!QUIETO) requestAnimationFrame(paso);
    window.addEventListener("resize", () => { medir(); dibujar(); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((e) => { visible = e[0].isIntersecting; }).observe(contenedor);
    }
  }

  // Números de los indicadores que cuentan desde cero ("118,281" -> 0 … 118,281).
  function contar(el) {
    const texto = el.textContent.trim();
    if (!/^[\d,.]+$/.test(texto)) return;
    const separador = texto.includes(",") ? "," : texto.includes(".") ? "." : "";
    const final = parseInt(texto.replace(/[.,]/g, ""), 10);
    if (!final || QUIETO) return;
    const inicio = performance.now(), dur = 1100;
    const fmt = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, separador);
    function cuadro(t) {
      const p = Math.min(1, (t - inicio) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(final * e));
      if (p < 1) requestAnimationFrame(cuadro); else el.textContent = texto;
    }
    el.textContent = fmt(0);
    requestAnimationFrame(cuadro);
  }

  // Aparición suave al hacer scroll (tarjetas, indicadores, tablas y títulos).
  function aparecer() {
    const elementos = document.querySelectorAll(
      ".contenido .tarjeta, .contenido .kpi, .contenido .tabla-caja, .contenido > h2, .contenido section > h2");
    if (QUIETO || !("IntersectionObserver" in window)) return;
    const obs = new IntersectionObserver((entradas) => {
      for (const e of entradas) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("visible");
        if (e.target.matches(".kpi")) e.target.querySelectorAll(".valor").forEach(contar);
        obs.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px -40px 0px", threshold: 0.08 });
    elementos.forEach((el) => {
      const hermanos = el.parentElement ? Array.from(el.parentElement.children) : [];
      el.style.setProperty("--i", Math.min(hermanos.indexOf(el), 8));
      el.classList.add("aparecer");
      obs.observe(el);
    });
  }

  // Calendarios: rango "desde – hasta" en un solo campo y fechas sueltas, en español y con el estilo de la marca.
  function calendarios() {
    if (!window.flatpickr) return;
    if (flatpickr.l10ns && flatpickr.l10ns.es) flatpickr.localize(flatpickr.l10ns.es);
    const iso = (d) => flatpickr.formatDate(d, "Y-m-d");

    document.querySelectorAll("input[data-rango]").forEach((campo) => {
      const desde = document.getElementById(campo.dataset.desde);
      const hasta = document.getElementById(campo.dataset.hasta);
      const guardar = (fechas) => {
        desde.value = fechas[0] ? iso(fechas[0]) : "";
        hasta.value = fechas[1] ? iso(fechas[1]) : (fechas[0] ? iso(fechas[0]) : "");
      };
      flatpickr(campo, {
        mode: "range", dateFormat: "Y-m-d", altInput: true, altFormat: "j M Y", altInputClass: "entrada-fecha",
        minDate: campo.dataset.min || null, maxDate: campo.dataset.max || null, disableMobile: true,
        defaultDate: [desde.value, hasta.value].filter(Boolean),
        showMonths: window.innerWidth > 720 ? 2 : 1, locale: { rangeSeparator: " – " },
        onChange: (fechas) => { if (fechas.length !== 1) guardar(fechas); },
        onClose: (fechas, _t, inst) => {
          if (fechas.length === 1) { inst.setDate([fechas[0], fechas[0]], true); guardar([fechas[0], fechas[0]]); }
        },
        onReady: (_f, _t, inst) => {
          // Atajos como en los paneles de analítica.
          const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
          const dias = (n) => { const d = new Date(hoy); d.setDate(d.getDate() - n); return d; };
          const atajos = [
            ["Hoy", () => [hoy, hoy]],
            ["Últimos 7 días", () => [dias(6), hoy]],
            ["Últimos 30 días", () => [dias(29), hoy]],
            ["Este mes", () => [new Date(hoy.getFullYear(), hoy.getMonth(), 1), hoy]],
            ["Mes pasado", () => [new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1),
                                   new Date(hoy.getFullYear(), hoy.getMonth(), 0)]],
          ];
          const barra = document.createElement("div");
          barra.className = "atajos-fecha";
          for (const [texto, rango] of atajos) {
            const b = document.createElement("button");
            b.type = "button"; b.textContent = texto;
            b.addEventListener("click", () => {
              // Se ajusta a los días que tienen envíos (el calendario no deja elegir fuera de ese rango).
              const min = inst.config.minDate, max = inst.config.maxDate;
              const r = rango().map((d) => (min && d < min ? min : max && d > max ? max : d));
              inst.setDate(r, true); guardar(r); inst.close();
            });
            barra.appendChild(b);
          }
          const limpiar = document.createElement("button");
          limpiar.type = "button"; limpiar.className = "limpiar"; limpiar.textContent = "Todas las fechas";
          limpiar.addEventListener("click", () => { inst.clear(); guardar([]); inst.close(); });
          barra.appendChild(limpiar);
          inst.calendarContainer.appendChild(barra);
        },
      });
    });

    // Fechas sueltas (fecha de solicitud, etc.): se ven como "5 nov 2026" y se envían como 2026-11-05.
    document.querySelectorAll('input[type="date"]').forEach((campo) => {
      flatpickr(campo, { dateFormat: "Y-m-d", altInput: true, altFormat: "j M Y", altInputClass: "entrada-fecha",
                         disableMobile: true });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    calendarios();
    document.querySelectorAll(".encabezado, .ingreso-hero").forEach(particulas);
    aparecer();
    // Si el menú no entra completo (pantallas medianas), se desplaza para mostrar la sección actual.
    const activo = document.querySelector(".menu a.activo");
    if (activo) activo.scrollIntoView({ block: "nearest", inline: "center" });
    const barra = document.querySelector(".barra");
    if (barra) window.addEventListener("scroll", () => barra.classList.toggle("sombra", window.scrollY > 8), { passive: true });

    const panel = document.getElementById("panel-respuestas");
    if (panel) urlRespondieron = panel.dataset.url;

    // Cada gráfico se pide por separado: la página aparece al instante con su skeleton del mismo alto.
    const tarjetas = document.querySelectorAll(".tarjeta[data-url]");
    if ("IntersectionObserver" in window) {
      const obs = new IntersectionObserver((entradas) => {
        for (const e of entradas) if (e.isIntersecting) { obs.unobserve(e.target); cargarGrafico(e.target); }
      }, { rootMargin: "400px" });
      tarjetas.forEach((t) => obs.observe(t));
    } else tarjetas.forEach(cargarGrafico);

    // Filas clicables (abrir una campaña).
    document.querySelectorAll("tr[data-url]").forEach((tr) => {
      tr.tabIndex = 0;
      tr.addEventListener("click", () => (window.location = tr.dataset.url));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") window.location = tr.dataset.url; });
    });

    // Selects que aplican el filtro al cambiar.
    document.querySelectorAll("select[data-auto]").forEach((s) =>
      s.addEventListener("change", () => s.form.submit()));

    // Confirmación de acciones peligrosas.
    document.querySelectorAll("form[data-confirmar]").forEach((f) =>
      f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirmar)) e.preventDefault(); }));

    // Botones que muestran "trabajando…" (descargas y sincronización tardan unos segundos).
    document.querySelectorAll("[data-espera]").forEach((b) =>
      b.addEventListener("click", () => {
        const texto = b.textContent;
        b.textContent = b.dataset.espera;
        setTimeout(() => (b.textContent = texto), 25000);
      }));
  });
})();
