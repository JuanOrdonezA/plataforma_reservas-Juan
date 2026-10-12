from flask import Flask, jsonify, request
from datetime import date, datetime
from decimal import Decimal
import requests, os
from database import conectar

url_usuarios = os.getenv("USUARIOS_URL")

app = Flask(__name__)

MINUTOS_BLOQUEO = 15

# Condicion SQL: la ocupacion "o" cruza las fechas pedidas y sigue vigente
# (dos rangos se cruzan si uno empieza antes de que el otro termine)
CRUCE_FECHAS = """
    o.fecha_entrada < %s AND o.fecha_salida > %s
    AND (o.tipo = 'confirmada' OR o.expira_en > NOW())
"""


# ---------------- FUNCIONES DE AYUDA ----------------

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


# Pregunta al servicio de Usuarios si el administrador existe
def validar_admin(admin_id):
    try:
        respuesta = requests.get(f"{url_usuarios}/usuarios/{admin_id}", timeout=3)
    except requests.exceptions.RequestException:
        return "No se pudo consultar el servicio de usuarios", 503
    if respuesta.status_code == 404:
        return "El administrador no existe", 400
    if respuesta.status_code != 200:
        return "No se pudo consultar el servicio de usuarios", 502
    return None, None


# ---------------- HOTELES ----------------

# Listar hoteles (opcional: /hoteles?ciudad=Popayan)
@app.route("/hoteles")
def listar_hoteles():
    ciudad = request.args.get("ciudad")
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    if ciudad:
        cursor.execute("SELECT * FROM hoteles WHERE estado = 'activo' AND ciudad = %s", (ciudad,))
    else:
        cursor.execute("SELECT * FROM hoteles WHERE estado = 'activo'")
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


# ---------------- DISPONIBILIDAD ----------------

# Buscar hoteles con habitaciones libres
# /hoteles/disponibles?ciudad=Popayan&entrada=2026-12-20&salida=2026-12-23&huespedes=2
@app.route("/hoteles/disponibles")
def hoteles_disponibles():
    entrada, salida, error = leer_fechas(request.args.get("entrada"), request.args.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400
    huespedes = request.args.get("huespedes", 1, type=int)
    ciudad = request.args.get("ciudad")
    noches = (salida - entrada).days

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = f"""
        SELECT ho.id AS hotel_id, ho.nombre AS hotel, ho.ciudad,
               h.id AS habitacion_id, h.numero, h.tipo, h.capacidad, h.precio_noche
        FROM habitaciones h
        JOIN hoteles ho ON ho.id = h.hotel_id
        WHERE ho.estado = 'activo'
          AND h.estado = 'activa'
          AND h.capacidad >= %s
          AND (%s IS NULL OR ho.ciudad = %s)
          AND NOT EXISTS (
              SELECT 1 FROM ocupaciones o
              WHERE o.habitacion_id = h.id AND {CRUCE_FECHAS}
          )
        ORDER BY h.precio_noche
    """
    cursor.execute(sql, (huespedes, ciudad, ciudad, salida, entrada))
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    # Agrupar las habitaciones por hotel
    hoteles = {}
    for fila in filas:
        fila = limpiar(fila)
        if fila["hotel_id"] not in hoteles:
            hoteles[fila["hotel_id"]] = {
                "hotel_id": fila["hotel_id"],
                "hotel": fila["hotel"],
                "ciudad": fila["ciudad"],
                "habitaciones": []
            }
        hoteles[fila["hotel_id"]]["habitaciones"].append({
            "habitacion_id": fila["habitacion_id"],
            "numero": fila["numero"],
            "tipo": fila["tipo"],
            "capacidad": fila["capacidad"],
            "precio_noche": fila["precio_noche"],
            "precio_total": fila["precio_noche"] * noches
        })

    return jsonify({
        "entrada": entrada.isoformat(),
        "salida": salida.isoformat(),
        "noches": noches,
        "hoteles": list(hoteles.values())
    })


# Consultar si una habitacion esta libre
# /habitaciones/1/disponibilidad?entrada=2026-12-20&salida=2026-12-23
@app.route("/habitaciones/<int:id>/disponibilidad")
def disponibilidad_habitacion(id):
    entrada, salida, error = leer_fechas(request.args.get("entrada"), request.args.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT precio_noche, estado FROM habitaciones WHERE id = %s", (id,))
    habitacion = cursor.fetchone()
    if habitacion is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Habitacion no encontrada"}), 404
    sql = f"""
        SELECT COUNT(*) AS cruces FROM ocupaciones o
        WHERE o.habitacion_id = %s AND {CRUCE_FECHAS}
    """
    cursor.execute(sql, (id, salida, entrada))
    cruces = cursor.fetchone()["cruces"]
    cursor.close()
    conexion.close()

    noches = (salida - entrada).days
    return jsonify({
        "habitacion_id": id,
        "disponible": cruces == 0 and habitacion["estado"] == "activa",
        "noches": noches,
        "precio_total": float(habitacion["precio_noche"]) * noches
    })


# ---------------- OCUPACIONES (uso interno: servicio de Reservas) ----------------


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
    cursor.close()
    conexion.close()
    return jsonify(ocupaciones)


# Buscar una ocupacion por id
@app.route("/ocupaciones/<int:id>")
def buscar_ocupacion(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ocupaciones WHERE id = %s", (id,))
    ocupacion = cursor.fetchone()
    cursor.close()
    conexion.close()
    if ocupacion is None:
        return jsonify({"Mensaje": "Ocupacion no encontrada"}), 404
    return jsonify(limpiar(ocupacion))


# Cambiar las fechas de una ocupacion
# body: {"entrada": "2026-12-21", "salida": "2026-12-24"}
@app.route("/ocupaciones/<int:id>", methods=["PUT"])
def actualizar_ocupacion(id):
    datos = request.json
    entrada, salida, error = leer_fechas(datos.get("entrada"), datos.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT habitacion_id FROM ocupaciones WHERE id = %s", (id,))
    ocupacion = cursor.fetchone()
    if ocupacion is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Ocupacion no encontrada"}), 404

    # Se revisan los cruces ignorando la propia ocupacion
    sql = f"""
        SELECT COUNT(*) AS cruces FROM ocupaciones o
        WHERE o.habitacion_id = %s AND o.id <> %s AND {CRUCE_FECHAS}
    """
    cursor.execute(sql, (ocupacion["habitacion_id"], id, salida, entrada))
    if cursor.fetchone()["cruces"] > 0:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "La habitacion ya esta ocupada en esas fechas"}), 409

    cursor.execute(
        "UPDATE ocupaciones SET fecha_entrada = %s, fecha_salida = %s WHERE id = %s",
        (entrada, salida, id)
    )
    conexion.commit()
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": "Ocupacion actualizada"})


# Bloquear una habitacion por unas fechas durante 15 minutos
# body: {"habitacion_id": 1, "entrada": "2026-12-20", "salida": "2026-12-23"}
@app.route("/ocupaciones", methods=["POST"])
def bloquear():
    datos = request.json
    entrada, salida, error = leer_fechas(datos.get("entrada"), datos.get("salida"))
    if error:
        return jsonify({"Mensaje": error}), 400
    habitacion_id = datos.get("habitacion_id")

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    conexion.start_transaction()

    # FOR UPDATE: si dos personas reservan la misma habitacion al mismo tiempo,
    # la segunda espera a que la primera termine (asi no hay reservas duplicadas)
    cursor.execute(
        "SELECT id, estado FROM habitaciones WHERE id = %s FOR UPDATE",
        (habitacion_id,)
    )
    habitacion = cursor.fetchone()
    if habitacion is None or habitacion["estado"] != "activa":
        conexion.rollback()
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Habitacion no encontrada o no disponible"}), 404

    sql = f"""
        SELECT COUNT(*) AS cruces FROM ocupaciones o
        WHERE o.habitacion_id = %s AND {CRUCE_FECHAS}
    """
    cursor.execute(sql, (habitacion_id, salida, entrada))
    if cursor.fetchone()["cruces"] > 0:
        conexion.rollback()
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "La habitacion ya esta ocupada en esas fechas"}), 409

    sql = f"""
        INSERT INTO ocupaciones
        (habitacion_id, fecha_entrada, fecha_salida, tipo, expira_en)
        VALUES (%s, %s, %s, 'bloqueo', NOW() + INTERVAL {MINUTOS_BLOQUEO} MINUTE)
    """
    cursor.execute(sql, (habitacion_id, entrada, salida))
    conexion.commit()
    nuevo_id = cursor.lastrowid
    cursor.close()
    conexion.close()
    return jsonify({
        "Mensaje": "Habitacion bloqueada",
        "ocupacion_id": nuevo_id,
        "minutos_para_confirmar": MINUTOS_BLOQUEO
    }), 201


# Confirmar un bloqueo (cuando la reserva queda confirmada)
# body: {"reserva_id": 10}
@app.route("/ocupaciones/<int:id>/confirmar", methods=["POST"])
def confirmar(id):
    reserva_id = (request.json or {}).get("reserva_id")
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        UPDATE ocupaciones
        SET tipo = 'confirmada', reserva_id = %s, expira_en = NULL
        WHERE id = %s AND tipo = 'bloqueo' AND expira_en > NOW()
    """
    cursor.execute(sql, (reserva_id, id))
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cursor.close()
    conexion.close()
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
    cursor.close()
    conexion.close()
    if filas_afectadas == 0:
        return jsonify({"Mensaje": "Ocupacion no encontrada"}), 404
    return jsonify({"Mensaje": "Fechas liberadas"})


app.run(host="0.0.0.0", port=5000)
