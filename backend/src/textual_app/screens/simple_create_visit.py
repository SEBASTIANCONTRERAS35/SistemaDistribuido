"""
Simple Create Visit Screen - Simplified version for creating emergency visits
"""

import asyncio
from typing import Dict, Any
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Label, Select
from textual.containers import Container, Vertical, Horizontal
from textual import work
from textual.binding import Binding


class SimpleCreateVisitScreen(ModalScreen):
    """Simplified screen for creating emergency visits"""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancelar", show=True),
        Binding("down", "focus_next", "↓ Siguiente", show=False),
        Binding("up", "focus_previous", "↑ Anterior", show=False),
        Binding("left", "focus_previous", "←", show=False),
        Binding("right", "focus_next", "→", show=False),
    ]

    CSS = """
    SimpleCreateVisitScreen {
        align: center middle;
    }

    #visit-container {
        width: 90;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #visit-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        padding-bottom: 1;
        border-bottom: solid $border;
        margin-bottom: 1;
    }

    .form-label {
        color: $text-secondary;
        padding: 1 0 0 0;
    }

    /* NOTE: Textual CSS doesn't support ::after pseudo-elements
     * Required fields should have asterisk in label text directly */
    .form-label-required {
        color: $error;
    }

    Input {
        margin: 0 0 1 0;
    }

    Select {
        margin: 0 0 1 0;
    }

    #button-container {
        align: center middle;
        margin-top: 2;
    }

    Button {
        margin: 0 1;
    }

    #error-message {
        color: $error;
        text-style: bold;
        text-align: center;
        margin: 1 0;
        min-height: 1;
    }
    """

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}

    def _save_visit_to_txt(self, visita, paciente, doctor, cama, sala_id, node_id):
        """Guarda la visita en archivo TXT para desarrollo"""
        import os
        from datetime import datetime

        # Crear directorio si no existe
        txt_dir = os.path.join(os.path.dirname(__file__), '../../..', 'data', 'visitas_txt')
        os.makedirs(txt_dir, exist_ok=True)

        # Archivo con timestamp
        filename = f"visitas_node_{node_id}.txt"
        filepath = os.path.join(txt_dir, filename)

        # Formatear información
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write(f"VISITA DE EMERGENCIA - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 70 + "\n")
            f.write(f"Folio: {visita.folio}\n")
            f.write(f"ID Visita: {visita.id_visita}\n")
            f.write(f"Estado: {visita.estado.upper()}\n")
            f.write(f"\n--- PACIENTE ---\n")
            f.write(f"ID: {paciente.id_paciente}\n")
            f.write(f"Nombre: {paciente.nombre}\n")
            f.write(f"Edad: {paciente.edad} años\n")
            f.write(f"Sexo: {paciente.sexo}\n")
            f.write(f"CURP: {paciente.curp or 'N/A'}\n")
            f.write(f"\n--- ASIGNACIÓN ---\n")
            f.write(f"Sala: {sala_id}\n")
            f.write(f"Doctor: {doctor.nombre} ({doctor.especialidad})\n")
            f.write(f"Cama: #{cama.numero}\n")
            f.write(f"\n--- CLÍNICO ---\n")
            f.write(f"Síntomas: {visita.sintomas}\n")
            f.write(f"Diagnóstico: {visita.diagnostico or '(pendiente)'}\n")
            f.write(f"\n--- METADATA ---\n")
            f.write(f"Nodo creador: {node_id}\n")
            f.write(f"Usuario: {self.username}\n")
            f.write(f"Timestamp: {visita.timestamp}\n")
            f.write("\n\n")

    def compose(self) -> ComposeResult:
        """Compose the create visit form"""
        with Container(id="visit-container"):
            yield Label("🏥 NUEVA VISITA DE EMERGENCIA", id="visit-title")

            # Patient Information
            yield Label("DATOS DEL PACIENTE", classes="form-label-required")
            yield Input(placeholder="Nombre completo", id="input-nombre")

            yield Label("Edad *", classes="form-label")
            yield Input(placeholder="Edad (años)", id="input-edad")

            yield Label("Sexo *", classes="form-label")
            yield Select(
                options=[
                    ("Masculino", "M"),
                    ("Femenino", "F"),
                ],
                prompt="Seleccione sexo",
                id="select-sexo",
                allow_blank=False
            )

            yield Label("CURP (opcional)", classes="form-label")
            yield Input(placeholder="CURP", id="input-curp")

            # Symptoms
            yield Label("Síntomas *", classes="form-label")
            yield Input(placeholder="Describa los síntomas", id="input-sintomas")

            # Error message
            yield Static("", id="error-message")

            # Buttons
            with Horizontal(id="button-container"):
                yield Button("✓ Crear Visita", variant="success", id="btn-create")
                yield Button("Cancelar", variant="error", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "btn-create":
            self.create_visit()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter en último campo crea visita, otros campos avanzan"""
        if event.input.id == "input-sintomas":
            self.create_visit()
        else:
            self.action_focus_next()

    @work(exclusive=True)
    async def create_visit(self) -> None:
        """Create the emergency visit - only for trabajador_social"""
        # Verificar permisos (doble validación)
        if self.user_info.get('rol') != 'trabajador_social':
            error_widget = self.query_one("#error-message", Static)
            error_widget.update("❌ No tienes permiso para crear visitas")
            return

        # Get form values
        nombre = self.query_one("#input-nombre", Input).value.strip()
        edad = self.query_one("#input-edad", Input).value.strip()
        sexo = self.query_one("#select-sexo", Select).value
        curp = self.query_one("#input-curp", Input).value.strip()
        sintomas = self.query_one("#input-sintomas", Input).value.strip()

        error_widget = self.query_one("#error-message", Static)

        # Validate
        if not nombre:
            error_widget.update("❌ El nombre es requerido")
            return

        if not edad:
            error_widget.update("❌ La edad es requerida")
            return

        try:
            edad_int = int(edad)
            if edad_int < 0 or edad_int > 150:
                error_widget.update("❌ Edad inválida (0-150)")
                return
        except ValueError:
            error_widget.update("❌ La edad debe ser un número")
            return

        if not sexo:
            error_widget.update("❌ El sexo es requerido")
            return

        if not sintomas:
            error_widget.update("❌ Los síntomas son requeridos")
            return

        if len(sintomas) < 10:
            error_widget.update("❌ Describa los síntomas con más detalle")
            return

        error_widget.update("")

        # Create visit
        self.notify("⏳ Creando visita...", severity="information")

        try:
            result = await asyncio.to_thread(
                self._create_visit_in_db,
                nombre, edad_int, sexo, curp, sintomas
            )

            if result['success']:
                self.dismiss(result)
            else:
                error_widget.update(f"❌ {result['error']}")

        except Exception as e:
            error_widget.update(f"❌ Error: {str(e)}")

    def _create_visit_in_db(
        self,
        nombre: str,
        edad: int,
        sexo: str,
        curp: str,
        sintomas: str
    ) -> Dict[str, Any]:
        """
        Create visit in database with distributed locks (exclusion mutua).

        Protocol:
        1. Get available resources (doctor, cama)
        2. Acquire distributed lock on doctor (all nodes must approve)
        3. Acquire distributed lock on cama (all nodes must approve)
        4. If any lock fails, release acquired locks and abort
        5. Create patient and visit
        6. Mark resources as occupied in DB
        7. Release distributed locks
        """
        with self.flask_app.app_context():
            from models import (
                db, VisitaEmergencia, Paciente, Doctor, Cama,
                get_doctores_disponibles, get_camas_disponibles,
                elegir_sala_menos_carga
            )
            from bully.distributed_locks import (
                solicitar_bloqueo_distribuido,
                liberar_bloqueo_distribuido,
                replicar_asignacion_con_consenso
            )
            import logging
            logger = logging.getLogger(__name__)

            doctor = None
            cama = None
            doctor_locked = False
            cama_locked = False

            try:
                node_id = self.bully_manager.node_id
                logger.warning(f"")
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  [Node-{node_id}] INICIANDO CREACION DE VISITA                     ║")
                logger.warning(f"║  Paciente: {nombre[:30]:<30}                    ║")
                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

                # 1. MAESTRO evalúa carga de TODAS las salas y elige la mejor
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 1: MAESTRO evaluando carga de todas las salas...")
                sala_destino = elegir_sala_menos_carga()

                if not sala_destino:
                    logger.error(f"[Node-{node_id}] [VISIT-CREATE] No hay salas con recursos disponibles")
                    return {'success': False, 'error': 'No hay salas con recursos disponibles'}

                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] MAESTRO decidió: Asignar a SALA {sala_destino}")

                # 2. Buscar recursos en la sala elegida
                doctores = get_doctores_disponibles(id_sala=sala_destino)
                camas = get_camas_disponibles(id_sala=sala_destino)
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Sala {sala_destino}: {len(doctores)} doctores, {len(camas)} camas disponibles")

                if not doctores:
                    return {'success': False, 'error': 'No hay doctores disponibles'}

                if not camas:
                    return {'success': False, 'error': 'No hay camas disponibles'}

                # 3. Try to lock a doctor (distributed mutual exclusion)
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 3: EXCLUSION MUTUA - Bloqueando doctor...")
                for d in doctores:
                    logger.warning(f"[Node-{node_id}] [LOCK-REQUEST] Intentando bloquear DOCTOR_{d.id_doctor} ({d.nombre})")
                    if solicitar_bloqueo_distribuido(
                        self.bully_manager,
                        self.flask_app,
                        'DOCTOR',
                        d.id_doctor
                    ):
                        doctor = d
                        doctor_locked = True
                        logger.warning(f"[Node-{node_id}] [LOCK-SUCCESS] ✓ DOCTOR_{d.id_doctor} BLOQUEADO")
                        break
                    else:
                        logger.warning(f"[Node-{node_id}] [LOCK-FAIL] ✗ No se pudo bloquear DOCTOR_{d.id_doctor}")

                if not doctor:
                    return {'success': False, 'error': 'No se pudo reservar ningun doctor (recursos ocupados)'}

                # 4. Try to lock a cama (distributed mutual exclusion)
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 4: EXCLUSION MUTUA - Bloqueando cama...")
                for c in camas:
                    logger.warning(f"[Node-{node_id}] [LOCK-REQUEST] Intentando bloquear CAMA_{c.id_cama} (#{c.numero})")
                    if solicitar_bloqueo_distribuido(
                        self.bully_manager,
                        self.flask_app,
                        'CAMA',
                        c.id_cama
                    ):
                        cama = c
                        cama_locked = True
                        logger.warning(f"[Node-{node_id}] [LOCK-SUCCESS] ✓ CAMA_{c.id_cama} BLOQUEADA")
                        break
                    else:
                        logger.warning(f"[Node-{node_id}] [LOCK-FAIL] ✗ No se pudo bloquear CAMA_{c.id_cama}")

                if not cama:
                    # Release doctor lock since we couldn't get a cama
                    liberar_bloqueo_distribuido(self.bully_manager, 'DOCTOR', doctor.id_doctor)
                    return {'success': False, 'error': 'No se pudo reservar ninguna cama (recursos ocupados)'}

                # 5. Create or find patient
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 5: Registrando paciente...")
                paciente = None
                if curp:
                    paciente = Paciente.query.filter_by(curp=curp).first()

                if not paciente:
                    paciente = Paciente(
                        nombre=nombre,
                        edad=edad,
                        sexo=sexo,
                        curp=curp if curp else None,
                        activo=1
                    )
                    db.session.add(paciente)
                    db.session.flush()  # Flush para obtener ID (ahora seguro porque get_next_consecutivo no hace flush)
                    logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Nuevo paciente creado: ID={paciente.id_paciente}")
                else:
                    logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paciente existente: ID={paciente.id_paciente}")

                # 6. Mark resources as occupied in local DB
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 6: Marcando recursos como ocupados...")
                doctor.disponible = False
                cama.ocupada = True
                cama.id_paciente = paciente.id_paciente

                # 7. Create visit
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 7: Creando visita en BD local (Sala {sala_destino})...")
                visita = VisitaEmergencia(
                    id_paciente=paciente.id_paciente,
                    id_doctor=doctor.id_doctor,
                    id_cama=cama.id_cama,
                    id_trabajador=1,  # TODO: Get from session
                    id_sala=sala_destino,  # Sala elegida por balanceo de carga
                    sintomas=sintomas,
                    estado='activa',
                    timestamp=datetime.utcnow()
                )

                db.session.add(visita)
                db.session.commit()
                db.session.refresh(visita)

                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] ✓ Visita creada localmente: FOLIO={visita.folio}")

                # 7.5. Guardar en archivo TXT (solo desarrollo)
                self._save_visit_to_txt(visita, paciente, doctor, cama, sala_destino, node_id)

                # 8. Replicate resource assignment to other nodes (consensus)
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 8: CONSENSO - Replicando a otros nodos...")
                replicar_asignacion_con_consenso(
                    self.bully_manager,
                    self.flask_app,
                    doctor.id_doctor,
                    cama.id_cama,
                    paciente.id_paciente
                )

                # 9. Release distributed locks (resources are now marked as occupied in DB)
                logger.warning(f"[Node-{node_id}] [VISIT-CREATE] Paso 9: Liberando bloqueos distribuidos...")
                liberar_bloqueo_distribuido(self.bully_manager, 'DOCTOR', doctor.id_doctor)
                liberar_bloqueo_distribuido(self.bully_manager, 'CAMA', cama.id_cama)

                logger.warning(f"")
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  [Node-{node_id}] VISITA CREADA EXITOSAMENTE                       ║")
                logger.warning(f"║  Folio: {visita.folio:<20}                              ║")
                logger.warning(f"║  Sala: {sala_destino:<3} (balanceada)                                    ║")
                logger.warning(f"║  Doctor: {doctor.nombre[:20]:<20}                             ║")
                logger.warning(f"║  Cama: #{cama.numero:<5}                                            ║")
                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

                return {
                    'success': True,
                    'folio': visita.folio,
                    'id_visita': visita.id_visita,
                    'doctor': doctor.nombre,
                    'cama': cama.numero,
                    'sala': sala_destino
                }

            except Exception as e:
                db.session.rollback()
                logger.error(f"[VISIT] Error creating visit: {e}")

                # Clean up locks on error
                if doctor_locked and doctor:
                    liberar_bloqueo_distribuido(self.bully_manager, 'DOCTOR', doctor.id_doctor)
                if cama_locked and cama:
                    liberar_bloqueo_distribuido(self.bully_manager, 'CAMA', cama.id_cama)

                return {'success': False, 'error': str(e)}


# Export
__all__ = ['SimpleCreateVisitScreen']
