-- Habilita el uso de claves foráneas en SQLite
PRAGMA foreign_keys = ON;

-- Tabla de pacientes que almacena información demográfica básica
CREATE TABLE IF NOT EXISTS PACIENTES (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    edad INTEGER,
    sexo TEXT,
    contacto TEXT
);

-- Tabla de doctores con información de disponibilidad y asignación de sala
CREATE TABLE IF NOT EXISTS DOCTORES (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    sala_id INTEGER,
    disponible INTEGER DEFAULT 1
);

-- Tabla de trabajadores sociales del sistema
CREATE TABLE IF NOT EXISTS TRABAJADORES_SOCIALES (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    sala_id INTEGER,
    activo INTEGER DEFAULT 1
);

-- Tabla de camas de atención con estado de ocupación - SIN UNIQUE constraint
CREATE TABLE IF NOT EXISTS CAMAS_ATENCION (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    sala_id INTEGER NOT NULL,
    ocupada INTEGER DEFAULT 0,
    paciente_id INTEGER,  -- ✅ SIN UNIQUE constraint
    
    FOREIGN KEY (paciente_id) REFERENCES PACIENTES(id)
);

-- Tabla principal de visitas de emergencia que registra todo el proceso
CREATE TABLE IF NOT EXISTS VISITAS_EMERGENCIA (
    folio TEXT PRIMARY KEY,
    paciente_id INTEGER NOT NULL,
    doctor_id INTEGER,
    cama_id INTEGER,
    trabajador_social_id INTEGER,
    sala_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    estado TEXT,
    
    FOREIGN KEY (paciente_id) REFERENCES PACIENTES(id),
    FOREIGN KEY (doctor_id) REFERENCES DOCTORES(id),
    FOREIGN KEY (cama_id) REFERENCES CAMAS_ATENCION(id),
    FOREIGN KEY (trabajador_social_id) REFERENCES TRABAJADORES_SOCIALES(id)
);

-- Tabla de usuarios del sistema para autenticación y control de acceso
CREATE TABLE IF NOT EXISTS USUARIOS_SISTEMA (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    rol TEXT NOT NULL,
    id_personal INTEGER
);

-- Tabla para control de números consecutivos en un ambiente distribuido
CREATE TABLE IF NOT EXISTS CONSECUTIVOS_VISITAS (
    sala_id INTEGER PRIMARY KEY,
    ultimo_consecutivo INTEGER DEFAULT 0
);

