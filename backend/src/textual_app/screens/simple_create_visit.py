"""
Simple Create Visit Screen - Simplified version for creating emergency visits
"""

import asyncio
from typing import Dict, Any
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Button, Label, Select, Footer
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual import work
from textual.binding import Binding


class SimpleCreateVisitScreen(Screen):
    """Simplified screen for creating emergency visits"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("ctrl+s", "submit_form", "Crear Visita", show=True),
        Binding("down", "focus_next", "↓ Siguiente", show=False),
        Binding("up", "focus_previous", "↑ Anterior", show=False),
    ]

    CSS = """
    SimpleCreateVisitScreen {
        background: $surface;
    }

    #visit-header {
        background: $primary;
        color: $surface;
        padding: 0 1;
        dock: top;
        height: 3;
        content-align: center middle;
    }

    #header-title {
        text-style: bold;
        color: $surface;
        text-align: center;
    }

    #form-container {
        height: 1fr;
        padding: 1 2;
    }

    .form-label {
        color: $text-muted;
        height: 1;
    }

    .form-label-required {
        color: $warning;
        text-style: bold;
        height: 1;
    }

    Input {
        height: 3;
    }

    Select {
        height: 3;
    }

    #row-edad-sexo {
        height: 4;
    }

    #col-edad {
        width: 1fr;
        margin-right: 1;
    }

    #col-sexo {
        width: 2fr;
    }

    #button-container {
        align: center middle;
        margin-top: 1;
        height: 3;
    }

    Button {
        margin: 0 1;
    }

    #error-message {
        color: $error;
        text-style: bold;
        text-align: center;
        height: 1;
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
        """Compose the create visit form - optimized for small terminals"""
        # Header compacto
        with Container(id="visit-header"):
            yield Label("🏥 NUEVA VISITA DE EMERGENCIA", id="header-title")

        # Form container con scroll
        with VerticalScroll(id="form-container"):
            # Nombre
            yield Label("Nombre *", classes="form-label-required")
            yield Input(placeholder="Nombre completo", id="input-nombre")

            # Edad + Sexo en una fila
            with Horizontal(id="row-edad-sexo"):
                with Vertical(id="col-edad"):
                    yield Label("Edad *", classes="form-label")
                    yield Input(placeholder="Años", id="input-edad")
                with Vertical(id="col-sexo"):
                    yield Label("Sexo *", classes="form-label")
                    yield Select(
                        options=[("Masculino", "M"), ("Femenino", "F")],
                        prompt="Sexo",
                        id="select-sexo",
                        allow_blank=False
                    )

            # CURP
            yield Label("CURP (opcional)", classes="form-label")
            yield Input(placeholder="CURP", id="input-curp")

            # Síntomas
            yield Label("Síntomas *", classes="form-label")
            yield Input(placeholder="Describa síntomas", id="input-sintomas")

            # Error message
            yield Static("", id="error-message")

            # Botones compactos
            with Horizontal(id="button-container"):
                yield Button("✓ Crear", variant="success", id="btn-create")
                yield Button("✗ Cancelar", variant="error", id="btn-cancel")

        # Footer (sin status-bar adicional)
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "btn-create":
            self.create_visit()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def action_submit_form(self) -> None:
        """Action for Ctrl+S binding"""
        self.create_visit()

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
                self.notify(
                    f"✅ Visita creada: {result['folio']}\n"
                    f"Sala {result['sala']} | Dr. {result['doctor']} | Cama #{result['cama']}",
                    severity="information",
                    timeout=8
                )
                self.app.pop_screen()
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
        Create visit in database using Two-Phase Commit (2PC) protocol.

        Protocol:
        1. Get available resources (doctor, cama) from best sala
        2. Acquire distributed locks on both resources (ordered to prevent deadlock)
        3. Begin 2PC transaction
        4. Execute 2PC: PREPARE -> COMMIT (if all YES) or ABORT (if any NO/timeout)
        5. Release distributed locks with retry
        6. Return result

        Guarantees:
        - ATOMIC: Either all nodes commit or all abort
        - CONSISTENT: No partial commits possible
        - CP (CAP): Rejects operation if consensus cannot be reached
        """
        with self.flask_app.app_context():
            from models import (
                db, Paciente, Doctor, Cama,
                get_doctores_disponibles, get_camas_disponibles,
                elegir_sala_menos_carga
            )
            from auth import get_active_sala_ids
            from bully.distributed_locks import (
                solicitar_bloqueo_con_orden,
                liberar_todos_bloqueos
            )
            from bully.two_phase_commit import TwoPhaseCommitCoordinator
            import logging
            logger = logging.getLogger(__name__)

            locked_resources = []
            doctor = None
            cama = None

            try:
                node_id = self.bully_manager.node_id
                logger.warning(f"")
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  [Node-{node_id}] INICIANDO CREACION DE VISITA (2PC)               ║")
                logger.warning(f"║  Paciente: {nombre[:30]:<30}                    ║")
                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

                # Obtener salas de nodos activos en el cluster
                active_salas = get_active_sala_ids(self.bully_manager)
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Salas activas en cluster: {active_salas}")

                # ====== PASO 1: Seleccionar sala con menor carga ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 1: Evaluando carga de salas...")
                sala_destino = elegir_sala_menos_carga(active_salas=active_salas)

                if not sala_destino:
                    logger.error(f"[Node-{node_id}] [2PC-VISIT] No hay salas con recursos disponibles")
                    return {'success': False, 'error': 'No hay salas con recursos disponibles'}

                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Sala elegida: {sala_destino}")

                # ====== PASO 2: Buscar recursos disponibles en salas activas ======
                doctores = get_doctores_disponibles(id_sala=sala_destino, active_salas=active_salas)
                camas = get_camas_disponibles(id_sala=sala_destino, active_salas=active_salas)
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Sala {sala_destino}: {len(doctores)} doctores, {len(camas)} camas")

                if not doctores:
                    return {'success': False, 'error': 'No hay doctores disponibles'}

                if not camas:
                    return {'success': False, 'error': 'No hay camas disponibles'}

                # Seleccionar primer doctor y cama disponibles
                doctor = doctores[0]
                cama = camas[0]

                # ====== PASO 3: Adquirir bloqueos distribuidos (orden deterministico) ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 3: Adquiriendo bloqueos distribuidos...")
                recursos_a_bloquear = [
                    ('DOCTOR', doctor.id_doctor),
                    ('CAMA', cama.id_cama)
                ]

                success, locked_resources = solicitar_bloqueo_con_orden(
                    self.bully_manager,
                    self.flask_app,
                    recursos_a_bloquear,
                    timeout=10.0
                )

                if not success:
                    logger.warning(f"[Node-{node_id}] [2PC-VISIT] No se pudieron adquirir bloqueos")
                    return {'success': False, 'error': 'No se pudieron reservar recursos (ocupados o timeout)'}

                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Bloqueos adquiridos: {locked_resources}")

                # ====== PASO 4: Buscar o crear paciente localmente (sin commit) ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 4: Preparando datos de paciente...")
                paciente_existente = None
                paciente_id = None

                if curp:
                    paciente_existente = Paciente.query.filter_by(curp=curp).first()

                if paciente_existente:
                    paciente_id = paciente_existente.id_paciente
                    logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paciente existente: ID={paciente_id}")
                else:
                    logger.warning(f"[Node-{node_id}] [2PC-VISIT] Nuevo paciente (se creara en commit)")

                # ====== PASO 5: Iniciar transaccion 2PC ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 5: Iniciando Two-Phase Commit...")
                coordinator = TwoPhaseCommitCoordinator(self.bully_manager, self.flask_app)

                # FOLIO: Se genera automaticamente en before_insert con formato:
                # P{id_paciente}-D{id_doctor}-S{id_sala}-{consecutivo:04d}
                # Ejemplo: P15-D3-S1-0001
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Folio se generara en commit con formato P-D-S-CONS")

                # Datos para la transaccion (folio=None, se genera en insert)
                txn_data = {
                    'folio': None,  # Se genera automaticamente en before_insert
                    'doctor_id': doctor.id_doctor,
                    'cama_id': cama.id_cama,
                    'sala_id': sala_destino,
                    'paciente_id': paciente_id,
                    'paciente_nombre': nombre if not paciente_existente else None,
                    'paciente_edad': edad if not paciente_existente else None,
                    'paciente_sexo': sexo if not paciente_existente else None,
                    'trabajador_id': self.user_info.get('id_trabajador', 1),
                    'sintomas': sintomas
                }

                txn_id = coordinator.begin_transaction('CREATE_VISIT', txn_data)
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Transaccion iniciada: {txn_id}")

                # ====== PASO 6: Ejecutar protocolo 2PC ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 6: Ejecutando 2PC (PREPARE -> COMMIT/ABORT)...")
                result = coordinator.execute_2pc(txn_id)

                if not result['success']:
                    logger.warning(f"[Node-{node_id}] [2PC-VISIT] 2PC ABORTADO: {result.get('error')}")
                    # El coordinador ya hizo ABORT, solo liberamos locks
                    liberar_todos_bloqueos(self.bully_manager, locked_resources)
                    return {'success': False, 'error': f"Transaccion rechazada: {result.get('error')}"}

                # ====== PASO 7: Obtener datos de la visita creada ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] 2PC EXITOSO - Obteniendo datos de visita...")
                from models import VisitaEmergencia

                # Buscar la visita recien creada (la mas reciente del paciente)
                if paciente_id:
                    visita = VisitaEmergencia.query.filter_by(
                        id_doctor=doctor.id_doctor,
                        id_cama=cama.id_cama,
                        estado='activa'
                    ).order_by(VisitaEmergencia.id_visita.desc()).first()
                else:
                    # Nuevo paciente - buscar por doctor y cama
                    visita = VisitaEmergencia.query.filter_by(
                        id_doctor=doctor.id_doctor,
                        id_cama=cama.id_cama,
                        estado='activa'
                    ).order_by(VisitaEmergencia.id_visita.desc()).first()

                if not visita:
                    logger.error(f"[Node-{node_id}] [2PC-VISIT] Visita no encontrada despues de commit")
                    liberar_todos_bloqueos(self.bully_manager, locked_resources)
                    return {'success': False, 'error': 'Error interno: visita no encontrada post-commit'}

                # Obtener datos para TXT
                paciente = Paciente.query.get(visita.id_paciente)

                # ====== PASO 8: Guardar en archivo TXT (desarrollo) ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 8: Guardando registro TXT...")
                self._save_visit_to_txt(visita, paciente, doctor, cama, sala_destino, node_id)

                # ====== PASO 9: Liberar bloqueos distribuidos ======
                logger.warning(f"[Node-{node_id}] [2PC-VISIT] Paso 9: Liberando bloqueos distribuidos...")
                liberar_todos_bloqueos(self.bully_manager, locked_resources)

                logger.warning(f"")
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  [Node-{node_id}] VISITA CREADA EXITOSAMENTE (2PC)                  ║")
                logger.warning(f"║  Folio: {visita.folio:<20}                              ║")
                logger.warning(f"║  Sala: {sala_destino:<3} (balanceada)                                    ║")
                logger.warning(f"║  Doctor: {doctor.nombre[:20]:<20}                             ║")
                logger.warning(f"║  Cama: #{cama.numero:<5}                                            ║")
                logger.warning(f"║  TXN: {txn_id[:30]:<30}                      ║")
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
                logger.error(f"[Node-{node_id}] [2PC-VISIT] Exception: {e}")

                # Liberar bloqueos en caso de error
                if locked_resources:
                    liberar_todos_bloqueos(self.bully_manager, locked_resources)

                return {'success': False, 'error': str(e)}


# Export
__all__ = ['SimpleCreateVisitScreen']
