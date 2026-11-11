-- Una reserva liga a un usuario (servicio Usuarios) con una habitacion (servicio Espacios).
-- ocupacion_id es el bloqueo/ocupacion que Espacios guarda para esas fechas.
-- pendiente  = habitacion apartada, falta confirmar (vence en expira_en)
-- confirmada = reserva confirmada
-- cancelada  = cancelada por el cliente
-- expirada   = no se confirmo a tiempo
CREATE TABLE IF NOT EXISTS reservas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    habitacion_id INT NOT NULL,
    ocupacion_id INT NOT NULL,
    hotel VARCHAR(150) NOT NULL,
    habitacion VARCHAR(100) NOT NULL,
    fecha_entrada DATE NOT NULL,
    fecha_salida DATE NOT NULL,
    huespedes INT NOT NULL DEFAULT 1,
    total DECIMAL(12, 2) NOT NULL,
    estado ENUM('pendiente', 'confirmada', 'cancelada', 'expirada') NOT NULL DEFAULT 'pendiente',
    expira_en DATETIME NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (usuario_id)
);
