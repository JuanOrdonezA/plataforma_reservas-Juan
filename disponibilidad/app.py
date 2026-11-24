from flask import Flask, jsonify, request
import time
from datetime import date, datetime
from decimal import Decimal
import requests, os, pybreaker
from database import conectar

url_espacios = os.getenv("ESPACIOS_URL")
TIEMPO_MAXIMO = float(os.getenv("ESPACIOS_TIMEOUT", "2"))  # timeout hacia Espacios (valor en .env)
MINUTOS_BLOQUEO = 15

app = Flask(__name__)

# Circuit breaker para las llamadas al servicio de Espacios (hoteles y habitaciones)
circuito_espacios = pybreaker.CircuitBreaker(fail_max=int(os.getenv("CB_MAX_FALLOS", "3")), reset_timeout=int(os.getenv("CB_RECUPERACION", "30")), throw_new_error_on_trip=False)

# Condicion SQL: la ocupacion "o" cruza las fechas pedidas y sigue vigente
# (dos rangos se cruzan si uno empieza antes de que el otro termine)
CRUCE_FECHAS = """
    o.fecha_entrada < %s AND o.fecha_salida > %s
    AND (o.tipo = 'confirmada' OR o.expira_en > NOW())
"""


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


# Respuestas JSON para errores generales (ruta inexistente, metodo no permitido, error interno)
@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({"Mensaje": "Ruta no encontrada"}), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return jsonify({"Mensaje": "Metodo HTTP no permitido en esta ruta"}), 405


@app.errorhandler(500)
def error_interno(e):
    return jsonify({"Mensaje": "Error interno del servicio"}), 500


# Llama a Espacios con timeout y circuit breaker.
# Si algo falla lanza ErrorServicio (503 / 504 / 502); si responde, devuelve la respuesta.
def llamar_espacios(ruta, **kwargs):
    try:
        with circuito_espacios.calling():
            respuesta = requests.get(url_espacios + ruta, timeout=TIEMPO_MAXIMO, **kwargs)
            if respuesta.status_code >= 500:
                respuesta.raise_for_status()  # los 5xx cuentan como fallo del circuito
            return respuesta
    except pybreaker.CircuitBreakerError:
        raise ErrorServicio("Circuito abierto: el servicio de espacios no esta disponible", 503)
    except requests.exceptions.Timeout:
        raise ErrorServicio("El servicio de espacios tardo demasiado en responder", 504)
    except requests.exceptions.ConnectionError:
        raise ErrorServicio("No se pudo establecer comunicacion con el servicio de espacios", 503)
    except requests.exceptions.HTTPError:
        raise ErrorServicio("Error en el servicio de espacios", 502)


# Trae una habitacion de Espacios. Devuelve (habitacion, None) o (None, respuesta de error)
def traer_habitacion(habitacion_id):
    r = llamar_espacios(f"/habitaciones/{habitacion_id}")
    if r.status_code == 404:
        return None, (jsonify({"Mensaje": "Habitacion no encontrada"}), 404)
    if r.status_code != 200:
        return None, (jsonify({"Mensaje": "No se pudo consultar el servicio de espacios"}), 502)
    return r.json(), None


# Convierte fechas y decimales para poder devolverlos en JSON
def limpiar(fila):
    for clave, valor in fila.items():
        if isinstance(valor, (date, datetime)):
            fila[clave] = valor.isoformat()
        elif isinstance(valor, Decimal):
            fila[clave] = float(valor)
    return fila


# Lee ?entrada=2026-12-20&salida=2026-12-23 (o del body) y las valida
def leer_fechas(entrada, salida):
    try:
        entrada = date.fromisoformat(entrada)
        salida = date.fromisoformat(salida)
    except (TypeError, ValueError):
        return None, None, "Fechas invalidas, use el formato AAAA-MM-DD"
    if salida <= entrada:
        return None, None, "La fecha de salida debe ser posterior a la de entrada"
    if entrada < date.today():
        return None, None, "La fecha de entrada no puede estar en el pasado"
    return entrada, salida, None


# Candado por habitacion: si dos personas apartan la misma habitacion al mismo tiempo,
# la segunda espera a que la primera termine (asi no hay reservas duplicadas).
# Antes se usaba FOR UPDATE sobre la tabla habitaciones, pero ahora esa tabla vive en otro servicio.
def tomar_candado(cursor, habitacion_id):
    cursor.execute("SELECT GET_LOCK(%s, 10) AS ok", (f"habitacion_{habitacion_id}",))
    return cursor.fetchone()["ok"] == 1


def soltar_candado(cursor, habitacion_id):
    cursor.execute("SELECT RELEASE_LOCK(%s)", (f"habitacion_{habitacion_id}",))
    cursor.fetchone()


def cerrar(cursor, conexion):
    cursor.close()
    conexion.close()


# ---------------- DISPONIBILIDAD ----------------

# Buscar hoteles con habitaciones libres
# /disponibilidad/hoteles?ciudad=Popayan&entrada=2026-12-20&salida=2026-12-23&huespedes=2
@app.route("/disponibilidad/hoteles")
def hoteles_disponibles():
    entrada, salida, error = leer_fechas(request.args.get("entrada"), request.args.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400
    huespedes = request.args.get("huespedes", 1, type=int)
    noches = (salida - entrada).days

    # 1. Habitaciones candidatas (activas, de hoteles activos, con capacidad suficiente)
    parametros = {"capacidad": huespedes}
    if request.args.get("ciudad"):
        parametros["ciudad"] = request.args.get("ciudad")
    r = llamar_espacios("/habitaciones", params=parametros)
    if r.status_code != 200:
        return jsonify({"Mensaje": "No se pudo consultar el servicio de espacios"}), 502
    candidatas = r.json()

    # 2. Quitar las que tienen una ocupacion vigente que se cruza con las fechas
    ocupadas = set()
    if candidatas:
        ids = [h["id"] for h in candidatas]
        marcas = ", ".join(["%s"] * len(ids))
        conexion = conectar()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            f"SELECT DISTINCT o.habitacion_id FROM ocupaciones o WHERE o.habitacion_id IN ({marcas}) AND {CRUCE_FECHAS}",
            (*ids, salida, entrada)
        )
        ocupadas = {fila["habitacion_id"] for fila in cursor.fetchall()}
        cerrar(cursor, conexion)

    # 3. Agrupar las habitaciones libres por hotel
    hoteles = {}
    for h in candidatas:
        if h["id"] in ocupadas:
            continue
        if h["hotel_id"] not in hoteles:
            hoteles[h["hotel_id"]] = {"hotel_id": h["hotel_id"], "hotel": h["hotel"], "ciudad": h["ciudad"], "habitaciones": []}
        hoteles[h["hotel_id"]]["habitaciones"].append({
            "habitacion_id": h["id"],
            "numero": h["numero"],
            "tipo": h["tipo"],
            "capacidad": h["capacidad"],
            "precio_noche": h["precio_noche"],
            "precio_total": h["precio_noche"] * noches
        })

    return jsonify({
        "entrada": entrada.isoformat(),
        "salida": salida.isoformat(),
        "noches": noches,
        "hoteles": list(hoteles.values())
    })


# Consultar si una habitacion esta libre
# /disponibilidad/habitaciones/1?entrada=2026-12-20&salida=2026-12-23
@app.route("/disponibilidad/habitaciones/<int:id>")
def disponibilidad_habitacion(id):
    entrada, salida, error = leer_fechas(request.args.get("entrada"), request.args.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400

    habitacion, respuesta_error = traer_habitacion(id)
    if respuesta_error:
        return respuesta_error

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        f"SELECT COUNT(*) AS cruces FROM ocupaciones o WHERE o.habitacion_id = %s AND {CRUCE_FECHAS}",
        (id, salida, entrada)
    )
    cruces = cursor.fetchone()["cruces"]
    cerrar(cursor, conexion)

    noches = (salida - entrada).days
    return jsonify({
        "habitacion_id": id,
        "disponible": cruces == 0 and habitacion["estado"] == "activa",
        "noches": noches,
        "precio_total": float(habitacion["precio_noche"]) * noches
    })


# ---------------- OCUPACIONES ----------------

# Listar ocupaciones (opcional: /ocupaciones?habitacion_id=1)
@app.route("/ocupaciones")
def listar_ocupaciones():
    habitacion_id = request.args.get("habitacion_id", type=int)
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    if habitacion_id:
        cursor.execute("SELECT * FROM ocupaciones WHERE habitacion_id = %s", (habitacion_id,))
    else:
        cursor.execute("SELECT * FROM ocupaciones")
    ocupaciones = [limpiar(o) for o in cursor.fetchall()]
    cerrar(cursor, conexion)
    return jsonify(ocupaciones)


# Buscar una ocupacion por id
@app.route("/ocupaciones/<int:id>")
def buscar_ocupacion(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ocupaciones WHERE id = %s", (id,))
    ocupacion = cursor.fetchone()
    cerrar(cursor, conexion)
    if ocupacion is None:
        return jsonify({"Mensaje": "Ocupacion no encontrada"}), 404
    return jsonify(limpiar(ocupacion))


# Bloquear una habitacion por unas fechas durante 15 minutos
# body: {"habitacion_id": 1, "entrada": "2026-12-20", "salida": "2026-12-23"}
@app.route("/ocupaciones", methods=["POST"])
def bloquear():
    datos = request.json or {}
    entrada, salida, error = leer_fechas(datos.get("entrada"), datos.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400
    habitacion_id = datos.get("habitacion_id")

    # La habitacion debe existir en Espacios y estar activa
    habitacion, respuesta_error = traer_habitacion(habitacion_id)
    if respuesta_error:
        return respuesta_error
    if habitacion["estado"] != "activa":
        return jsonify({"Mensaje": "Habitacion no encontrada o no disponible"}), 404

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    if not tomar_candado(cursor, habitacion_id):
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "La habitacion esta siendo reservada, intente de nuevo"}), 409
    try:
        conexion.commit()  # lectura fresca: ver lo que otros guardaron mientras esperabamos el candado
        cursor.execute(
            f"SELECT COUNT(*) AS cruces FROM ocupaciones o WHERE o.habitacion_id = %s AND {CRUCE_FECHAS}",
            (habitacion_id, salida, entrada)
        )
        if cursor.fetchone()["cruces"] > 0:
            return jsonify({"Mensaje": "La habitacion ya esta ocupada en esas fechas"}), 409

        cursor.execute(
            f"""
            INSERT INTO ocupaciones (habitacion_id, fecha_entrada, fecha_salida, tipo, expira_en)
            VALUES (%s, %s, %s, 'bloqueo', NOW() + INTERVAL {MINUTOS_BLOQUEO} MINUTE)
            """,
            (habitacion_id, entrada, salida)
        )
        conexion.commit()
        nuevo_id = cursor.lastrowid
    finally:
        soltar_candado(cursor, habitacion_id)
        cerrar(cursor, conexion)
    return jsonify({
        "Mensaje": "Habitacion bloqueada",
        "ocupacion_id": nuevo_id,
        "minutos_para_confirmar": MINUTOS_BLOQUEO
    }), 201


# Cambiar las fechas de una ocupacion
# body: {"entrada": "2026-12-21", "salida": "2026-12-24"}
@app.route("/ocupaciones/<int:id>", methods=["PUT"])
def actualizar_ocupacion(id):
    datos = request.json or {}
    entrada, salida, error = leer_fechas(datos.get("entrada"), datos.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT habitacion_id FROM ocupaciones WHERE id = %s", (id,))
    ocupacion = cursor.fetchone()
    if ocupacion is None:
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "Ocupacion no encontrada"}), 404
    habitacion_id = ocupacion["habitacion_id"]

    if not tomar_candado(cursor, habitacion_id):
        cerrar(cursor, conexion)
        return jsonify({"Mensaje": "La habitacion esta siendo reservada, intente de nuevo"}), 409
    try:
        conexion.commit()
        # Se revisan los cruces ignorando la propia ocupacion
        cursor.execute(
            f"""
            SELECT COUNT(*) AS cruces FROM ocupaciones o
            WHERE o.habitacion_id = %s AND o.id <> %s AND {CRUCE_FECHAS}
            """,
            (habitacion_id, id, salida, entrada)
        )
        if cursor.fetchone()["cruces"] > 0:
            return jsonify({"Mensaje": "La habitacion ya esta ocupada en esas fechas"}), 409
        cursor.execute(
            "UPDATE ocupaciones SET fecha_entrada = %s, fecha_salida = %s WHERE id = %s",
            (entrada, salida, id)
        )
        conexion.commit()
    finally:
        soltar_candado(cursor, habitacion_id)
        cerrar(cursor, conexion)
    return jsonify({"Mensaje": "Ocupacion actualizada"})


# Confirmar un bloqueo (cuando la reserva queda confirmada)
# body: {"reserva_id": 10}
@app.route("/ocupaciones/<int:id>/confirmar", methods=["POST"])
def confirmar(id):
    reserva_id = (request.json or {}).get("reserva_id")
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        """
        UPDATE ocupaciones
        SET tipo = 'confirmada', reserva_id = %s, expira_en = NULL
        WHERE id = %s AND tipo = 'bloqueo' AND expira_en > NOW()
        """,
        (reserva_id, id)
    )
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cerrar(cursor, conexion)
    if filas_afectadas == 0:
        return jsonify({"Mensaje": "Bloqueo no encontrado o vencido"}), 404
    return jsonify({"Mensaje": "Ocupacion confirmada"})


# Liberar fechas (reserva cancelada o pago rechazado)
@app.route("/ocupaciones/<int:id>", methods=["DELETE"])
def liberar(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("DELETE FROM ocupaciones WHERE id = %s", (id,))
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cerrar(cursor, conexion)
    if filas_afectadas == 0:
        return jsonify({"Mensaje": "Ocupacion no encontrada"}), 404
    return jsonify({"Mensaje": "Fechas liberadas"})


# Estado del circuit breaker hacia Espacios (CLOSED, OPEN o HALF-OPEN)
@app.route("/circuito")
def estado_circuito():
    return jsonify({"espacios": {
            "estado": circuito_espacios.current_state.upper(),
            "fallos_consecutivos": circuito_espacios.fail_counter,
            "umbral_fallos": circuito_espacios.fail_max,
            "periodo_recuperacion": circuito_espacios.reset_timeout
        }})


app.run(host="0.0.0.0", port=5000)
