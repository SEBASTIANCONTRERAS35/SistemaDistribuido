# Sistema Médico Distribuido de Emergencias

Sistema distribuido peer-to-peer para gestión de emergencias hospitalarias sin servidor central. Utiliza el algoritmo Bully para consenso distribuido y auto-descubrimiento de nodos vía multicast.

## 📋 Descripción General

Este sistema permite que múltiples salas de emergencia (nodos) coordinen la atención de pacientes de forma distribuida, sin depender de un servidor central. Cada nodo es autónomo y puede funcionar independientemente, pero se coordina con otros nodos para elección de líder y sincronización de datos.

### Características Principales

- **Consenso Distribuido**: Algoritmo Bully para elección automática de líder
- **Auto-descubrimiento**: Los nodos se encuentran automáticamente usando multicast UDP
- **Sin Servidor Central**: Arquitectura P2P completamente distribuida
- **Interface Moderna**: TUI (Terminal User Interface) con Textual
- **Base de Datos Local**: SQLite por nodo con sincronización eventual
- **Tolerante a Fallos**: Reelección automática si el líder falla

### Tecnologías

- **Python 3.8+**
- **Textual** - Framework TUI moderno
- **SQLAlchemy** - ORM para base de datos
- **Flask** - Context para base de datos (sin servidor web)
- **Multicast UDP** - Auto-descubrimiento de nodos
- **TCP/UDP Sockets** - Comunicación entre nodos

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────┐
│         Red Multicast (224.0.0.100:5005)                │
│         Auto-descubrimiento de nodos                    │
└─────────────────────────────────────────────────────────┘
         ↓                  ↓                  ↓
    ┌─────────┐        ┌─────────┐       ┌─────────┐
    │ NODO 1  │        │ NODO 2  │       │ NODO 3  │
    │ (LEADER)│←──────→│(FOLLOWER│←─────→│(FOLLOWER│
    │  ID: 3  │        │  ID: 1) │       │  ID: 2) │
    └─────────┘        └─────────┘       └─────────┘
         │                  │                  │
    TCP: 5557          TCP: 5555          TCP: 5556
    UDP: 6002          UDP: 6000          UDP: 6001
         │                  │                  │
    SQLite DB          SQLite DB          SQLite DB
    (sala3.db)         (sala1.db)         (sala2.db)
```

### Componentes Principales

| Componente | Ubicación | Descripción |
|------------|-----------|-------------|
| **main.py** | `backend/src/` | Entry point - Inicia Textual TUI |
| **bully/** | `backend/src/bully/` | Algoritmo de consenso distribuido |
| **textual_app/** | `backend/src/textual_app/` | Interface de usuario (screens, widgets) |
| **models.py** | `backend/src/` | Modelos de datos SQLAlchemy |
| **config.py** | `backend/src/` | Configuración y puertos |
| **auth.py** | `backend/src/` | Autenticación con bcrypt |

---

## 🎯 Algoritmo Bully Explicado

El algoritmo Bully es un método de elección de líder en sistemas distribuidos. Aquí está explicado de forma simple:

### Regla Básica

> **El nodo con el ID más alto se convierte en líder**

### ¿Cuándo se ejecuta una elección?

1. **Al inicio**: Cuando un nodo arranca por primera vez
2. **Líder caído**: Cuando no se reciben heartbeats del líder por 10 segundos
3. **Nodo nuevo**: Cuando se une un nodo con ID mayor al líder actual

### Flujo de Elección Paso a Paso

```
1. Nodo detecta ausencia de líder (sin heartbeat por 10s)
   ↓
2. Envía mensaje ELECTION a todos los nodos con ID > mi_id
   ↓
3. ¿Alguien responde con OK?
   ├─ SÍ → Espero recibir mensaje COORDINATOR del nuevo líder
   └─ NO → Me declaro líder y envío COORDINATOR a todos
   ↓
4. Líder envía HEARTBEAT cada 3 segundos
   ↓
5. Followers verifican heartbeats cada segundo
```

### Protocolos de Red

| Protocolo | Puerto | Uso | Características |
|-----------|--------|-----|-----------------|
| **TCP** | 5555 + NODE_ID | Mensajes ELECTION, OK, COORDINATOR | Confiable, garantiza entrega |
| **UDP** | 6000 + NODE_ID | Heartbeats del líder | Rápido, no crítico si se pierde |
| **Multicast UDP** | 224.0.0.100:5005 | Auto-descubrimiento de nodos | Announce cada 5s, timeout 15s |

### Ejemplo Práctico

```
Cluster con 3 nodos: ID=1, ID=2, ID=3

1. Todos arrancan → Esperan 10s para descubrir líder
2. No hay líder → Inician elección
3. Node 1 envía ELECTION a Node 2 y Node 3
4. Node 2 envía ELECTION a Node 3
5. Node 3 (ID más alto) → Se declara LEADER
6. Node 3 envía COORDINATOR a Node 1 y Node 2
7. Node 3 envía heartbeats cada 3s por UDP

Resultado: Node 3 = LEADER, Node 1 y 2 = FOLLOWERS
```

---

## 📦 Instalación y Configuración

### Requisitos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)
- Sistema operativo: Linux, macOS o Windows
- Red que soporte multicast (para auto-descubrimiento)

### Pasos de Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd Proyectos

# 2. Crear entorno virtual (recomendado)
python3 -m venv venv

# Activar en Linux/Mac:
source venv/bin/activate

# Activar en Windows:
venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Verificar instalación
cd backend/src
python3 -c "import textual; print('✓ Textual instalado correctamente')"
```

### Variables de Entorno (Opcional)

Puedes configurar estas variables antes de ejecutar:

```bash
export NODE_ID=1              # ID del nodo (1, 2, 3...) - Auto-generado si no se especifica
export CLUSTER_MODE=dynamic   # 'dynamic' (default) o 'static'
export MULTICAST_GROUP=224.0.0.100  # Grupo multicast para discovery
export MULTICAST_PORT=5005    # Puerto multicast
```

---

## 🚀 Cómo Ejecutar el Sistema

### Ejecución Simple (1 Nodo)

```bash
cd backend/src
python3 main.py
```

El sistema:
1. Auto-genera un NODE_ID (basado en puertos disponibles)
2. Inicia en modo dinámico (auto-descubrimiento)
3. Muestra splash screen con información del nodo
4. Presenta pantalla de login

### Ejecución Multi-Nodo (Desarrollo Local)

Abre **3 terminales diferentes** y ejecuta en cada una:

**Terminal 1:**
```bash
cd backend/src
NODE_ID=1 python3 main.py
```

**Terminal 2:**
```bash
cd backend/src
NODE_ID=2 python3 main.py
```

**Terminal 3:**
```bash
cd backend/src
NODE_ID=3 python3 main.py
```

### Credenciales de Prueba

| Usuario | Contraseña | Rol |
|---------|------------|-----|
| `admin` | `admin123` | Administrador |
| `doctor1` | `doc123` | Doctor |
| `trabajador1` | `trab123` | Trabajador Social |

### Verificar que Funciona Correctamente

1. **Iniciar sesión** con cualquier credencial
2. Presionar **Ctrl+B** o navegar a "Ver estado del cluster Bully"
3. **Verificar** que aparecen:
   - ✅ 1 nodo marcado como **LEADER** (el de ID más alto)
   - ✅ Los demás nodos como **FOLLOWER**
   - ✅ Todos los nodos muestran "Active" en "Last Seen"

**Ejemplo esperado** (3 nodos):
```
Node 1: FOLLOWER (última actividad: Active)
Node 2: FOLLOWER (última actividad: Active)
Node 3: 👑 LEADER (última actividad: Active)
```

---

## 📁 Estructura del Código

```
backend/src/
├── main.py                 # Entry point - Inicia aplicación Textual
├── app_factory.py          # Factory de Flask (solo DB, sin web server)
├── config.py               # Configuración global y cálculo de puertos
├── models.py               # Modelos SQLAlchemy (Paciente, Doctor, Visita, etc.)
├── auth.py                 # Autenticación con bcrypt
│
├── bully/                  # 📡 Sistema de Consenso Distribuido
│   ├── bully_node.py       # ⭐ Lógica principal del algoritmo Bully
│   ├── communication.py    # Sockets TCP/UDP para mensajes
│   ├── discovery.py        # Auto-descubrimiento vía multicast
│   └── id_generator.py     # Generación automática de NODE_ID
│
└── textual_app/            # 🖥️ Interface de Usuario (TUI)
    ├── app.py              # Aplicación Textual principal
    ├── screens/            # Pantallas del sistema
    │   ├── splash.py       # Splash screen animado
    │   ├── login.py        # Login con validación
    │   ├── visitas.py      # Dashboard principal (tabla de visitas)
    │   ├── visita_detail.py # Detalles de una visita
    │   ├── simple_create_visit.py # Formulario crear visita
    │   └── bully_cluster.py # Visualización del cluster
    ├── widgets/            # Widgets personalizados
    ├── animations/         # Efectos visuales
    └── themes/             # Estilos CSS para terminal
        └── medical_blue.tcss # Tema médico profesional
```

### Archivos Clave

| Archivo | Líneas | Responsabilidad |
|---------|--------|-----------------|
| `bully/bully_node.py` | ~664 | Algoritmo Bully, elección de líder, heartbeats |
| `bully/discovery.py` | ~362 | Multicast para auto-descubrimiento |
| `textual_app/screens/visitas.py` | ~300+ | Dashboard principal con tabla de visitas |
| `models.py` | ~644 | Definición de modelos de base de datos |
| `main.py` | ~163 | Inicialización y arranque del sistema |

---

## 🗄️ Modelos de Datos

El sistema utiliza SQLAlchemy ORM con SQLite. Cada nodo tiene su propia base de datos local.

### Diagrama de Entidades

```
┌──────────────┐      ┌──────────────┐
│   Usuario    │      │     Sala     │
│              │      │              │
│ - username   │      │ - numero     │
│ - password   │      │ - ip_address │
│ - rol        │      │ - es_maestro │
└──────────────┘      └──────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼──────┐     ┌───────▼───────┐   ┌───────▼─────┐
│   Doctor     │     │TrabajadorSocial│   │     Cama    │
│              │     │                │   │             │
│ - nombre     │     │ - nombre       │   │ - numero    │
│ - especialidad│     └────────────────┘   │ - ocupada   │
└──────────────┘              │            └─────────────┘
       │                      │                   │
       │        ┌─────────────┴─────┐            │
       │        │                   │            │
       │   ┌────▼──────┐       ┌────▼────┐      │
       │   │ Paciente  │       │         │      │
       │   │           │       │         │      │
       │   │ - nombre  │       │         │      │
       │   │ - edad    │       │         │      │
       │   │ - curp    │       │         │      │
       │   └───────────┘       │         │      │
       │         │             │         │      │
       └─────────┴─────────────▼─────────┴──────┘
                    ┌──────────────────┐
                    │ VisitaEmergencia │
                    │                  │
                    │ - folio (único)  │
                    │ - sintomas       │
                    │ - diagnostico    │
                    │ - estado         │
                    │ - timestamp      │
                    └──────────────────┘
```

### Entidades Principales

#### VisitaEmergencia (Núcleo del Sistema)
```python
Campos:
  - folio: String único auto-generado (formato: PACIENTE+DOCTOR+SALA+CONSECUTIVO)
  - id_paciente: FK → Paciente
  - id_doctor: FK → Doctor
  - id_cama: FK → Cama
  - id_trabajador: FK → TrabajadorSocial
  - sintomas: Texto con descripción de síntomas
  - diagnostico: Texto con diagnóstico (nullable)
  - estado: 'activa' | 'completada' | 'cancelada'
  - timestamp: Fecha/hora de creación
  - fecha_cierre: Fecha/hora de cierre (nullable)

Relaciones:
  - Pertenece a: 1 Paciente, 1 Doctor, 1 Cama, 1 TrabajadorSocial, 1 Sala
```

#### Paciente
```python
Campos:
  - nombre: String(200)
  - edad: Integer
  - sexo: 'M' | 'F'
  - curp: String(18) - único, nullable
  - telefono: String(15)
  - contacto_emergencia: String(200)

Relaciones:
  - Tiene muchas: VisitaEmergencia
  - Puede ocupar: 1 Cama
```

#### Doctor
```python
Campos:
  - nombre: String(200)
  - especialidad: String(100)
  - id_sala: FK → Sala
  - disponible: Boolean (default: True)

Relaciones:
  - Pertenece a: 1 Sala
  - Atiende muchas: VisitaEmergencia
```

---

## 🔄 Flujos de Trabajo Principales

### Flujo 1: Inicio del Sistema

```
┌────────────────────┐
│ python3 main.py    │
└────────┬───────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ 1. Config.initialize_node_id()       │
│    - Auto-genera o lee NODE_ID       │
│    - Calcula puertos (TCP, UDP)      │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ 2. create_app()                       │
│    - Crea Flask context               │
│    - Inicializa SQLAlchemy            │
│    - Crea tablas de BD                │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ 3. BullyNode(use_discovery=True)     │
│    - Inicia NodeDiscovery (multicast) │
│    - Busca nodos en la red (10s)      │
│    - Inicia elección si no hay líder  │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ 4. MedicalApp.run()                   │
│    - SplashScreen (animación)         │
│    - LoginScreen                      │
│    - VisitasScreen (dashboard)        │
└───────────────────────────────────────┘
```

### Flujo 2: Elección de Líder (Algoritmo Bully)

```
╔═══════════════════════════════════════╗
║  Trigger: Sin heartbeat por 10s       ║
╚═══════════════════════════════════════╝
         │
         ▼
┌───────────────────────────────────────┐
│ 1. start_election()                   │
│    higher_nodes = [id > mi_id]        │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ 2. Enviar ELECTION a higher_nodes     │
│    (TCP - Puerto 5555+)               │
└────────┬──────────────────────────────┘
         │
         ├─────────┬──────────────┐
         │         │              │
         ▼         ▼              ▼
   ┌─────────┬─────────┬───────────────┐
   │ Caso A  │ Caso B  │   Caso C      │
   │ Recibo  │ Recibo  │   Nadie       │
   │   OK    │ timeout │  responde     │
   └─────────┴─────────┴───────────────┘
         │         │              │
         ▼         ▼              ▼
   ┌──────────────────┐    ┌─────────────────┐
   │ Espero           │    │ Me declaro      │
   │ COORDINATOR      │    │ LEADER          │
   │ (10s timeout)    │    │                 │
   └─────┬────────────┘    └────┬────────────┘
         │                      │
         ▼                      ▼
   ┌──────────────────┐    ┌─────────────────┐
   │ Recibido →       │    │ Envío           │
   │ Soy FOLLOWER     │    │ COORDINATOR     │
   │                  │    │ a todos         │
   └──────────────────┘    └────┬────────────┘
                                │
                                ▼
                          ┌─────────────────┐
                          │ Inicio          │
                          │ heartbeats      │
                          │ cada 3s (UDP)   │
                          └─────────────────┘
```

### Flujo 3: Crear Visita de Emergencia

```
Usuario presiona "Nueva Visita" (Ctrl+N)
         │
         ▼
┌───────────────────────────────────────┐
│ SimpleCreateVisitScreen               │
│ - Input: Nombre, Edad, Sexo, CURP    │
│ - Input: Síntomas (min 10 chars)     │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ Validación de campos                  │
│ - Edad: 0-150                         │
│ - Síntomas: >= 10 caracteres          │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ Buscar o crear Paciente               │
│ - Si CURP existe → Recuperar          │
│ - Si no → Crear nuevo                 │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ Auto-asignación de recursos           │
│ - Primer Doctor disponible            │
│ - Primera Cama disponible             │
│ - TrabajadorSocial (TODO: dinámico)   │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ Crear VisitaEmergencia                │
│ - Estado: 'activa'                    │
│ - Timestamp: now()                    │
│ - Folio: Auto-generado por trigger    │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ Actualizar UI                         │
│ - Cerrar modal                        │
│ - Refrescar tabla de visitas          │
│ - Notificación: "✓ Visita creada"    │
└───────────────────────────────────────┘
```

---

## 🛠️ Desarrollo y Testing

### Agregar Nueva Pantalla Textual

```python
# 1. Crear archivo: textual_app/screens/mi_nueva_screen.py
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, Label

class MiNuevaScreen(Screen):
    """Nueva pantalla del sistema"""

    BINDINGS = [
        ("escape", "app.pop_screen", "Volver"),
    ]

    def compose(self):
        """Compose UI widgets"""
        yield Header()
        yield Container(
            Label("Contenido de mi pantalla"),
            id="content"
        )
        yield Footer()

# 2. Importar en textual_app/app.py
from .screens.mi_nueva_screen import MiNuevaScreen

# 3. Navegar desde otra screen
def action_abrir_mi_pantalla(self):
    self.app.push_screen(MiNuevaScreen())
```

### Agregar Nuevo Modelo de Datos

```python
# 1. En models.py - Definir modelo
class NuevoModelo(db.Model):
    __tablename__ = 'nuevo_modelo'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'activo': self.activo
        }

# 2. Las tablas se crean automáticamente en app_factory.py:
# db.create_all()

# 3. Usar en queries
with app.app_context():
    # Crear
    nuevo = NuevoModelo(nombre="Test", descripcion="Ejemplo")
    db.session.add(nuevo)
    db.session.commit()

    # Consultar
    items = NuevoModelo.query.filter_by(activo=True).all()

    # Actualizar
    item = NuevoModelo.query.get(1)
    item.nombre = "Nuevo nombre"
    db.session.commit()
```

### Testing Multi-Nodo Local

#### Método 1: Manual (3-4 terminales)

```bash
# Terminal 1
cd backend/src
NODE_ID=1 python3 main.py

# Terminal 2
cd backend/src
NODE_ID=2 python3 main.py

# Terminal 3
cd backend/src
NODE_ID=3 python3 main.py
```

#### Método 2: Logs

Los logs se guardan automáticamente en `backend/logs/`:

```bash
# Ver logs en tiempo real
tail -f backend/logs/node_1.log

# Buscar errores
grep ERROR backend/logs/node_*.log

# Ver mensajes de elección
grep ELECTION backend/logs/node_*.log
```

#### Método 3: Verificar Estado del Cluster

Dentro de la aplicación:
1. Login con `admin / admin123`
2. Presionar **Ctrl+B**
3. Ver estado de todos los nodos
4. Verificar 1 LEADER, resto FOLLOWERS

---

## 🐛 Troubleshooting

### Problema: Sistema se queda en "Starting election..."

**Síntomas:**
- El splash screen muestra "Starting election" indefinidamente
- No aparece login screen

**Causa:**
- Puertos TCP/UDP bloqueados o ya en uso
- Otro proceso Python usando los mismos puertos

**Solución:**
```bash
# 1. Verificar puertos en uso
lsof -i :5555-5560  # TCP Bully
lsof -i :6000-6005  # UDP Heartbeat

# 2. Matar procesos Python antiguos
killall python3

# 3. Limpiar bases de datos si es necesario
rm backend/data/emergency_sala*.db

# 4. Reiniciar
cd backend/src
python3 main.py
```

---

### Problema: Todos los nodos son LEADER (split-brain)

**Síntomas:**
- En Bully Cluster Screen todos muestran estado LEADER
- Múltiples nodos intentan crear visitas

**Causa:**
- Los nodos no pueden comunicarse entre sí (firewall, red diferente)
- Mensajes TCP bloqueados

**Solución:**
```bash
# Para pruebas locales, asegurarse de usar localhost
NODE_ID=1 python3 main.py  # Usa localhost automáticamente

# Verificar que no hay firewall bloqueando:
# - TCP 5555-5560
# - UDP 6000-6005
# - Multicast 224.0.0.100:5005
```

---

### Problema: "Invalid credentials" al hacer login

**Síntomas:**
- Login falla con credenciales correctas
- Mensaje "Invalid credentials" en pantalla roja

**Causa:**
- Base de datos no inicializada o corrupta
- Usuarios no creados en app_factory.py

**Solución:**
```bash
# 1. Eliminar bases de datos
rm backend/data/emergency_sala*.db

# 2. Reiniciar (se recrean automáticamente)
cd backend/src
python3 main.py

# 3. Intentar login con credenciales por defecto:
# Usuario: admin
# Password: admin123
```

---

### Problema: Multicast no funciona (nodos no se descubren)

**Síntomas:**
- En Bully Cluster Screen solo aparece el nodo actual
- Logs muestran: "No nodes discovered"

**Causa:**
- Red no soporta multicast (algunas WiFi públicas, VPNs)
- Firewall bloqueando multicast

**Solución Temporal - Modo Estático:**
```bash
# Ejecutar en modo estático con lista fija de nodos
CLUSTER_MODE=static NODE_ID=1 python3 main.py
```

**Solución Permanente:**
- Configurar router/switch para permitir multicast
- Usar red local sin restricciones
- Probar con `localhost` en desarrollo

---

### Problema: Error "ModuleNotFoundError: No module named 'textual'"

**Causa:**
- Dependencias no instaladas o entorno virtual no activado

**Solución:**
```bash
# 1. Activar entorno virtual (si lo usas)
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows

# 2. Reinstalar dependencias
pip install -r requirements.txt

# 3. Verificar
python3 -c "import textual; print(textual.__version__)"
```

---

## ⚙️ Configuración Avanzada

### Cambiar Grupo Multicast

Por defecto usa `224.0.0.100:5005`. Para cambiar:

```bash
MULTICAST_GROUP=239.1.1.1 MULTICAST_PORT=5007 python3 main.py
```

### Ajustar Timeouts de Heartbeat

Editar `backend/src/bully/bully_node.py`:

```python
# Línea 72-73
self.heartbeat_interval = 3   # Cambiar a 5 para heartbeats menos frecuentes
self.election_timeout = 10     # Cambiar a 15 para tolerar más latencia
```

O editar `backend/src/config.py`:

```python
# Línea 80-81
HEARTBEAT_INTERVAL = 5  # segundos entre heartbeats
NODE_TIMEOUT = 20       # segundos antes de considerar nodo muerto
```

### Logging Detallado

Editar `backend/src/main.py` línea 26:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Cambiar de INFO a DEBUG
    # ...
)
```

Ver logs en:
```bash
# Logs por nodo
tail -f backend/logs/node_1.log

# Logs de Textual
tail -f backend/src/textual_app.log
```

### Cambiar Base de Datos a PostgreSQL

Editar `backend/src/config.py`:

```python
# En lugar de SQLite
SQLALCHEMY_DATABASE_URI = 'postgresql://user:password@localhost/emergency_db'
```

Instalar driver:
```bash
pip install psycopg2-binary
```

---

## 🗺️ Próximos Pasos / Roadmap

### Funcionalidades Pendientes (TODO en código)

- [ ] **Cerrar visita con diagnóstico**
  - Formulario de diagnóstico
  - Actualizar estado a 'completada'
  - Timestamp de cierre

- [ ] **Replicación de visitas entre nodos**
  - Propagar nueva visita a todos los nodos
  - Sincronización eventual
  - Resolución de conflictos

- [ ] **Dashboard con métricas avanzadas**
  - Gráficos de visitas por hora
  - Ocupación de camas en tiempo real
  - Estadísticas de doctores

- [ ] **Asignación dinámica de trabajador social**
  - Actualmente hardcoded a ID=1
  - Seleccionar desde sesión de usuario

- [ ] **Soporte para múltiples salas por nodo**
  - Un nodo puede gestionar varias salas
  - Balanceo de carga

### Contribuir al Proyecto

1. **Fork** del repositorio
2. Crear branch de feature:
   ```bash
   git checkout -b feature/nueva-funcionalidad
   ```
3. Hacer cambios y commits:
   ```bash
   git commit -m "Agregar nueva funcionalidad X"
   ```
4. Push a tu fork:
   ```bash
   git push origin feature/nueva-funcionalidad
   ```
5. Crear **Pull Request** en GitHub

### Convenciones de Código

- Usar **snake_case** para variables y funciones
- Usar **PascalCase** para clases
- Docstrings en todas las funciones públicas
- Máximo 100 caracteres por línea
- Type hints cuando sea posible

---

## 📚 Referencias y Recursos

### Documentación de Librerías

- **Textual**: https://textual.textualize.io/
  - Tutorial: https://textual.textualize.io/tutorial/
  - Widget Guide: https://textual.textualize.io/widget_gallery/

- **SQLAlchemy**: https://docs.sqlalchemy.org/
  - ORM Tutorial: https://docs.sqlalchemy.org/en/20/tutorial/

- **Flask**: https://flask.palletsprojects.com/
  - Flask-SQLAlchemy: https://flask-sqlalchemy.palletsprojects.com/

### Algoritmo Bully

- **Paper Original**: Garcia-Molina, H. (1982). "Elections in a Distributed Computing System"
- **Wikipedia**: https://en.wikipedia.org/wiki/Bully_algorithm
- **Tutorial**: https://www.geeksforgeeks.org/bully-algorithm/

### Sistemas Distribuidos

- **Libro**: "Distributed Systems" - Tanenbaum & Van Steen
- **Consensus Algorithms**: https://raft.github.io/ (Raft, alternativa a Bully)
- **CAP Theorem**: https://en.wikipedia.org/wiki/CAP_theorem

### Ayuda y Soporte

- **Issues**: [Reportar bugs o solicitar features]
- **Discusiones**: [Preguntas generales sobre el proyecto]
- **Contacto**: [Email del equipo o instructor]

---

## 📄 Licencia

[Especificar licencia del proyecto - MIT, GPL, etc.]

---

## 👥 Autores

[Nombres de los integrantes del equipo]

---

**Última actualización**: Noviembre 2025
