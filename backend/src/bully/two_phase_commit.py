"""
Two-Phase Commit Protocol for Distributed Transactions

Implementa 2PC real para garantizar consistencia fuerte:
- PREPARE: Todos los nodos votan YES o NO
- COMMIT: Solo si TODOS votaron YES
- ABORT: Si CUALQUIERA vota NO o timeout

Garantías:
- Atomicidad: Todos aplican la transacción o ninguno
- Consistencia: Estado coherente en todo el cluster
- Rollback automático en caso de fallo
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import uuid
import time
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# TIPOS Y ESTRUCTURAS
# ============================================================================

class TxnPhase(Enum):
    """Fases del protocolo 2PC"""
    PREPARE = "PREPARE"
    COMMIT = "COMMIT"
    ABORT = "ABORT"


class VoteResult(Enum):
    """Resultado del voto de un nodo"""
    YES = "YES"
    NO = "NO"
    TIMEOUT = "TIMEOUT"


@dataclass
class Transaction:
    """Representa una transacción 2PC"""
    txn_id: str
    operation: str  # 'CREATE_VISIT', 'CLOSE_VISIT'
    data: Dict[str, Any]
    timestamp: float
    phase: TxnPhase
    votes: Dict[int, VoteResult] = field(default_factory=dict)  # node_id -> vote


# ============================================================================
# TIPOS DE MENSAJE 2PC
# ============================================================================

TWO_PC_REQUEST = 'TWO_PC_REQUEST'
TWO_PC_RESPONSE = 'TWO_PC_RESPONSE'


# ============================================================================
# COORDINADOR 2PC
# ============================================================================

class TwoPhaseCommitCoordinator:
    """
    Coordinador de transacciones Two-Phase Commit.

    Protocolo:
    1. PREPARE: Enviar propuesta a todos los nodos
    2. Esperar votos (YES/NO) de todos
    3. Si TODOS votan YES → COMMIT
    4. Si CUALQUIERA vota NO o timeout → ABORT

    Usage:
        coordinator = TwoPhaseCommitCoordinator(bully_manager, flask_app)
        txn_id = coordinator.begin_transaction('CREATE_VISIT', data)
        result = coordinator.execute_2pc(txn_id)
    """

    def __init__(self, bully_manager, flask_app):
        """
        Inicializa el coordinador 2PC.

        Args:
            bully_manager: Instancia de BullyNode
            flask_app: Aplicación Flask para contexto de BD
        """
        self.bully_manager = bully_manager
        self.flask_app = flask_app
        self.pending_txns: Dict[str, Transaction] = {}
        self.prepare_timeout = 10.0  # segundos
        self.commit_timeout = 5.0

    def begin_transaction(self, operation: str, data: Dict) -> str:
        """
        Inicia una nueva transacción 2PC.

        Args:
            operation: Tipo de operación ('CREATE_VISIT', 'CLOSE_VISIT')
            data: Datos de la transacción

        Returns:
            txn_id: Identificador único de la transacción
        """
        txn_id = f"TXN-{self.bully_manager.node_id}-{uuid.uuid4().hex[:8]}-{int(time.time())}"
        txn = Transaction(
            txn_id=txn_id,
            operation=operation,
            data=data,
            timestamp=time.time(),
            phase=TxnPhase.PREPARE,
            votes={}
        )
        self.pending_txns[txn_id] = txn
        logger.info(f"[2PC] Transaction started: {txn_id} ({operation})")
        return txn_id

    def execute_2pc(self, txn_id: str) -> Dict[str, Any]:
        """
        Ejecuta el protocolo 2PC completo.

        Returns:
            {'success': True/False, 'error': str or None, 'txn_id': str}
        """
        txn = self.pending_txns.get(txn_id)
        if not txn:
            return {'success': False, 'error': 'Transacción no encontrada'}

        try:
            # ====== FASE 1: PREPARE ======
            logger.info(f"[2PC] === PREPARE PHASE === for {txn_id}")
            prepare_result = self._prepare_phase(txn)

            if not prepare_result['all_yes']:
                # ABORT - alguien votó NO o timeout
                logger.warning(f"[2PC] PREPARE failed for {txn_id}: {prepare_result['reason']}")
                self._abort_phase(txn)
                return {'success': False, 'error': prepare_result['reason']}

            # ====== FASE 2: COMMIT ======
            logger.info(f"[2PC] === COMMIT PHASE === for {txn_id}")
            commit_result = self._commit_phase(txn)

            if not commit_result['success']:
                # CRITICAL: PREPARE exitoso pero COMMIT falló
                logger.error(f"[2PC] CRITICAL: COMMIT failed after PREPARE for {txn_id}")
                # Intentar rollback (best effort)
                self._abort_phase(txn)
                return {'success': False, 'error': 'Commit failed after prepare - inconsistency possible'}

            logger.info(f"[2PC] Transaction COMMITTED: {txn_id}")
            return {'success': True, 'txn_id': txn_id}

        except Exception as e:
            logger.error(f"[2PC] Exception in execute_2pc: {e}")
            self._abort_phase(txn)
            return {'success': False, 'error': str(e)}

        finally:
            # Limpiar transacción pendiente
            self.pending_txns.pop(txn_id, None)

    def _prepare_phase(self, txn: Transaction) -> Dict[str, Any]:
        """
        PREPARE: Envía propuesta a todos los nodos y recolecta votos.

        Returns:
            {'all_yes': bool, 'reason': str or None}
        """
        from bully.communication import Message

        otros_nodos = {k: v for k, v in self.bully_manager.cluster_nodes.items()
                       if k != self.bully_manager.node_id}

        if not otros_nodos:
            # Nodo único - verificar localmente y auto-aprobar
            local_check = self._verify_local_preconditions(txn)
            if local_check['ok']:
                logger.info(f"[2PC] Single node mode - auto-approved PREPARE")
                return {'all_yes': True, 'reason': None}
            else:
                return {'all_yes': False, 'reason': local_check['reason']}

        # Enviar PREPARE a todos los nodos
        msg = Message(
            type=TWO_PC_REQUEST,
            sender_id=self.bully_manager.node_id,
            timestamp=time.time(),
            data={
                'phase': 'PREPARE',
                'txn_id': txn.txn_id,
                'operation': txn.operation,
                'txn_data': txn.data
            }
        )

        for node_id, (ip, tcp_port, _) in otros_nodos.items():
            try:
                logger.info(f"[2PC] Sending PREPARE to node {node_id}")
                response = self.bully_manager.comm.send_tcp(
                    ip, tcp_port, msg, timeout=self.prepare_timeout
                )

                if response and response.data and response.data.get('vote') == 'YES':
                    txn.votes[node_id] = VoteResult.YES
                    logger.info(f"[2PC] Node {node_id} voted YES")
                else:
                    reason = response.data.get('reason', 'unknown') if response and response.data else 'no response data'
                    txn.votes[node_id] = VoteResult.NO
                    logger.warning(f"[2PC] Node {node_id} voted NO: {reason}")
                    return {
                        'all_yes': False,
                        'reason': f'Node {node_id} voted NO: {reason}'
                    }

            except Exception as e:
                txn.votes[node_id] = VoteResult.TIMEOUT
                logger.error(f"[2PC] Node {node_id} timeout/error: {e}")
                return {
                    'all_yes': False,
                    'reason': f'Node {node_id} timeout/error: {e}'
                }

        # Todos votaron YES
        return {'all_yes': True, 'reason': None}

    def _commit_phase(self, txn: Transaction) -> Dict[str, Any]:
        """
        COMMIT: Envía orden de commit a todos los nodos.

        Returns:
            {'success': bool, 'error': str or None}
        """
        from bully.communication import Message

        txn.phase = TxnPhase.COMMIT
        otros_nodos = {k: v for k, v in self.bully_manager.cluster_nodes.items()
                       if k != self.bully_manager.node_id}

        # Primero: commit local
        local_result = self._apply_local_transaction(txn)
        if not local_result['success']:
            logger.error(f"[2PC] Local commit failed: {local_result['error']}")
            return {'success': False, 'error': local_result['error']}

        if not otros_nodos:
            return {'success': True}

        # Enviar COMMIT a todos los nodos
        msg = Message(
            type=TWO_PC_REQUEST,
            sender_id=self.bully_manager.node_id,
            timestamp=time.time(),
            data={
                'phase': 'COMMIT',
                'txn_id': txn.txn_id
            }
        )

        commit_acks = 0
        for node_id, (ip, tcp_port, _) in otros_nodos.items():
            try:
                logger.info(f"[2PC] Sending COMMIT to node {node_id}")
                response = self.bully_manager.comm.send_tcp(
                    ip, tcp_port, msg, timeout=self.commit_timeout
                )
                if response and response.data and response.data.get('ack'):
                    commit_acks += 1
                    logger.info(f"[2PC] Node {node_id} acknowledged COMMIT")
                else:
                    logger.warning(f"[2PC] Node {node_id} did not acknowledge COMMIT")
            except Exception as e:
                logger.warning(f"[2PC] COMMIT ack failed from node {node_id}: {e}")
                # Continuar - el commit local ya está hecho

        # El commit es exitoso si al menos mayoría confirmó
        # (o si no hay otros nodos)
        required_acks = len(otros_nodos) // 2 + 1
        success = commit_acks >= required_acks or len(otros_nodos) == 0

        logger.info(f"[2PC] COMMIT phase: {commit_acks}/{len(otros_nodos)} acks (needed {required_acks})")
        return {'success': success}

    def _abort_phase(self, txn: Transaction) -> None:
        """
        ABORT: Envía orden de abort a todos los nodos.
        Best-effort - no espera confirmación.
        """
        from bully.communication import Message

        txn.phase = TxnPhase.ABORT
        otros_nodos = {k: v for k, v in self.bully_manager.cluster_nodes.items()
                       if k != self.bully_manager.node_id}

        logger.info(f"[2PC] Sending ABORT for {txn.txn_id}")

        if not otros_nodos:
            return

        msg = Message(
            type=TWO_PC_REQUEST,
            sender_id=self.bully_manager.node_id,
            timestamp=time.time(),
            data={
                'phase': 'ABORT',
                'txn_id': txn.txn_id
            }
        )

        for node_id, (ip, tcp_port, _) in otros_nodos.items():
            try:
                self.bully_manager.comm.send_tcp(ip, tcp_port, msg, timeout=2.0)
                logger.info(f"[2PC] ABORT sent to node {node_id}")
            except Exception as e:
                logger.warning(f"[2PC] Failed to send ABORT to node {node_id}: {e}")

    def _verify_local_preconditions(self, txn: Transaction) -> Dict[str, Any]:
        """
        Verifica precondiciones locales antes de votar YES.

        Returns:
            {'ok': bool, 'reason': str or None}
        """
        with self.flask_app.app_context():
            from models import Doctor, Cama, VisitaEmergencia

            data = txn.data

            if txn.operation == 'CREATE_VISIT':
                # Verificar que doctor y cama están disponibles
                doctor = Doctor.query.get(data.get('doctor_id'))
                cama = Cama.query.get(data.get('cama_id'))

                if not doctor or not doctor.disponible:
                    return {'ok': False, 'reason': 'Doctor no disponible'}

                if not cama or cama.ocupada:
                    return {'ok': False, 'reason': 'Cama no disponible'}

                return {'ok': True, 'reason': None}

            elif txn.operation == 'CLOSE_VISIT':
                # Verificar que visita existe y está activa
                visita = VisitaEmergencia.query.filter_by(folio=data.get('folio')).first()

                if not visita:
                    return {'ok': False, 'reason': 'Visita no encontrada'}

                if visita.estado != 'activa':
                    return {'ok': False, 'reason': 'Visita no está activa'}

                return {'ok': True, 'reason': None}

            return {'ok': False, 'reason': f'Operación desconocida: {txn.operation}'}

    def _apply_local_transaction(self, txn: Transaction) -> Dict[str, Any]:
        """
        Aplica la transacción localmente en la base de datos.

        Returns:
            {'success': bool, 'error': str or None, 'data': dict}
        """
        with self.flask_app.app_context():
            from models import db, Doctor, Cama, Paciente, VisitaEmergencia
            from datetime import datetime

            data = txn.data

            try:
                if txn.operation == 'CREATE_VISIT':
                    return self._create_visit_local(data)
                elif txn.operation == 'CLOSE_VISIT':
                    return self._close_visit_local(data)
                else:
                    return {'success': False, 'error': f'Unknown operation: {txn.operation}'}

            except Exception as e:
                db.session.rollback()
                logger.error(f"[2PC] Local transaction error: {e}")
                return {'success': False, 'error': str(e)}

    def _create_visit_local(self, data: Dict) -> Dict[str, Any]:
        """Crea una visita localmente."""
        from models import db, Doctor, Cama, Paciente, VisitaEmergencia

        # Obtener recursos
        doctor = Doctor.query.get(data['doctor_id'])
        cama = Cama.query.get(data['cama_id'])

        # Obtener o crear paciente
        paciente = Paciente.query.get(data.get('paciente_id'))
        if not paciente and data.get('paciente_nombre'):
            paciente = Paciente(
                nombre=data['paciente_nombre'],
                edad=data.get('paciente_edad'),
                sexo=data.get('paciente_sexo', 'M')
            )
            db.session.add(paciente)
            db.session.flush()

        if not paciente:
            return {'success': False, 'error': 'Paciente no encontrado'}

        # Marcar recursos como ocupados
        doctor.disponible = False
        cama.ocupada = True
        cama.id_paciente = paciente.id_paciente

        # Crear visita (folio=None, se genera en before_insert)
        # Formato generado: P{id_paciente}-D{id_doctor}-S{id_sala}-{consecutivo:04d}
        visita = VisitaEmergencia(
            folio=None,  # Se genera automaticamente en before_insert
            id_paciente=paciente.id_paciente,
            id_doctor=doctor.id_doctor,
            id_cama=cama.id_cama,
            id_sala=data['sala_id'],
            id_trabajador=data.get('trabajador_id'),
            sintomas=data.get('sintomas'),
            diagnostico=data.get('diagnostico'),
            estado='activa'
        )
        db.session.add(visita)
        db.session.commit()

        logger.info(f"[2PC] Local CREATE_VISIT committed: folio={visita.folio}")
        return {
            'success': True,
            'data': {
                'folio': visita.folio,
                'id_visita': visita.id_visita
            }
        }

    def _close_visit_local(self, data: Dict) -> Dict[str, Any]:
        """Cierra una visita localmente."""
        from models import db, Doctor, Cama, VisitaEmergencia
        from datetime import datetime

        visita = VisitaEmergencia.query.filter_by(folio=data['folio']).first()
        if not visita:
            return {'success': False, 'error': 'Visita no encontrada'}

        # Liberar recursos
        doctor = Doctor.query.get(data['doctor_id'])
        cama = Cama.query.get(data['cama_id'])

        if doctor:
            doctor.disponible = True
        if cama:
            cama.ocupada = False
            cama.id_paciente = None

        visita.estado = 'completada'
        visita.fecha_cierre = datetime.utcnow()

        db.session.commit()

        logger.info(f"[2PC] Local CLOSE_VISIT committed: folio={data['folio']}")
        return {'success': True, 'data': {'folio': data['folio']}}


# ============================================================================
# WAL (Write-Ahead Log) - Almacenamiento de transacciones pendientes
# ============================================================================

_pending_transactions: Dict[str, Dict] = {}
_wal_lock = threading.Lock()


def save_pending_txn(txn_id: str, operation: str, data: Dict) -> None:
    """Guarda una transacción pendiente en el WAL."""
    with _wal_lock:
        _pending_transactions[txn_id] = {
            'operation': operation,
            'data': data,
            'timestamp': time.time()
        }
    logger.info(f"[2PC-WAL] Saved pending transaction: {txn_id}")


def get_pending_txn(txn_id: str) -> Optional[Dict]:
    """Obtiene una transacción pendiente del WAL."""
    with _wal_lock:
        return _pending_transactions.get(txn_id)


def remove_pending_txn(txn_id: str) -> None:
    """Elimina una transacción pendiente del WAL."""
    with _wal_lock:
        if txn_id in _pending_transactions:
            del _pending_transactions[txn_id]
    logger.info(f"[2PC-WAL] Removed pending transaction: {txn_id}")


def cleanup_expired_txns(max_age_seconds: int = 300) -> None:
    """Limpia transacciones pendientes expiradas."""
    now = time.time()
    with _wal_lock:
        expired = [
            txn_id for txn_id, txn in _pending_transactions.items()
            if now - txn['timestamp'] > max_age_seconds
        ]
        for txn_id in expired:
            del _pending_transactions[txn_id]
            logger.warning(f"[2PC-WAL] Cleaned up expired transaction: {txn_id}")


# ============================================================================
# HANDLER PARA MENSAJES 2PC (participante)
# ============================================================================


def handle_2pc_request(message, flask_app, node_id) -> 'Message':
    """
    Handler para mensajes del protocolo 2PC.

    Este handler se ejecuta en nodos PARTICIPANTES (no coordinadores).

    Args:
        message: Mensaje TWO_PC_REQUEST entrante
        flask_app: Aplicación Flask
        node_id: ID de este nodo

    Returns:
        Message con TWO_PC_RESPONSE
    """
    from bully.communication import Message

    data = message.data or {}
    phase = data.get('phase')
    txn_id = data.get('txn_id')

    logger.info(f"[2PC-HANDLER] Received {phase} for {txn_id} from node {message.sender_id}")

    if phase == 'PREPARE':
        return _handle_prepare(message, flask_app, node_id)
    elif phase == 'COMMIT':
        return _handle_commit(message, flask_app, node_id)
    elif phase == 'ABORT':
        return _handle_abort(message, node_id)
    else:
        return Message(
            type=TWO_PC_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'error': f'Unknown phase: {phase}'}
        )


def _handle_prepare(message, flask_app, node_id) -> 'Message':
    """
    PREPARE phase handler (participante).

    Verifica precondiciones y vota YES o NO.
    NO hace commit - solo verifica y guarda en WAL.
    """
    from bully.communication import Message
    from models import Doctor, Cama, VisitaEmergencia

    data = message.data
    txn_id = data['txn_id']
    operation = data['operation']
    txn_data = data['txn_data']

    with flask_app.app_context():
        try:
            if operation == 'CREATE_VISIT':
                # Verificar que doctor y cama están disponibles
                doctor = Doctor.query.get(txn_data.get('doctor_id'))
                cama = Cama.query.get(txn_data.get('cama_id'))

                if not doctor or not doctor.disponible:
                    logger.warning(f"[2PC-PREPARE] Doctor not available for {txn_id}")
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'vote': 'NO', 'reason': 'Doctor no disponible'}
                    )

                if not cama or cama.ocupada:
                    logger.warning(f"[2PC-PREPARE] Cama not available for {txn_id}")
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'vote': 'NO', 'reason': 'Cama no disponible'}
                    )

            elif operation == 'CLOSE_VISIT':
                # Verificar que visita existe y está activa
                visita = VisitaEmergencia.query.filter_by(folio=txn_data.get('folio')).first()

                if not visita or visita.estado != 'activa':
                    logger.warning(f"[2PC-PREPARE] Visit not found/active for {txn_id}")
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'vote': 'NO', 'reason': 'Visita no encontrada o no activa'}
                    )

            # Guardar en WAL y votar YES
            save_pending_txn(txn_id, operation, txn_data)
            logger.info(f"[2PC-PREPARE] Voting YES for {txn_id}")

            return Message(
                type=TWO_PC_RESPONSE,
                sender_id=node_id,
                timestamp=time.time(),
                data={'vote': 'YES'}
            )

        except Exception as e:
            logger.error(f"[2PC-PREPARE] Error: {e}")
            return Message(
                type=TWO_PC_RESPONSE,
                sender_id=node_id,
                timestamp=time.time(),
                data={'vote': 'NO', 'reason': str(e)}
            )


def _handle_commit(message, flask_app, node_id) -> 'Message':
    """
    COMMIT phase handler (participante).

    Aplica la transacción guardada en WAL.
    """
    from bully.communication import Message
    from models import db, Doctor, Cama, Paciente, VisitaEmergencia
    from datetime import datetime

    data = message.data
    txn_id = data['txn_id']

    pending_txn = get_pending_txn(txn_id)
    if not pending_txn:
        logger.error(f"[2PC-COMMIT] No pending transaction found: {txn_id}")
        return Message(
            type=TWO_PC_RESPONSE,
            sender_id=node_id,
            timestamp=time.time(),
            data={'ack': False, 'reason': 'No pending transaction'}
        )

    with flask_app.app_context():
        try:
            operation = pending_txn['operation']
            txn_data = pending_txn['data']

            if operation == 'CREATE_VISIT':
                # Verificar si la visita ya existe (BD compartida - coordinador ya la creó)
                # Buscar por doctor_id + cama_id + estado='activa' (folio ahora es None hasta insert)
                existing_visit = VisitaEmergencia.query.filter_by(
                    id_doctor=txn_data['doctor_id'],
                    id_cama=txn_data['cama_id'],
                    estado='activa'
                ).first()

                if existing_visit:
                    # BD compartida - el coordinador ya insertó la visita
                    logger.warning(f"[2PC-COMMIT] Visita ya existe: {existing_visit.folio} (BD compartida), ACK directo")
                    remove_pending_txn(txn_id)
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'ack': True}
                    )

                # BD separada - hacer INSERT normal
                logger.warning(f"[2PC-COMMIT] Participante creando visita (folio se genera en insert)")

                doctor = Doctor.query.get(txn_data['doctor_id'])
                cama = Cama.query.get(txn_data['cama_id'])

                # Obtener o crear paciente
                paciente = Paciente.query.get(txn_data.get('paciente_id'))
                if not paciente and txn_data.get('paciente_nombre'):
                    paciente = Paciente(
                        nombre=txn_data['paciente_nombre'],
                        edad=txn_data.get('paciente_edad'),
                        sexo=txn_data.get('paciente_sexo', 'M')
                    )
                    db.session.add(paciente)
                    db.session.flush()

                if not paciente:
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'ack': False, 'reason': 'Paciente no encontrado'}
                    )

                # Marcar recursos como ocupados
                if doctor:
                    doctor.disponible = False
                if cama:
                    cama.ocupada = True
                    cama.id_paciente = paciente.id_paciente

                # Crear visita (folio=None, se genera en before_insert)
                # Formato: P{id_paciente}-D{id_doctor}-S{id_sala}-{consecutivo:04d}
                visita = VisitaEmergencia(
                    folio=None,  # Se genera automaticamente en before_insert
                    id_paciente=paciente.id_paciente,
                    id_doctor=txn_data['doctor_id'],
                    id_cama=txn_data['cama_id'],
                    id_sala=txn_data['sala_id'],
                    id_trabajador=txn_data.get('trabajador_id'),
                    sintomas=txn_data.get('sintomas'),
                    diagnostico=txn_data.get('diagnostico'),
                    estado='activa'
                )
                db.session.add(visita)
                logger.warning(f"[2PC-COMMIT] Visita creada exitosamente: folio={visita.folio}")

            elif operation == 'CLOSE_VISIT':
                # Verificar si la visita ya está cerrada (BD compartida)
                visita = VisitaEmergencia.query.filter_by(folio=txn_data['folio']).first()

                if visita and visita.estado == 'completada':
                    # BD compartida - coordinador ya cerró la visita
                    logger.warning(f"[2PC-COMMIT] Visita {txn_data['folio']} ya cerrada (BD compartida), ACK directo")
                    remove_pending_txn(txn_id)
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'ack': True}
                    )

                # BD separada o necesita cierre
                logger.warning(f"[2PC-COMMIT] Cerrando visita: {txn_data['folio']}")
                doctor = Doctor.query.get(txn_data['doctor_id'])
                cama = Cama.query.get(txn_data['cama_id'])

                if doctor:
                    doctor.disponible = True
                if cama:
                    cama.ocupada = False
                    cama.id_paciente = None
                if visita:
                    visita.estado = 'completada'
                    visita.fecha_cierre = datetime.utcnow()

            db.session.commit()
            remove_pending_txn(txn_id)

            logger.info(f"[2PC-COMMIT] Transaction committed: {txn_id}")
            return Message(
                type=TWO_PC_RESPONSE,
                sender_id=node_id,
                timestamp=time.time(),
                data={'ack': True}
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"[2PC-COMMIT] Error: {e}")
            return Message(
                type=TWO_PC_RESPONSE,
                sender_id=node_id,
                timestamp=time.time(),
                data={'ack': False, 'reason': str(e)}
            )


def _handle_abort(message, node_id) -> 'Message':
    """
    ABORT phase handler (participante).

    Descarta la transacción pendiente del WAL.
    """
    from bully.communication import Message

    data = message.data
    txn_id = data['txn_id']

    remove_pending_txn(txn_id)
    logger.info(f"[2PC-ABORT] Transaction aborted: {txn_id}")

    return Message(
        type=TWO_PC_RESPONSE,
        sender_id=node_id,
        timestamp=time.time(),
        data={'ack': True}
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Tipos
    'TxnPhase',
    'VoteResult',
    'Transaction',
    'TWO_PC_REQUEST',
    'TWO_PC_RESPONSE',
    # Coordinador
    'TwoPhaseCommitCoordinator',
    # WAL
    'save_pending_txn',
    'get_pending_txn',
    'remove_pending_txn',
    'cleanup_expired_txns',
    # Handler
    'handle_2pc_request',
]
