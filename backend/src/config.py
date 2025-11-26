import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuración base para la aplicación Flask"""

    # Identificador del nodo - Puede ser auto-generado o especificado manualmente
    # Si no se proporciona NODE_ID en environment, será None y se auto-generará
    _node_id_env = os.getenv('NODE_ID', None)
    NODE_ID = int(_node_id_env) if _node_id_env is not None else None

    # Flag para indicar si el NODE_ID fue auto-generado
    _node_id_auto_generated = False

    # Secret key para sessions
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Base de datos SQLite local del nodo (usar path absoluto)
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _DATA_DIR = os.path.join(_BASE_DIR, 'data')

    # Crear directorio de datos si no existe
    os.makedirs(_DATA_DIR, exist_ok=True)

    # DATABASE_URI - BD única compartida (replicada en cada nodo)
    # Todos los nodos usan el mismo nombre de archivo para tener datos idénticos
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URI',
        f'sqlite:///{os.path.join(_DATA_DIR, "emergencias.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Puerto Flask - usar variable de entorno o auto-asignar (0 = OS auto-asigna)
    FLASK_PORT = int(os.getenv('FLASK_PORT', 0))

    # Puerto TCP - será calculado después de tener NODE_ID (0 = OS auto-asigna)
    TCP_PORT = 0

    # Puerto UDP - será calculado después de tener NODE_ID (0 = OS auto-asigna)
    UDP_PORT = 0

    # ========================================================================
    # DESCUBRIMIENTO DINÁMICO DE NODOS
    # ========================================================================

    # Configuración de multicast para auto-descubrimiento
    MULTICAST_GROUP = os.getenv('MULTICAST_GROUP', '224.0.0.100')
    MULTICAST_PORT = int(os.getenv('MULTICAST_PORT', '5005'))

    # Intervalo de anuncio de presencia (segundos)
    DISCOVERY_ANNOUNCE_INTERVAL = int(os.getenv('DISCOVERY_ANNOUNCE_INTERVAL', '5'))

    # Timeout para considerar nodo muerto (segundos)
    DISCOVERY_NODE_TIMEOUT = int(os.getenv('DISCOVERY_NODE_TIMEOUT', '15'))

    # Modo de operación: 'dynamic' (auto-descubrimiento) o 'static' (lista fija)
    CLUSTER_MODE = os.getenv('CLUSTER_MODE', 'dynamic')

    # ========================================================================
    # CONFIGURACIÓN OPCIONAL PARA VMs (todo auto-detectado por defecto)
    # ========================================================================

    # IP local explícita (solo si auto-detección falla)
    # Ejemplo: BIND_IP=192.168.1.101
    BIND_IP = os.getenv('BIND_IP', None)

    # Interfaz de red específica (solo si hay múltiples interfaces)
    # Ejemplo: NETWORK_INTERFACE=eth0
    NETWORK_INTERFACE = os.getenv('NETWORK_INTERFACE', None)

    # TTL para paquetes multicast (aumentado para redes más complejas)
    MULTICAST_TTL = int(os.getenv('MULTICAST_TTL', '4'))

    # Habilitar broadcast UDP como fallback si multicast no funciona
    USE_BROADCAST_FALLBACK = os.getenv('USE_BROADCAST_FALLBACK', 'true').lower() == 'true'

    # Timeout de elección de líder (segundos sin heartbeat para iniciar elección)
    ELECTION_TIMEOUT = int(os.getenv('ELECTION_TIMEOUT', '10'))

    # Intervalo de heartbeat del líder (segundos)
    BULLY_HEARTBEAT_INTERVAL = int(os.getenv('HEARTBEAT_INTERVAL', '3'))

    # TCP backlog (conexiones pendientes en cola)
    TCP_BACKLOG = int(os.getenv('TCP_BACKLOG', '20'))

    # ========================================================================
    # CONFIGURACIÓN ESTÁTICA (Solo para modo CLUSTER_MODE='static')
    # ========================================================================

    # IPs y puertos de otros nodos (DEPRECATED - usar auto-descubrimiento)
    # Solo se usa si CLUSTER_MODE='static'
    OTROS_NODOS = [
        {'id': 1, 'url': 'http://localhost:5000', 'tcp_port': 5555},
        {'id': 2, 'url': 'http://localhost:5001', 'tcp_port': 5556},
        {'id': 3, 'url': 'http://localhost:5002', 'tcp_port': 5557},
        {'id': 4, 'url': 'http://localhost:5003', 'tcp_port': 5558},
    ]

    # Configuración de SocketIO
    SOCKETIO_ASYNC_MODE = 'threading'
    SOCKETIO_CORS_ALLOWED_ORIGINS = '*'

    # Configuración de timeouts
    HEARTBEAT_INTERVAL = 5  # segundos
    NODE_TIMEOUT = 15  # segundos para considerar nodo caído

    # Configuración de logs
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def initialize_node_id(cls):
        """
        Inicializa el NODE_ID si no está configurado.

        Si NODE_ID es None (no especificado en environment), genera un ID
        automáticamente usando el módulo id_generator.

        Este método debe llamarse al inicio de la aplicación, antes de
        inicializar cualquier componente que dependa de NODE_ID.

        Returns:
            int: El NODE_ID (existente o recién generado)
        """
        if cls.NODE_ID is None:
            # Importar aquí para evitar circular imports
            # FIX FASE 9: Usar función v2 con discovery (no la vieja con file locking)
            from bully.id_generator import get_or_create_node_id_v2

            # Generar ID con discovery de nodos existentes
            generated_id = get_or_create_node_id_v2()

            # Asignar al config
            cls.NODE_ID = generated_id
            cls._node_id_auto_generated = True

            print(f"[CONFIG] Auto-generated NODE_ID: {generated_id}")

        # Actualizar puertos basados en NODE_ID (solo si no fueron especificados)
        if cls.FLASK_PORT == 0:
            cls.FLASK_PORT = 5000 + cls.NODE_ID % 1000  # Evitar puertos muy altos
        if cls.TCP_PORT == 0:
            cls.TCP_PORT = 5555 + cls.NODE_ID % 1000
        if cls.UDP_PORT == 0:
            cls.UDP_PORT = 6000 + cls.NODE_ID % 1000

        # BD usa nombre fijo "emergencias.db" - no se actualiza con NODE_ID

        return cls.NODE_ID

    @classmethod
    def is_node_id_auto_generated(cls):
        """Retorna True si el NODE_ID fue auto-generado."""
        return cls._node_id_auto_generated

    @classmethod
    def is_dynamic_mode(cls):
        """Retorna True si el cluster usa auto-descubrimiento dinámico."""
        return cls.CLUSTER_MODE == 'dynamic'

    @classmethod
    def get_otros_nodos_activos(cls):
        """
        Retorna lista de otros nodos (excluyendo el actual).

        DEPRECATED: Solo se usa en modo estático (CLUSTER_MODE='static').
        En modo dinámico, los nodos se descubren automáticamente.
        """
        if cls.is_dynamic_mode():
            # En modo dinámico, retornar lista vacía (nodos se descubren dinámicamente)
            return []

        return [nodo for nodo in cls.OTROS_NODOS if nodo['id'] != cls.NODE_ID]

    @classmethod
    def get_info_nodo_actual(cls):
        """
        Retorna información del nodo actual.

        DEPRECATED: Solo se usa en modo estático (CLUSTER_MODE='static').
        """
        if cls.is_dynamic_mode():
            # En modo dinámico, construir info basado en NODE_ID y puerto
            return {
                'id': cls.NODE_ID,
                'url': f'http://localhost:{cls.FLASK_PORT}',
                'tcp_port': cls.TCP_PORT
            }

        for nodo in cls.OTROS_NODOS:
            if nodo['id'] == cls.NODE_ID:
                return nodo
        return None
