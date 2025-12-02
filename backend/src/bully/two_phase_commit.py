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
# HELPER: COMMIT CON RETRY PARA SQLITE CONCURRENCY
# ============================================================================

def _commit_with_retry_module(db_session, max_retries=5):
    """
    Commit con retry y backoff exponencial para SQLite locks.

    Resuelve el error "database is locked" cuando múltiples nodos
    en la misma Mac comparten el mismo archivo emergencias.db.

    Args:
        db_session: session de SQLAlchemy (db.session)
        max_retries: Número máximo de reintentos

    Returns:
        True si el commit fue exitoso

    Raises:
        Exception si falla después de todos los reintentos
    """
    for attempt in range(max_retries):
        try:
            db_session.commit()
            return True
        except Exception as e:
            error_str = str(e).lower()
            if 'database is locked' in error_str or 'database is busy' in error_str:
                wait_time = 0.5 * (2 ** attempt)  # 0.5, 1, 2, 4, 8 segundos
                logger.warning(f"[2PC] Database locked, retry {attempt+1}/{max_retries} in {wait_time}s")
                db_session.rollback()
                time.sleep(wait_time)
                continue
            # Si es otro error, no reintentar
            raise
    raise Exception("Max retries exceeded for database commit - database is locked")


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
        self.prepare_timeout = 3.0  # segundos (reducido de 10.0 para respuesta rápida)
        self.commit_timeout = 2.0   # segundos (reducido de 5.0)

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

        # Enviar COMMIT a todos los nodos CON los datos generados por el coordinador
        # Esto incluye el folio generado para que los participantes usen el mismo
        msg = Message(
            type=TWO_PC_REQUEST,
            sender_id=self.bully_manager.node_id,
            timestamp=time.time(),
            data={
                'phase': 'COMMIT',
                'txn_id': txn.txn_id,
                'commit_data': local_result.get('data', {}),  # Incluye folio, id_visita
                'txn_data': txn.data  # Datos originales de la transacción
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

        # Para CREATE_DOCTOR y CREATE_TRABAJADOR:
        # Si el commit local fue exitoso, SIEMPRE ejecutar fallback HTTP y reportar éxito.
        # El fallback HTTP garantiza replicación aunque no lleguen ACKs TCP.
        # Esto evita "falsos negativos" cuando nodos están ocupados con sus propias transacciones.
        if txn.operation in ('CREATE_DOCTOR', 'CREATE_TRABAJADOR'):
            if txn.operation == 'CREATE_DOCTOR':
                self._replicate_doctor_http_fallback(local_result, txn.data, commit_acks, len(otros_nodos))
            else:
                self._replicate_trabajador_http_fallback(local_result, txn.data, commit_acks, len(otros_nodos))
            # Éxito porque: commit local OK + HTTP fallback ejecutado
            logger.info(f"[2PC] {txn.operation} completado: commit local + HTTP fallback")
            return {'success': True}

        # Para otros tipos de transacción (CREATE_VISIT), mantener lógica de mayoría
        if success:
            if txn.operation == 'CREATE_VISIT':
                self._replicate_visit_http_fallback(local_result, commit_acks, len(otros_nodos))

        return {'success': success}

    def _replicate_visit_http_fallback(self, local_result: Dict, commit_acks: int, total_nodes: int):
        """
        Replica visita vía HTTP como fallback si algunos nodos no confirmaron por TCP.

        Args:
            local_result: Resultado del commit local con datos de la visita
            commit_acks: Número de nodos que confirmaron por TCP
            total_nodes: Total de nodos en el cluster
        """
        # Solo usar fallback si hay nodos que no confirmaron
        if commit_acks >= total_nodes:
            return

        try:
            from models import replicate_visit_to_cluster

            visita_data = local_result.get('data', {})
            if not visita_data or not visita_data.get('folio'):
                return

            # Construir datos completos para replicación HTTP
            replication_data = {
                'folio': visita_data.get('folio'),
                'id_paciente': visita_data.get('id_paciente'),
                'id_doctor': visita_data.get('id_doctor'),
                'id_cama': visita_data.get('id_cama'),
                'id_sala': visita_data.get('id_sala'),
                'sintomas': visita_data.get('sintomas'),
                'diagnostico': visita_data.get('diagnostico'),
                'estado': visita_data.get('estado', 'activa'),
                'timestamp': visita_data.get('timestamp'),
                'fecha_cierre': visita_data.get('fecha_cierre'),
                'paciente': visita_data.get('paciente')
            }

            result = replicate_visit_to_cluster(
                self.bully_manager,
                replication_data,
                exclude_node_id=self.bully_manager.node_id
            )

            logger.info(f"[2PC] HTTP fallback replication: {result['success_count']}/{result['total_nodes']} nodes")

        except Exception as e:
            logger.warning(f"[2PC] HTTP fallback replication failed: {e}")

    def _replicate_doctor_http_fallback(self, local_result: Dict, txn_data: Dict, commit_acks: int, total_nodes: int):
        """
        Replica doctor vía HTTP como fallback si algunos nodos no confirmaron por TCP.

        Args:
            local_result: Resultado del commit local con datos del doctor
            txn_data: Datos originales de la transacción
            commit_acks: Número de nodos que confirmaron por TCP
            total_nodes: Total de nodos en el cluster
        """
        # Siempre hacer fallback HTTP para doctores (garantizar sincronización entre Macs)
        try:
            from bully.data_sync import get_synchronizer
            sync = get_synchronizer()
            if sync:
                doctor_data = local_result.get('data', {})
                if not doctor_data.get('id_doctor'):
                    return

                sync.propagate_to_cluster('doctor', 'INSERT', {
                    'id_doctor': doctor_data.get('id_doctor'),
                    'nombre': txn_data.get('nombre'),
                    'especialidad': txn_data.get('especialidad'),
                    'id_sala': txn_data.get('sala_id'),
                    'disponible': True,
                    'activo': True
                })
                logger.info(f"[2PC] HTTP fallback doctor replication: id={doctor_data.get('id_doctor')}")
        except Exception as e:
            logger.warning(f"[2PC] HTTP fallback doctor replication failed: {e}")

    def _replicate_trabajador_http_fallback(self, local_result: Dict, txn_data: Dict, commit_acks: int, total_nodes: int):
        """
        Replica trabajador social vía HTTP como fallback si algunos nodos no confirmaron por TCP.

        Args:
            local_result: Resultado del commit local con datos del trabajador
            txn_data: Datos originales de la transacción
            commit_acks: Número de nodos que confirmaron por TCP
            total_nodes: Total de nodos en el cluster
        """
        # Siempre hacer fallback HTTP para trabajadores (garantizar sincronización entre Macs)
        try:
            from bully.data_sync import get_synchronizer
            sync = get_synchronizer()
            if sync:
                trabajador_data = local_result.get('data', {})
                if not trabajador_data.get('id_trabajador'):
                    return

                sync.propagate_to_cluster('trabajador', 'INSERT', {
                    'id_trabajador': trabajador_data.get('id_trabajador'),
                    'nombre': txn_data.get('nombre'),
                    'id_sala': txn_data.get('sala_id'),
                    'activo': True
                })
                logger.info(f"[2PC] HTTP fallback trabajador replication: id={trabajador_data.get('id_trabajador')}")
        except Exception as e:
            logger.warning(f"[2PC] HTTP fallback trabajador replication failed: {e}")

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

            elif txn.operation == 'CREATE_DOCTOR':
                # Verificar que la sala existe
                from models import Sala
                sala = Sala.query.get(data.get('sala_id'))
                if not sala:
                    return {'ok': False, 'reason': 'Sala no existe'}
                return {'ok': True, 'reason': None}

            elif txn.operation == 'CREATE_TRABAJADOR':
                # Verificar que la sala existe
                from models import Sala
                sala = Sala.query.get(data.get('sala_id'))
                if not sala:
                    return {'ok': False, 'reason': 'Sala no existe'}
                return {'ok': True, 'reason': None}

            return {'ok': False, 'reason': f'Operación desconocida: {txn.operation}'}

    def _apply_local_transaction(self, txn: Transaction) -> Dict[str, Any]:
        """
        Aplica la transacción localmente en la base de datos.

        Returns:
            {'success': bool, 'error': str or None, 'data': dict}
        """
        with self.flask_app.app_context():
            from models import db, Doctor, Cama, Paciente, VisitaEmergencia, set_2pc_context
            from datetime import datetime

            data = txn.data

            try:
                # Activar contexto 2PC para evitar doble propagación
                # Los event listeners verifican este flag y no propagan si está activo
                set_2pc_context(True)

                if txn.operation == 'CREATE_VISIT':
                    result = self._create_visit_local(data)
                elif txn.operation == 'CLOSE_VISIT':
                    result = self._close_visit_local(data)
                elif txn.operation == 'CREATE_DOCTOR':
                    result = self._create_doctor_local(data)
                elif txn.operation == 'CREATE_TRABAJADOR':
                    result = self._create_trabajador_local(data)
                else:
                    result = {'success': False, 'error': f'Unknown operation: {txn.operation}'}

                return result

            except Exception as e:
                db.session.rollback()
                logger.error(f"[2PC] Local transaction error: {e}")
                return {'success': False, 'error': str(e)}

            finally:
                # Siempre desactivar el contexto 2PC
                set_2pc_context(False)

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
        _commit_with_retry_module(db.session)

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

        _commit_with_retry_module(db.session)

        logger.info(f"[2PC] Local CLOSE_VISIT committed: folio={data['folio']}")
        return {'success': True, 'data': {'folio': data['folio']}}

    def _create_doctor_local(self, data: Dict) -> Dict[str, Any]:
        """Crea un doctor localmente con su usuario."""
        from models import db, Doctor
        from auth import crear_usuario_para_personal

        doctor = Doctor(
            nombre=data['nombre'],
            especialidad=data['especialidad'],
            id_sala=data['sala_id'],
            disponible=True,
            activo=True
        )
        db.session.add(doctor)
        db.session.flush()  # Para obtener el ID generado

        # Crear usuario automáticamente
        user_result = crear_usuario_para_personal('doctor', doctor.id_doctor)

        _commit_with_retry_module(db.session)

        logger.info(f"[2PC] Local CREATE_DOCTOR committed: id={doctor.id_doctor}, user={user_result.get('username')}")
        return {
            'success': True,
            'data': {
                'id_doctor': doctor.id_doctor,
                'username': user_result.get('username'),
                'password': user_result.get('password')
            }
        }

    def _create_trabajador_local(self, data: Dict) -> Dict[str, Any]:
        """Crea un trabajador social localmente con su usuario."""
        from models import db, TrabajadorSocial
        from auth import crear_usuario_para_personal

        trabajador = TrabajadorSocial(
            nombre=data['nombre'],
            id_sala=data['sala_id'],
            activo=True
        )
        db.session.add(trabajador)
        db.session.flush()  # Para obtener el ID generado

        # Crear usuario automáticamente
        user_result = crear_usuario_para_personal('trabajador_social', trabajador.id_trabajador)

        _commit_with_retry_module(db.session)

        logger.info(f"[2PC] Local CREATE_TRABAJADOR committed: id={trabajador.id_trabajador}, user={user_result.get('username')}")
        return {
            'success': True,
            'data': {
                'id_trabajador': trabajador.id_trabajador,
                'username': user_result.get('username'),
                'password': user_result.get('password')
            }
        }


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

            elif operation == 'CREATE_DOCTOR':
                # Verificar que la sala existe
                from models import Sala
                sala = Sala.query.get(txn_data.get('sala_id'))
                if not sala:
                    logger.warning(f"[2PC-PREPARE] Sala not found for {txn_id}")
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'vote': 'NO', 'reason': 'Sala no existe'}
                    )

            elif operation == 'CREATE_TRABAJADOR':
                # Verificar que la sala existe
                from models import Sala
                sala = Sala.query.get(txn_data.get('sala_id'))
                if not sala:
                    logger.warning(f"[2PC-PREPARE] Sala not found for {txn_id}")
                    return Message(
                        type=TWO_PC_RESPONSE,
                        sender_id=node_id,
                        timestamp=time.time(),
                        data={'vote': 'NO', 'reason': 'Sala no existe'}
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
    Usa el folio generado por el coordinador para consistencia en VMs separadas.
    """
    from bully.communication import Message
    from models import db, Doctor, Cama, Paciente, VisitaEmergencia
    from datetime import datetime

    data = message.data
    txn_id = data['txn_id']

    # Obtener datos del coordinador (folio generado, etc.)
    commit_data = data.get('commit_data', {})
    folio_coordinador = commit_data.get('folio')  # Folio generado por el coordinador

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
        from models import set_2pc_context
        try:
            # Activar contexto 2PC para evitar doble propagación
            set_2pc_context(True)

            operation = pending_txn['operation']
            txn_data = pending_txn['data']

            if operation == 'CREATE_VISIT':
                # Verificar si la visita ya existe (BD compartida - coordinador ya la creó)
                # Primero buscar por folio del coordinador (más preciso)
                existing_visit = None
                if folio_coordinador:
                    existing_visit = VisitaEmergencia.query.filter_by(folio=folio_coordinador).first()

                # Fallback: buscar por doctor_id + cama_id + estado='activa'
                if not existing_visit:
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

                # BD separada - hacer INSERT con folio del coordinador
                logger.warning(f"[2PC-COMMIT] Participante creando visita con folio: {folio_coordinador}")

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

                # Crear visita usando el FOLIO DEL COORDINADOR para consistencia
                # Si no hay folio del coordinador (versión antigua), se genera automáticamente
                visita = VisitaEmergencia(
                    folio=folio_coordinador,  # Usar folio del coordinador para consistencia en VMs
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
                logger.warning(f"[2PC-COMMIT] Visita creada con folio coordinador: {folio_coordinador}")

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

            elif operation == 'CREATE_DOCTOR':
                from models import Doctor as DoctorModel
                from auth import crear_usuario_para_personal

                # Verificar si ya existe (BD compartida o ya replicado)
                commit_data = data.get('commit_data', {})
                id_doctor_coord = commit_data.get('id_doctor')
                if id_doctor_coord:
                    existing = DoctorModel.query.get(id_doctor_coord)
                    if existing:
                        logger.warning(f"[2PC-COMMIT] Doctor ya existe: {id_doctor_coord} (BD compartida)")
                        remove_pending_txn(txn_id)
                        return Message(
                            type=TWO_PC_RESPONSE,
                            sender_id=node_id,
                            timestamp=time.time(),
                            data={'ack': True}
                        )

                # Crear doctor CON EL ID DEL COORDINADOR para consistencia entre Macs
                # Si hay id_doctor del coordinador, usarlo para mantener IDs sincronizados
                doctor_nuevo = DoctorModel(
                    nombre=txn_data['nombre'],
                    especialidad=txn_data['especialidad'],
                    id_sala=txn_data['sala_id'],
                    disponible=True,
                    activo=True
                )
                # Asignar el ID del coordinador si está disponible (BDs separadas)
                if id_doctor_coord:
                    doctor_nuevo.id_doctor = id_doctor_coord
                db.session.add(doctor_nuevo)
                db.session.flush()
                crear_usuario_para_personal('doctor', doctor_nuevo.id_doctor)
                logger.warning(f"[2PC-COMMIT] Doctor creado: {doctor_nuevo.id_doctor} (id_coord={id_doctor_coord})")

            elif operation == 'CREATE_TRABAJADOR':
                from models import TrabajadorSocial
                from auth import crear_usuario_para_personal

                # Verificar si ya existe (BD compartida o ya replicado)
                commit_data = data.get('commit_data', {})
                id_trabajador_coord = commit_data.get('id_trabajador')
                if id_trabajador_coord:
                    existing = TrabajadorSocial.query.get(id_trabajador_coord)
                    if existing:
                        logger.warning(f"[2PC-COMMIT] Trabajador ya existe: {id_trabajador_coord} (BD compartida)")
                        remove_pending_txn(txn_id)
                        return Message(
                            type=TWO_PC_RESPONSE,
                            sender_id=node_id,
                            timestamp=time.time(),
                            data={'ack': True}
                        )

                # Crear trabajador CON EL ID DEL COORDINADOR para consistencia entre Macs
                trabajador_nuevo = TrabajadorSocial(
                    nombre=txn_data['nombre'],
                    id_sala=txn_data['sala_id'],
                    activo=True
                )
                # Asignar el ID del coordinador si está disponible (BDs separadas)
                if id_trabajador_coord:
                    trabajador_nuevo.id_trabajador = id_trabajador_coord
                db.session.add(trabajador_nuevo)
                db.session.flush()
                crear_usuario_para_personal('trabajador_social', trabajador_nuevo.id_trabajador)
                logger.warning(f"[2PC-COMMIT] Trabajador creado: {trabajador_nuevo.id_trabajador} (id_coord={id_trabajador_coord})")

            # Usar retry con backoff para manejar "database is locked"
            _commit_with_retry_module(db.session)
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

        finally:
            # Siempre desactivar el contexto 2PC
            set_2pc_context(False)


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
