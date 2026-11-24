# Endpoints

Todas las solicitudes van al API Gateway: `http://localhost:5000`. La tabla completa de endpoints (entradas y respuestas) está en el [README](../../README.md#4-endpoints).

## Colección de Thunder Client

`thunder-collection_hoteles.json` trae una solicitud de ejemplo por cada operación, agrupadas por servicio.

Para importarla: Thunder Client → **Collections** → menú `≡` → **Import** → elegir el archivo.

> Los ids de ejemplo (`/usuarios/3`, `/reservas/1`…) dependen de los datos de tu base; ajústalos con el id que devuelva el POST.

## 0. Gateway y estado

| Método | Ruta | Solicitud |
| --- | --- | --- |
| GET | `/salud` | Salud de los servicios |
| GET | `/circuito/disponibilidad` | Circuito Disponibilidad -> Espacios |
| GET | `/circuito/reservas` | Circuito Reservas |
| GET | `/circuito/espacios` | Circuito Espacios -> Usuarios |
| GET | `/no-existe` | Ruta inexistente (404) |

## 1. Usuarios

| Método | Ruta | Solicitud |
| --- | --- | --- |
| GET | `/usuarios` | Listar usuarios |
| GET | `/usuarios/1` | Consultar usuario |
| POST | `/usuarios` | Crear usuario |
| PUT | `/usuarios/3` | Actualizar usuario |
| PATCH | `/usuarios/3/estado` | Desactivar cuenta |
| DELETE | `/usuarios/3` | Eliminar usuario |
| GET | `/usuarios/999999` | Usuario inexistente (404) |
| POST | `/login` | Login |

## 2. Espacios

| Método | Ruta | Solicitud |
| --- | --- | --- |
| GET | `/hoteles` | Listar hoteles |
| GET | `/hoteles/1` | Consultar hotel |
| POST | `/hoteles` | Crear hotel (valida admin en Usuarios) |
| POST | `/hoteles` | Crear hotel con admin inexistente (400) |
| PUT | `/hoteles/3` | Actualizar hotel |
| DELETE | `/hoteles/3` | Eliminar hotel |
| POST | `/hoteles/1/habitaciones` | Crear habitacion |
| GET | `/habitaciones?ciudad=Popayan&capacidad=2` | Listar habitaciones |
| GET | `/habitaciones/1` | Consultar habitacion |
| PUT | `/habitaciones/1` | Actualizar habitacion |
| DELETE | `/habitaciones/4` | Eliminar habitacion |

## 3. Disponibilidad

| Método | Ruta | Solicitud |
| --- | --- | --- |
| GET | `/disponibilidad/hoteles?ciudad=Popayan&entrada=2027-01-15&salida=2027-01-18&huespedes=2` | Buscar hoteles con habitaciones libres |
| GET | `/disponibilidad/habitaciones/1?entrada=2027-01-15&salida=2027-01-18` | Habitacion libre? |
| GET | `/ocupaciones` | Listar ocupaciones |
| GET | `/ocupaciones/1` | Consultar ocupacion |
| POST | `/ocupaciones` | Apartar fechas 15 min |
| PUT | `/ocupaciones/1` | Cambiar fechas |
| POST | `/ocupaciones/1/confirmar` | Confirmar ocupacion |
| DELETE | `/ocupaciones/1` | Liberar fechas |

## 4. Reservas

| Método | Ruta | Solicitud |
| --- | --- | --- |
| GET | `/reservas` | Listar reservas |
| GET | `/reservas?usuario_id=1&estado=confirmada` | Reservas de un usuario |
| GET | `/reservas/1` | Consultar reserva |
| POST | `/reservas` | Crear reserva (Usuarios + Espacios + Disponibilidad) |
| POST | `/reservas/1/confirmar` | Confirmar reserva |
| PUT | `/reservas/1` | Cambiar fechas |
| POST | `/reservas/1/cancelar` | Cancelar reserva |
| DELETE | `/reservas/1` | Eliminar reserva |
| POST | `/reservas` | Usuario inexistente (400) |
