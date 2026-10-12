#  Definición de Servicios del Sistema

---

##  Servicios del Primer Avance (Fase 1 - Core)

### 1.  Servicio de Usuarios
* **Responsabilidad Principal:**
  Gestionar la autenticación de usuarios, creación y administración de cuentas, perfiles de clientes y asignación de roles de acceso.
* **Información que Manejará:**
  * Datos personales (Nombres, Apellidos, Teléfono, Correo).
  * Credenciales de acceso (Contraseñas encriptadas).
  * Roles del sistema (Cliente / Administrador).
  * Estado de la cuenta (Activa / Inactiva).
* **Comunicación con otros Servicios:**
  * **Ninguna directa:** Recibe solicitudes de autenticación y consulta desde la Vista Principal / API Gateway.

---

### 2.  Servicio de Espacios (Hoteles y Habitaciones)
* **Responsabilidad Principal:**
  Administrar el catálogo de establecimientos, la gestión de habitaciones/salas, definición de tarifas y el control del calendario de disponibilidad.
* **Información que Manejará:**
  * Datos del inmueble (Nombre, Dirección, Ubicación, Descripción).
  * Catálogo de espacios (Tipos de habitación, Capacidad máxima, Amenidades).
  * Tarifas por noche o por hora.
  * Calendario de disponibilidad en tiempo real.
* **Comunicación con otros Servicios:**
  * **Servicio de Reservas:** Atiende consultas de disponibilidad y aplica bloqueos preventivos sobre habitaciones o espacios.

---

### 3.  Servicio de Reservas
* **Responsabilidad Principal:**
  Procesar y administrar el ciclo de vida completo de las reservas realizadas por los usuarios en la plataforma.
* **Información que Manejará:**
  * Identificador único de reserva (ID).
  * Referencia al cliente (ID de Usuario) y espacio reservado (ID de Espacio).
  * Rango de fechas (Fecha de check-in / check-out).
  * Monto total de la estancia.
  * Estado de la reserva (*Pendiente*, *Confirmada*, *Cancelada*).
* **Comunicación con otros Servicios:**
  * **Servicio de Espacios:** Consulta la disponibilidad antes de confirmar una reserva.
  * **Servicio de Pagos (Fase 2):** Notifica la creación de una reserva para iniciar el cobro.
  * **Servicio de Notificaciones (Fase 2):** Emite eventos de reserva para enviar confirmaciones al cliente.

---

##  Componentes Futuros (Fase 2 - Extensión)

### 4.  Servicio de Pagos
* **Responsabilidad Principal:**
  Procesar, validar y registrar las transacciones financieras vinculadas a la reserva de un espacio.
* **Información que Manejará:**
  * ID de Transacción y Comprobante de Pago.
  * ID de Reserva asociada.
  * Monto cobrado y método de pago.
  * Estado del pago (*Aprobado*, *Rechazado*, *Reembolsado*).
* **Comunicación con otros Servicios:**
  * **Servicio de Reservas:** Informa la aprobación o rechazo del pago para actualizar el estado final de la reserva.

---

### 5.  Servicio de Notificaciones
* **Responsabilidad Principal:**
  Gestionar el envío automático de alertas, comprobantes y recordatorios a los clientes a través de correo electrónico o SMS.
* **Información que Manejará:**
  * Plantillas de mensajería (Emails / SMS).
  * Datos de contacto del destinatario.
  * Registro e historial de envíos.
* **Comunicación con otros Servicios:**
  * **Servicio de Reservas y Servicio de Pagos:** Escucha eventos de creación de reserva o confirmación de pago para enviar las notificaciones.

---

##  Resumen de Comunicación e Interconexión