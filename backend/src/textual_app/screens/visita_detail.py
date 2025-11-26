"""
Visit Detail Modal - Shows detailed information about a visit
With distributed lock support for closing visits.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label
from textual.containers import Container, Vertical, Horizontal, Grid
from textual.binding import Binding
from textual import work
from rich.text import Text
from rich.panel import Panel


class VisitDetailModal(ModalScreen):
    """Modal screen to show detailed visit information"""

    BINDINGS = [
        Binding("escape", "dismiss", "Cerrar", show=True),
    ]

    CSS = """
    VisitDetailModal {
        align: center middle;
    }

    #detail-container {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #detail-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        padding-bottom: 1;
        border-bottom: solid $border;
        margin-bottom: 1;
    }

    .detail-section {
        margin: 1 0;
        padding: 1;
        background: $panel;
        border: solid $border;
    }

    .section-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        color: $text-secondary;
        width: 20;
    }

    .field-value {
        color: $text;
        text-style: bold;
        min-width: 20;
    }

    .field-row {
        height: auto;
        margin: 0 0 1 0;
    }

    #button-container {
        align: center middle;
        margin-top: 2;
    }

    #close-btn {
        margin: 0 1;
    }

    #cerrar-visita-btn {
        margin: 0 1;
    }

    .estado-badge {
        padding: 0 2;
        text-align: center;
    }

    .estado-activa {
        background: $success;
        color: $surface;
        text-style: bold;
    }

    .estado-completada {
        background: $panel;
        color: $text;
    }

    .estado-cancelada {
        background: $error;
        color: $surface;
        text-style: bold;
    }
    """

    def __init__(self, visita: Dict[str, Any], flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.visita = visita
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}

        # DEBUG: Log visita data
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[DETALLE-MODAL] Inicializando modal con visita: {visita.get('folio')}")
        logger.warning(f"[DETALLE-MODAL] Keys en visita dict: {list(visita.keys())}")
        logger.warning(f"[DETALLE-MODAL] paciente={repr(visita.get('paciente'))}")
        logger.warning(f"[DETALLE-MODAL] doctor={repr(visita.get('doctor'))}")
        logger.warning(f"[DETALLE-MODAL] sala={repr(visita.get('sala'))}")
        logger.warning(f"[DETALLE-MODAL] cama={repr(visita.get('cama'))}")

    def _puede_cerrar_visita(self) -> bool:
        """Determina si el usuario actual puede cerrar esta visita.
        Segun requisitos: SOLO DOCTORES pueden cerrar visitas, y solo las suyas.
        """
        rol = self.user_info.get('rol', '')

        # Solo doctores pueden cerrar visitas
        if rol == 'doctor':
            # Solo puede cerrar si él es el doctor asignado
            id_relacionado = self.user_info.get('id_relacionado')
            return self.visita.get('id_doctor') == id_relacionado

        # Trabajador social NO puede cerrar visitas
        return False

    def _save_close_to_txt(self, visita, doctor, cama):
        """Guarda el cierre de visita en archivo TXT para desarrollo"""
        import os
        from datetime import datetime
        from config import Config

        # Crear directorio si no existe
        txt_dir = os.path.join(os.path.dirname(__file__), '../../..', 'data', 'visitas_txt')
        os.makedirs(txt_dir, exist_ok=True)

        # Archivo del nodo actual
        node_id = Config.NODE_ID or 1
        filename = f"visitas_node_{node_id}.txt"
        filepath = os.path.join(txt_dir, filename)

        # Formatear información
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write(f"VISITA CERRADA - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 70 + "\n")
            f.write(f"Folio: {visita.folio}\n")
            f.write(f"Estado: COMPLETADA\n")
            f.write(f"Fecha cierre: {visita.fecha_cierre}\n")
            f.write(f"\n--- RECURSOS LIBERADOS ---\n")
            f.write(f"Doctor: {doctor.nombre if doctor else 'N/A'} - DISPONIBLE\n")
            f.write(f"Cama: #{cama.numero if cama else 'N/A'} - LIBRE\n")
            f.write(f"\n--- USUARIO ---\n")
            f.write(f"Cerrado por: {self.username}\n")
            f.write(f"Nodo: {node_id}\n")
            f.write("\n\n")

    def compose(self) -> ComposeResult:
        """Compose the detail modal UI"""
        import logging
        logger = logging.getLogger(__name__)

        # Extraer valores para logging
        paciente_nombre = self.visita.get('paciente', 'N/A')
        doctor_nombre = self.visita.get('doctor', 'N/A')
        sala_num = str(self.visita.get('sala', 'N/A'))
        cama_num = str(self.visita.get('cama', 'N/A'))

        logger.warning(f"[COMPOSE] Creando Labels con: paciente='{paciente_nombre}', doctor='{doctor_nombre}', sala='{sala_num}', cama='{cama_num}'")

        with Container(id="detail-container"):
            # Title
            yield Label(
                f"📋 DETALLE DE VISITA: {self.visita.get('folio', 'N/A')}",
                id="detail-title"
            )

            # Patient section
            with Vertical(classes="detail-section"):
                yield Label("👤 INFORMACIÓN DEL PACIENTE", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Nombre:", classes="field-label")
                    yield Static(paciente_nombre, classes="field-value")

            # Medical staff section
            with Vertical(classes="detail-section"):
                yield Label("👨‍⚕️ PERSONAL MÉDICO", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Doctor asignado:", classes="field-label")
                    yield Static(doctor_nombre, classes="field-value")

            # Location section
            with Vertical(classes="detail-section"):
                yield Label("🏥 UBICACIÓN", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Sala:", classes="field-label")
                    yield Static(sala_num, classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Cama:", classes="field-label")
                    yield Static(cama_num, classes="field-value")

            # Clinical info section
            with Vertical(classes="detail-section"):
                yield Label("📝 INFORMACIÓN CLÍNICA", classes="section-title")

                # Estado with color badge
                estado = self.visita.get('estado', 'desconocido')
                estado_classes = f"estado-badge estado-{estado}"

                with Horizontal(classes="field-row"):
                    yield Label("Estado:", classes="field-label")
                    yield Label(estado.upper(), classes=estado_classes)

                # Timestamps
                timestamp = self.visita.get('timestamp', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp_formatted = dt.strftime('%d/%m/%Y %H:%M:%S')
                    except:
                        timestamp_formatted = timestamp
                else:
                    timestamp_formatted = 'N/A'

                with Horizontal(classes="field-row"):
                    yield Label("Fecha de ingreso:", classes="field-label")
                    yield Static(timestamp_formatted, classes="field-value")

                # Fecha cierre (if exists)
                fecha_cierre = self.visita.get('fecha_cierre', '')
                if fecha_cierre:
                    try:
                        dt = datetime.fromisoformat(fecha_cierre.replace('Z', '+00:00'))
                        cierre_formatted = dt.strftime('%d/%m/%Y %H:%M:%S')
                    except:
                        cierre_formatted = fecha_cierre

                    with Horizontal(classes="field-row"):
                        yield Label("Fecha de cierre:", classes="field-label")
                        yield Static(cierre_formatted, classes="field-value")

                # Sintomas
                with Horizontal(classes="field-row"):
                    yield Label("Síntomas:", classes="field-label")
                    yield Static(self.visita.get('sintomas', 'N/A'), classes="field-value")

                # Diagnostico (si existe)
                diagnostico = self.visita.get('diagnostico')
                if diagnostico:
                    with Horizontal(classes="field-row"):
                        yield Label("Diagnóstico:", classes="field-label")
                        yield Static(diagnostico, classes="field-value")

            # Buttons
            with Horizontal(id="button-container"):
                # Show "Cerrar Visita" button only if visit is active AND user has permission
                if self.visita.get('estado') == 'activa' and self._puede_cerrar_visita():
                    yield Button(
                        "🩺 Cerrar Visita",
                        variant="success",
                        id="cerrar-visita-btn"
                    )

                yield Button("← Volver", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "close-btn":
            self.dismiss()
        elif event.button.id == "cerrar-visita-btn":
            self.action_cerrar_visita()

    @work(exclusive=True)
    async def action_cerrar_visita(self) -> None:
        """
        Close the visit with distributed locks.

        Protocol:
        1. Verify user has permission to close
        2. Acquire distributed locks on doctor and cama
        3. Release resources in local DB
        4. Mark visit as completed
        5. Replicate to cluster via consensus
        6. Release distributed locks
        """
        # Doble validación de permisos
        if not self._puede_cerrar_visita():
            self.notify("❌ No tienes permiso para cerrar esta visita", severity="error")
            return

        folio = self.visita.get('folio')
        if not folio:
            self.notify("Error: No se encontro el folio", severity="error")
            return

        self.notify("Cerrando visita...", severity="information")

        try:
            result = await asyncio.to_thread(
                self._cerrar_visita_db,
                folio
            )

            if result['success']:
                self.notify(
                    f"Visita {folio} cerrada exitosamente",
                    title="Visita Cerrada",
                    severity="information",
                    timeout=3
                )
                # Dismiss with result to refresh parent
                self.dismiss({'action': 'closed', 'folio': folio})
            else:
                self.notify(
                    f"Error: {result['error']}",
                    severity="error",
                    timeout=5
                )

        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")

    def _cerrar_visita_db(self, folio: str) -> Dict[str, Any]:
        """
        Close visit in database with distributed locks.

        Args:
            folio: Visit folio to close

        Returns:
            Dict with success status and error message if failed
        """
        with self.flask_app.app_context():
            from models import db, VisitaEmergencia, Doctor, Cama
            from bully.distributed_locks import (
                solicitar_bloqueo_distribuido,
                liberar_bloqueo_distribuido,
                replicar_liberacion_con_consenso
            )
            import logging
            logger = logging.getLogger(__name__)

            doctor_locked = False
            cama_locked = False
            doctor_id = None
            cama_id = None

            try:
                # 1. Find the visit
                visita = VisitaEmergencia.query.filter_by(folio=folio).first()
                if not visita:
                    return {'success': False, 'error': 'Visita no encontrada'}

                if visita.estado == 'completada':
                    return {'success': False, 'error': 'La visita ya esta cerrada'}

                doctor_id = visita.id_doctor
                cama_id = visita.id_cama

                logger.info(f"[VISIT-CLOSE] Closing visit {folio}: doctor={doctor_id}, cama={cama_id}")

                # 2. Acquire distributed lock on doctor
                # Note: For closing, we need to lock resources that are currently OCCUPIED
                # The verification function checks availability, so we skip it for closing
                logger.info(f"[VISIT-CLOSE] Attempting to lock doctor {doctor_id}")
                if solicitar_bloqueo_distribuido(
                    self.bully_manager,
                    self.flask_app,
                    'DOCTOR',
                    doctor_id
                ):
                    doctor_locked = True
                    logger.info(f"[VISIT-CLOSE] Doctor {doctor_id} locked")
                else:
                    # For closing, we proceed even if lock fails (resource might be marked occupied)
                    logger.warning(f"[VISIT-CLOSE] Could not lock doctor {doctor_id}, proceeding anyway")

                # 3. Acquire distributed lock on cama
                logger.info(f"[VISIT-CLOSE] Attempting to lock cama {cama_id}")
                if solicitar_bloqueo_distribuido(
                    self.bully_manager,
                    self.flask_app,
                    'CAMA',
                    cama_id
                ):
                    cama_locked = True
                    logger.info(f"[VISIT-CLOSE] Cama {cama_id} locked")
                else:
                    logger.warning(f"[VISIT-CLOSE] Could not lock cama {cama_id}, proceeding anyway")

                # 4. Release resources in local DB
                doctor = Doctor.query.get(doctor_id)
                cama = Cama.query.get(cama_id)

                if doctor:
                    doctor.disponible = True
                    logger.info(f"[VISIT-CLOSE] Doctor {doctor_id} marked as available")

                if cama:
                    cama.ocupada = False
                    cama.id_paciente = None
                    logger.info(f"[VISIT-CLOSE] Cama {cama_id} marked as free")

                # 5. Close visit
                visita.estado = 'completada'
                visita.fecha_cierre = datetime.utcnow()

                db.session.commit()
                logger.info(f"[VISIT-CLOSE] Visit {folio} closed locally")

                # 5.5. Guardar cierre en archivo TXT (solo desarrollo)
                self._save_close_to_txt(visita, doctor, cama)

                # 6. Replicate resource release to other nodes (consensus)
                logger.info(f"[VISIT-CLOSE] Replicating resource release to cluster...")
                replicar_liberacion_con_consenso(
                    self.bully_manager,
                    self.flask_app,
                    doctor_id,
                    cama_id
                )

                # 7. Release distributed locks
                if doctor_locked:
                    liberar_bloqueo_distribuido(self.bully_manager, 'DOCTOR', doctor_id)
                if cama_locked:
                    liberar_bloqueo_distribuido(self.bully_manager, 'CAMA', cama_id)

                logger.info(f"[VISIT-CLOSE] Visit closure complete: {folio}")

                return {'success': True, 'folio': folio}

            except Exception as e:
                db.session.rollback()
                logger.error(f"[VISIT-CLOSE] Error closing visit: {e}")

                # Clean up locks on error
                if doctor_locked and doctor_id:
                    liberar_bloqueo_distribuido(self.bully_manager, 'DOCTOR', doctor_id)
                if cama_locked and cama_id:
                    liberar_bloqueo_distribuido(self.bully_manager, 'CAMA', cama_id)

                return {'success': False, 'error': str(e)}

    def action_dismiss(self) -> None:
        """Dismiss the modal"""
        self.dismiss()


# Export
__all__ = ['VisitDetailModal']
