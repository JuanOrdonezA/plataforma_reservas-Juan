from flask import Flask, jsonify, request
from werkzeug.security import generate_password_hash
import mysql.connector
from database import conectar

app = Flask(__name__)

# Columnas que se devuelven (nunca se devuelve la contrasena)
COLUMNAS = "id, nombre, apellido, correo, telefono, estado"


# Listar usuarios
@app.route("/usuarios")
def listar():
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(f"SELECT {COLUMNAS} FROM usuarios")
    usuarios = cursor.fetchall()
    cursor.close()
    conexion.close()
    return jsonify(usuarios)


# Buscar un usuario por id 
@app.route("/usuarios/<int:id>")
def buscar(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = f"""
        SELECT {COLUMNAS} FROM usuarios
        WHERE id = %s
    """
    cursor.execute(sql, (id,))
    usuario = cursor.fetchone()
    cursor.close()
    conexion.close()
    if usuario is None:
        return jsonify({"Mensaje": "Usuario no encontrado"}), 404
    return jsonify(usuario)


# Registrar un usuario nuevo
@app.route("/usuarios", methods=["POST"])
def crear():
    nuevoUsuario = request.json
    obligatorios = ["nombre", "apellido", "correo", "password"]
    faltantes = [campo for campo in obligatorios if not nuevoUsuario.get(campo)]
    if faltantes:
        return jsonify({"Mensaje": "Faltan campos", "campos": faltantes}), 400

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        INSERT INTO usuarios
        (nombre, apellido, correo, telefono, password)
        VALUES (%s, %s, %s, %s, %s)
    """
    valores = (
        nuevoUsuario["nombre"],
        nuevoUsuario["apellido"],
        nuevoUsuario["correo"],
        nuevoUsuario.get("telefono"),
        generate_password_hash(nuevoUsuario["password"])
    )
    try:
        cursor.execute(sql, valores)
        conexion.commit()
    except mysql.connector.IntegrityError:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "El correo ya esta registrado"}), 409
    nuevo_id = cursor.lastrowid
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": "Usuario creado", "id": nuevo_id}), 201


# Actualizar datos de contacto
@app.route("/usuarios/<int:id>", methods=["PUT"])
def actualizar(id):
    datos = request.json
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        UPDATE usuarios
        SET nombre = COALESCE(%s, nombre),
            apellido = COALESCE(%s, apellido),
            telefono = COALESCE(%s, telefono)
        WHERE id = %s
    """
    valores = (datos.get("nombre"), datos.get("apellido"), datos.get("telefono"), id)
    cursor.execute(sql, valores)
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cursor.close()
    conexion.close()
    if filas_afectadas == 0:
        return buscar(id)  # si no existe devuelve 404, si no hubo cambios devuelve el usuario
    return jsonify({"Mensaje": "Usuario actualizado"})


# Activar o desactivar cuenta (Administrador del sistema)
@app.route("/usuarios/<int:id>/estado", methods=["PATCH"])
def cambiar_estado(id):
    estado = request.json.get("estado")
    if estado not in ["activa", "inactiva"]:
        return jsonify({"Mensaje": "Estado no valido: use activa o inactiva"}), 400
    return actualizar_campo(id, "estado", estado)


def actualizar_campo(id, campo, valor):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT id FROM usuarios WHERE id = %s", (id,))
    existe = cursor.fetchone()
    if existe is None:
        cursor.close()
        conexion.close()
        return jsonify({"Mensaje": "Usuario no encontrado"}), 404
    # campo solo puede ser "estado" (lo decide el codigo, no el usuario)
    cursor.execute(f"UPDATE usuarios SET {campo} = %s WHERE id = %s", (valor, id))
    conexion.commit()
    cursor.close()
    conexion.close()
    return jsonify({"Mensaje": f"{campo} actualizado", campo: valor})


# Eliminar un usuario
@app.route("/usuarios/<int:id>", methods=["DELETE"])
def eliminar(id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    sql = """
        DELETE FROM usuarios
        WHERE id = %s
    """
    cursor.execute(sql, (id,))
    conexion.commit()
    filas_afectadas = cursor.rowcount
    cursor.close()
    conexion.close()
    if filas_afectadas == 0:
        return jsonify({"Mensaje": "Usuario no encontrado"}), 404
    return jsonify({"Mensaje": "Usuario eliminado"})


app.run(host="0.0.0.0", port=5000)
