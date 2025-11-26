import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'emergencias.db')

def poblar_datos_reales():
    """
    Función principal para poblar la base de datos con datos de prueba.
    Crea todas las tablas necesarias y inserta datos iniciales para pruebas.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        print("🧹 Limpiando y recreando base de datos...")
        
        # ELIMINAR tablas en orden de dependencias
        tablas = [
            "VISITAS_EMERGENCIA",
            "CAMAS_ATENCION", 
            "DOCTORES",
            "TRABAJADORES_SOCIALES",
            "PACIENTES",
            "USUARIOS_SISTEMA",
            "CONSECUTIVOS_VISITAS"
        ]
        
        for tabla in tablas:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {tabla}")
                print(f"   - Tabla {tabla} eliminada")
            except Exception as e:
                print(f"   - Error eliminando {tabla}: {e}")
        
        # RECREAR todas las tablas desde schema2.sql
        schema_path = os.path.join(BASE_DIR, 'schema2.sql')
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                sql_script = f.read()
            cursor.executescript(sql_script)
            print("✅ Tablas recreadas desde schema2.sql")
        else:
            print("❌ schema2.sql no encontrado")

        print("📦 Insertando datos de prueba...")

        # Datos de pacientes de ejemplo
        pacientes = [
            ('Ana García López', 28, 'F', '555-0101'),
            ('Carlos Rodríguez', 45, 'M', '555-0102'),
            ('María Fernández', 32, 'F', '555-0103')
        ]
        cursor.executemany(
            "INSERT INTO PACIENTES (nombre, edad, sexo, contacto) VALUES (?, ?, ?, ?)", 
            pacientes
        )

        # Plantilla médica inicial
        doctores = [
            ('Dr. Ricardo Mendiola', 1, 1),
            ('Dra. Elena Vázquez', 1, 1),
            ('Dr. Samuel Kim', 1, 1)
        ]
        cursor.executemany(
            "INSERT INTO DOCTORES (nombre, sala_id, disponible) VALUES (?, ?, ?)", 
            doctores
        )

        # Personal de trabajo social
        cursor.execute(
            "INSERT INTO TRABAJADORES_SOCIALES (nombre, sala_id, activo) VALUES (?, ?, ?)",
            ('Lic. Roberto Gómez', 1, 1)
        )

        # Configuración de camas disponibles (SIN restricciones UNIQUE)
        for i in range(101, 106):
            cursor.execute(
                "INSERT INTO CAMAS_ATENCION (numero, sala_id, ocupada) VALUES (?, ?, ?)",
                (i, 1, 0)
            )

        # Usuarios del sistema para acceso
        usuarios = [
            ('social1', '1234', 'SOCIAL', 1),
            ('doctor1', 'doctor1', 'DOCTOR', 1),
            ('doctor2', 'doctor2', 'DOCTOR', 2),
            ('doctor3', 'doctor3', 'DOCTOR', 3)
        ]
        cursor.executemany(
            "INSERT INTO USUARIOS_SISTEMA (username, password, rol, id_personal) VALUES (?, ?, ?, ?)", 
            usuarios
        )

        # Inicialización del sistema de consecutivos
        cursor.execute(
            "INSERT OR REPLACE INTO CONSECUTIVOS_VISITAS (sala_id, ultimo_consecutivo) VALUES (?, ?)",
            (1, 0)
        )

        conn.commit()
        
        print("\n✅ Base de datos poblada exitosamente!")
        print("\n🔧 Cambios aplicados:")
        print("   - Tablas recreadas sin UNIQUE constraint en CAMAS_ATENCION.paciente_id")
        print("   - Exclusión mutua manejada a nivel de aplicación")
        
        print("\n🔑 Credenciales de acceso para pruebas:")
        print("   Trabajador Social: usuario 'social1' - contraseña '1234'")
        print("   Doctores: usuario 'doctor1' - contraseña 'doctor1'")
        print("              usuario 'doctor2' - contraseña 'doctor2'")
        print("              usuario 'doctor3' - contraseña 'doctor3'")

    except Exception as e:
        print(f"❌ Error durante la población de la base de datos: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    poblar_datos_reales()
