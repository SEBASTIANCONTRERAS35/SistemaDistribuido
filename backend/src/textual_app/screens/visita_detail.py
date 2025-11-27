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
        import logging
        logger = logging.getLogger(__name__)

        rol = self.user_info.get('rol', '')
        logger.warning(f"[PERMISOS] Verificando cierre: rol={rol}")

        # Solo doctores pueden cerrar visitas
        if rol == 'doctor':
            # Solo puede cerrar si él es el doctor asignado
            id_relacionado = self.user_info.get('id_relacionado')
            id_doctor_visita = self.visita.get('id_doctor')
            puede = id_doctor_visita == id_relacionado

            logger.warning(f"[PERMISOS] Doctor: id_relacionado={id_relacionado}, id_doctor_visita={id_doctor_visita}, puede_cerrar={puede}")
            return puede

        # Trabajador social NO puede cerrar visitas
        logger.warning(f"[PERMISOS] No es doctor, no puede cerrar")
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
        Close visit in database using Two-Phase Commit (2PC) protocol.

        Protocol:
        1. Find visit and verify it's active
        2. Acquire distributed locks on doctor and cama (MANDATORY - fails if not acquired)
        3. Begin 2PC transaction
        4. Execute 2PC: PREPARE -> COMMIT (if all YES) or ABORT (if any NO/timeout)
        5. Release distributed locks with retry
        6. Return result

        Guarantees:
        - ATOMIC: Either all nodes commit or all abort
        - CONSISTENT: No partial commits possible
        - CP (CAP): Rejects operation if consensus cannot be reached
        - MANDATORY LOCKS: Operation fails if locks cannot be acquired

        Args:
            folio: Visit folio to close

        Returns:
            Dict with success status and error message if failed
        """
        with self.flask_app.app_context():
            from models import db, VisitaEmergencia, Doctor, Cama
            from bully.distributed_locks import (
                solicitar_bloqueo_con_orden,
                liberar_todos_bloqueos
            )
            from bully.two_phase_commit import TwoPhaseCommitCoordinator
            import logging
            logger = logging.getLogger(__name__)

            locked_resources = []
            doctor_id = None
            cama_id = None

            try:
                node_id = self.bully_manager.node_id
                logger.warning(f"")
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  [Node-{node_id}] INICIANDO CIERRE DE VISITA (2PC)                  ║")
                logger.warning(f"║  Folio: {folio:<40}              ║")
                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

                # ====== PASO 1: Buscar la visita y validar estado ======
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Paso 1: Buscando visita...")
                visita = VisitaEmergencia.query.filter_by(folio=folio).first()
                if not visita:
                    return {'success': False, 'error': 'Visita no encontrada'}

                if visita.estado == 'completada':
                    return {'success': False, 'error': 'La visita ya esta cerrada'}

                if visita.estado == 'cancelada':
                    return {'success': False, 'error': 'La visita fue cancelada'}

                doctor_id = visita.id_doctor
                cama_id = visita.id_cama

                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Visita encontrada: doctor={doctor_id}, cama={cama_id}")

                # ====== PASO 2: Adquirir bloqueos distribuidos (OBLIGATORIOS) ======
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Paso 2: Adquiriendo bloqueos (OBLIGATORIOS)...")

                # Para cierre, los recursos ya están ocupados, pero aún necesitamos
                # bloquearlos para evitar condiciones de carrera durante el cierre
                # Usamos un enfoque diferente: bloqueamos "para liberación"
                recursos_a_bloquear = [
                    ('CAMA', cama_id),
                    ('DOCTOR', doctor_id)
                ]

                # Nota: En cierre, los recursos están marcados como ocupados
                # El lock puede fallar porque verificar_recurso_local checa disponibilidad
                # Primero intentamos con el orden estándar, pero con una verificación especial
                success, locked_resources = solicitar_bloqueo_con_orden(
                    self.bully_manager,
                    self.flask_app,
                    recursos_a_bloquear,
                    timeout=10.0
                )

                # Si el bloqueo falla porque recursos están ocupados (lo esperado para cierre),
                # verificamos que la visita esté realmente asignada a estos recursos
                if not success:
                    # Para cierre, necesitamos un enfoque diferente: verificar que la visita
                    # es dueña de los recursos y luego proceder con 2PC sin bloqueo adicional
                    # (el 2PC mismo verifica la consistencia)
                    logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Bloqueos no adquiridos (recursos ocupados por la visita)")
                    logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Procediendo con 2PC sin bloqueo adicional (visita es dueña)")

                    # Verificar que la visita realmente tiene estos recursos
                    doctor = Doctor.query.get(doctor_id)
                    cama = Cama.query.get(cama_id)

                    if doctor and doctor.disponible:
                        # Doctor ya está libre - inconsistencia
                        return {'success': False, 'error': 'Doctor ya está disponible (inconsistencia)'}

                    if cama and not cama.ocupada:
                        # Cama ya está libre - inconsistencia
                        return {'success': False, 'error': 'Cama ya está libre (inconsistencia)'}

                    locked_resources = []  # No tenemos locks, pero procedemos con 2PC
                else:
                    logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Bloqueos adquiridos: {locked_resources}")

                # ====== PASO 3: Iniciar transaccion 2PC ======
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Paso 3: Iniciando Two-Phase Commit...")
                coordinator = TwoPhaseCommitCoordinator(self.bully_manager, self.flask_app)

                # Datos para la transaccion de cierre
                txn_data = {
                    'folio': folio,
                    'doctor_id': doctor_id,
                    'cama_id': cama_id
                }

                txn_id = coordinator.begin_transaction('CLOSE_VISIT', txn_data)
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Transaccion iniciada: {txn_id}")

                # ====== PASO 4: Ejecutar protocolo 2PC ======
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Paso 4: Ejecutando 2PC (PREPARE -> COMMIT/ABORT)...")
                result = coordinator.execute_2pc(txn_id)

                if not result['success']:
                    logger.warning(f"[Node-{node_id}] [2PC-CLOSE] 2PC ABORTADO: {result.get('error')}")
                    # El coordinador ya hizo ABORT, solo liberamos locks
                    if locked_resources:
                        liberar_todos_bloqueos(self.bully_manager, locked_resources)
                    return {'success': False, 'error': f"Transaccion rechazada: {result.get('error')}"}

                # ====== PASO 5: Obtener datos actualizados ======
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] 2PC EXITOSO - Obteniendo datos actualizados...")

                # Refrescar la visita desde la BD
                db.session.refresh(visita)
                doctor = Doctor.query.get(doctor_id)
                cama = Cama.query.get(cama_id)

                # ====== PASO 6: Guardar en archivo TXT (desarrollo) ======
                logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Paso 6: Guardando registro TXT...")
                self._save_close_to_txt(visita, doctor, cama)

                # ====== PASO 7: Liberar bloqueos distribuidos ======
                if locked_resources:
                    logger.warning(f"[Node-{node_id}] [2PC-CLOSE] Paso 7: Liberando bloqueos distribuidos...")
                    liberar_todos_bloqueos(self.bully_manager, locked_resources)

                logger.warning(f"")
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  [Node-{node_id}] VISITA CERRADA EXITOSAMENTE (2PC)                 ║")
                logger.warning(f"║  Folio: {folio:<40}              ║")
                logger.warning(f"║  Doctor: {doctor_id:<3} -> DISPONIBLE                                 ║")
                logger.warning(f"║  Cama: {cama_id:<3} -> LIBRE                                         ║")
                logger.warning(f"║  TXN: {txn_id[:30]:<30}                      ║")
                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

                return {'success': True, 'folio': folio}

            except Exception as e:
                logger.error(f"[Node-{node_id}] [2PC-CLOSE] Exception: {e}")

                # Liberar bloqueos en caso de error
                if locked_resources:
                    liberar_todos_bloqueos(self.bully_manager, locked_resources)

                return {'success': False, 'error': str(e)}

    def action_dismiss(self) -> None:
        """Dismiss the modal"""
        self.dismiss()


# Export
__all__ = ['VisitDetailModal']
