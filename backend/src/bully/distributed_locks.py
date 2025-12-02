"""
Modulo de Exclusion Mutua Distribuida y Consenso.
Integrado con el sistema Bully existente.

Protocolo de Exclusion Mutua:
- ATOMICO: TODOS los nodos deben aprobar o la operacion se aborta
- Si cualquier nodo rechaza o no responde, el bloqueo falla

Protocolo de Consenso:
- MAYORIA: (n/2)+1 nodos deben aprobar
- Usado para replicar transacciones entre nodos
"""

import threading
import time
import logging
from datetime import datetime
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# ============================================================================
# ESTADO GLOBAL DE BLOQUEOS
# ============================================================================

bloqueos_locales: Dict[str, datetime] = {}  # {clave: timestamp}
lock_bloqueos = threading.Lock()

# ============================================================================
# TIPOS DE MENSAJE
# ============================================================================

LOCK_REQUEST = 'LOCK_REQUEST'
LOCK_RESPONSE = 'LOCK_RESPONSE'
UNLOCK_REQUEST = 'UNLOCK_REQUEST'
CONSENSUS_REQUEST = 'CONSENSUS_REQUEST'
CONSENSUS_RESPONSE = 'CONSENSUS_RESPONSE'

# ============================================================================
# FUNCIONES DE VERIFICACION LOCAL
# ============================================================================


def verificar_recurso_local(flask_app, recurso_tipo: str, recurso_id: int) -> bool:
    """
    Verifica disponibilidad del recurso en BD local.

    Args:
        flask_app: Aplicacion Flask para contexto de BD
        recurso_tipo: 'DOCTOR', 'CAMA', o 'SALA_*' (recursos virtuales)
        recurso_id: ID del recurso

    Returns:
        True si el recurso esta disponible
    """
    # Los tipos SALA_* son recursos virtuales para serializar operaciones
    # (SALA_DOCTOR, SALA_TRABAJADOR, etc.)
    # La disponibilidad real se verifica en el 2PC, aquí solo permitimos el lock
    if recurso_tipo.startswith("SALA_"):
        logger.info(f"[LOCK] Recurso virtual {recurso_tipo}_{recurso_id} - permitiendo lock")
        return True

    with flask_app.app_context():
        from models import Doctor, Cama

        if recurso_tipo == "DOCTOR":
            doctor = Doctor.query.get(recurso_id)
            return doctor is not None and doctor.disponible and doctor.activo

        elif recurso_tipo == "CAMA":
            cama = Cama.query.get(recurso_id)
            return cama is not None and not cama.ocupada

    logger.warning(f"[LOCK] Tipo de recurso desconocido: {recurso_tipo}")
    return False


def esta_bloqueado_localmente(recurso_tipo: str, recurso_id: int) -> bool:
    """Verifica si el recurso esta bloqueado localmente."""
    clave = f"{recurso_tipo}_{recurso_id}"
    with lock_bloqueos:
        return clave in bloqueos_locales


def bloquear_localmente(recurso_tipo: str, recurso_id: int) -> None:
    """Registra bloqueo local."""
    clave = f"{recurso_tipo}_{recurso_id}"
    with lock_bloqueos:
        bloqueos_locales[clave] = datetime.now()
    logger.info(f"[LOCK] Bloqueado localmente: {clave}")


def desbloquear_localmente(recurso_tipo: str, recurso_id: int) -> None:
    """Remueve bloqueo local."""
    clave = f"{recurso_tipo}_{recurso_id}"
    with lock_bloqueos:
        if clave in bloqueos_locales:
            del bloqueos_locales[clave]
    logger.info(f"[LOCK] Desbloqueado localmente: {clave}")


def limpiar_bloqueos_expirados(timeout_segundos: int = 30) -> None:
    """Limpia bloqueos que han expirado (safety cleanup)."""
    ahora = datetime.now()
    with lock_bloqueos:
        expirados = [
            clave for clave, timestamp in bloqueos_locales.items()
            if (ahora - timestamp).total_seconds() > timeout_segundos
        ]
        for clave in expirados:
            del bloqueos_locales[clave]
            logger.warning(f"[LOCK] Bloqueo expirado limpiado: {clave}")


# ============================================================================
# PROTOCOLO DE BLOQUEO DISTRIBUIDO (EXCLUSION MUTUA)
# ============================================================================


def solicitar_bloqueo_distribuido(
    bully_node,
    flask_app,
    recurso_tipo: str,
    recurso_id: int,
    timeout: float = 10.0
) -> bool:
    """
    Solicita bloqueo distribuido sobre un recurso.

    Protocolo ATOMICO:
    - Si CUALQUIER nodo rechaza -> ABORTA
    - Si CUALQUIER nodo no responde -> ABORTA
    - Solo si TODOS aprueban -> CONCEDE BLOQUEO

    Args:
        bully_node: Instancia de BullyNode
        flask_app: Aplicacion Flask
        recurso_tipo: 'DOCTOR', 'CAMA', o 'SALA_*'
        recurso_id: ID del recurso
        timeout: Timeout en segundos para cada nodo

    Returns:
        True si se obtuvo el bloqueo, False si fue rechazado
    """
    logger.warning(f"[LOCK] ========== INICIO SOLICITUD BLOQUEO ==========")
    logger.warning(f"[LOCK] Node {bully_node.node_id} solicitando: {recurso_tipo}_{recurso_id}")

    # Limpiar bloqueos expirados antes de solicitar nuevos
    limpiar_bloqueos_expirados()

    # 1. Verificacion local inmediata
    logger.warning(f"[LOCK] Paso 1: Verificando disponibilidad local de {recurso_tipo}_{recurso_id}")
    if not verificar_recurso_local(flask_app, recurso_tipo, recurso_id):
        logger.warning(f"[LOCK] FALLO: {recurso_tipo}_{recurso_id} no disponible localmente")
        return False
    logger.warning(f"[LOCK] OK: {recurso_tipo}_{recurso_id} disponible localmente")

    logger.warning(f"[LOCK] Paso 2: Verificando si ya está bloqueado localmente")
    if esta_bloqueado_localmente(recurso_tipo, recurso_id):
        logger.warning(f"[LOCK] FALLO: {recurso_tipo}_{recurso_id} ya bloqueado localmente")
        return False
    logger.warning(f"[LOCK] OK: {recurso_tipo}_{recurso_id} no está bloqueado localmente")

    # 2. Si no hay otros nodos, solo bloqueo local
    otros_nodos = {k: v for k, v in bully_node.cluster_nodes.items()
                   if k != bully_node.node_id}

    logger.warning(f"[LOCK] Paso 3: Otros nodos en cluster: {list(otros_nodos.keys())}")

    if not otros_nodos:
        bloquear_localmente(recurso_tipo, recurso_id)
        logger.warning(f"[LOCK] ÉXITO: Bloqueo concedido (solo local, sin otros nodos)")
        return True

    # 3. Solicitar bloqueo a TODOS los nodos
    from bully.communication import Message

    nodos_aprobados = []
    msg = Message(
        type=LOCK_REQUEST,
        sender_id=bully_node.node_id,
        timestamp=time.time(),
        data={
            'recurso_tipo': recurso_tipo,
            'recurso_id': recurso_id
        }
    )

    logger.warning(f"[LOCK] Paso 4: Solicitando bloqueo a {len(otros_nodos)} nodos...")

    for node_id, (ip, tcp_port, udp_port) in otros_nodos.items():
        try:
            logger.warning(f"[LOCK] Enviando LOCK_REQUEST a nodo {node_id} ({ip}:{tcp_port})")
            response = bully_node.comm.send_tcp(ip, tcp_port, msg, timeout=timeout)

            if response and response.data and response.data.get('approved'):
                nodos_aprobados.append(node_id)
                logger.warning(f"[LOCK] ✓ Nodo {node_id} APROBÓ bloqueo de {recurso_tipo}_{recurso_id}")
            else:
                reason = response.data.get('reason', 'unknown') if response and response.data else 'no_response'
                logger.warning(f"[LOCK] ✗ Nodo {node_id} RECHAZÓ bloqueo: {reason}")
                # Si CUALQUIERA rechaza, abortar y liberar los ya aprobados
                logger.warning(f"[LOCK] Haciendo rollback de {len(nodos_aprobados)} bloqueos aprobados...")
                _rollback_bloqueos(bully_node, recurso_tipo, recurso_id, nodos_aprobados)
                logger.warning(f"[LOCK] ========== FIN SOLICITUD (RECHAZADO) ==========")
                return False

        except Exception as e:
            logger.error(f"[LOCK] ✗ Nodo {node_id} no respondió: {e}")
            # Si CUALQUIERA no responde, abortar
            logger.warning(f"[LOCK] Haciendo rollback de {len(nodos_aprobados)} bloqueos aprobados...")
            _rollback_bloqueos(bully_node, recurso_tipo, recurso_id, nodos_aprobados)
            logger.warning(f"[LOCK] ========== FIN SOLICITUD (TIMEOUT) ==========")
            return False

    # 4. Solo si TODOS aprobaron, bloquear localmente
    if len(nodos_aprobados) == len(otros_nodos):
        bloquear_localmente(recurso_tipo, recurso_id)
        logger.warning(f"[LOCK] ========== ÉXITO: BLOQUEO CONCEDIDO ==========")
        logger.warning(f"[LOCK] {recurso_tipo}_{recurso_id} bloqueado (aprobado por {len(nodos_aprobados)} nodos)")
        return True

    logger.warning(f"[LOCK] ========== FIN SOLICITUD (ERROR INESPERADO) ==========")
    return False


def _rollback_bloqueos(bully_node, recurso_tipo: str, recurso_id: int, nodos_aprobados: list) -> None:
    """Envia UNLOCK a los nodos que ya habian aprobado (rollback)."""
    if not nodos_aprobados:
        return

    from bully.communication import Message

    msg = Message(
        type=UNLOCK_REQUEST,
        sender_id=bully_node.node_id,
        timestamp=time.time(),
        data={
            'recurso_tipo': recurso_tipo,
            'recurso_id': recurso_id
        }
    )

    for node_id in nodos_aprobados:
        if node_id in bully_node.cluster_nodes:
            ip, tcp_port, udp_port = bully_node.cluster_nodes[node_id]
            try:
                bully_node.comm.send_tcp(ip, tcp_port, msg, timeout=1.0)
                logger.info(f"[LOCK] Rollback enviado a nodo {node_id}")
            except:
                pass  # Best effort


def liberar_bloqueo_distribuido(
    bully_node,
    recurso_tipo: str,
    recurso_id: int
) -> None:
    """
    Libera bloqueo distribuido.
    Notifica a todos los nodos (best-effort, no bloquea si falla).

    Args:
        bully_node: Instancia de BullyNode
        recurso_tipo: 'DOCTOR' o 'CAMA'
        recurso_id: ID del recurso
    """
    logger.info(f"[LOCK] Liberando bloqueo: {recurso_tipo}_{recurso_id}")

    # 1. Liberar localmente primero
    desbloquear_localmente(recurso_tipo, recurso_id)

    # 2. Notificar a otros nodos (fire-and-forget)
    from bully.communication import Message

    otros_nodos = {k: v for k, v in bully_node.cluster_nodes.items()
                   if k != bully_node.node_id}

    if not otros_nodos:
        return

    msg = Message(
        type=UNLOCK_REQUEST,
        sender_id=bully_node.node_id,
        timestamp=time.time(),
        data={
            'recurso_tipo': recurso_tipo,
            'recurso_id': recurso_id
        }
    )

    for node_id, (ip, tcp_port, udp_port) in otros_nodos.items():
        try:
            bully_node.comm.send_tcp(ip, tcp_port, msg, timeout=1.0)
        except:
            pass  # Ignorar errores en liberacion

    logger.info(f"[LOCK] Bloqueo LIBERADO: {recurso_tipo}_{recurso_id}")


# ============================================================================
# HANDLERS PARA MENSAJES DE BLOQUEO
# ============================================================================


def handle_lock_request(message, flask_app, node_id) -> 'Message':
    """
    Handler para solicitudes de bloqueo entrantes.
    Responde APROBADO o RECHAZADO.

    Args:
        message: Mensaje LOCK_REQUEST entrante
        flask_app: Aplicacion Flask
        node_id: ID de este nodo

    Returns:
        Message con LOCK_RESPONSE
    """
    from bully.communication import Message

    data = message.data or {}
    recurso_tipo = data.get('recurso_tipo')
    recurso_id = data.get('recurso_id')

    logger.warning(f"[LOCK-HANDLER] ===== RECIBIDA SOLICITUD DE BLOQUEO =====")
    logger.warning(f"[LOCK-HANDLER] Node {node_id} recibió solicitud de {recurso_tipo}_{recurso_id} desde nodo {message.sender_id}")

    # Verificar si ya esta bloqueado localmente
    if esta_bloqueado_localmente(recurso_tipo, recurso_id):
        logger.warning(f"[LOCK-HANDLER] ✗ RECHAZANDO {recurso_tipo}_{recurso_id} (ya bloqueado localmente)")
        return Message(
            type=LOCK_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'approved': False, 'reason': 'already_locked'}
        )

    # Verificar disponibilidad en BD
    logger.warning(f"[LOCK-HANDLER] Verificando disponibilidad de {recurso_tipo}_{recurso_id}...")
    if not verificar_recurso_local(flask_app, recurso_tipo, recurso_id):
        logger.warning(f"[LOCK-HANDLER] ✗ RECHAZANDO {recurso_tipo}_{recurso_id} (no disponible en BD)")
        return Message(
            type=LOCK_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'approved': False, 'reason': 'not_available'}
        )

    # Aprobar y bloquear localmente
    bloquear_localmente(recurso_tipo, recurso_id)
    logger.warning(f"[LOCK-HANDLER] ✓ APROBANDO bloqueo {recurso_tipo}_{recurso_id} para nodo {message.sender_id}")

    return Message(
        type=LOCK_RESPONSE,
        sender_id=node_id,
        timestamp=time.time(),
        data={'approved': True}
    )


def handle_unlock_request(message, node_id) -> 'Message':
    """
    Handler para solicitudes de liberacion entrantes.

    Args:
        message: Mensaje UNLOCK_REQUEST entrante
        node_id: ID de este nodo

    Returns:
        Message con LOCK_RESPONSE confirmando liberacion
    """
    from bully.communication import Message

    data = message.data or {}
    recurso_tipo = data.get('recurso_tipo')
    recurso_id = data.get('recurso_id')

    logger.info(f"[LOCK] Recibida solicitud de liberacion: {recurso_tipo}_{recurso_id} de nodo {message.sender_id}")

    desbloquear_localmente(recurso_tipo, recurso_id)

    return Message(
        type=LOCK_RESPONSE,
        sender_id=node_id,
        timestamp=time.time(),
        data={'released': True}
    )


# ============================================================================
# SISTEMA DE CONSENSO DISTRIBUIDO
# ============================================================================


def propagar_transaccion_con_consenso(
    bully_node,
    flask_app,
    comando: Dict[str, Any],
    timeout: float = 10.0
) -> bool:
    """
    Propaga una transaccion con consenso por MAYORIA.

    Protocolo:
    - Envia transaccion a todos los nodos
    - Umbral = (total_nodos // 2) + 1
    - Si mayoria aprueba -> ejecutar localmente
    - Si no -> rechazar

    Args:
        bully_node: Instancia de BullyNode
        flask_app: Aplicacion Flask
        comando: {'accion': str, 'datos': dict}
        timeout: Timeout por nodo

    Returns:
        True si se alcanzo consenso y se ejecuto
    """
    from bully.communication import Message

    otros_nodos = {k: v for k, v in bully_node.cluster_nodes.items()
                   if k != bully_node.node_id}

    # Si no hay otros nodos, ejecutar localmente directamente
    if not otros_nodos:
        logger.info(f"[CONSENSUS] Sin otros nodos, ejecutando localmente: {comando.get('accion')}")
        return _ejecutar_transaccion_local(flask_app, comando)

    confirmaciones = 0
    total_nodos = len(otros_nodos)

    msg = Message(
        type=CONSENSUS_REQUEST,
        sender_id=bully_node.node_id,
        timestamp=time.time(),
        data=comando
    )

    logger.info(f"[CONSENSUS] Iniciando consenso para: {comando.get('accion')} con {total_nodos} nodos")

    for node_id, (ip, tcp_port, udp_port) in otros_nodos.items():
        try:
            response = bully_node.comm.send_tcp(ip, tcp_port, msg, timeout=timeout)

            if response and response.data and response.data.get('ok'):
                confirmaciones += 1
                logger.info(f"[CONSENSUS] Nodo {node_id} aprobo")
            else:
                logger.warning(f"[CONSENSUS] Nodo {node_id} rechazo")

        except Exception as e:
            logger.error(f"[CONSENSUS] Nodo {node_id} no respondio: {e}")

    # Calcular umbral de mayoria
    umbral = (total_nodos // 2) + 1

    if confirmaciones >= umbral:
        # Ejecutar localmente tambien
        resultado = _ejecutar_transaccion_local(flask_app, comando)
        if resultado:
            logger.info(f"[CONSENSUS] Alcanzado ({confirmaciones}/{total_nodos} >= {umbral})")
            return True
        else:
            logger.error("[CONSENSUS] Error en ejecucion local")
            return False
    else:
        logger.warning(f"[CONSENSUS] Fallido ({confirmaciones}/{total_nodos} < {umbral})")
        return False


def _ejecutar_transaccion_local(flask_app, comando: Dict) -> bool:
    """
    Ejecuta transaccion en BD local.

    Args:
        flask_app: Aplicacion Flask
        comando: {'accion': str, 'datos': dict}

    Returns:
        True si se ejecuto correctamente
    """
    with flask_app.app_context():
        from models import db, Paciente, Doctor, Cama, VisitaEmergencia

        accion = comando.get('accion')
        datos = comando.get('datos', {})

        try:
            if accion == 'INSERTAR_PACIENTE':
                paciente = Paciente(
                    nombre=datos['nombre'],
                    edad=datos['edad'],
                    sexo=datos.get('sexo', 'M'),
                    curp=datos.get('curp'),
                    activo=1
                )
                db.session.add(paciente)
                db.session.commit()
                logger.info(f"[CONSENSUS] Paciente insertado: {datos['nombre']}")
                return True

            elif accion == 'ASIGNAR_RECURSOS':
                # Actualizar doctor
                doctor = Doctor.query.get(datos['doctor_id'])
                if doctor:
                    doctor.disponible = False

                # Actualizar cama
                cama = Cama.query.get(datos['cama_id'])
                if cama:
                    cama.ocupada = True
                    cama.id_paciente = datos.get('paciente_id')

                db.session.commit()
                logger.info(f"[CONSENSUS] Recursos asignados: doctor={datos['doctor_id']}, cama={datos['cama_id']}")
                return True

            elif accion == 'LIBERAR_RECURSOS':
                # Liberar doctor
                doctor = Doctor.query.get(datos['doctor_id'])
                if doctor:
                    doctor.disponible = True

                # Liberar cama
                cama = Cama.query.get(datos['cama_id'])
                if cama:
                    cama.ocupada = False
                    cama.id_paciente = None

                db.session.commit()
                logger.info(f"[CONSENSUS] Recursos liberados: doctor={datos['doctor_id']}, cama={datos['cama_id']}")
                return True

            elif accion == 'CERRAR_VISITA':
                visita = VisitaEmergencia.query.filter_by(folio=datos['folio']).first()
                if visita:
                    # Liberar doctor
                    doctor = Doctor.query.get(visita.id_doctor)
                    if doctor:
                        doctor.disponible = True

                    # Liberar cama
                    cama = Cama.query.get(visita.id_cama)
                    if cama:
                        cama.ocupada = False
                        cama.id_paciente = None

                    visita.estado = 'completada'
                    db.session.commit()
                    logger.info(f"[CONSENSUS] Visita cerrada: {datos['folio']}")
                    return True
                return False

            else:
                logger.warning(f"[CONSENSUS] Accion desconocida: {accion}")
                return False

        except Exception as e:
            logger.error(f"[CONSENSUS] Error ejecutando {accion}: {e}")
            db.session.rollback()
            return False


def handle_consensus_request(message, flask_app, node_id) -> 'Message':
    """
    Handler para solicitudes de consenso entrantes.

    Args:
        message: Mensaje CONSENSUS_REQUEST
        flask_app: Aplicacion Flask
        node_id: ID de este nodo

    Returns:
        Message con CONSENSUS_RESPONSE
    """
    from bully.communication import Message

    comando = message.data
    accion = comando.get('accion', 'unknown')

    logger.info(f"[CONSENSUS] Recibida solicitud de consenso: {accion} de nodo {message.sender_id}")

    resultado = _ejecutar_transaccion_local(flask_app, comando)

    return Message(
        type=CONSENSUS_RESPONSE,
        sender_id=node_id,
        timestamp=time.time(),
        data={'ok': resultado}
    )


# ============================================================================
# FUNCIONES DE REPLICACION CON CONSENSO
# ============================================================================


def replicar_asignacion_con_consenso(
    bully_node,
    flask_app,
    doctor_id: int,
    cama_id: int,
    paciente_id: int
) -> bool:
    """
    Replica asignacion de recursos a todos los nodos usando consenso.

    Args:
        bully_node: Instancia de BullyNode
        flask_app: Aplicacion Flask
        doctor_id: ID del doctor asignado
        cama_id: ID de la cama asignada
        paciente_id: ID del paciente

    Returns:
        True si se alcanzo consenso
    """
    comando = {
        'accion': 'ASIGNAR_RECURSOS',
        'datos': {
            'doctor_id': doctor_id,
            'cama_id': cama_id,
            'paciente_id': paciente_id
        }
    }

    return propagar_transaccion_con_consenso(bully_node, flask_app, comando)


def replicar_liberacion_con_consenso(
    bully_node,
    flask_app,
    doctor_id: int,
    cama_id: int
) -> bool:
    """
    Replica liberacion de recursos a todos los nodos usando consenso.

    Args:
        bully_node: Instancia de BullyNode
        flask_app: Aplicacion Flask
        doctor_id: ID del doctor a liberar
        cama_id: ID de la cama a liberar

    Returns:
        True si se alcanzo consenso
    """
    comando = {
        'accion': 'LIBERAR_RECURSOS',
        'datos': {
            'doctor_id': doctor_id,
            'cama_id': cama_id
        }
    }

    return propagar_transaccion_con_consenso(bully_node, flask_app, comando)


def replicar_cierre_con_consenso(bully_node, flask_app, folio: str) -> bool:
    """
    Replica cierre de visita con consenso.

    Args:
        bully_node: Instancia de BullyNode
        flask_app: Aplicacion Flask
        folio: Folio de la visita

    Returns:
        True si se alcanzo consenso
    """
    comando = {
        'accion': 'CERRAR_VISITA',
        'datos': {'folio': folio}
    }

    return propagar_transaccion_con_consenso(bully_node, flask_app, comando)


# ============================================================================
# FUNCIONES DE BLOQUEO MEJORADAS (2PC SUPPORT)
# ============================================================================


def liberar_bloqueo_distribuido_con_retry(
    bully_node,
    recurso_tipo: str,
    recurso_id: int,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> bool:
    """
    Libera bloqueo distribuido con reintentos exponenciales.

    A diferencia de liberar_bloqueo_distribuido que es fire-and-forget,
    esta función reintenta la liberación hasta tener éxito.

    Args:
        bully_node: Instancia de BullyNode
        recurso_tipo: 'DOCTOR' o 'CAMA'
        recurso_id: ID del recurso
        max_retries: Número máximo de reintentos
        base_delay: Delay base para backoff exponencial

    Returns:
        True si se liberó exitosamente
    """
    for attempt in range(max_retries):
        try:
            # Primero liberar localmente
            desbloquear_localmente(recurso_tipo, recurso_id)

            # Luego notificar a otros nodos
            from bully.communication import Message

            otros_nodos = {k: v for k, v in bully_node.cluster_nodes.items()
                          if k != bully_node.node_id}

            if not otros_nodos:
                logger.info(f"[LOCK-RETRY] Released {recurso_tipo}_{recurso_id} (no other nodes)")
                return True

            msg = Message(
                type=UNLOCK_REQUEST,
                sender_id=bully_node.node_id,
                timestamp=time.time(),
                data={
                    'recurso_tipo': recurso_tipo,
                    'recurso_id': recurso_id
                }
            )

            success_count = 0
            for node_id, (ip, tcp_port, udp_port) in otros_nodos.items():
                try:
                    response = bully_node.comm.send_tcp(ip, tcp_port, msg, timeout=2.0)
                    if response and response.data and response.data.get('released'):
                        success_count += 1
                except:
                    pass

            if success_count == len(otros_nodos):
                logger.info(f"[LOCK-RETRY] Released {recurso_tipo}_{recurso_id} on all nodes")
                return True

            if success_count > 0:
                # Al menos algunos nodos liberaron - considerar éxito parcial
                logger.warning(f"[LOCK-RETRY] Partial release {recurso_tipo}_{recurso_id}: {success_count}/{len(otros_nodos)}")
                return True

        except Exception as e:
            logger.warning(f"[LOCK-RETRY] Attempt {attempt+1} failed for {recurso_tipo}_{recurso_id}: {e}")

        # Esperar con backoff exponencial
        delay = base_delay * (2 ** attempt)
        time.sleep(delay)

    logger.error(f"[LOCK-RETRY] Failed after {max_retries} attempts for {recurso_tipo}:{recurso_id}")
    return False


def solicitar_bloqueo_con_orden(
    bully_node,
    flask_app,
    recursos: list,  # [('DOCTOR', 1), ('CAMA', 5)]
    timeout: float = 10.0
) -> tuple:
    """
    Solicita múltiples bloqueos en orden determinístico para evitar deadlocks.

    Los recursos se ordenan alfabéticamente por (tipo, id) para garantizar
    que todos los nodos adquieran locks en el mismo orden.

    Protocol:
    1. Ordenar recursos por (tipo, id)
    2. Adquirir locks secuencialmente
    3. Si alguno falla -> rollback de los ya adquiridos
    4. Retornar lista de recursos bloqueados

    Args:
        bully_node: Instancia de BullyNode
        flask_app: Aplicación Flask
        recursos: Lista de tuplas [(tipo, id), ...]
        timeout: Timeout por bloqueo

    Returns:
        (success: bool, locked_resources: list)
    """
    if not recursos:
        return (True, [])

    # Ordenar recursos para evitar deadlock (orden global)
    recursos_ordenados = sorted(recursos, key=lambda x: (x[0], x[1]))
    locked = []

    logger.info(f"[LOCK-ORDER] Requesting locks in order: {recursos_ordenados}")

    for recurso_tipo, recurso_id in recursos_ordenados:
        if solicitar_bloqueo_distribuido(
            bully_node, flask_app, recurso_tipo, recurso_id, timeout=timeout
        ):
            locked.append((recurso_tipo, recurso_id))
            logger.info(f"[LOCK-ORDER] Acquired lock: {recurso_tipo}_{recurso_id}")
        else:
            # Rollback: liberar los que ya se bloquearon (en orden inverso)
            logger.warning(f"[LOCK-ORDER] Failed to acquire {recurso_tipo}_{recurso_id}, rolling back {len(locked)} locks")
            for tipo, rid in reversed(locked):
                liberar_bloqueo_distribuido_con_retry(bully_node, tipo, rid)
            return (False, [])

    logger.info(f"[LOCK-ORDER] All {len(locked)} locks acquired successfully")
    return (True, locked)


def liberar_todos_bloqueos(
    bully_node,
    recursos: list  # [('DOCTOR', 1), ('CAMA', 5)]
) -> None:
    """
    Libera múltiples bloqueos con retry.

    Útil para cleanup en finally blocks.

    Args:
        bully_node: Instancia de BullyNode
        recursos: Lista de tuplas [(tipo, id), ...]
    """
    for recurso_tipo, recurso_id in recursos:
        try:
            liberar_bloqueo_distribuido_con_retry(bully_node, recurso_tipo, recurso_id)
        except Exception as e:
            logger.error(f"[LOCK-CLEANUP] Error releasing {recurso_tipo}_{recurso_id}: {e}")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Tipos de mensaje
    'LOCK_REQUEST',
    'LOCK_RESPONSE',
    'UNLOCK_REQUEST',
    'CONSENSUS_REQUEST',
    'CONSENSUS_RESPONSE',
    # Funciones de bloqueo básicas
    'solicitar_bloqueo_distribuido',
    'liberar_bloqueo_distribuido',
    # Funciones de bloqueo mejoradas (2PC)
    'liberar_bloqueo_distribuido_con_retry',
    'solicitar_bloqueo_con_orden',
    'liberar_todos_bloqueos',
    # Handlers
    'handle_lock_request',
    'handle_unlock_request',
    'handle_consensus_request',
    # Consenso
    'propagar_transaccion_con_consenso',
    'replicar_asignacion_con_consenso',
    'replicar_liberacion_con_consenso',
    'replicar_cierre_con_consenso',
]
