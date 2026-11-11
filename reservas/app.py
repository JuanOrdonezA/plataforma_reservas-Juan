from flask import Flask, jsonify, request
from datetime import date, datetime
from decimal import Decimal
import requests, os, pybreaker
from database import conectar

url_usuarios = os.getenv("USUARIOS_URL")
url_espacios = os.getenv("ESPACIOS_URL")
TIEMPO_MAXIMO = float(os.getenv("SERVICIOS_TIMEOUT", "2"))
MINUTOS_BLOQUEO = 15  # debe coincidir con el bloqueo del servicio de Espacios

app = Flask(__name__)


# Un circuit breaker por servicio del que dependemos
def nuevo_circuito():
    return pybreaker.CircuitBreaker(
        fail_max=int(os.getenv("CB_MAX_FALLOS", "3")),
        reset_timeout=int(os.getenv("CB_RECUPERACION", "30")),
        throw_new_error_on_trip=False
    )


circuitos = {"usuarios": nuevo_circuito(), "espacios": nuevo_circuito()}


# Permite que la pagina (otro puerto) llame a este servicio desde el navegador
@app.after_request
def permitir_navegador(respuesta):
    respuesta.headers["Access-Control-Allow-Origin"] = "*"
    respuesta.headers["Access-Control-Allow-Headers"] = "Content-Type"
    respuesta.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return respuesta


# ---------------- FUNCIONES DE AYUDA ----------------

class ErrorServicio(Exception):
    def __init__(self, mensaje, codigo):
        self.mensaje = mensaje
        self.codigo = codigo


@app.errorhandler(ErrorServicio)
def responder_error(e):
    return jsonify({"Mensaje": e.mensaje}), e.codigo


# Llama a otro servicio con timeout y circuit breaker.
def llamar(servicio, metodo, ruta, **kwargs):
    base = url_usuarios if servicio == "usuarios" else url_espacios
    try:
        with circuitos[servicio].calling():
            respuesta = requests.request(metodo, base + ruta, timeout=TIEMPO_MAXIMO, **kwargs)
            if respuesta.status_code >= 500:
                respuesta.raise_for_status()  # los 5xx cuentan como fallo del circuito
            return respuesta
    except pybreaker.CircuitBreakerError:
        raise ErrorServicio(f"Circuito abierto: el servicio de {servicio} no esta disponible", 503)
    except requests.exceptions.Timeout:
        raise ErrorServicio(f"El servicio de {servicio} tardo demasiado en responder", 504)
    except requests.exceptions.ConnectionError:
        raise ErrorServicio(f"No se pudo establecer comunicacion con el servicio de {servicio}", 503)
    except requests.exceptions.HTTPError:
        raise ErrorServicio(f"Error en el servicio de {servicio}", 502)


def mensaje_de(respuesta):
    try:
        return respuesta.json().get("Mensaje", "Error en el servicio de espacios")
    except ValueError:
        return "Error en el servicio de espacios"


# Convierte fechas y decimales para poder devolverlos en JSON
def limpiar(fila):
    for clave, valor in fila.items():
        if isinstance(valor, (date, datetime)):
            fila[clave] = valor.isoformat()
        elif isinstance(valor, Decimal):
            fila[clave] = float(valor)
    return fila


# Las reservas pendientes que no se confirmaron a tiempo pasan a "expirada"
def vencer_pendientes(cursor, conexion):
    cursor.execute("UPDATE reservas SET estado = 'expirada' WHERE estado = 'pendiente' AND expira_en < NOW()")
    conexion.commit()


# Busca una reserva (ya con las vencidas actualizadas). Devuelve None si no existe.
def traer_reserva(cursor, conexion, id):
    vencer_pendientes(cursor, conexion)
    cursor.execute("SELECT * FROM reservas WHERE id = %s", (id,))
    return cursor.fetchone()


def cerrar(cursor, conexion):
    cursor.close()
    conexion.close()


# ---------------- RESERVAS ----------------

# Listar reservas (opcional: /reservas?usuario_id=1&estado=confirmada)
@app.route("/reservas")
def listar():
    usuario_id = request.args.get("usuario_id", type=int)
    estado = request.args.get("estado")
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    vencer_pendientes(cursor, conexion)
    cursor.execute(
        """
        SELECT * FROM reservas
        WHERE (%s IS NULL OR usuario_id = %s) AND (%s IS NULL OR estado = %s)
        ORDER BY id DESC
        """,
        (usuario_id, usuario_id, estado, estado)
    )
    reservas = [limpiar(r) for r in cursor.fetchall()]
    cerrar(cursor, conexion)
    return jsonify(reservas)


@app.route("/reservas/<int:id>")
def buscar(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    reserva = traer_reserva(cursor, conexion, id)
    cerrar(cursor, conexion)
    if reserva is None:
        return jsonify({"Mensaje": "Reserva no encontrada"}), 404
    return jsonify(limpiar(reserva))


# Crear una reserva: valida el usuario, aparta la habitacion en Espacios y guarda la reserva
# body: {"usuario_id": 1, "habitacion_id": 1, "entrada": "2026-12-20", "salida": "2026-12-23", "huespedes": 2}
@app.route("/reservas", methods=["POST"])
def crear():
    datos = request.json or {}
    obligatorios = ["usuario_id", "habitacion_id", "entrada", "salida"]
    faltantes = [campo for campo in obligatorios if not datos.get(campo)]
    if faltantes:
        return jsonify({"Mensaje": "Faltan campos", "campos": faltantes}), 400
    huespedes = datos.get("huespedes", 1)
    # bool se descarta aparte porque en Python True cuenta como entero
    if not isinstance(huespedes, int) or isinstance(huespedes, bool) or huespedes < 1:
        return jsonify({"Mensaje": "huespedes debe ser un numero entero mayor a 0"}), 400

    # 1. El usuario debe existir y estar activo
    r = llamar("usuarios", "GET", f"/usuarios/{datos['usuario_id']}")
    if r.status_code == 404:
        return jsonify({"Mensaje": "El usuario no existe"}), 400
    if r.status_code != 200:
        return jsonify({"Mensaje": "No se pudo consultar el servicio de usuarios"}), 502
    if r.json().get("estado") != "activa":
        return jsonify({"Mensaje": "La cuenta del usuario esta inactiva"}), 400

    # 2. La habitacion debe existir y soportar a los huespedes
    r = llamar("espacios", "GET", f"/habitaciones/{datos['habitacion_id']}")
    if r.status_code == 404:
        return jsonify({"Mensaje": "Habitacion no encontrada"}), 404
    if r.status_code != 200:
        return jsonify({"Mensaje": "No se pudo consultar el servicio de espacios"}), 502
    habitacion = r.json()
    if huespedes > habitacion["capacidad"]:
        return jsonify({"Mensaje": f"La habitacion admite maximo {habitacion['capacidad']} huespedes"}), 400

    # 3. Precio total (Espacios tambien valida las fechas y responde 400 si son invalidas)
    r = llamar("espacios", "GET", f"/habitaciones/{habitacion['id']}/disponibilidad",
               params={"entrada": datos["entrada"], "salida": datos["salida"]})
    if r.status_code != 200:
        return jsonify({"Mensaje": mensaje_de(r)}), r.status_code
    disponibilidad = r.json()
    if not disponibilidad["disponible"]:
        return jsonify({"Mensaje": "La habitacion ya esta ocupada en esas fechas"}), 409

    # 4. Apartar la habitacion (Espacios evita las reservas duplicadas)
    r = llamar("espacios", "POST", "/ocupaciones", json={
        "habitacion_id": habitacion["id"], "entrada": datos["entrada"], "salida": datos["salida"]
    })
    if r.status_code != 201:
        return jsonify({"Mensaje": mensaje_de(r)}), r.status_code
    ocupacion_id = r.json()["ocupacion_id"]

    # 5. Guardar la reserva. Si falla la base de datos se libera la habitacion.
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            INSERT INTO reservas
            (usuario_id, habitacion_id, ocupacion_id, hotel, habitacion, fecha_entrada,
             fecha_salida, huespedes, total, estado, expira_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendiente', NOW() + INTERVAL {MINUTOS_BLOQUEO} MINUTE)
            """,
            (datos["usuario_id"], habitacion["id"], ocupacion_id, habitacion["hotel"],
             f"{habitacion['numero']} · {habitacion['tipo']}", datos["entrada"], datos["salida"],
             huespedes, disponibilidad["precio_total"])
        )
        conexion.commit()
    except Exception:
        cerrar(cursor, conexion)
        try:
            llamar("espacios", "DELETE", f"/ocupaciones/{ocupacion_id}")
        except ErrorServicio:
            pass  # el bloqueo vence solo en 15 minutos
        return jsonify({"Mensaje": "No se pudo guardar la reserva"}), 500
    nuevo_id = cursor.lastrowid
    cerrar(cursor, conexion)
    return jsonify({
        "Mensaje": "Reserva creada, falta confirmarla",
        "id": nuevo_id,
        "ocupacion_id": ocupacion_id,
        "total": disponibilidad["precio_total"],
        "minutos_para_confirmar": MINUTOS_BLOQUEO
    }), 201


# Confirmar una reserva pendiente (en un sistema real aqui iria el pago)
@app.route("/reservas/<int:id>/confirmar", methods=["POST"])
def confirmar(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    reserva = traer_reserva(cursor, conexion, id)
    if reserva is None:
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "Reserva no encontrada"}), 404
    if reserva["estado"] != "pendiente":
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": f"La reserva esta {reserva['estado']}, no se puede confirmar"}), 409

    try:
        r = llamar("espacios", "POST", f"/ocupaciones/{reserva['ocupacion_id']}/confirmar", json={"reserva_id": id})
    except ErrorServicio:
        cerrar(cursor, conexion)
        raise
    if r.status_code == 404:  # el bloqueo vencio en Espacios
        cursor.execute("UPDATE reservas SET estado = 'expirada' WHERE id = %s", (id,))
        conexion.commit()
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "El tiempo para confirmar se acabo, la habitacion fue liberada"}), 409
    if r.status_code != 200:
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": mensaje_de(r)}), 502

    cursor.execute("UPDATE reservas SET estado = 'confirmada', expira_en = NULL WHERE id = %s", (id,))
    conexion.commit()
    cerrar(cursor, conexion)
    return jsonify({"Mensaje": "Reserva confirmada", "id": id})


# Cancelar una reserva (pendiente o confirmada) y liberar las fechas
@app.route("/reservas/<int:id>/cancelar", methods=["POST"])
def cancelar(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    reserva = traer_reserva(cursor, conexion, id)
    if reserva is None:
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "Reserva no encontrada"}), 404
    if reserva["estado"] in ("cancelada", "expirada"):
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": f"La reserva ya esta {reserva['estado']}"}), 409

    try:
        r = llamar("espacios", "DELETE", f"/ocupaciones/{reserva['ocupacion_id']}")
    except ErrorServicio:
        cerrar(cursor, conexion)
        raise
    if r.status_code not in (200, 404):  # 404: las fechas ya estaban libres
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": mensaje_de(r)}), 502

    cursor.execute("UPDATE reservas SET estado = 'cancelada', expira_en = NULL WHERE id = %s", (id,))
    conexion.commit()
    cerrar(cursor, conexion)
    return jsonify({"Mensaje": "Reserva cancelada", "id": id})


# Cambiar las fechas de una reserva
# body: {"entrada": "2026-12-21", "salida": "2026-12-24"}
@app.route("/reservas/<int:id>", methods=["PUT"])
def cambiar_fechas(id):
    datos = request.json or {}
    if not datos.get("entrada") or not datos.get("salida"):
        return jsonify({"Mensaje": "Faltan campos", "campos": ["entrada", "salida"]}), 400

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    reserva = traer_reserva(cursor, conexion, id)
    if reserva is None:
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "Reserva no encontrada"}), 404
    if reserva["estado"] not in ("pendiente", "confirmada"):
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": f"La reserva esta {reserva['estado']}, no se puede modificar"}), 409

    try:
        # Espacios valida las fechas y que no se crucen con otras ocupaciones
        r = llamar("espacios", "PUT", f"/ocupaciones/{reserva['ocupacion_id']}",
                   json={"entrada": datos["entrada"], "salida": datos["salida"]})
        if r.status_code != 200:
            cerrar(cursor, conexion)
            return jsonify({"Mensaje": mensaje_de(r)}), r.status_code
        r = llamar("espacios", "GET", f"/habitaciones/{reserva['habitacion_id']}")
    except ErrorServicio:
        cerrar(cursor, conexion)
        raise
    if r.status_code != 200:
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "Fechas cambiadas, pero no se pudo recalcular el precio"}), 502

    noches = (date.fromisoformat(datos["salida"]) - date.fromisoformat(datos["entrada"])).days
    total = r.json()["precio_noche"] * noches
    cursor.execute(
        "UPDATE reservas SET fecha_entrada = %s, fecha_salida = %s, total = %s WHERE id = %s",
        (datos["entrada"], datos["salida"], total, id)
    )
    conexion.commit()
    cerrar(cursor, conexion)
    return jsonify({"Mensaje": "Reserva actualizada", "total": total})


# Estado de los circuit breakers (CLOSED, OPEN o HALF-OPEN)
@app.route("/circuito")
def estado_circuitos():
    return jsonify({
        nombre: {
            "estado": c.current_state.upper(),
            "fallos_consecutivos": c.fail_counter,
            "umbral_fallos": c.fail_max,
            "periodo_recuperacion": c.reset_timeout
        } for nombre, c in circuitos.items()
    })


app.run(host="0.0.0.0", port=5000)
