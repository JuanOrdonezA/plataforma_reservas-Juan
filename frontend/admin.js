// Panel de administración: CRUD de usuarios, hoteles, habitaciones, ocupaciones y reservas
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

function formatoFecha(iso) {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
}

function avisar(texto, error = false) {
  const t = $("toast");
  t.textContent = texto;
  t.className = `toast${error ? " mal" : ""}`;
  t.hidden = false;
  clearTimeout(avisar.reloj);
  avisar.reloj = setTimeout(() => { t.hidden = true; }, 3500);
}

// ---------------- Sesión del administrador ----------------

let admin = null;
try { admin = JSON.parse(sessionStorage.getItem("admin")); } catch { admin = null; }

async function iniciarSesion(evento) {
  evento.preventDefault();
  const error = $("error-login");
  error.hidden = true;
  const r = await api(API_USUARIOS, "/login", {
    method: "POST",
    body: { correo: $("l-correo").value, password: $("l-password").value }
  });
  if (!r.ok) { error.textContent = mensajeDe(r); error.hidden = false; return; }
  if (r.datos.usuario.rol !== "admin_sistema") {
    error.textContent = "Esta cuenta no es de administrador del sistema.";
    error.hidden = false;
    return;
  }
  admin = r.datos.usuario;
  sessionStorage.setItem("admin", JSON.stringify(admin));
  $("form-login").reset();
  mostrarPanel();
}

function cerrarSesion() {
  admin = null;
  sessionStorage.removeItem("admin");
  $("vista-panel").hidden = true;
  $("vista-login").hidden = false;
}

function mostrarPanel() {
  $("vista-login").hidden = true;
  $("vista-panel").hidden = false;
  $("admin-nombre").textContent = `${admin.nombre} ${admin.apellido}`;
  irA(seccionActual);
}

// ---------------- Datos ----------------

const db = { usuarios: [], hoteles: [], habitaciones: [], ocupaciones: [], reservas: [] };

// Carga todo de los tres servicios. Devuelve la lista de servicios que no respondieron.
async function cargarTodo() {
  const [u, h, o, rv] = await Promise.all([
    api(API_USUARIOS, "/usuarios"),
    api(API_ESPACIOS, "/hoteles?todos=1"),
    api(API_ESPACIOS, "/ocupaciones"),
    api(API_RESERVAS, "/reservas")
  ]);
  db.usuarios = u.ok ? u.datos : [];
  db.hoteles = h.ok ? h.datos : [];
  db.ocupaciones = o.ok ? o.datos : [];
  db.reservas = rv.ok ? rv.datos : [];

  // Las habitaciones vienen dentro de cada hotel
  const detalles = await Promise.all(db.hoteles.map((x) => api(API_ESPACIOS, `/hoteles/${x.id}`)));
  db.habitaciones = detalles.flatMap((d) => (d.ok ? d.datos.habitaciones : []));

  const fallos = [];
  if (!u.ok) fallos.push("Usuarios");
  if (!h.ok || !o.ok) fallos.push("Espacios");
  if (!rv.ok) fallos.push("Reservas");
  return fallos;
}

const usuarioPorId = (id) => db.usuarios.find((x) => x.id === id);
const hotelPorId = (id) => db.hoteles.find((x) => x.id === id);
const habitacionPorId = (id) => db.habitaciones.find((x) => x.id === id);
const nombreUsuario = (id) => { const u = usuarioPorId(id); return u ? `${u.nombre} ${u.apellido}` : `Usuario #${id}`; };
function etiquetaHabitacion(id) {
  const h = habitacionPorId(id);
  if (!h) return `Habitación #${id}`;
  const hotel = hotelPorId(h.hotel_id);
  return `${hotel ? hotel.nombre : "Hotel #" + h.hotel_id} · ${h.numero} (${h.tipo})`;
}

// ---------------- Piezas reutilizables ----------------

const etiqueta = (valor) => `<span class="etiqueta ${esc(valor)}">${esc(valor)}</span>`;
const boton = (accion, id, texto, peligro = false) =>
  `<button class="enlace${peligro ? " peligro" : ""}" type="button" data-accion="${accion}" data-id="${id}">${texto}</button>`;

function tabla(columnas, filas, vacio) {
  if (filas.length === 0) return `<div class="tabla-caja"><p class="vacio">${vacio}</p></div>`;
  return `
    <div class="tabla-caja"><table>
      <thead><tr>${columnas.map((c) => `<th>${c.t}</th>`).join("")}</tr></thead>
      <tbody>${filas.map((f) => `<tr>${columnas.map((c) => `<td class="${c.clase || ""}">${c.v(f)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>`;
}

const campo = (id, label, tipo = "text", extra = {}) => ({ id, label, tipo, ...extra });
const opciones = (lista, valor, texto) => lista.map((x) => [String(valor(x)), texto(x)]);

let envioActual = null;
let camposActuales = [];

function abrirForm({ titulo, campos, valores = {}, boton = "Guardar", enviar }) {
  camposActuales = campos;
  envioActual = enviar;
  $("form-titulo").textContent = titulo;
  $("form-enviar").textContent = boton;
  $("form-enviar").disabled = false;
  $("form-error").hidden = true;
  $("form-campos").innerHTML = campos.map((c) => {
    if (c.ayuda) return `<p class="ayuda">${esc(c.ayuda)}</p>`;
    const valor = valores[c.id] ?? "";
    const clase = c.completo ? "completo" : "";
    const comunes = `id="f-${c.id}" ${c.requerido ? "required" : ""}`;
    let control;
    if (c.tipo === "select") {
      control = `<select ${comunes}>
        ${c.requerido ? "" : `<option value=""></option>`}
        ${c.opciones.map(([v, t]) => `<option value="${esc(v)}" ${String(valor) === v ? "selected" : ""}>${esc(t)}</option>`).join("")}
      </select>`;
    } else if (c.tipo === "textarea") {
      control = `<textarea ${comunes} rows="3">${esc(valor)}</textarea>`;
    } else {
      control = `<input ${comunes} type="${c.tipo}" value="${esc(valor)}" ${c.min !== undefined ? `min="${c.min}"` : ""} ${c.minlength ? `minlength="${c.minlength}"` : ""} ${c.paso ? `step="${c.paso}"` : ""}>`;
    }
    return `<label class="${clase}">${esc(c.label)}${control}</label>`;
  }).join("");
  $("dlg-form").showModal();
}

// Lee el formulario: los campos vacíos no se envían
function leerForm() {
  const valores = {};
  for (const c of camposActuales) {
    if (c.ayuda) continue;
    const bruto = $(`f-${c.id}`).value.trim();
    if (bruto === "") continue;
    valores[c.id] = c.tipo === "number" || c.numero ? Number(bruto) : bruto;
  }
  return valores;
}

async function enviarForm(evento) {
  evento.preventDefault();
  const boton = $("form-enviar");
  boton.disabled = true;
  $("form-error").hidden = true;
  const r = await envioActual(leerForm());
  if (!r.ok) {
    $("form-error").textContent = mensajeDe(r);
    $("form-error").hidden = false;
    boton.disabled = false;
    return;
  }
  $("dlg-form").close();
  avisar(r.datos?.Mensaje || "Cambios guardados");
  irA(seccionActual);
}

// Ejecuta una acción directa (sin formulario) y refresca
async function ejecutar(promesa) {
  const r = await promesa;
  if (!r.ok) return avisar(mensajeDe(r), true);
  avisar(r.datos?.Mensaje || "Listo");
  irA(seccionActual);
}

// ---------------- Secciones ----------------

let seccionActual = "resumen";
let filtroHotel = "";
let filtroEstado = "";

const secciones = {

  // ----- Resumen -----
  resumen: {
    titulo: "Resumen",
    async render() {
      const [usuarios, espacios, reservas, cEspacios, cReservas] = await Promise.all([
        api(API_USUARIOS, "/usuarios"),
        api(API_ESPACIOS, "/hoteles"),
        api(API_RESERVAS, "/reservas?usuario_id=0"),
        api(API_ESPACIOS, "/circuito/usuarios"),
        api(API_RESERVAS, "/circuito")
      ]);
      const servicio = (nombre, r, puerto) => `
        <div class="servicio"><strong class="punto ${r.ok ? "bien" : "mal"}">${nombre}</strong>
        <span>${r.ok ? "En línea" : esc(mensajeDe(r))}</span><small>Puerto ${puerto}</small></div>`;
      const circuito = (nombre, c) => {
        const estado = c?.estado || "SIN DATOS";
        const nivel = estado === "CLOSED" ? "bien" : estado === "OPEN" ? "mal" : "medio";
        const texto = { CLOSED: "Cerrado (normal)", OPEN: "Abierto", "HALF-OPEN": "Semiabierto" }[estado] || estado;
        return `<div class="servicio"><strong class="punto ${nivel}">${nombre}</strong><span>${texto}</span>
          ${c ? `<small>Fallos seguidos: ${c.fallos_consecutivos} de ${c.umbral_fallos}</small>` : ""}</div>`;
      };
      const confirmadas = db.reservas.filter((r) => r.estado === "confirmada").length;
      const pendientes = db.reservas.filter((r) => r.estado === "pendiente").length;
      return `
        <div class="tarjetas">
          <div class="tarjeta"><strong>${db.usuarios.length}</strong><span>Usuarios</span></div>
          <div class="tarjeta"><strong>${db.hoteles.length}</strong><span>Hoteles</span></div>
          <div class="tarjeta"><strong>${db.habitaciones.length}</strong><span>Habitaciones</span></div>
          <div class="tarjeta"><strong>${confirmadas}</strong><span>Reservas confirmadas</span></div>
          <div class="tarjeta"><strong>${pendientes}</strong><span>Reservas pendientes</span></div>
        </div>
        <h2 class="sub">Servicios</h2>
        <div class="servicios">
          ${servicio("Usuarios", usuarios, 5001)}${servicio("Espacios", espacios, 5002)}${servicio("Reservas", reservas, 5003)}
        </div>
        <h2 class="sub" style="margin-top:26px">Circuit breakers</h2>
        <div class="servicios">
          ${circuito("Espacios → Usuarios", cEspacios.ok ? cEspacios.datos : null)}
          ${circuito("Reservas → Usuarios", cReservas.ok ? cReservas.datos.usuarios : null)}
          ${circuito("Reservas → Espacios", cReservas.ok ? cReservas.datos.espacios : null)}
        </div>`;
    }
  },

  // ----- Usuarios -----
  usuarios: {
    titulo: "Usuarios",
    nuevo: "Nuevo usuario",
    render() {
      return tabla([
        { t: "ID", v: (u) => u.id },
        { t: "Nombre", v: (u) => `${esc(u.nombre)} ${esc(u.apellido)}<small>${esc(u.correo)}</small>` },
        { t: "Teléfono", v: (u) => esc(u.telefono || "—") },
        { t: "Rol", v: (u) => esc(u.rol) },
        { t: "Estado", v: (u) => etiqueta(u.estado) },
        { t: "", clase: "acciones", v: (u) =>
            boton("editar", u.id, "Editar") +
            boton("estado", u.id, u.estado === "activa" ? "Desactivar" : "Activar") +
            boton("eliminar", u.id, "Eliminar", true) }
      ], db.usuarios, "No hay usuarios.");
    },
    roles: ["cliente", "agencia", "admin_hotel", "admin_sistema"],
    campos(editando) {
      const rol = campo("rol", "Rol", "select", { requerido: true, opciones: this.roles.map((r) => [r, r]) });
      return editando
        ? [campo("nombre", "Nombre", "text", { requerido: true }), campo("apellido", "Apellido", "text", { requerido: true }),
           campo("telefono", "Teléfono", "tel"), rol]
        : [campo("nombre", "Nombre", "text", { requerido: true }), campo("apellido", "Apellido", "text", { requerido: true }),
           campo("correo", "Correo", "email", { requerido: true, completo: true }),
           campo("telefono", "Teléfono", "tel"), campo("password", "Contraseña", "password", { requerido: true, minlength: 6 }), rol];
    },
    crear() {
      abrirForm({ titulo: "Nuevo usuario", campos: this.campos(false), valores: { rol: "cliente" },
        enviar: (v) => api(API_USUARIOS, "/usuarios", { method: "POST", body: v }) });
    },
    acciones: {
      editar(id) {
        const u = usuarioPorId(id);
        abrirForm({ titulo: `Editar usuario #${id}`, campos: secciones.usuarios.campos(true), valores: u,
          enviar: (v) => api(API_USUARIOS, `/usuarios/${id}`, { method: "PUT", body: v }) });
      },
      estado(id) {
        const nuevo = usuarioPorId(id).estado === "activa" ? "inactiva" : "activa";
        ejecutar(api(API_USUARIOS, `/usuarios/${id}/estado`, { method: "PATCH", body: { estado: nuevo } }));
      },
      eliminar(id) {
        const hoteles = db.hoteles.filter((h) => h.admin_id === id).length;
        const reservas = db.reservas.filter((r) => r.usuario_id === id).length;
        let aviso = `¿Eliminar a ${nombreUsuario(id)}?`;
        if (hoteles || reservas) aviso += `\n\nAtención: administra ${hoteles} hotel(es) y tiene ${reservas} reserva(s). Esos registros quedarán apuntando a un usuario que ya no existe.`;
        if (confirm(aviso)) ejecutar(api(API_USUARIOS, `/usuarios/${id}`, { method: "DELETE" }));
      }
    }
  },

  // ----- Hoteles -----
  hoteles: {
    titulo: "Hoteles",
    nuevo: "Nuevo hotel",
    render() {
      return tabla([
        { t: "ID", v: (h) => h.id },
        { t: "Hotel", v: (h) => `${esc(h.nombre)}<small>${esc(h.direccion || "")}</small>` },
        { t: "Ciudad", v: (h) => esc(h.ciudad) },
        { t: "Administrador", v: (h) => esc(nombreUsuario(h.admin_id)) },
        { t: "Habitaciones", clase: "num", v: (h) => db.habitaciones.filter((x) => x.hotel_id === h.id).length },
        { t: "Estado", v: (h) => etiqueta(h.estado) },
        { t: "", clase: "acciones", v: (h) =>
            boton("habitaciones", h.id, "Habitaciones") + boton("editar", h.id, "Editar") +
            boton("estado", h.id, h.estado === "activo" ? "Desactivar" : "Activar") +
            boton("eliminar", h.id, "Eliminar", true) }
      ], db.hoteles, "No hay hoteles.");
    },
    camposComunes: () => [
      campo("nombre", "Nombre", "text", { requerido: true }),
      campo("ciudad", "Ciudad", "text", { requerido: true }),
      campo("direccion", "Dirección", "text", { completo: true }),
      campo("servicios", "Servicios (wifi, piscina…)", "text", { completo: true }),
      campo("telefono", "Teléfono", "tel"),
      campo("correo", "Correo", "email"),
      campo("descripcion", "Descripción", "textarea", { completo: true })
    ],
    crear() {
      const admins = db.usuarios.filter((u) => u.rol === "admin_hotel" || u.rol === "admin_sistema");
      abrirForm({
        titulo: "Nuevo hotel",
        campos: [
          campo("admin_id", "Administrador del hotel", "select", { requerido: true, numero: true, completo: true,
            opciones: opciones(admins, (u) => u.id, (u) => `${u.nombre} ${u.apellido} (${u.rol})`) }),
          ...this.camposComunes()
        ],
        enviar: (v) => api(API_ESPACIOS, "/hoteles", { method: "POST", body: v })
      });
    },
    acciones: {
      editar(id) {
        abrirForm({
          titulo: `Editar hotel #${id}`, valores: hotelPorId(id),
          campos: [...secciones.hoteles.camposComunes(),
            campo("estado", "Estado", "select", { requerido: true, opciones: [["activo", "activo"], ["inactivo", "inactivo"]] })],
          enviar: (v) => api(API_ESPACIOS, `/hoteles/${id}`, { method: "PUT", body: v })
        });
      },
      estado(id) {
        const nuevo = hotelPorId(id).estado === "activo" ? "inactivo" : "activo";
        ejecutar(api(API_ESPACIOS, `/hoteles/${id}`, { method: "PUT", body: { estado: nuevo } }));
      },
      habitaciones(id) { filtroHotel = String(id); irA("habitaciones"); },
      eliminar(id) {
        const n = db.habitaciones.filter((x) => x.hotel_id === id).length;
        if (confirm(`¿Eliminar "${hotelPorId(id).nombre}"?\n\nTambién se borran sus ${n} habitación(es) y sus ocupaciones.`)) {
          ejecutar(api(API_ESPACIOS, `/hoteles/${id}`, { method: "DELETE" }));
        }
      }
    }
  },

  // ----- Habitaciones -----
  habitaciones: {
    titulo: "Habitaciones",
    nuevo: "Nueva habitación",
    render() {
      const filas = db.habitaciones.filter((h) => !filtroHotel || String(h.hotel_id) === filtroHotel);
      const filtro = `
        <div class="filtros"><label>Hotel
          <select data-filtro="hotel"><option value="">Todos</option>
            ${db.hoteles.map((h) => `<option value="${h.id}" ${String(h.id) === filtroHotel ? "selected" : ""}>${esc(h.nombre)}</option>`).join("")}
          </select></label></div>`;
      return filtro + tabla([
        { t: "ID", v: (h) => h.id },
        { t: "Hotel", v: (h) => esc(hotelPorId(h.hotel_id)?.nombre || `#${h.hotel_id}`) },
        { t: "Número", v: (h) => esc(h.numero) },
        { t: "Tipo", v: (h) => esc(h.tipo) },
        { t: "Capacidad", clase: "num", v: (h) => h.capacidad },
        { t: "Precio / noche", clase: "num", v: (h) => pesos(h.precio_noche) },
        { t: "Estado", v: (h) => etiqueta(h.estado) },
        { t: "", clase: "acciones", v: (h) => boton("editar", h.id, "Editar") + boton("eliminar", h.id, "Eliminar", true) }
      ], filas, "No hay habitaciones.");
    },
    camposComunes: () => [
      campo("tipo", "Tipo (sencilla, doble, suite…)", "text", { requerido: true }),
      campo("capacidad", "Capacidad", "number", { requerido: true, min: 1 }),
      campo("precio_noche", "Precio por noche", "number", { requerido: true, min: 1 }),
      campo("amenidades", "Amenidades", "text")
    ],
    crear() {
      abrirForm({
        titulo: "Nueva habitación",
        valores: { hotel_id: filtroHotel },
        campos: [
          campo("hotel_id", "Hotel", "select", { requerido: true, numero: true, completo: true,
            opciones: opciones(db.hoteles, (h) => h.id, (h) => `${h.nombre} (${h.ciudad})`) }),
          campo("numero", "Número", "text", { requerido: true }),
          ...this.camposComunes()
        ],
        enviar: (v) => {
          const { hotel_id, ...cuerpo } = v;
          return api(API_ESPACIOS, `/hoteles/${hotel_id}/habitaciones`, { method: "POST", body: cuerpo });
        }
      });
    },
    acciones: {
      editar(id) {
        abrirForm({
          titulo: `Editar habitación #${id}`, valores: habitacionPorId(id),
          campos: [...secciones.habitaciones.camposComunes(),
            campo("estado", "Estado", "select", { requerido: true, opciones: [["activa", "activa"], ["mantenimiento", "mantenimiento"]] })],
          enviar: (v) => api(API_ESPACIOS, `/habitaciones/${id}`, { method: "PUT", body: v })
        });
      },
      eliminar(id) {
        if (confirm(`¿Eliminar la habitación ${etiquetaHabitacion(id)}?\n\nTambién se borran sus ocupaciones.`)) {
          ejecutar(api(API_ESPACIOS, `/habitaciones/${id}`, { method: "DELETE" }));
        }
      }
    }
  },

  // ----- Ocupaciones -----
  ocupaciones: {
    titulo: "Ocupaciones",
    nuevo: "Bloquear habitación",
    render() {
      return tabla([
        { t: "ID", v: (o) => o.id },
        { t: "Habitación", v: (o) => esc(etiquetaHabitacion(o.habitacion_id)) },
        { t: "Entrada", v: (o) => formatoFecha(o.fecha_entrada) },
        { t: "Salida", v: (o) => formatoFecha(o.fecha_salida) },
        { t: "Tipo", v: (o) => etiqueta(o.tipo) },
        { t: "Reserva", v: (o) => (o.reserva_id ? `#${o.reserva_id}` : "—") },
        { t: "Vence", v: (o) => (o.expira_en ? esc(o.expira_en.replace("T", " ").slice(0, 16)) : "—") },
        { t: "", clase: "acciones", v: (o) =>
            (o.tipo === "bloqueo" ? boton("confirmar", o.id, "Confirmar") : "") +
            boton("editar", o.id, "Cambiar fechas") + boton("liberar", o.id, "Liberar", true) }
      ], db.ocupaciones, "No hay ocupaciones.");
    },
    crear() {
      abrirForm({
        titulo: "Bloquear habitación",
        campos: [
          campo("habitacion_id", "Habitación", "select", { requerido: true, numero: true, completo: true,
            opciones: opciones(db.habitaciones, (h) => h.id, (h) => etiquetaHabitacion(h.id)) }),
          campo("entrada", "Entrada", "date", { requerido: true }),
          campo("salida", "Salida", "date", { requerido: true }),
          { ayuda: "El bloqueo dura 15 minutos y después se libera solo si no se confirma." }
        ],
        enviar: (v) => api(API_ESPACIOS, "/ocupaciones", { method: "POST", body: v })
      });
    },
    acciones: {
      confirmar(id) {
        abrirForm({
          titulo: `Confirmar ocupación #${id}`, boton: "Confirmar",
          campos: [campo("reserva_id", "Número de reserva (opcional)", "number", { min: 1, completo: true })],
          enviar: (v) => api(API_ESPACIOS, `/ocupaciones/${id}/confirmar`, { method: "POST", body: v })
        });
      },
      editar(id) {
        const o = db.ocupaciones.find((x) => x.id === id);
        abrirForm({
          titulo: `Cambiar fechas de la ocupación #${id}`,
          valores: { entrada: o.fecha_entrada, salida: o.fecha_salida },
          campos: [campo("entrada", "Entrada", "date", { requerido: true }), campo("salida", "Salida", "date", { requerido: true })],
          enviar: (v) => api(API_ESPACIOS, `/ocupaciones/${id}`, { method: "PUT", body: v })
        });
      },
      liberar(id) {
        const o = db.ocupaciones.find((x) => x.id === id);
        let aviso = `¿Liberar la ocupación #${id}? Las fechas quedarán disponibles.`;
        if (o.reserva_id) aviso += `\n\nAtención: está ligada a la reserva #${o.reserva_id}. Para anularla mejor cancela la reserva desde la sección Reservas.`;
        if (confirm(aviso)) ejecutar(api(API_ESPACIOS, `/ocupaciones/${id}`, { method: "DELETE" }));
      }
    }
  },

  // ----- Reservas -----
  reservas: {
    titulo: "Reservas",
    nuevo: "Nueva reserva",
    render() {
      const filas = db.reservas.filter((r) => !filtroEstado || r.estado === filtroEstado);
      const filtro = `
        <div class="filtros"><label>Estado
          <select data-filtro="estado"><option value="">Todos</option>
            ${["pendiente", "confirmada", "cancelada", "expirada"].map((e) => `<option ${e === filtroEstado ? "selected" : ""}>${e}</option>`).join("")}
          </select></label></div>`;
      return filtro + tabla([
        { t: "ID", v: (r) => r.id },
        { t: "Huésped", v: (r) => esc(nombreUsuario(r.usuario_id)) },
        { t: "Hotel", v: (r) => `${esc(r.hotel)}<small>Hab. ${esc(r.habitacion)}</small>` },
        { t: "Fechas", v: (r) => `${formatoFecha(r.fecha_entrada)} → ${formatoFecha(r.fecha_salida)}` },
        { t: "Total", clase: "num", v: (r) => pesos(r.total) },
        { t: "Estado", v: (r) => etiqueta(r.estado) },
        { t: "", clase: "acciones", v: (r) =>
            (r.estado === "pendiente" ? boton("confirmar", r.id, "Confirmar") : "") +
            (r.estado === "pendiente" || r.estado === "confirmada" ? boton("editar", r.id, "Cambiar fechas") + boton("cancelar", r.id, "Cancelar", true) : "") }
      ], filas, "No hay reservas.");
    },
    crear() {
      const activos = db.usuarios.filter((u) => u.estado === "activa");
      abrirForm({
        titulo: "Nueva reserva",
        campos: [
          campo("usuario_id", "Huésped", "select", { requerido: true, numero: true, completo: true,
            opciones: opciones(activos, (u) => u.id, (u) => `${u.nombre} ${u.apellido} · ${u.correo}`) }),
          campo("habitacion_id", "Habitación", "select", { requerido: true, numero: true, completo: true,
            opciones: opciones(db.habitaciones.filter((h) => h.estado === "activa"), (h) => h.id, (h) => `${etiquetaHabitacion(h.id)} · ${pesos(h.precio_noche)}`) }),
          campo("entrada", "Entrada", "date", { requerido: true }),
          campo("salida", "Salida", "date", { requerido: true }),
          campo("huespedes", "Huéspedes", "number", { min: 1 }),
          { ayuda: "Queda pendiente: tiene 15 minutos para confirmarla." }
        ],
        valores: { huespedes: 1 },
        enviar: (v) => api(API_RESERVAS, "/reservas", { method: "POST", body: v })
      });
    },
    acciones: {
      confirmar(id) { ejecutar(api(API_RESERVAS, `/reservas/${id}/confirmar`, { method: "POST" })); },
      editar(id) {
        const r = db.reservas.find((x) => x.id === id);
        abrirForm({
          titulo: `Cambiar fechas de la reserva #${id}`,
          valores: { entrada: r.fecha_entrada, salida: r.fecha_salida },
          campos: [campo("entrada", "Entrada", "date", { requerido: true }), campo("salida", "Salida", "date", { requerido: true })],
          enviar: (v) => api(API_RESERVAS, `/reservas/${id}`, { method: "PUT", body: v })
        });
      },
      cancelar(id) {
        if (confirm(`¿Cancelar la reserva #${id}? Las fechas quedarán libres.`)) {
          ejecutar(api(API_RESERVAS, `/reservas/${id}/cancelar`, { method: "POST" }));
        }
      }
    }
  }
};

// ---------------- Navegación ----------------

async function irA(nombre) {
  seccionActual = nombre;
  const seccion = secciones[nombre];
  for (const b of document.querySelectorAll("#menu button")) b.classList.toggle("activo", b.dataset.seccion === nombre);
  $("titulo").textContent = seccion.titulo;
  $("btn-nuevo").hidden = !seccion.nuevo;
  $("btn-nuevo").textContent = seccion.nuevo ? `+ ${seccion.nuevo}` : "";

  $("contenido").innerHTML = `<p class="vacio">Cargando…</p>`;
  const fallos = await cargarTodo();
  $("aviso").hidden = fallos.length === 0;
  $("aviso").textContent = fallos.length ? `No respondió: ${fallos.join(", ")}. Algunos datos pueden estar incompletos.` : "";
  if (nombre !== seccionActual) return;  // el usuario cambió de sección mientras cargaba
  $("contenido").innerHTML = await seccion.render();
}

// ---------------- Eventos ----------------

$("form-login").addEventListener("submit", iniciarSesion);
$("btn-salir").addEventListener("click", cerrarSesion);
$("btn-recargar").addEventListener("click", () => irA(seccionActual));
$("btn-nuevo").addEventListener("click", () => secciones[seccionActual].crear());
$("form").addEventListener("submit", enviarForm);
$("form-cerrar").addEventListener("click", () => $("dlg-form").close());
$("menu").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-seccion]");
  if (b) irA(b.dataset.seccion);
});
$("contenido").addEventListener("click", (e) => {
  const b = e.target.closest("[data-accion]");
  if (b) secciones[seccionActual].acciones[b.dataset.accion](Number(b.dataset.id));
});
$("contenido").addEventListener("change", (e) => {
  const filtro = e.target.dataset.filtro;
  if (!filtro) return;
  if (filtro === "hotel") filtroHotel = e.target.value;
  if (filtro === "estado") filtroEstado = e.target.value;
  irA(seccionActual);
});

if (admin) mostrarPanel();
