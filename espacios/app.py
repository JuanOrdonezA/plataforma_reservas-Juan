from flask import Flask, jsonify, request
import time
from datetime import date, datetime
from decimal import Decimal
import requests, os, pybreaker
from database import conectar

url_usuarios = os.getenv("USUARIOS_URL")
TIEMPO_MAXIMO = float(os.getenv("USUARIOS_TIMEOUT", "2")) 

app = Flask(__name__)
#time.sleep(3)

# Circuit breaker hacia Usuarios
circuito_usuarios = pybreaker.CircuitBreaker(fail_max=int(os.getenv("CB_MAX_FALLOS", "3")), reset_timeout=int(os.getenv("CB_RECUPERACION", "30")), throw_new_error_on_trip=False)


# Permite que la pagina (otro puerto) llame a este servicio desde el navegador
@app.after_request
def permitir_navegador(respuesta):
    respuesta.headers["Access-Control-Allow-Origin"] = "*"
    respuesta.headers["Access-Control-Allow-Headers"] = "Content-Type"
    respuesta.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return respuesta


# ---------------- FUNCIONES DE AYUDA ----------------

# Convierte fechas y decimales para poder devolverlos en JSON
def limpiar(fila):
    for clave, valor in fila.items():
        if isinstance(valor, (date, datetime)):
            fila[clave] = valor.isoformat()
        elif isinstance(valor, Decimal):
            fila[clave] = float(valor)
    return fila


# Pregunta al servicio de Usuarios si el administrador existe
# (con timeout y circuit breaker: si Usuarios falla o tarda, no se deja esperando al cliente)
def validar_admin(admin_id):
    try:
        with circuito_usuarios.calling():
            respuesta = requests.get(f"{url_usuarios}/usuarios/{admin_id}", timeout=TIEMPO_MAXIMO)
            if respuesta.status_code >= 500:
                respuesta.raise_for_status()  # los 5xx cuentan como fallo del circuito
    except pybreaker.CircuitBreakerError:
        return "Circuito abierto: el servicio de usuarios no esta disponible", 503
    except requests.exceptions.Timeout:
        return "El servicio de usuarios tardo demasiado en responder", 504
    except requests.exceptions.ConnectionError:
        return "No se pudo establecer comunicacion con el servicio de usuarios", 503
    except requests.exceptions.HTTPError:
        return "Error en el servicio de usuarios", 502
    if respuesta.status_code == 404:
        return "El administrador no existe", 400
    if respuesta.status_code != 200:
        return "No se pudo consultar el servicio de usuarios", 502
    return None, None


# Estado del circuit breaker hacia Usuarios (CLOSED, OPEN o HALF-OPEN)
@app.route("/circuito")
def estado_circuito():
    return jsonify({"usuarios": {
            "estado": circuito_usuarios.current_state.upper(),
            "fallos_consecutivos": circuito_usuarios.fail_counter,
            "umbral_fallos": circuito_usuarios.fail_max,
            "periodo_recuperacion": circuito_usuarios.reset_timeout
        }})


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


# ---------------- HOTELES ----------------

# Listar hoteles activos.
@app.route("/hoteles")
def listar_hoteles():
    ciudad = request.args.get("ciudad")
    todos = request.args.get("todos") == "1"
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT * FROM hoteles
        WHERE (%s OR estado = 'activo') AND (%s IS NULL OR ciudad = %s)
        """,
        (todos, ciudad, ciudad)
    )
    hoteles = cursor.fetchall()
    cursor.close()
    conexion.close()
    return jsonify(hoteles)


# Detalle de un hotel con sus habitaciones
@app.route("/hoteles/<int:id>")
def buscar_hotel(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM hoteles WHERE id = %s", (id,))
    hotel = cursor.fetchone()
    if hotel is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Hotel no encontrado"}), 404
    cursor.execute("SELECT * FROM habitaciones WHERE hotel_id = %s", (id,))
    hotel["habitaciones"] = [limpiar(h) for h in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify(hotel)


# Crear un hotel (consulta al servicio de Usuarios para validar el administrador)
@app.route("/hoteles", methods=["POST"])
def crear_hotel():
    nuevoHotel = request.json
    obligatorios = ["admin_id", "nombre", "ciudad"]
    faltantes = [campo for campo in obligatorios if not nuevoHotel.get(campo)]
    if faltantes:
        return jsonify({"Mensaje": "Faltan campos", "campos": faltantes}), 400

    error, codigo = validar_admin(nuevoHotel["admin_id"])
    if error:
        return jsonify({"Mensaje": error}), codigo

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        INSERT INTO hoteles
        (admin_id, nombre, ciudad, direccion, descripcion, servicios, telefono, correo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    valores = (
        nuevoHotel["admin_id"],
        nuevoHotel["nombre"],
        nuevoHotel["ciudad"],
        nuevoHotel.get("direccion"),
        nuevoHotel.get("descripcion"),
        nuevoHotel.get("servicios"),
        nuevoHotel.get("telefono"),
        nuevoHotel.get("correo")
    )
    cursor.execute(sql, valores)
    conexion.commit()
    nuevo_id = cursor.lastrowid
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": "Hotel creado", "id": nuevo_id}), 201


# Actualizar un hotel (solo se cambian los campos enviados)
@app.route("/hoteles/<int:id>", methods=["PUT"])
def actualizar_hotel(id):
    datos = request.json
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT id FROM hoteles WHERE id = %s", (id,))
    if cursor.fetchone() is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Hotel no encontrado"}), 404
    sql = """
        UPDATE hoteles
        SET nombre = COALESCE(%s, nombre),
            ciudad = COALESCE(%s, ciudad),
            direccion = COALESCE(%s, direccion),
            descripcion = COALESCE(%s, descripcion),
            servicios = COALESCE(%s, servicios),
            telefono = COALESCE(%s, telefono),
            correo = COALESCE(%s, correo),
            estado = COALESCE(%s, estado)
        WHERE id = %s
    """
    valores = (
        datos.get("nombre"), datos.get("ciudad"), datos.get("direccion"),
        datos.get("descripcion"), datos.get("servicios"), datos.get("telefono"),
        datos.get("correo"), datos.get("estado"), id
    )
    cursor.execute(sql, valores)
    conexion.commit()
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": "Hotel actualizado"})


# Eliminar un hotel (borra tambien sus habitaciones)
@app.route("/hoteles/<int:id>", methods=["DELETE"])
def eliminar_hotel(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("DELETE FROM hoteles WHERE id = %s", (id,))
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cursor.close()
    conexion.close()
    if filas_afectadas == 0:
        return jsonify({"Mensaje": "Hotel no encontrado"}), 404
    return jsonify({"Mensaje": "Hotel eliminado"})


# ---------------- HABITACIONES ----------------

# Crear una habitacion en un hotel
@app.route("/hoteles/<int:hotel_id>/habitaciones", methods=["POST"])
def crear_habitacion(hotel_id):
    nueva = request.json
    obligatorios = ["numero", "tipo", "capacidad", "precio_noche"]
    faltantes = [campo for campo in obligatorios if not nueva.get(campo)]
    if faltantes:
        return jsonify({"Mensaje": "Faltan campos", "campos": faltantes}), 400

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT id FROM hoteles WHERE id = %s", (hotel_id,))
    if cursor.fetchone() is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Hotel no encontrado"}), 404
    cursor.execute(
        "SELECT id FROM habitaciones WHERE hotel_id = %s AND numero = %s",
        (hotel_id, nueva["numero"])
    )
    if cursor.fetchone() is not None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Ya existe una habitacion con ese numero en el hotel"}), 409
    sql = """
        INSERT INTO habitaciones
        (hotel_id, numero, tipo, capacidad, precio_noche, amenidades)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    valores = (
        hotel_id, nueva["numero"], nueva["tipo"],
        nueva["capacidad"], nueva["precio_noche"], nueva.get("amenidades")
    )
    cursor.execute(sql, valores)
    conexion.commit()
    nuevo_id = cursor.lastrowid
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": "Habitacion creada", "id": nuevo_id}), 201


# Listar habitaciones activas de hoteles activos (lo usa el servicio de Disponibilidad)
@app.route("/habitaciones")
def listar_habitaciones():
    ciudad = request.args.get("ciudad")
    capacidad = request.args.get("capacidad", 1, type=int)
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        SELECT h.*, ho.nombre AS hotel, ho.ciudad
        FROM habitaciones h
        JOIN hoteles ho ON ho.id = h.hotel_id
        WHERE ho.estado = 'activo' AND h.estado = 'activa'
          AND h.capacidad >= %s
          AND (%s IS NULL OR ho.ciudad = %s)
        ORDER BY h.precio_noche
    """
    cursor.execute(sql, (capacidad, ciudad, ciudad))
    habitaciones = [limpiar(h) for h in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify(habitaciones)


# Detalle de una habitacion (lo usara el servicio de Reservas para conocer el precio)
@app.route("/habitaciones/<int:id>")
def buscar_habitacion(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        SELECT h.*, ho.nombre AS hotel, ho.ciudad
        FROM habitaciones h
        JOIN hoteles ho ON ho.id = h.hotel_id
        WHERE h.id = %s
    """
    cursor.execute(sql, (id,))
    habitacion = cursor.fetchone()
    cursor.close()
    conexion.close()
    if habitacion is None:
        return jsonify({"Mensaje": "Habitacion no encontrada"}), 404
    return jsonify(limpiar(habitacion))


# Actualizar una habitacion (precio, estado, etc.)
@app.route("/habitaciones/<int:id>", methods=["PUT"])
def actualizar_habitacion(id):
    datos = request.json
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT id FROM habitaciones WHERE id = %s", (id,))
    if cursor.fetchone() is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Habitacion no encontrada"}), 404
    sql = """
        UPDATE habitaciones
        SET tipo = COALESCE(%s, tipo),
            capacidad = COALESCE(%s, capacidad),
            precio_noche = COALESCE(%s, precio_noche),
            amenidades = COALESCE(%s, amenidades),
            estado = COALESCE(%s, estado)
        WHERE id = %s
    """
    valores = (
        datos.get("tipo"), datos.get("capacidad"), datos.get("precio_noche"),
        datos.get("amenidades"), datos.get("estado"), id
    )
    cursor.execute(sql, valores)
    conexion.commit()
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": "Habitacion actualizada"})


# Eliminar una habitacion
@app.route("/habitaciones/<int:id>", methods=["DELETE"])
def eliminar_habitacion(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("DELETE FROM habitaciones WHERE id = %s", (id,))
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cursor.close()
    conexion.close()
    if filas_afectadas == 0:
        return jsonify({"Mensaje": "Habitacion no encontrada"}), 404
    return jsonify({"Mensaje": "Habitacion eliminada"})



app.run(host="0.0.0.0", port=5000)
