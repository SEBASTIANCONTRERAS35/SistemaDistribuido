"""
Data Synchronization Module for Distributed Database.

Este módulo maneja la sincronización de datos entre nodos del cluster:
1. Sincronización inicial cuando un nodo se une al cluster
2. Propagación de cambios a otros nodos
3. Recuperación de datos de nodos existentes
"""

import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List, Any

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

    def set_bully_manager(self, bully_manager):
        """Asigna el BullyManager después de la inicialización."""
        self.bully_manager = bully_manager

    @property
    def is_synced(self) -> bool:
        """Retorna True si el nodo ya realizó sincronización inicial."""
        return self._synced

    def perform_initial_sync(self, timeout: float = 10.0) -> bool:
        """
        Realiza sincronización inicial desde el líder o cualquier nodo disponible.

        Args:
            timeout: Timeout para las requests HTTP

        Returns:
            bool: True si la sincronización fue exitosa
        """
        if not self.bully_manager:
            sync_logger.warning("No bully_manager configured, skipping sync")
            return False

        # Obtener nodos del cluster
        cluster_nodes = self.bully_manager.cluster_nodes
        if not cluster_nodes:
            sync_logger.info("No other nodes in cluster, nothing to sync")
            self._synced = True
            return True

        from config import Config

        # Intentar sincronizar con el líder primero
        leader_id = self.bully_manager.current_leader
        if leader_id and leader_id != Config.NODE_ID and leader_id in cluster_nodes:
            host, tcp_port, udp_port = cluster_nodes[leader_id]
            flask_port = 5000 + leader_id % 1000

            sync_logger.info(f"Attempting initial sync from leader (Node {leader_id})")
            if self._sync_from_node(host, flask_port, timeout):
                return True

        # Si no hay líder o falló, intentar con otros nodos
        for node_id, (host, tcp_port, udp_port) in cluster_nodes.items():
            if node_id == Config.NODE_ID:
                continue

            flask_port = 5000 + node_id % 1000
            sync_logger.info(f"Attempting initial sync from Node {node_id}")

            if self._sync_from_node(host, flask_port, timeout):
                return True

        sync_logger.warning("Could not sync from any node")
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

        Args:
            sync_data: Diccionario con listas de entidades a sincronizar
        """
        from models import db, Sala, Doctor, Cama, Paciente, TrabajadorSocial, VisitaEmergencia, Consecutivo
        from config import Config

        # Orden de inserción (respetando foreign keys)
        # 1. Salas (sin dependencias)
        # 2. Doctores, Camas, Trabajadores (dependen de Sala)
        # 3. Pacientes (sin dependencias)
        # 4. Visitas (dependen de Paciente, Doctor, Cama, Sala)
        # 5. Consecutivos

        # 1. Sincronizar Salas
        salas = sync_data.get('salas', [])
        for sala_data in salas:
            # No sincronizar nuestra propia sala
            if sala_data['id_sala'] == Config.NODE_ID:
                continue

            existing = Sala.query.filter_by(id_sala=sala_data['id_sala']).first()
            if not existing:
                sala = Sala(
                    id_sala=sala_data['id_sala'],
                    numero=sala_data.get('numero'),
                    activa=sala_data.get('activa', True)
                )
                db.session.add(sala)
                sync_logger.debug(f"Added sala {sala_data['id_sala']}")

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
                    sintomas=vis_data.get('sintomas'),
                    diagnostico=vis_data.get('diagnostico'),
                    tratamiento=vis_data.get('tratamiento'),
                    activa=vis_data.get('activa', True),
                    fecha_entrada=datetime.fromisoformat(vis_data['fecha_entrada']) if vis_data.get('fecha_entrada') else datetime.now(),
                    fecha_salida=datetime.fromisoformat(vis_data['fecha_salida']) if vis_data.get('fecha_salida') else None
                )
                db.session.add(visita)
                sync_logger.debug(f"Added visita {vis_data['folio']}")

        # 7. Sincronizar Consecutivos (para mantener secuencia de folios)
        consecutivos = sync_data.get('consecutivos', [])
        for cons_data in consecutivos:
            existing = Consecutivo.query.filter_by(id_sala=cons_data['id_sala']).first()
            if existing:
                # Actualizar solo si el consecutivo remoto es mayor
                if cons_data['ultimo_consecutivo'] > existing.ultimo_consecutivo:
                    existing.ultimo_consecutivo = cons_data['ultimo_consecutivo']
                    sync_logger.debug(f"Updated consecutivo for sala {cons_data['id_sala']}")
            else:
                consecutivo = Consecutivo(
                    id_sala=cons_data['id_sala'],
                    ultimo_consecutivo=cons_data['ultimo_consecutivo']
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

        cluster_nodes = self.bully_manager.cluster_nodes
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
