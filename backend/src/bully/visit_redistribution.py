"""
Visit Redistribution Module

Redistribuye visitas activas cuando un nodo/sala falla.
Solo el LIDER puede ejecutar redistribución para garantizar consistencia.

Requisito: "Si una SALA DE EMERGENCIAS tiene falla de sistema debe
redistribuir LAS VISITAS Y PACIENTES a las demás y actualizar la información."
"""

import logging
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class VisitRedistributor:
    """
    Redistribuye visitas cuando un nodo falla.

    Solo el LIDER ejecuta la redistribución para evitar conflictos.
    """

    def __init__(self, flask_app, bully_manager):
        """
        Args:
            flask_app: Aplicación Flask para contexto de BD
            bully_manager: Instancia de BullyNode para verificar liderazgo
        """
        self.flask_app = flask_app
        self.bully_manager = bully_manager

    def redistribute_visits_from_node(self, failed_node_id: int) -> Dict[str, Any]:
        """
        Redistribuye visitas activas del nodo/sala fallido.

        Solo el LÍDER puede ejecutar redistribución.

        Args:
            failed_node_id: ID del nodo que falló (también es id_sala)

        Returns:
            {
                'success': bool,
                'redistributed': int,
                'failed': int,
                'details': [...]
            }
        """
        logger.warning(f"")
        logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
        logger.warning(f"║  [REDISTRIBUTION] Iniciando redistribución                   ║")
        logger.warning(f"║  Nodo/Sala fallido: {failed_node_id}                                         ║")
        logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

        # 1. Verificar que soy el líder
        if not self._am_i_leader():
            logger.warning(f"[REDISTRIBUTION] No soy líder, ignorando redistribución")
            return {'success': False, 'error': 'Not leader', 'redistributed': 0, 'failed': 0}

        with self.flask_app.app_context():
            # 2. Buscar visitas activas de la sala fallida
            visitas = self._get_active_visits_for_sala(failed_node_id)

            if not visitas:
                logger.info(f"[REDISTRIBUTION] No hay visitas activas en sala {failed_node_id}")
                return {'success': True, 'redistributed': 0, 'failed': 0, 'details': []}

            logger.warning(f"[REDISTRIBUTION] Encontradas {len(visitas)} visitas activas para redistribuir")

            redistributed = 0
            failed = 0
            details = []

            # 3. Para cada visita, reasignar a otra sala
            for visita in visitas:
                result = self._redistribute_single_visit(visita, failed_node_id)

                if result['success']:
                    redistributed += 1
                    details.append({
                        'folio': visita.folio,
                        'nueva_sala': result['nueva_sala'],
                        'nuevo_doctor': result['nuevo_doctor'],
                        'nueva_cama': result['nueva_cama']
                    })
                    logger.warning(f"[REDISTRIBUTION] ✓ {visita.folio} → Sala {result['nueva_sala']}, "
                                 f"Doctor {result['nuevo_doctor']}, Cama {result['nueva_cama']}")
                else:
                    failed += 1
                    details.append({
                        'folio': visita.folio,
                        'error': result['error']
                    })
                    logger.error(f"[REDISTRIBUTION] ✗ {visita.folio} - Error: {result['error']}")

            logger.warning(f"")
            logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
            logger.warning(f"║  [REDISTRIBUTION] Completado                                 ║")
            logger.warning(f"║  Redistribuidas: {redistributed}                                          ║")
            logger.warning(f"║  Fallidas: {failed}                                               ║")
            logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

            return {
                'success': True,
                'redistributed': redistributed,
                'failed': failed,
                'details': details
            }

    def _am_i_leader(self) -> bool:
        """Verifica si este nodo es el líder actual."""
        from bully.bully_node import NodeState
        return self.bully_manager.state == NodeState.LEADER

    def _get_active_visits_for_sala(self, sala_id: int) -> List:
        """Obtiene visitas activas de una sala específica."""
        from models import VisitaEmergencia
        return VisitaEmergencia.query.filter_by(
            id_sala=sala_id,
            estado='activa'
        ).all()

    def _redistribute_single_visit(self, visita, failed_sala_id: int) -> Dict[str, Any]:
        """
        Redistribuye una sola visita a otra sala.

        Args:
            visita: Objeto VisitaEmergencia
            failed_sala_id: ID de la sala que falló

        Returns:
            {'success': bool, 'nueva_sala': int, 'nuevo_doctor': int, 'nueva_cama': int}
            o {'success': False, 'error': str}
        """
        from models import db, Doctor, Cama, Sala, VisitaEmergencia

        try:
            # 1. Encontrar sala destino con recursos disponibles
            nueva_sala_id = self._find_best_sala_for_redistribution(exclude_sala=failed_sala_id)

            if not nueva_sala_id:
                return {'success': False, 'error': 'No hay salas disponibles con recursos'}

            # 2. Encontrar doctor disponible en nueva sala
            nuevo_doctor = self._find_available_doctor(nueva_sala_id)

            if not nuevo_doctor:
                return {'success': False, 'error': f'No hay doctores disponibles en sala {nueva_sala_id}'}

            # 3. Encontrar cama disponible en nueva sala
            nueva_cama = self._find_available_cama(nueva_sala_id)

            if not nueva_cama:
                return {'success': False, 'error': f'No hay camas disponibles en sala {nueva_sala_id}'}

            # 4. Liberar recursos antiguos (de la sala fallida)
            old_doctor = Doctor.query.get(visita.id_doctor)
            old_cama = Cama.query.get(visita.id_cama)

            if old_doctor:
                old_doctor.disponible = True
            if old_cama:
                old_cama.ocupada = False
                old_cama.id_paciente = None

            # 5. Asignar nuevos recursos
            nuevo_doctor.disponible = False
            nueva_cama.ocupada = True
            nueva_cama.id_paciente = visita.id_paciente

            # 6. Actualizar visita
            old_folio = visita.folio
            visita.id_sala = nueva_sala_id
            visita.id_doctor = nuevo_doctor.id_doctor
            visita.id_cama = nueva_cama.id_cama

            # Regenerar folio con nueva información
            # Formato: P{id_paciente}-D{id_doctor}-S{id_sala}-{consecutivo}
            # Mantenemos el consecutivo original para trazabilidad
            old_parts = old_folio.split('-')
            if len(old_parts) >= 4:
                consecutivo = old_parts[-1]  # Mantener consecutivo original
            else:
                consecutivo = '0000'

            visita.folio = f"P{visita.id_paciente}-D{nuevo_doctor.id_doctor}-S{nueva_sala_id}-{consecutivo}"

            db.session.commit()

            logger.info(f"[REDISTRIBUTION] Visita {old_folio} redistribuida a {visita.folio}")

            return {
                'success': True,
                'nueva_sala': nueva_sala_id,
                'nuevo_doctor': nuevo_doctor.id_doctor,
                'nueva_cama': nueva_cama.id_cama,
                'nuevo_folio': visita.folio
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"[REDISTRIBUTION] Error redistribuyendo visita {visita.folio}: {e}")
            return {'success': False, 'error': str(e)}

    def _find_best_sala_for_redistribution(self, exclude_sala: int = None) -> Optional[int]:
        """
        Encuentra la mejor sala para redistribuir visitas.

        Criterio: Sala con menos visitas activas Y recursos disponibles.

        Args:
            exclude_sala: ID de sala a excluir (la fallida)

        Returns:
            int: ID de la mejor sala, o None si no hay disponible
        """
        from models import Sala, Doctor, Cama, VisitaEmergencia

        salas_stats = []

        for sala in Sala.query.filter_by(activa=True).all():
            # Excluir la sala fallida
            if sala.id_sala == exclude_sala:
                continue

            visitas_activas = VisitaEmergencia.query.filter_by(
                id_sala=sala.id_sala, estado='activa'
            ).count()

            camas_libres = Cama.query.filter_by(
                id_sala=sala.id_sala, ocupada=False
            ).count()

            doctores_libres = Doctor.query.filter_by(
                id_sala=sala.id_sala, disponible=True, activo=True
            ).count()

            # Solo considerar salas con recursos disponibles
            if camas_libres > 0 and doctores_libres > 0:
                salas_stats.append({
                    'id_sala': sala.id_sala,
                    'visitas_activas': visitas_activas,
                    'camas_libres': camas_libres,
                    'doctores_libres': doctores_libres
                })

        if not salas_stats:
            return None

        # Ordenar por: menos visitas activas, más camas libres
        salas_stats.sort(key=lambda x: (x['visitas_activas'], -x['camas_libres']))

        return salas_stats[0]['id_sala']

    def _find_available_doctor(self, sala_id: int) -> Optional['Doctor']:
        """Encuentra un doctor disponible en la sala especificada."""
        from models import Doctor
        return Doctor.query.filter_by(
            id_sala=sala_id,
            disponible=True,
            activo=True
        ).first()

    def _find_available_cama(self, sala_id: int) -> Optional['Cama']:
        """Encuentra una cama disponible en la sala especificada."""
        from models import Cama
        return Cama.query.filter_by(
            id_sala=sala_id,
            ocupada=False
        ).first()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ['VisitRedistributor']
