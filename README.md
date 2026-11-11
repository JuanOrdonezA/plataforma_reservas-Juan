# Sistema de Reserva de Hoteles

## Nombre del proyecto

**Hoteles Cauca**: sistema de reserva de hoteles basado en microservicios (Sistemas Distribuidos, Unicomfacauca).

## Problema que resuelve

Buscar hotel y comprobar qué habitaciones están libres en unas fechas suele implicar llamar o revisar cada hotel por separado, y es fácil que dos personas reserven la misma habitación a la vez.

Este sistema reúne en un solo lugar los hoteles y sus habitaciones, calcula la disponibilidad por fechas y apaga la habitación durante 15 minutos mientras se completa una reserva, para evitar reservas duplicadas.

## Arquitectura

Microservicios en Flask (Python), cada uno con su propia base de datos MySQL, orquestados con Docker Compose.

```
                 ┌─────────────┐
   navegador ──▶ │  frontend   │  :3000  (nginx, página estática)
                 └─────────────┘

                 ┌─────────────┐   GET /usuarios/{id}   ┌─────────────┐
   cliente HTTP ▶│  espacios   │ ─────────────────────▶ │  usuarios   │
                 │  :5002      │                        │  :5001      │
                 └──────┬──────┘                        └──────┬──────┘
                        │                                      │
                 ┌──────▼──────┐                        ┌──────▼──────┐
                 │mysql_espacios│ :3308                 │mysql_usuarios│ :3307
                 │ espacios_db │                        │ usuarios_db │
                 └─────────────┘                        └─────────────┘
```

- Una base de datos por servicio. Los servicios no comparten tablas.
- Comunicación entre servicios por HTTP: al crear un hotel, **espacios** consulta a **usuarios** para comprobar que el administrador (`admin_id`) existe.
- Los puertos entre paréntesis son los que se publican en tu máquina. Dentro de la red de Docker, los servicios escuchan en el 5000 y MySQL en el 3306.
- El API Gateway (nginx) está en el `docker-compose.yml` pero **comentado** por ahora.
- Hay login básico (`POST /login` en usuarios, contraseñas con hash) pero **sin tokens ni roles**: la página guarda el usuario en el navegador y los servicios no verifican quién llama.

```
hoteles/
├── docker-compose.yml
├── .env
├── frontend/       # página de inicio (index.html, styles.css, Dockerfile)
├── usuarios/       # servicio de Usuarios (app.py, database.py, Dockerfile)
└── espacios/       # servicio de Espacios (app.py, database.py, Dockerfile)
```

## Servicios implementados

### Responsabilidades

| Servicio | Responsabilidad | Información administrada | Comunicación con otros servicios |
| --- | --- | --- | --- |
| usuarios (:5001) | Registrar y administrar las personas del sistema | Usuarios: nombre, apellido, correo, teléfono, contraseña (con hash) y estado de la cuenta | Responde las consultas de espacios. No llama a ningún servicio. |
| espacios (:5002) | Administrar hoteles y habitaciones, calcular disponibilidad por fechas y bloquear habitaciones durante 15 minutos | Hoteles, habitaciones y ocupaciones (bloqueos y fechas confirmadas) | Consulta a usuarios (HTTP) para validar el administrador de un hotel. |
| frontend (:3000) | Buscar disponibilidad, reservar (apartar 15 min y confirmar), ver mis reservas y el estado de los servicios | Página estática (`index.html`, `styles.css`, `app.js`); las reservas del usuario se guardan en el navegador | Llama desde el navegador a usuarios (:5001) y espacios (:5002). |



### Comunicación entre servicios

| Elemento | Descripción |
| --- | --- |
| Servicio que solicita | espacios |
| Servicio que responde | usuarios |
| Endpoint utilizado | `GET http://usuarios:5000/usuarios/{id}` |
| Información enviada | El `admin_id` (id del usuario) en la ruta, al crear un hotel con `POST /hoteles` |
| Información recibida | `200` con el usuario (id, nombre, apellido, correo, teléfono, estado) o `404` si no existe |

Si el usuario no existe, espacios responde `400`. Esta es la única comunicación entre servicios por ahora; la siguiente la traerá el servicio de Reservas.

### Resiliencia: timeout y circuit breaker

La llamada de espacios a usuarios usa **timeout** y un **circuit breaker** (`pybreaker`):

| Situación | Respuesta de espacios |
| --- | --- |
| Usuarios tarda más de `USUARIOS_TIMEOUT` segundos | `504` |
| Usuarios no se puede alcanzar | `503` |
| Usuarios responde 5xx | `502` (cuenta como fallo del circuito) |
| Circuito abierto (muchos fallos seguidos) | `503` inmediato, sin llamar a usuarios |

Tras `CB_MAX_FALLOS` fallos seguidos el circuito pasa a `OPEN`; después de `CB_RECUPERACION` segundos queda `HALF-OPEN` y deja pasar una llamada de prueba (si funciona vuelve a `CLOSED`). El estado se consulta en `GET http://localhost:5002/circuito/usuarios`. Para probarlo: `docker compose stop usuarios` y crear hoteles (`POST /hoteles`) varias veces.

## Endpoints

Los servicios implementan los métodos REST principales: GET (consultar), GET por id, POST (crear), PUT (actualizar) y DELETE (eliminar). Los errores devuelven un JSON con `Mensaje`.

### Servicio Usuarios (`http://localhost:5001`)

| Método | Endpoint | Descripción | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| GET | /usuarios | Consultar usuarios | Ninguna | Lista de usuarios |
| GET | /usuarios/{id} | Consultar un usuario | ID del usuario | Usuario específico, o 404 |
| POST | /usuarios | Crear usuario | JSON: nombre, apellido, correo, password, telefono (opcional) | Confirmación con el id (201), o 409 si el correo ya existe |
| PUT | /usuarios/{id} | Actualizar usuario | JSON con nombre, apellido y/o telefono | Confirmación, o 404 |
| PATCH | /usuarios/{id}/estado | Activar o desactivar la cuenta | JSON: `{"estado":"activa"}` o `"inactiva"` | Confirmación, o 404 |
| DELETE | /usuarios/{id} | Eliminar usuario | ID del usuario | Confirmación, o 404 |

| POST | /login | Iniciar sesión | JSON: correo, password | Usuario (sin contraseña), 401 si los datos son incorrectos, 403 si la cuenta está inactiva |

### Servicio Reservas (`http://localhost:5003`)

Una reserva une a un usuario con una habitación y unas fechas. Para crearla, reservas valida el usuario en **usuarios**, consulta la habitación y su precio en **espacios** y aparta las fechas (bloqueo de 15 minutos). Ambas llamadas usan timeout y circuit breaker (uno por servicio).

| Método | Endpoint | Descripción | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| GET | /reservas | Consultar reservas | Opcional: `?usuario_id=` y `?estado=` | Lista de reservas |
| GET | /reservas/{id} | Consultar una reserva | ID de la reserva | Reserva, o 404 |
| POST | /reservas | Crear reserva (queda `pendiente`) | JSON: usuario_id, habitacion_id, entrada, salida, huespedes (opcional) | Id y total (201); 400 usuario o fechas inválidas; 409 habitación ocupada |
| POST | /reservas/{id}/confirmar | Confirmar la reserva pendiente | ID de la reserva | Confirmación, o 409 si ya venció |
| POST | /reservas/{id}/cancelar | Cancelar y liberar las fechas | ID de la reserva | Confirmación, o 409 si ya estaba cancelada o vencida |
| PUT | /reservas/{id} | Cambiar las fechas | JSON: entrada, salida | Confirmación y nuevo total, o 409 si se cruzan |
| GET | /circuito | Estado de los circuit breakers hacia usuarios y espacios | Ninguna | `CLOSED`, `OPEN` o `HALF-OPEN` por servicio |

Estados: `pendiente` (vence a los 15 minutos), `confirmada`, `cancelada` y `expirada`. Los errores de comunicación devuelven 503, 504 o 502, igual que en espacios.

### Servicio Espacios (`http://localhost:5002`)

#### Hoteles

| Método | Endpoint | Descripción | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| GET | /hoteles | Consultar hoteles activos | Opcional: `?ciudad=` | Lista de hoteles |
| GET | /hoteles/{id} | Consultar un hotel | ID del hotel | Hotel con sus habitaciones, o 404 |
| POST | /hoteles | Crear hotel | JSON: admin_id, nombre, ciudad y opcionales (direccion, descripcion, servicios, telefono, correo) | Confirmación con el id (201) |
| PUT | /hoteles/{id} | Actualizar hotel | JSON con los campos a cambiar | Confirmación, o 404 |
| DELETE | /hoteles/{id} | Eliminar hotel y sus habitaciones | ID del hotel | Confirmación, o 404 |
| GET | /hoteles/disponibles | Buscar hoteles con habitaciones libres | `?entrada=&salida=` (AAAA-MM-DD), opcional `huespedes` y `ciudad` | Hoteles con sus habitaciones libres y el precio total |

#### Habitaciones

| Método | Endpoint | Descripción | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| POST | /hoteles/{id}/habitaciones | Crear habitación | JSON: numero, tipo, capacidad, precio_noche, amenidades (opcional) | Confirmación con el id (201), o 409 si el número ya existe |
| GET | /habitaciones/{id} | Consultar una habitación | ID de la habitación | Habitación con su hotel y ciudad, o 404 |
| PUT | /habitaciones/{id} | Actualizar habitación | JSON con tipo, capacidad, precio_noche, amenidades y/o estado | Confirmación, o 404 |
| DELETE | /habitaciones/{id} | Eliminar habitación | ID de la habitación | Confirmación, o 404 |
| GET | /habitaciones/{id}/disponibilidad | Consultar si está libre | `?entrada=&salida=` | `disponible` (true/false), noches y precio total |

#### Ocupaciones

| Método | Endpoint | Descripción | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| GET | /ocupaciones | Consultar ocupaciones | Opcional: `?habitacion_id=` | Lista de ocupaciones |
| GET | /ocupaciones/{id} | Consultar una ocupación | ID de la ocupación | Ocupación específica, o 404 |
| POST | /ocupaciones | Bloquear una habitación 15 minutos | JSON: habitacion_id, entrada, salida | Confirmación con el id (201), o 409 si ya está ocupada |
| PUT | /ocupaciones/{id} | Cambiar las fechas | JSON: entrada, salida | Confirmación, o 404 / 409 |
| POST | /ocupaciones/{id}/confirmar | Convertir el bloqueo en ocupación confirmada | JSON: `{"reserva_id":10}` | Confirmación, o 404 si venció |
| DELETE | /ocupaciones/{id} | Liberar las fechas | ID de la ocupación | Confirmación, o 404 |


## Bases de datos

| Servicio | Base de datos utilizada | Tablas principales |
| --- | --- | --- |
| usuarios | `usuarios_db` (MySQL 8.0, contenedor `mysql_usuarios`, puerto local 3307) | `usuarios` |
| reservas | `reservas_db` (MySQL 8.0, contenedor `mysql_reservas`, puerto local 3309) | `reservas` (el script está en `reservas/init.sql`) |
| espacios | `espacios_db` (MySQL 8.0, contenedor `mysql_espacios`, puerto local 3308) | `hoteles`, `habitaciones`, `ocupaciones` |

Cada servicio tiene su propio MySQL 8.0 con volumen persistente (`datos_usuarios`, `datos_espacios`). Docker crea las bases de datos vacías; **las tablas se crean manualmente** (por ejemplo desde un cliente MySQL en `localhost:3307` y `localhost:3308`, usuario `root`).

**usuarios_db**

```sql
CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    telefono VARCHAR(30),
    password VARCHAR(255) NOT NULL,
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**espacios_db**

```sql
CREATE TABLE hoteles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,              -- id de un usuario (vive en usuarios_db)
    nombre VARCHAR(150) NOT NULL,
    ciudad VARCHAR(100) NOT NULL,
    direccion VARCHAR(200),
    descripcion TEXT,
    servicios VARCHAR(255),
    telefono VARCHAR(30),
    correo VARCHAR(150),
    estado ENUM('activo', 'inactivo') NOT NULL DEFAULT 'activo'
);

CREATE TABLE habitaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hotel_id INT NOT NULL,
    numero VARCHAR(20) NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    capacidad INT NOT NULL,
    precio_noche DECIMAL(12, 2) NOT NULL,
    amenidades VARCHAR(255),
    estado ENUM('activa', 'mantenimiento') NOT NULL DEFAULT 'activa',
    FOREIGN KEY (hotel_id) REFERENCES hoteles(id) ON DELETE CASCADE,
    UNIQUE (hotel_id, numero)
);

CREATE TABLE ocupaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    habitacion_id INT NOT NULL,
    fecha_entrada DATE NOT NULL,
    fecha_salida DATE NOT NULL,
    tipo ENUM('bloqueo', 'confirmada') NOT NULL DEFAULT 'bloqueo',
    reserva_id INT NULL,
    expira_en DATETIME NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (habitacion_id) REFERENCES habitaciones(id) ON DELETE CASCADE,
    INDEX (habitacion_id, fecha_entrada, fecha_salida)
);
```

## Variables de entorno

Se definen en el archivo `.env` y los servicios las leen con `env_file`. `DB_HOST` y `DB_NAME` las fija el `docker-compose.yml` para cada servicio.

| Variable | Valor | Descripción |
| --- | --- | --- |
| DB_USER | root | Usuario de MySQL |
| DB_PASSWORD | root | Contraseña de MySQL (también es la contraseña root del contenedor) |
| DB_PORT | 3306 | Puerto interno de MySQL |
| USUARIOS_URL | http://usuarios:5000 | Dirección del servicio de Usuarios, usada por Espacios |
| USUARIOS_TIMEOUT | 2 (opcional) | Segundos máximos de espera a Usuarios (en espacios) |
| SERVICIOS_TIMEOUT | 2 (opcional) | Segundos máximos de espera a Usuarios y Espacios (en reservas) |
| ESPACIOS_URL | http://espacios:5000 | Dirección de Espacios, usada por Reservas (la fija el compose) |
| CB_MAX_FALLOS | 3 (opcional) | Fallos seguidos para abrir el circuito |
| CB_RECUPERACION | 30 (opcional) | Segundos con el circuito abierto antes de probar de nuevo |
| DB_HOST | mysql_usuarios / mysql_espacios | Definida en el compose por servicio |
| DB_NAME | usuarios_db / espacios_db | Definida en el compose por servicio |

## Cómo ejecutar el sistema

Requisitos: Docker y Docker Compose.

```bash
# 1. Construir y levantar todo
docker compose up -d --build

# 2. Crear las tablas a mano (ver sección Bases de datos)
#    usuarios_db -> localhost:3307   espacios_db -> localhost:3308
#    Conectarse desde la terminal (contraseña: root):
docker compose exec mysql_usuarios mysql -uroot -proot usuarios_db
docker compose exec mysql_espacios mysql -uroot -proot espacios_db
docker compose exec -T mysql_reservas mysql -uroot -proot reservas_db < reservas/init.sql
#    O, si tienes el cliente mysql instalado en tu máquina:
mysql -h 127.0.0.1 -P 3307 -uroot -proot usuarios_db
mysql -h 127.0.0.1 -P 3308 -uroot -proot espacios_db

# 3. Probar
#    Página:   http://localhost:3000
#    Usuarios: http://localhost:5001/usuarios
#    Espacios: http://localhost:5002/hoteles
#    Reservas: http://localhost:5003/reservas
```

Comandos útiles:

```bash
docker compose logs -f espacios   # ver los registros de un servicio
docker compose down               # detener (conserva los datos)
docker compose down -v            # detener y borrar las bases de datos
```
