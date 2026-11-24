-- Fechas ocupadas de cada habitacion (calendario de disponibilidad)
-- habitacion_id es el id de la habitacion en el servicio de Espacios (no hay llave foranea: otra base de datos)
-- bloqueo    = reserva en proceso, vence en 15 minutos
-- confirmada = reserva confirmada
CREATE TABLE IF NOT EXISTS ocupaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    habitacion_id INT NOT NULL,
    fecha_entrada DATE NOT NULL,
    fecha_salida DATE NOT NULL,
    tipo ENUM('bloqueo', 'confirmada') NOT NULL DEFAULT 'bloqueo',
    reserva_id INT NULL,
    expira_en DATETIME NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (habitacion_id, fecha_entrada, fecha_salida)
);
