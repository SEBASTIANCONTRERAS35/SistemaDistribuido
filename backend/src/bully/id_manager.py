"""
Gestor de IDs Globales para Doctores y Trabajadores Sociales.

Solo el líder Bully puede asignar IDs.
Los nodos no-líder solicitan IDs via TCP al líder.
"""

import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tipos de mensaje para solicitud de ID
ID_REQUEST = 'ID_REQUEST'
ID_RESPONSE = 'ID_RESPONSE'

# Lock para operaciones de ID (thread-safe)
_id_lock = threading.Lock()


def request_id_from_leader(bully_manager, flask_app, entity_type: str,
                           timeout: float = 5.0) -> Optional[int]:
    """
    Solicita un ID al líder del cluster.

    Args:
        bully_manager: Instancia de BullyNode
        flask_app: Aplicación Flask
        entity_type: 'doctor' o 'trabajador'
        timeout: Timeout en segundos

    Returns:
        int: ID asignado por el líder, o None si falla
    """
    from bully.communication import Message

    # Si YO soy el líder, generar localmente
    if bully_manager.is_leader():
        logger.info(f"[ID-REQUEST] Soy líder, generando {entity_type} ID localmente")
        return _generate_id_locally(flask_app, entity_type)

    leader_id = bully_manager.get_current_leader()

    if leader_id is None:
        logger.error("[ID-REQUEST] No hay líder disponible")
        return None

    # Obtener info del líder
    if leader_id not in bully_manager.cluster_nodes:
        logger.error(f"[ID-REQUEST] Líder {leader_id} no está en cluster_nodes")
        return None

    ip, tcp_port, _ = bully_manager.cluster_nodes[leader_id]

    # Enviar solicitud
    msg = Message(
        type=ID_REQUEST,
        sender_id=bully_manager.node_id,
        timestamp=time.time(),
        data={
            'entity_type': entity_type
        }
    )

    logger.info(f"[ID-REQUEST] Solicitando {entity_type} ID al líder {leader_id} ({ip}:{tcp_port})")

    try:
        response = bully_manager.comm.send_tcp(ip, tcp_port, msg, timeout=timeout)

        if response and response.data and response.data.get('success'):
            assigned_id = response.data.get('id')
            logger.info(f"[ID-REQUEST] Líder asignó {entity_type} ID: {assigned_id}")
            return assigned_id
        else:
            reason = response.data.get('error', 'unknown') if response and response.data else 'sin respuesta'
            logger.error(f"[ID-REQUEST] Líder rechazó solicitud: {reason}")
            return None

    except Exception as e:
        logger.error(f"[ID-REQUEST] Error contactando al líder: {e}")
        return None


def _generate_id_locally(flask_app, entity_type: str) -> int:
    """
    Genera ID localmente consultando max(id) + 1.
    Solo debe llamarse en el líder.
    """
    with flask_app.app_context():
        from models import db, Doctor, TrabajadorSocial

        with _id_lock:
            if entity_type == 'doctor':
                max_id = db.session.query(
                    db.func.max(Doctor.id_doctor)
                ).scalar() or 0
                next_id = max_id + 1
                logger.info(f"[ID-MANAGER] Generado doctor ID: {next_id} (max era {max_id})")
                return next_id

            elif entity_type == 'trabajador':
                max_id = db.session.query(
                    db.func.max(TrabajadorSocial.id_trabajador)
                ).scalar() or 0
                next_id = max_id + 1
                logger.info(f"[ID-MANAGER] Generado trabajador ID: {next_id} (max era {max_id})")
                return next_id

            else:
                raise ValueError(f"Tipo de entidad desconocido: {entity_type}")


def generate_fallback_id(node_id: int, entity_type: str) -> int:
    """
    Genera un ID de fallback cuando el líder no responde.

    Formato: node_id * 100000 + timestamp_suffix
    Esto garantiza unicidad pero puede crear gaps.

    Args:
        node_id: ID del nodo actual
        entity_type: 'doctor' o 'trabajador'

    Returns:
        int: ID de fallback único
    """
    # Usar prefijo de nodo + últimos 5 dígitos del timestamp
    timestamp_suffix = int(time.time()) % 100000
    fallback_id = node_id * 100000 + timestamp_suffix

    logger.warning(f"[ID-FALLBACK] Generado {entity_type} ID fallback: {fallback_id} (líder no respondió)")
    return fallback_id


def handle_id_request(message, flask_app, node_id) -> 'Message':
    """
    Handler para solicitudes de ID entrantes (solo en el líder).

    Args:
        message: Mensaje ID_REQUEST entrante
        flask_app: Aplicación Flask
        node_id: ID de este nodo

    Returns:
        Message con ID_RESPONSE
    """
    from bully.communication import Message

    data = message.data or {}
    entity_type = data.get('entity_type')

    logger.info(f"[ID-HANDLER] Recibida solicitud de ID para {entity_type} desde nodo {message.sender_id}")

    if entity_type not in ('doctor', 'trabajador'):
        return Message(
            type=ID_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'success': False, 'error': f'Tipo de entidad inválido: {entity_type}'}
        )

    try:
        assigned_id = _generate_id_locally(flask_app, entity_type)

        logger.info(f"[ID-HANDLER] Asignado {entity_type} ID {assigned_id} al nodo {message.sender_id}")

        return Message(
            type=ID_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'success': True, 'id': assigned_id, 'entity_type': entity_type}
        )

    except Exception as e:
        logger.error(f"[ID-HANDLER] Error generando ID: {e}")
        return Message(
            type=ID_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'success': False, 'error': str(e)}
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'ID_REQUEST',
    'ID_RESPONSE',
    'request_id_from_leader',
    'generate_fallback_id',
    'handle_id_request',
]
