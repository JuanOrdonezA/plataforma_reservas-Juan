from flask import Flask, jsonify, Response, request
import os
import requests

app = Flask(__name__)

USUARIOS_URL = os.getenv("USUARIOS_URL")
ESPACIOS_URL = os.getenv("ESPACIOS_URL")
DISPONIBILIDAD_URL = os.getenv("DISPONIBILIDAD_URL")
RESERVAS_URL = os.getenv("RESERVAS_URL")
TIEMPO_MAXIMO = float(os.getenv("GATEWAY_TIMEOUT", "5"))  # timeout hacia cualquier servicio (valor en .env)

SERVICIOS = {
    "usuarios": USUARIOS_URL,
    "espacios": ESPACIOS_URL,
    "disponibilidad": DISPONIBILIDAD_URL,
    "reservas": RESERVAS_URL
}


# Permite que la pagina (otro puerto) llame al gateway desde el navegador
@app.after_request
def permitir_navegador(respuesta):
    respuesta.headers["Access-Control-Allow-Origin"] = "*"
    respuesta.headers["Access-Control-Allow-Headers"] = "Content-Type"
    respuesta.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return respuesta


# Reenvia la peticion tal cual (metodo, parametros y JSON) al servicio destino
# y devuelve su respuesta con el mismo codigo de estado
def reenviar(metodo, url):
    try:
        respuesta = requests.request(metodo, url, params=request.args,
                                     json=request.get_json(silent=True), timeout=TIEMPO_MAXIMO)
        return Response(respuesta.content, status=respuesta.status_code,
                        content_type=respuesta.headers.get("Content-Type", "application/json"))
    except requests.exceptions.Timeout:
        return jsonify({"Mensaje": "El servicio destino tardo en contestar"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"Mensaje": "No se pudo conectar el servicio"}), 503


# Respuestas JSON para errores generales (ruta inexistente, metodo no permitido, error interno)
@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({"Mensaje": "Ruta no encontrada"}), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return jsonify({"Mensaje": "Metodo HTTP no permitido en esta ruta"}), 405


@app.errorhandler(500)
def error_interno(e):
    return jsonify({"Mensaje": "Error interno del gateway"}), 500


# ---------------- USUARIOS ----------------

@app.route("/usuarios", methods=["GET", "POST"])
def ruta_usuarios():
    return reenviar(request.method, USUARIOS_URL + "/usuarios")


@app.route("/usuarios/<path:ruta>", methods=["GET", "PUT", "PATCH", "DELETE"])
def ruta_usuario_detalle(ruta):
    return reenviar(request.method, USUARIOS_URL + "/usuarios/" + ruta)


@app.route("/login", methods=["POST"])
def ruta_login():
    return reenviar(request.method, USUARIOS_URL + "/login")


# ---------------- ESPACIOS (hoteles y habitaciones) ----------------

@app.route("/hoteles", methods=["GET", "POST"])
def ruta_hoteles():
    return reenviar(request.method, ESPACIOS_URL + "/hoteles")


# Incluye POST /hoteles/{id}/habitaciones (crear habitacion)
@app.route("/hoteles/<path:ruta>", methods=["GET", "POST", "PUT", "DELETE"])
def ruta_hotel_detalle(ruta):
    return reenviar(request.method, ESPACIOS_URL + "/hoteles/" + ruta)


@app.route("/habitaciones", methods=["GET"])
def ruta_habitaciones():
    return reenviar(request.method, ESPACIOS_URL + "/habitaciones")


@app.route("/habitaciones/<path:ruta>", methods=["GET", "PUT", "DELETE"])
def ruta_habitacion_detalle(ruta):
    return reenviar(request.method, ESPACIOS_URL + "/habitaciones/" + ruta)


# ---------------- DISPONIBILIDAD (disponibilidad y ocupaciones) ----------------

@app.route("/disponibilidad/<path:ruta>", methods=["GET"])
def ruta_disponibilidad(ruta):
    return reenviar(request.method, DISPONIBILIDAD_URL + "/disponibilidad/" + ruta)


@app.route("/ocupaciones", methods=["GET", "POST"])
def ruta_ocupaciones():
    return reenviar(request.method, DISPONIBILIDAD_URL + "/ocupaciones")


@app.route("/ocupaciones/<path:ruta>", methods=["GET", "POST", "PUT", "DELETE"])
def ruta_ocupacion_detalle(ruta):
    return reenviar(request.method, DISPONIBILIDAD_URL + "/ocupaciones/" + ruta)


# ---------------- RESERVAS ----------------

@app.route("/reservas", methods=["GET", "POST"])
def ruta_reservas():
    return reenviar(request.method, RESERVAS_URL + "/reservas")


@app.route("/reservas/<path:ruta>", methods=["GET", "POST", "PUT", "DELETE"])
def ruta_reserva_detalle(ruta):
    return reenviar(request.method, RESERVAS_URL + "/reservas/" + ruta)


# ---------------- ESTADO DEL SISTEMA ----------------

# Circuit breakers de un servicio: /circuito/espacios, /circuito/disponibilidad, /circuito/reservas
@app.route("/circuito/<servicio>", methods=["GET"])
def ruta_circuito(servicio):
    if servicio not in ("espacios", "disponibilidad", "reservas"):
        return jsonify({"Mensaje": "Ese servicio no tiene circuit breaker"}), 404
    return reenviar(request.method, SERVICIOS[servicio] + "/circuito")


# Pregunta a cada servicio si responde (lo usa el panel de administracion)
@app.route("/salud", methods=["GET"])
def salud():
    pruebas = {
        "usuarios": USUARIOS_URL + "/usuarios/0",
        "espacios": ESPACIOS_URL + "/hoteles/0",
        "disponibilidad": DISPONIBILIDAD_URL + "/ocupaciones/0",
        "reservas": RESERVAS_URL + "/reservas/0"
    }
    estado = {}
    for nombre, url in pruebas.items():
        try:
            respuesta = requests.get(url, timeout=2)
            estado[nombre] = "en linea" if respuesta.status_code < 500 else "con errores"
        except requests.exceptions.RequestException:
            estado[nombre] = "sin respuesta"
    return jsonify(estado)


app.run(host="0.0.0.0", port=5000)
