"""
Data Synchronization Module for Distributed Database.

Este módulo maneja la sincronización de datos entre nodos del cluster:
1. Sincronización inicial cuando un nodo se une al cluster
2. Propagación de cambios a otros nodos
3. Recuperación de datos de nodos existentes
4. Re-sincronización cuando cambia el cluster
"""

import logging
import requests
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any, Set

# Logger específico para sincronización
sync_logger = logging.getLogger('cluster.sync')


class DataSynchronizer:
    """
    Sincronizador de datos distribuidos.

    Maneja la sincronización inicial de un nodo nuevo y la propagación
    de cambios a otros nodos del cluster.
    """

    def __init__(self, flask_app, bully_manager=None):
        """
        Inicializa el sincronizador.

        Args:
            flask_app: Aplicación Flask con contexto de base de datos
            bully_manager: Instancia de BullyNode (opcional, se puede asignar después)
        """
        self.app = flask_app
        self.bully_manager = bully_manager
        self._synced = False
        self._sync_timestamp = None
        self._known_nodes: Set[int] = set()  # Nodos conocidos para detectar cambios
        self._sync_lock = threading.Lock()  # Lock para evitar syncs simultáneos

    def set_bully_manager(self, bully_manager):
        """Asigna el BullyManager después de la inicialización."""
        self.bully_manager = bully_manager

    @property
    def is_synced(self) -> bool:
        """Retorna True si el nodo ya realizó sincronización inicial."""
        return self._synced

    def perform_initial_sync(self, timeout: float = 10.0) -> bool:
        """
        Realiza sincronización desde TODOS los nodos del cluster.
        Esto garantiza tener datos completos de todas las salas.

        Args:
            timeout: Timeout para las requests HTTP

        Returns:
            bool: True si la sincronización fue exitosa
        """
        with self._sync_lock:
            if not self.bully_manager:
                sync_logger.warning("No bully_manager configured, skipping sync")
                return False

            # Obtener nodos del cluster (copia para evitar modificación durante iteración)
            cluster_nodes = dict(self.bully_manager.cluster_nodes)
            if not cluster_nodes:
                sync_logger.info("No other nodes in cluster, nothing to sync")
                self._synced = True
                return True

            from config import Config

            sync_logger.info(f"[SYNC] Starting full cluster sync from {len(cluster_nodes)} nodes")

            # Actualizar nodos conocidos
            self._known_nodes = set(cluster_nodes.keys())

            # Sincronizar desde TODOS los nodos para obtener datos completos
            success_count = 0
            for node_id, (host, tcp_port, udp_port) in cluster_nodes.items():
                if node_id == Config.NODE_ID:
                    continue

                flask_port = 5000 + node_id % 1000
                sync_logger.info(f"[SYNC] Syncing from Node {node_id} ({host}:{flask_port})")

                if self._sync_from_node(host, flask_port, timeout):
                    success_count += 1
                    sync_logger.info(f"[SYNC] Successfully synced from Node {node_id}")
                else:
                    sync_logger.warning(f"[SYNC] Failed to sync from Node {node_id}")

            if success_count > 0:
                self._synced = True
                self._sync_timestamp = datetime.now()
                sync_logger.info(f"[SYNC] Completed: synced from {success_count}/{len(cluster_nodes)-1} nodes")
                return True

            sync_logger.warning("[SYNC] Could not sync from any node")
            return False

    def _sync_from_node(self, host: str, port: int, timeout: float) -> bool:
        """
        Sincroniza datos desde un nodo específico.

        Args:
            host: IP del nodo
            port: Puerto Flask del nodo
            timeout: Timeout de la request

        Returns:
            bool: True si la sincronización fue exitosa
        """
        url = f"http://{host}:{port}/api/cluster/full-sync"

        try:
            sync_logger.info(f"Fetching full sync from {url}")
            response = requests.get(url, timeout=timeout)

            if not response.ok:
                sync_logger.warning(f"Sync request failed: {response.status_code}")
                return False

            data = response.json()
            sync_data = data.get('data', {})

            # Aplicar datos en orden correcto (dependencias primero)
            with self.app.app_context():
                self._apply_sync_data(sync_data)

            self._synced = True
            self._sync_timestamp = datetime.now()

            sync_logger.info(f"Initial sync completed successfully from {host}:{port}")
            return True

        except requests.exceptions.Timeout:
            sync_logger.warning(f"Timeout syncing from {host}:{port}")
        except requests.exceptions.ConnectionError:
            sync_logger.warning(f"Connection error to {host}:{port}")
        except Exception as e:
            sync_logger.error(f"Error syncing from {host}:{port}: {e}")

        return False

    def _apply_sync_data(self, sync_data: Dict[str, List[Dict]]):
        """
        Aplica los datos sincronizados a la base de datos local.
        IMPORTANTE: Elimina datos de otras salas antes de insertar para garantizar consistencia.

        Args:
            sync_data: Diccionario con listas de entidades a sincronizar
        """
        from models import db, Sala, Doctor, Cama, Paciente, TrabajadorSocial, VisitaEmergencia, Consecutivo
        from config import Config

        my_sala_id = Config.NODE_ID
        sync_logger.info(f"[SYNC] Iniciando sincronización. Mi sala: {my_sala_id}")

        # =========================================================================
        # PASO 0: LIMPIAR datos de OTRAS salas (no la propia)
        # Esto garantiza que siempre tendremos los datos actuales
        # =========================================================================

        # Obtener IDs de salas que vienen en el sync (excluyendo la propia)
        salas_remotas = [s['id_sala'] for s in sync_data.get('salas', []) if s['id_sala'] != my_sala_id]

        if salas_remotas:
            sync_logger.info(f"[SYNC] Limpiando datos de salas remotas: {salas_remotas}")

            # Eliminar en orden inverso (por foreign keys)
            # 1. Visitas de otras salas
            deleted_visitas = VisitaEmergencia.query.filter(VisitaEmergencia.id_sala.in_(salas_remotas)).delete(synchronize_session='fetch')
            sync_logger.info(f"[SYNC] Eliminadas {deleted_visitas} visitas de otras salas")

            # 2. Consecutivos de otras salas
            deleted_cons = Consecutivo.query.filter(Consecutivo.id_sala.in_(salas_remotas)).delete(synchronize_session='fetch')
            sync_logger.info(f"[SYNC] Eliminados {deleted_cons} consecutivos de otras salas")

            # 3. Trabajadores de otras salas
            deleted_trab = TrabajadorSocial.query.filter(TrabajadorSocial.id_sala.in_(salas_remotas)).delete(synchronize_session='fetch')
            sync_logger.info(f"[SYNC] Eliminados {deleted_trab} trabajadores de otras salas")

            # 4. Camas de otras salas
            deleted_camas = Cama.query.filter(Cama.id_sala.in_(salas_remotas)).delete(synchronize_session='fetch')
            sync_logger.info(f"[SYNC] Eliminadas {deleted_camas} camas de otras salas")

            # 5. Doctores de otras salas
            deleted_docs = Doctor.query.filter(Doctor.id_sala.in_(salas_remotas)).delete(synchronize_session='fetch')
            sync_logger.info(f"[SYNC] Eliminados {deleted_docs} doctores de otras salas")

            db.session.flush()
            sync_logger.info(f"[SYNC] Limpieza completada, insertando datos nuevos...")

        # Orden de inserción (respetando foreign keys)
        # 1. Salas (sin dependencias)
        # 2. Doctores, Camas, Trabajadores (dependen de Sala)
        # 3. Pacientes (sin dependencias)
        # 4. Visitas (dependen de Paciente, Doctor, Cama, Sala)
        # 5. Consecutivos

        # 1. Sincronizar Salas (TODAS, incluida la propia para consistencia)
        salas = sync_data.get('salas', [])
        for sala_data in salas:
            existing = Sala.query.filter_by(id_sala=sala_data['id_sala']).first()
            # Fallback: si numero es None, usar id_sala
            numero_value = sala_data.get('numero') or sala_data['id_sala']

            if not existing:
                sala = Sala(
                    id_sala=sala_data['id_sala'],
                    numero=numero_value,
                    activa=sala_data.get('activa', True)
                )
                db.session.add(sala)
                sync_logger.debug(f"Added sala {sala_data['id_sala']}")
            elif existing.numero is None:
                # Actualizar numero si está NULL
                existing.numero = numero_value
                sync_logger.debug(f"Updated sala {sala_data['id_sala']} numero to {numero_value}")

        db.session.flush()

        # 2. Sincronizar Doctores
        doctores = sync_data.get('doctores', [])
        for doc_data in doctores:
            existing = Doctor.query.filter_by(id_doctor=doc_data['id_doctor']).first()
            if not existing:
                doctor = Doctor(
                    id_doctor=doc_data['id_doctor'],
                    nombre=doc_data['nombre'],
                    especialidad=doc_data.get('especialidad'),
                    disponible=doc_data.get('disponible', True),
                    activo=doc_data.get('activo', True),
                    id_sala=doc_data['id_sala']
                )
                db.session.add(doctor)
                sync_logger.debug(f"Added doctor {doc_data['id_doctor']}")

        # 3. Sincronizar Camas
        camas = sync_data.get('camas', [])
        for cama_data in camas:
            existing = Cama.query.filter_by(id_cama=cama_data['id_cama']).first()
            if not existing:
                cama = Cama(
                    id_cama=cama_data['id_cama'],
                    numero=cama_data['numero'],
                    ocupada=cama_data.get('ocupada', False),
                    id_sala=cama_data['id_sala'],
                    id_paciente=cama_data.get('id_paciente')
                )
                db.session.add(cama)
                sync_logger.debug(f"Added cama {cama_data['id_cama']}")

        # 4. Sincronizar Trabajadores Sociales
        trabajadores = sync_data.get('trabajadores', [])
        for trab_data in trabajadores:
            existing = TrabajadorSocial.query.filter_by(id_trabajador=trab_data['id_trabajador']).first()
            if not existing:
                trabajador = TrabajadorSocial(
                    id_trabajador=trab_data['id_trabajador'],
                    nombre=trab_data['nombre'],
                    activo=trab_data.get('activo', True),
                    id_sala=trab_data['id_sala']
                )
                db.session.add(trabajador)
                sync_logger.debug(f"Added trabajador {trab_data['id_trabajador']}")

        db.session.flush()

        # 5. Sincronizar Pacientes
        pacientes = sync_data.get('pacientes', [])
        for pac_data in pacientes:
            existing = Paciente.query.filter_by(id_paciente=pac_data['id_paciente']).first()
            if not existing:
                paciente = Paciente(
                    id_paciente=pac_data['id_paciente'],
                    nombre=pac_data['nombre'],
                    edad=pac_data.get('edad'),
                    sexo=pac_data.get('sexo'),
                    curp=pac_data.get('curp')
                )
                db.session.add(paciente)
                sync_logger.debug(f"Added paciente {pac_data['id_paciente']}")

        db.session.flush()

        # 6. Sincronizar Visitas
        visitas = sync_data.get('visitas', [])
        for vis_data in visitas:
            existing = VisitaEmergencia.query.filter_by(folio=vis_data['folio']).first()
            if not existing:
                visita = VisitaEmergencia(
                    folio=vis_data['folio'],
                    id_paciente=vis_data['id_paciente'],
                    id_doctor=vis_data.get('id_doctor'),
                    id_cama=vis_data.get('id_cama'),
                    id_sala=vis_data['id_sala'],
                    id_trabajador=vis_data.get('id_trabajador'),
                    sintomas=vis_data.get('sintomas'),
                    diagnostico=vis_data.get('diagnostico'),
                    estado=vis_data.get('estado', 'activa'),
                    timestamp=datetime.fromisoformat(vis_data['timestamp']) if vis_data.get('timestamp') else datetime.now(),
                    fecha_cierre=datetime.fromisoformat(vis_data['fecha_cierre']) if vis_data.get('fecha_cierre') else None
                )
                db.session.add(visita)
                sync_logger.debug(f"Added visita {vis_data['folio']}")

        # 7. Sincronizar Consecutivos (para mantener secuencia de folios)
        consecutivos = sync_data.get('consecutivos', [])
        for cons_data in consecutivos:
            # Consecutivo usa fecha + id_sala como clave
            fecha = datetime.fromisoformat(cons_data['fecha']).date() if cons_data.get('fecha') else datetime.now().date()
            existing = Consecutivo.query.filter_by(id_sala=cons_data['id_sala'], fecha=fecha).first()
            if existing:
                # Actualizar solo si el consecutivo remoto es mayor
                if cons_data.get('consecutivo', 0) > existing.consecutivo:
                    existing.consecutivo = cons_data['consecutivo']
                    sync_logger.debug(f"Updated consecutivo for sala {cons_data['id_sala']}")
            else:
                consecutivo = Consecutivo(
                    id_sala=cons_data['id_sala'],
                    fecha=fecha,
                    consecutivo=cons_data.get('consecutivo', 0)
                )
                db.session.add(consecutivo)
                sync_logger.debug(f"Added consecutivo for sala {cons_data['id_sala']}")

        # Commit final
        db.session.commit()

        sync_logger.info(f"Sync data applied: {len(salas)} salas, {len(doctores)} doctores, "
                        f"{len(camas)} camas, {len(pacientes)} pacientes, {len(visitas)} visitas")

    def propagate_to_cluster(self, entity_type: str, operation: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Propaga un cambio a todos los nodos del cluster.

        Args:
            entity_type: Tipo de entidad (sala, doctor, cama, paciente, visita, trabajador)
            operation: Operación (INSERT, UPDATE, DELETE)
            data: Datos de la entidad

        Returns:
            dict: Resultado con success_count, failed_nodes, total_nodes
        """
        if not self.bully_manager:
            return {'success_count': 0, 'failed_nodes': [], 'total_nodes': 0}

        from config import Config

        # Copia para evitar modificación durante iteración
        cluster_nodes = dict(self.bully_manager.cluster_nodes)
        success_count = 0
        failed_nodes = []

        for node_id, (host, tcp_port, udp_port) in cluster_nodes.items():
            if node_id == Config.NODE_ID:
                continue

            flask_port = 5000 + node_id % 1000

            try:
                # Usar endpoint específico para visitas
                if entity_type == 'visita' and operation == 'UPDATE':
                    url = f"http://{host}:{flask_port}/api/cluster/update-visit"
                    response = requests.put(url, json=data, timeout=3)
                else:
                    # Endpoint genérico para otras entidades
                    url = f"http://{host}:{flask_port}/api/cluster/replicate-entity"
                    payload = {
                        'type': entity_type,
                        'operation': operation,
                        'data': data
                    }
                    response = requests.post(url, json=payload, timeout=3)

                if response.ok:
                    success_count += 1
                    sync_logger.debug(f"Propagated {operation} {entity_type} to Node {node_id}")
                else:
                    failed_nodes.append(node_id)
                    sync_logger.warning(f"Node {node_id} rejected propagation: {response.status_code}")
            except Exception as e:
                failed_nodes.append(node_id)
                sync_logger.warning(f"Error propagating to Node {node_id}: {e}")

        total = len(cluster_nodes) - (1 if Config.NODE_ID in cluster_nodes else 0)

        return {
            'success_count': success_count,
            'failed_nodes': failed_nodes,
            'total_nodes': total
        }

    def check_and_resync_if_needed(self):
        """
        Verifica si hay cambios en el cluster y re-sincroniza si es necesario.
        Se llama periódicamente para detectar nodos nuevos o reiniciados.
        """
        if not self.bully_manager:
            return

        from config import Config

        # Obtener nodos actuales del cluster
        current_nodes = set(dict(self.bully_manager.cluster_nodes).keys())

        # Detectar cambios en el cluster
        new_nodes = current_nodes - self._known_nodes
        removed_nodes = self._known_nodes - current_nodes

        if new_nodes or removed_nodes:
            sync_logger.info(f"[SYNC-MONITOR] Cluster change detected!")
            if new_nodes:
                sync_logger.info(f"[SYNC-MONITOR] New nodes: {new_nodes}")
            if removed_nodes:
                sync_logger.info(f"[SYNC-MONITOR] Removed nodes: {removed_nodes}")

            # Re-sincronizar para obtener datos actualizados
            sync_logger.info(f"[SYNC-MONITOR] Triggering re-sync...")
            self._synced = False  # Permitir re-sincronización

            with self.app.app_context():
                self.perform_initial_sync(timeout=10.0)

    def start_periodic_sync(self, interval: int = 30):
        """
        Inicia un thread que monitorea cambios en el cluster periódicamente.

        Args:
            interval: Segundos entre cada verificación (default: 30)
        """
        def monitor_cluster():
            import time
            sync_logger.info(f"[SYNC-MONITOR] Started (checking every {interval}s)")
            while True:
                time.sleep(interval)
                try:
                    self.check_and_resync_if_needed()
                except Exception as e:
                    sync_logger.error(f"[SYNC-MONITOR] Error: {e}")

        monitor_thread = threading.Thread(target=monitor_cluster, daemon=True)
        monitor_thread.start()


# Singleton global para acceso fácil
_synchronizer: Optional[DataSynchronizer] = None


def get_synchronizer() -> Optional[DataSynchronizer]:
    """Obtiene la instancia global del sincronizador."""
    return _synchronizer


def init_synchronizer(flask_app, bully_manager=None) -> DataSynchronizer:
    """
    Inicializa el sincronizador global.

    Args:
        flask_app: Aplicación Flask
        bully_manager: Instancia de BullyNode (opcional)

    Returns:
        DataSynchronizer: Instancia del sincronizador
    """
    global _synchronizer
    _synchronizer = DataSynchronizer(flask_app, bully_manager)
    return _synchronizer
