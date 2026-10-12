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
- Por ahora no hay login ni manejo de roles.

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
| frontend (:3000) | Mostrar la página de inicio (solo visual por ahora) | Página estática | Ninguna todavía. |



### Comunicación entre servicios

| Elemento | Descripción |
| --- | --- |
| Servicio que solicita | espacios |
| Servicio que responde | usuarios |
| Endpoint utilizado | `GET http://usuarios:5000/usuarios/{id}` |
| Información enviada | El `admin_id` (id del usuario) en la ruta, al crear un hotel con `POST /hoteles` |
| Información recibida | `200` con el usuario (id, nombre, apellido, correo, teléfono, estado) o `404` si no existe |

Si el usuario no existe, espacios responde `400`; si usuarios no responde, responde `503`. Esta es la única comunicación entre servicios por ahora; la siguiente la traerá el servicio de Reservas.

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
#    O, si tienes el cliente mysql instalado en tu máquina:
mysql -h 127.0.0.1 -P 3307 -uroot -proot usuarios_db
mysql -h 127.0.0.1 -P 3308 -uroot -proot espacios_db

# 3. Probar
#    Página:   http://localhost:3000
#    Usuarios: http://localhost:5001/usuarios
#    Espacios: http://localhost:5002/hoteles
```

Comandos útiles:

```bash
docker compose logs -f espacios   # ver los registros de un servicio
docker compose down               # detener (conserva los datos)
docker compose down -v            # detener y borrar las bases de datos
```
