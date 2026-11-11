// Direcciones de los servicios (los puertos que publica el docker-compose)
const API_USUARIOS = `http://${location.hostname}:5001`;
const API_ESPACIOS = `http://${location.hostname}:5002`;
const API_RESERVAS = `http://${location.hostname}:5003`;
const TIEMPO_MAXIMO_MS = 5000;

const $ = (id) => document.getElementById(id);
const moneda = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const pesos = (n) => moneda.format(n);

// Evita que un texto de la base de datos se interprete como HTML
function esc(texto) {
  const div = document.createElement("div");
  div.textContent = texto ?? "";
  return div.innerHTML;
}

// fetch con timeout: si el servicio no responde a tiempo se corta la espera
async function api(base, ruta, opciones = {}) {
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), TIEMPO_MAXIMO_MS);
  try {
    const respuesta = await fetch(base + ruta, {
      ...opciones,
      headers: opciones.body ? { "Content-Type": "application/json" } : undefined,
      body: opciones.body ? JSON.stringify(opciones.body) : undefined,
      signal: control.signal
    });
    let datos = null;
    try { datos = await respuesta.json(); } catch { /* respuesta sin cuerpo */ }
    return { ok: respuesta.ok, estado: respuesta.status, datos };
  } catch (e) {
    const motivo = e.name === "AbortError" ? "El servicio tardó demasiado en responder" : "No se pudo conectar con el servicio";
    return { ok: false, estado: 0, datos: { Mensaje: motivo } };
  } finally {
    clearTimeout(reloj);
  }
}

const mensajeDe = (r) => r.datos?.Mensaje || r.datos?.mensaje || "Ocurrió un error inesperado";

function fechaISO(fecha) {
  const m = String(fecha.getMonth() + 1).padStart(2, "0");
  const d = String(fecha.getDate()).padStart(2, "0");
  return `${fecha.getFullYear()}-${m}-${d}`;
}

function formatoFecha(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
}

// ---------------- Sesión (login) ----------------

let sesion = null;  // {id, nombre, apellido, correo}
try { sesion = JSON.parse(localStorage.getItem("sesion")); } catch { sesion = null; }

let despuesDeIngresar = null;  // acción pendiente que se retoma al iniciar sesión

function pintarSesion() {
  $("btn-sesion").textContent = sesion ? `Salir (${sesion.nombre})` : "Ingresar";
}

function guardarSesion(usuario) {
  sesion = { id: usuario.id, nombre: usuario.nombre, apellido: usuario.apellido, correo: usuario.correo };
  localStorage.setItem("sesion", JSON.stringify(sesion));
  pintarSesion();
}

function cerrarSesion() {
  sesion = null;
  localStorage.removeItem("sesion");
  pintarSesion();
}

function abrirAuth(luego) {
  despuesDeIngresar = luego || null;
  mostrarFormAuth("login");
  $("dlg-auth").showModal();
}

function mostrarFormAuth(cual) {
  $("form-login").hidden = cual !== "login";
  $("form-registro").hidden = cual !== "registro";
  $("error-login").hidden = true;
  $("error-registro").hidden = true;
}

function errorAuth(id, texto) {
  $(id).textContent = texto;
  $(id).hidden = false;
}

async function iniciarSesion(correo, password) {
  const r = await api(API_USUARIOS, "/login", { method: "POST", body: { correo, password } });
  if (r.ok) guardarSesion(r.datos.usuario);
  return r;
}

function terminarAuth() {
  $("dlg-auth").close();
  const accion = despuesDeIngresar;
  despuesDeIngresar = null;
  if (accion) accion();
}

async function enviarLogin(evento) {
  evento.preventDefault();
  const r = await iniciarSesion($("l-correo").value, $("l-password").value);
  if (!r.ok) return errorAuth("error-login", mensajeDe(r));
  $("form-login").reset();
  terminarAuth();
}

async function enviarRegistro(evento) {
  evento.preventDefault();
  const correo = $("g-correo").value.trim();
  const password = $("g-password").value;
  const creado = await api(API_USUARIOS, "/usuarios", {
    method: "POST",
    body: {
      nombre: $("g-nombre").value.trim(),
      apellido: $("g-apellido").value.trim(),
      correo,
      telefono: $("g-telefono").value.trim() || null,
      password
    }
  });
  if (!creado.ok) return errorAuth("error-registro", mensajeDe(creado));
  const r = await iniciarSesion(correo, password);
  if (!r.ok) return errorAuth("error-registro", mensajeDe(r));
  $("form-registro").reset();
  terminarAuth();
}

// ---------------- Hoteles ----------------

async function cargarHoteles() {
  const lista = $("lista-hoteles");
  const r = await api(API_ESPACIOS, "/hoteles");
  if (!r.ok) {
    lista.innerHTML = `<p class="vacio">No pudimos cargar los hoteles. ${esc(mensajeDe(r))}.</p>`;
    return;
  }
  if (r.datos.length === 0) {
    lista.innerHTML = `<p class="vacio">Todavía no hay hoteles registrados.</p>`;
    return;
  }

  // Ciudades del buscador
  const ciudades = [...new Set(r.datos.map((h) => h.ciudad))].sort();
  for (const ciudad of ciudades) {
    $("ciudad").insertAdjacentHTML("beforeend", `<option>${esc(ciudad)}</option>`);
  }

  // Precio "desde" de cada hotel (consulta sus habitaciones)
  const detalles = await Promise.all(r.datos.map((h) => api(API_ESPACIOS, `/hoteles/${h.id}`)));
  lista.innerHTML = r.datos.map((h, i) => {
    const habitaciones = detalles[i].ok ? detalles[i].datos.habitaciones.filter((x) => x.estado === "activa") : [];
    const desde = habitaciones.length ? Math.min(...habitaciones.map((x) => x.precio_noche)) : null;
    return `
      <article class="hotel">
        <div class="foto f${(i % 3) + 1}" aria-hidden="true"></div>
        <div>
          <h3>${esc(h.nombre)}</h3>
          <p>${esc(h.ciudad)} · ${esc(h.direccion || "")}${h.servicios ? " · " + esc(h.servicios) : ""}</p>
        </div>
        <div class="precio">
          ${desde !== null ? `<strong>${pesos(desde)}</strong>por noche` : "Sin habitaciones"}
          <button class="enlace" type="button" data-hotel="${h.id}" data-ciudad="${esc(h.ciudad)}">Ver disponibilidad</button>
        </div>
      </article>`;
  }).join("");
}

// ---------------- Búsqueda de disponibilidad ----------------

let ultimaBusqueda = null;

async function buscar(evento) {
  evento.preventDefault();
  const entrada = $("entrada").value;
  const salida = $("salida").value;
  const huespedes = $("huespedes").value;
  const ciudad = $("ciudad").value;

  const params = new URLSearchParams({ entrada, salida, huespedes });
  if (ciudad) params.set("ciudad", ciudad);

  mostrarResultados(`<p class="vacio">Buscando habitaciones…</p>`, "Habitaciones libres");
  const r = await api(API_ESPACIOS, `/hoteles/disponibles?${params}`);
  if (!r.ok) {
    mostrarResultados(`<p class="vacio error-texto">${esc(mensajeDe(r))}</p>`, "Habitaciones libres");
    return;
  }

  ultimaBusqueda = { ...r.datos, huespedes: Number(huespedes) };
  const hoteles = r.datos.hoteles;
  const titulo = `${hoteles.length ? "Habitaciones libres" : "Sin habitaciones libres"} · ${r.datos.noches} ${r.datos.noches === 1 ? "noche" : "noches"}`;
  if (hoteles.length === 0) {
    mostrarResultados(`<p class="vacio">No hay habitaciones libres para ${esc(huespedes)} huésped(es) del ${formatoFecha(entrada)} al ${formatoFecha(salida)}. Prueba con otras fechas.</p>`, titulo);
    return;
  }

  const html = hoteles.map((h) => `
    <article class="resultado">
      <h3>${esc(h.hotel)} <span class="ciudad">${esc(h.ciudad)}</span></h3>
      ${h.habitaciones.map((x) => `
        <div class="habitacion">
          <div>
            <strong>Habitación ${esc(x.numero)} · ${esc(x.tipo)}</strong>
            <p>Hasta ${x.capacidad} huésped(es) · ${pesos(x.precio_noche)} por noche</p>
          </div>
          <div class="precio"><strong>${pesos(x.precio_total)}</strong>total
            <button class="boton" type="button" data-reservar="${x.habitacion_id}" data-hotel-nombre="${esc(h.hotel)}" data-hab="${esc(x.numero + " · " + x.tipo)}" data-total="${x.precio_total}">Reservar</button>
          </div>
        </div>`).join("")}
    </article>`).join("");
  mostrarResultados(html, titulo);
}

function mostrarResultados(html, titulo) {
  $("resultados").hidden = false;
  $("resultados-titulo").textContent = titulo;
  $("resultados-lista").innerHTML = html;
  $("resultados").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------- Reserva (servicio de Reservas) ----------------

let reserva = null;     // datos de la reserva en curso
let temporizador = null;

const dlgReserva = $("dlg-reserva");
const pasos = ["paso-datos", "paso-confirmar", "paso-listo", "paso-fallo"];

function irAPaso(id) {
  for (const p of pasos) $(p).hidden = p !== id;
}

function resumenHTML(r) {
  return `
    <strong>${esc(r.hotel)}</strong>
    <span>Habitación ${esc(r.habitacion)}</span>
    <span>${formatoFecha(r.entrada)} → ${formatoFecha(r.salida)}</span>
    <span class="total">${pesos(r.total)}</span>`;
}

function abrirReserva(boton) {
  // Para reservar hay que haber iniciado sesión; al ingresar se retoma la reserva
  if (!sesion) return abrirAuth(() => abrirReserva(boton));

  reserva = {
    habitacion_id: Number(boton.dataset.reservar),
    hotel: boton.dataset.hotelNombre,
    habitacion: boton.dataset.hab,
    total: Number(boton.dataset.total),
    entrada: ultimaBusqueda.entrada,
    salida: ultimaBusqueda.salida,
    huespedes: ultimaBusqueda.huespedes
  };
  $("resumen").innerHTML = resumenHTML(reserva);
  $("r-huesped").textContent = `${sesion.nombre} ${sesion.apellido}`;
  $("error-datos").hidden = true;
  $("btn-apartar").disabled = false;
  $("btn-apartar").textContent = "Apartar por 15 minutos";
  irAPaso("paso-datos");
  dlgReserva.showModal();
}

async function apartar(evento) {
  evento.preventDefault();
  const boton = $("btn-apartar");
  boton.disabled = true;
  boton.textContent = "Apartando…";
  $("error-datos").hidden = true;

  const r = await api(API_RESERVAS, "/reservas", {
    method: "POST",
    body: {
      usuario_id: sesion.id,
      habitacion_id: reserva.habitacion_id,
      entrada: reserva.entrada,
      salida: reserva.salida,
      huespedes: reserva.huespedes
    }
  });
  if (!r.ok) {
    $("error-datos").textContent = r.estado === 409
      ? "Alguien acaba de tomar esta habitación en esas fechas. Elige otra."
      : mensajeDe(r);
    $("error-datos").hidden = false;
    boton.disabled = false;
    boton.textContent = "Apartar por 15 minutos";
    return;
  }

  reserva.id = r.datos.id;
  reserva.total = r.datos.total;
  reserva.vence = Date.now() + r.datos.minutos_para_confirmar * 60000;
  $("resumen2").innerHTML = resumenHTML(reserva);
  $("error-confirmar").hidden = true;
  $("btn-confirmar").disabled = false;
  irAPaso("paso-confirmar");
  iniciarReloj();
}

function iniciarReloj() {
  detenerReloj();
  const pintar = () => {
    const restante = Math.max(0, reserva.vence - Date.now());
    const min = String(Math.floor(restante / 60000)).padStart(2, "0");
    const seg = String(Math.floor((restante % 60000) / 1000)).padStart(2, "0");
    $("reloj").textContent = `${min}:${seg}`;
    if (restante === 0) {
      detenerReloj();
      fallo("Se acabó el tiempo", "La habitación se liberó porque pasaron los 15 minutos. Puedes buscarla de nuevo.");
    }
  };
  pintar();
  temporizador = setInterval(pintar, 1000);
}

function detenerReloj() {
  clearInterval(temporizador);
  temporizador = null;
}

function fallo(titulo, texto) {
  detenerReloj();
  $("fallo-titulo").textContent = titulo;
  $("fallo-texto").textContent = texto;
  irAPaso("paso-fallo");
}

async function confirmar() {
  const boton = $("btn-confirmar");
  boton.disabled = true;
  const r = await api(API_RESERVAS, `/reservas/${reserva.id}/confirmar`, { method: "POST" });
  if (!r.ok) {
    if (r.estado === 409 || r.estado === 404) return fallo("Reserva vencida", mensajeDe(r));
    $("error-confirmar").textContent = mensajeDe(r);
    $("error-confirmar").hidden = false;
    boton.disabled = false;
    return;
  }
  detenerReloj();
  $("resumen3").innerHTML = resumenHTML(reserva);
  $("codigo").textContent = `#${reserva.id}`;
  irAPaso("paso-listo");
}

async function liberar() {
  detenerReloj();
  await api(API_RESERVAS, `/reservas/${reserva.id}/cancelar`, { method: "POST" });
  irAPaso("paso-fallo");
  dlgReserva.close();
}

// ---------------- Mis reservas ----------------

const ESTADOS = { pendiente: "Pendiente", confirmada: "Confirmada", cancelada: "Cancelada", expirada: "Vencida" };

async function pintarMisReservas() {
  const cont = $("mis-reservas");
  if (!sesion) {
    cont.innerHTML = `<p class="vacio">Ingresa para ver tus reservas.</p><button class="boton ancho-boton" type="button" id="mr-ingresar">Ingresar</button>`;
    return;
  }
  cont.innerHTML = `<p class="vacio">Cargando…</p>`;
  const r = await api(API_RESERVAS, `/reservas?usuario_id=${sesion.id}`);
  if (!r.ok) {
    cont.innerHTML = `<p class="vacio error-texto">${esc(mensajeDe(r))}.</p>`;
    return;
  }
  cont.innerHTML = r.datos.length === 0
    ? `<p class="vacio">Todavía no tienes reservas.</p>`
    : r.datos.map((x) => `
        <div class="reserva-item">
          <div>
            <strong>${esc(x.hotel)}</strong> <span class="etiqueta ${esc(x.estado)}">${esc(ESTADOS[x.estado] || x.estado)}</span>
            <p>Habitación ${esc(x.habitacion)} · ${formatoFecha(x.fecha_entrada)} → ${formatoFecha(x.fecha_salida)}</p>
            <p>Reserva #${x.id} · ${pesos(x.total)}</p>
          </div>
          ${x.estado === "confirmada" || x.estado === "pendiente"
            ? `<button class="enlace" type="button" data-cancelar="${x.id}">Cancelar</button>` : ""}
        </div>`).join("");
}

async function cancelarReserva(id) {
  const r = await api(API_RESERVAS, `/reservas/${id}/cancelar`, { method: "POST" });
  if (!r.ok && r.estado !== 409) {
    alert(`No se pudo cancelar: ${mensajeDe(r)}`);
    return;
  }
  pintarMisReservas();
}

// ---------------- Estado de los servicios ----------------

function chip(id, texto, nivel) {
  const el = $(id);
  el.textContent = texto;
  el.className = `chip ${nivel}`;
}

async function revisarServicios() {
  const [usuarios, espacios, reservas, cEspacios, cReservas] = await Promise.all([
    api(API_USUARIOS, "/usuarios"),
    api(API_ESPACIOS, "/hoteles"),
    api(API_RESERVAS, "/reservas?usuario_id=0"),
    api(API_ESPACIOS, "/circuito/usuarios"),
    api(API_RESERVAS, "/circuito")
  ]);
  const linea = (nombre, r) => chip(`chip-${nombre}`, `${nombre[0].toUpperCase() + nombre.slice(1)}: ${r.ok ? "en línea" : "sin respuesta"}`, r.ok ? "bien" : "mal");
  linea("usuarios", usuarios);
  linea("espacios", espacios);
  linea("reservas", reservas);

  // Estado de todos los circuit breakers: si alguno está abierto, se muestra
  const estados = [];
  if (cEspacios.ok) estados.push(cEspacios.datos.estado);
  if (cReservas.ok) estados.push(...Object.values(cReservas.datos).map((c) => c.estado));
  if (estados.length === 0) return chip("chip-circuito", "Circuitos: sin datos", "mal");
  if (estados.includes("OPEN")) return chip("chip-circuito", "Circuitos: hay uno abierto", "mal");
  if (estados.includes("HALF-OPEN")) return chip("chip-circuito", "Circuitos: probando recuperación", "medio");
  chip("chip-circuito", "Circuitos: cerrados (normal)", "bien");
}

// ---------------- Eventos ----------------

function iniciar() {
  const hoy = new Date();
  const manana = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + 1);
  const pasado = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + 3);
  $("entrada").min = fechaISO(hoy);
  $("entrada").value = fechaISO(manana);
  $("salida").value = fechaISO(pasado);
  $("entrada").addEventListener("change", () => {
    $("salida").min = $("entrada").value;
    if ($("salida").value <= $("entrada").value) {
      const [a, m, d] = $("entrada").value.split("-").map(Number);
      $("salida").value = fechaISO(new Date(a, m - 1, d + 1));
    }
  });
  $("salida").min = $("entrada").value;

  pintarSesion();
  $("buscador").addEventListener("submit", buscar);
  $("limpiar-resultados").addEventListener("click", () => { $("resultados").hidden = true; });
  $("paso-datos").addEventListener("submit", apartar);
  $("btn-confirmar").addEventListener("click", confirmar);
  $("btn-liberar").addEventListener("click", liberar);
  $("form-login").addEventListener("submit", enviarLogin);
  $("form-registro").addEventListener("submit", enviarRegistro);
  $("ir-registro").addEventListener("click", () => mostrarFormAuth("registro"));
  $("ir-login").addEventListener("click", () => mostrarFormAuth("login"));
  $("btn-sesion").addEventListener("click", () => (sesion ? cerrarSesion() : abrirAuth()));
  $("abrir-reservas").addEventListener("click", () => { pintarMisReservas(); $("dlg-mis-reservas").showModal(); });

  document.addEventListener("click", (e) => {
    const reservar = e.target.closest("[data-reservar]");
    if (reservar) return abrirReserva(reservar);
    const cancelar = e.target.closest("[data-cancelar]");
    if (cancelar) return cancelarReserva(cancelar.dataset.cancelar);
    if (e.target.closest("#mr-ingresar")) {
      $("dlg-mis-reservas").close();
      return abrirAuth(() => { pintarMisReservas(); $("dlg-mis-reservas").showModal(); });
    }
    const hotel = e.target.closest("[data-hotel]");
    if (hotel) {
      $("ciudad").value = hotel.dataset.ciudad;
      $("buscador").scrollIntoView({ behavior: "smooth" });
      return $("buscador").requestSubmit();
    }
    if (e.target.closest("[data-cerrar]")) e.target.closest("dialog").close();
  });

  // Si cierran la ventana con una habitación apartada, se cancela para no bloquearla 15 minutos
  dlgReserva.addEventListener("close", () => {
    if (!$("paso-confirmar").hidden && reserva?.id) {
      api(API_RESERVAS, `/reservas/${reserva.id}/cancelar`, { method: "POST" });
    }
    detenerReloj();
  });

  cargarHoteles();
  revisarServicios();
  setInterval(revisarServicios, 15000);
}

iniciar();
