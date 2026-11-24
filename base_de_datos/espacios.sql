CREATE TABLE IF NOT EXISTS hoteles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,                 -- id del usuario admin_hotel (vive en el servicio de Usuarios)
    nombre VARCHAR(150) NOT NULL,
    ciudad VARCHAR(100) NOT NULL,
    direccion VARCHAR(200),
    descripcion TEXT,
    servicios VARCHAR(255),                -- ej: "wifi, piscina, parqueadero"
    telefono VARCHAR(30),
    correo VARCHAR(150),
    estado ENUM('activo', 'inactivo') NOT NULL DEFAULT 'activo'
);

CREATE TABLE IF NOT EXISTS habitaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hotel_id INT NOT NULL,
    numero VARCHAR(20) NOT NULL,
    tipo VARCHAR(50) NOT NULL,             -- sencilla, doble, suite...
    capacidad INT NOT NULL,
    precio_noche DECIMAL(12, 2) NOT NULL,
    amenidades VARCHAR(255),
    estado ENUM('activa', 'mantenimiento') NOT NULL DEFAULT 'activa',
    FOREIGN KEY (hotel_id) REFERENCES hoteles(id) ON DELETE CASCADE,
    UNIQUE (hotel_id, numero)
);

-- Datos de prueba (admin_id = 2 es hotel@hoteles.com en el servicio de Usuarios)
-- INSERT IGNORE con id fijo: si el script se vuelve a ejecutar, no duplica ni falla.
INSERT IGNORE INTO hoteles (id, admin_id, nombre, ciudad, direccion, descripcion, servicios, telefono, correo) VALUES
(1, 2, 'Hotel Colonial Popayan', 'Popayan', 'Calle 5 # 4-50', 'Hotel en el centro historico', 'wifi, desayuno, parqueadero', '6028200000', 'reservas@colonial.com'),
(2, 2, 'Hotel Mirador del Mar', 'Cartagena', 'Av. San Martin # 8-20', 'Frente a la playa de Bocagrande', 'wifi, piscina, aire acondicionado', '6056500000', 'info@mirador.com');

INSERT IGNORE INTO habitaciones (hotel_id, numero, tipo, capacidad, precio_noche, amenidades) VALUES
(1, '101', 'sencilla', 1, 150000, 'tv, wifi'),
(1, '102', 'doble', 2, 220000, 'tv, wifi, balcon'),
(1, '201', 'suite', 4, 380000, 'tv, wifi, jacuzzi'),
(2, '301', 'doble', 2, 350000, 'vista al mar, minibar'),
(2, '302', 'familiar', 5, 520000, 'vista al mar, cocineta');
