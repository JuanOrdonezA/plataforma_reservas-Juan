CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    telefono VARCHAR(30),
    password VARCHAR(255) NOT NULL,
    rol ENUM('cliente', 'agencia', 'admin_hotel', 'admin_sistema') NOT NULL DEFAULT 'cliente',
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usuarios de prueba
-- admin@hoteles.com / admin123    (admin_sistema)
-- hotel@hoteles.com / hotel123    (admin_hotel)
INSERT INTO usuarios (nombre, apellido, correo, telefono, password, rol) VALUES
('Admin', 'Sistema', 'admin@hoteles.com', '3000000000',
 'scrypt:32768:8:1$o1rvoaUSTZCRkDII$0e48ce4342484e22d958e9558c719dc723f4513288d54397b82d67e4fd0941dc0853c92536b19cc65403a6838b1eed7242cac478646d4366a52716c6e91481a6',
 'admin_sistema'),
('Laura', 'Gomez', 'hotel@hoteles.com', '3001111111',
 'scrypt:32768:8:1$WUrAhGCtr1Erp4OZ$1c089d71cb1fb67d288b916d5dc9850104ca2bc44225d89c20bc83d4dcbaf953a1c9cc53bb42ca54825191a672719422851878ac172c37249a59956f44dae279',
 'admin_hotel');
