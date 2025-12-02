"""
Doctores Screen - View all doctors across all salas
Trabajador social can view and CREATE new doctors
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Input,
    Button,
    Static,
    Label,
    Select
)
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.reactive import reactive
from textual import work
from textual.binding import Binding
from rich.text import Text


class CredencialesModal(ModalScreen):
    """Modal para mostrar credenciales generadas"""

    CSS = """
    CredencialesModal {
        align: center middle;
    }

    #cred-container {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $success;
        padding: 1 2;
    }

    #cred-title {
        text-align: center;
        text-style: bold;
        color: $success;
        margin-bottom: 1;
    }

    #cred-warning {
        text-align: center;
        color: $warning;
        margin-bottom: 1;
    }

    .cred-section {
        background: $panel;
        border: solid $border;
        padding: 1;
        margin: 1 0;
    }

    .cred-label {
        color: $text-muted;
    }

    .cred-value {
        text-style: bold;
        color: $primary;
        margin-left: 1;
    }

    #cred-buttons {
        margin-top: 1;
        height: 3;
        align: center middle;
    }
    """

    def __init__(self, tipo: str, nombre: str, username: str, password: str):
        super().__init__()
        self.tipo = tipo
        self.nombre = nombre
        self.username = username
        self.password = password

    def compose(self) -> ComposeResult:
        with Vertical(id="cred-container"):
            yield Label(f"✅ {self.tipo.upper()} CREADO", id="cred-title")
            yield Label("⚠️ GUARDA ESTAS CREDENCIALES", id="cred-warning")

            with Vertical(classes="cred-section"):
                yield Label(f"Nombre: {self.nombre}")

            with Vertical(classes="cred-section"):
                with Horizontal():
                    yield Label("Usuario:", classes="cred-label")
                    yield Label(self.username, classes="cred-value")

            with Vertical(classes="cred-section"):
                with Horizontal():
                    yield Label("Contraseña:", classes="cred-label")
                    yield Label(self.password, classes="cred-value")

            with Horizontal(id="cred-buttons"):
                yield Button("✓ Entendido", variant="success", id="btn-ok")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ok":
            self.dismiss()


class CrearDoctorModal(ModalScreen[Dict[str, Any]]):
    """Modal para crear un nuevo doctor"""

    CSS = """
    CrearDoctorModal {
        align: center middle;
    }

    #modal-container {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #modal-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        margin-top: 1;
        color: $text;
    }

    Input {
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    #buttons {
        margin-top: 1;
        height: 3;
    }

    #btn-crear {
        margin-right: 1;
    }
    """

    def __init__(self, salas_options: List[tuple]):
        super().__init__()
        self.salas_options = salas_options

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("➕ CREAR NUEVO DOCTOR", id="modal-title")

            yield Label("Nombre:", classes="field-label")
            yield Input(placeholder="Ej: Dr. Juan Pérez", id="input-nombre")

            yield Label("Especialidad:", classes="field-label")
            yield Input(placeholder="Ej: Medicina General", id="input-especialidad")

            yield Label("Sala asignada:", classes="field-label")
            # Selector dinámico de salas desde BD
            default_value = self.salas_options[0][1] if self.salas_options else 1
            yield Select(
                options=self.salas_options,
                id="select-sala",
                allow_blank=False,
                value=default_value
            )

            with Horizontal(id="buttons"):
                yield Button("Crear", variant="success", id="btn-crear")
                yield Button("Cancelar", variant="default", id="btn-cancelar")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-crear":
            nombre = self.query_one("#input-nombre", Input).value.strip()
            especialidad = self.query_one("#input-especialidad", Input).value.strip()
            sala = self.query_one("#select-sala", Select).value

            if not nombre:
                self.notify("❌ El nombre es requerido", severity="error")
                return
            if not especialidad:
                self.notify("❌ La especialidad es requerida", severity="error")
                return

            self.dismiss({
                'nombre': nombre,
                'especialidad': especialidad,
                'sala_id': sala
            })
        elif event.button.id == "btn-cancelar":
            self.dismiss(None)


class DoctoresScreen(Screen):
    """
    Screen for viewing all doctors (trabajador social only)
    Features: DataTable, Filters by sala and availability
    """

    BINDINGS = [
        Binding("ctrl+n", "create_doctor", "Nuevo Doctor", show=True),
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
    ]

    CSS = """
    DoctoresScreen {
        background: $surface;
    }

    #doctores-header {
        background: $primary;
        color: $surface;
        padding: 1 2;
        dock: top;
        height: 5;
    }

    #header-title {
        text-style: bold;
        color: $surface;
        text-align: center;
    }

    #header-stats {
        color: $surface;
        text-align: center;
        margin-top: 1;
    }

    #toolbar {
        background: $panel;
        padding: 1 2;
        height: auto;
        border: solid $border;
    }

    #filter-sala {
        width: 20;
        margin-right: 2;
    }

    #filter-disponibilidad {
        width: 20;
        margin-right: 2;
    }

    #btn-nuevo-doctor {
        margin-left: 2;
    }

    #doctores-table {
        height: 1fr;
        margin: 1 2;
    }

    #status-bar {
        background: $panel;
        color: $text-muted;
        padding: 0 2;
        dock: bottom;
        height: 1;
    }

    .disponible {
        color: $success;
        text-style: bold;
    }

    .ocupado {
        color: $error;
        text-style: bold;
    }
    """

    # Reactive state
    doctores_data: reactive[List[Dict[str, Any]]] = reactive([], init=False)
    filter_sala: reactive[str] = reactive("todas")
    filter_disponibilidad: reactive[str] = reactive("todos")
    is_loading: reactive[bool] = reactive(False)

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}
        self.filtered_doctores: List[Dict[str, Any]] = []
        self.salas_options: List[tuple] = []  # Para selectores dinámicos

        # Verificar permisos
        if self.user_info.get('rol') != 'trabajador_social':
            self.notify("❌ Acceso denegado: Solo trabajadores sociales", severity="error")

    def compose(self) -> ComposeResult:
        """Compose the doctores screen UI"""

        # Header with stats
        with Container(id="doctores-header"):
            yield Label("👨‍⚕️ ESTADO DE DOCTORES - TODAS LAS SALAS", id="header-title")

            # Display user info
            user_display = self.user_info.get('nombre') or self.user_info.get('username', self.username)
            stats_text = f"👤 {user_display} | Nodo {self.bully_manager.node_id}"
            yield Label(stats_text, id="header-stats")

        # Toolbar with filters
        with Horizontal(id="toolbar"):
            # Selector dinámico de salas - se popula en on_mount
            yield Select(
                options=[("Todas las salas", "todas")],  # Placeholder, se actualiza en on_mount
                value="todas",
                id="filter-sala",
                allow_blank=False
            )

            yield Select(
                options=[
                    ("Todos", "todos"),
                    ("Disponible", "disponible"),
                    ("Ocupado", "ocupado"),
                ],
                value="todos",
                id="filter-disponibilidad",
                allow_blank=False
            )

            yield Button("➕ Nuevo Doctor", variant="success", id="btn-nuevo-doctor")

        # DataTable for doctors
        yield DataTable(id="doctores-table", zebra_stripes=True, cursor_type="row")

        # Status bar
        yield Static("", id="status-bar")

        # Footer with shortcuts
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted"""
        # Setup DataTable columns
        table = self.query_one("#doctores-table", DataTable)
        table.add_columns(
            "ID",
            "Nombre",
            "Especialidad",
            "Sala",
            "Estado",
            "Visita Actual"
        )

        # Load initial data
        self.load_doctores()

    @work(exclusive=True)
    async def load_doctores(self) -> None:
        """Load doctors from database asynchronously"""
        self.is_loading = True
        self.update_status("⏳ Cargando doctores...")

        try:
            # Run DB query in thread pool to avoid blocking UI
            result = await asyncio.to_thread(self._fetch_doctores_from_db)

            # Guardar opciones de salas para el modal de crear
            self.salas_options = result['salas_options']

            # Actualizar el selector de filtro dinámicamente
            filter_sala = self.query_one("#filter-sala", Select)
            filter_sala.set_options(result['salas_filter'])

            # Update reactive state (triggers watch_doctores_data)
            self.doctores_data = result['doctores']

            self.update_status(f"✓ {len(result['doctores'])} doctores cargados")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            self.notify(f"Error al cargar doctores: {str(e)}", severity="error")
        finally:
            self.is_loading = False

    def _fetch_doctores_from_db(self) -> Dict[str, Any]:
        """Fetch doctors and salas from database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import Doctor, VisitaEmergencia, Sala
            from auth import get_active_sala_ids
            from sqlalchemy.orm import joinedload

            # Obtener salas de nodos activos en el cluster
            active_salas = get_active_sala_ids(self.bully_manager)

            # Eager load sala, filtrar por salas activas
            query = Doctor.query.options(
                joinedload(Doctor.sala)
            ).filter_by(activo=True)

            if active_salas:
                query = query.filter(Doctor.id_sala.in_(active_salas))

            doctores = query.order_by(Doctor.nombre).all()

            result_doctores = []
            for doc in doctores:
                # Buscar visita activa del doctor
                visita_activa = VisitaEmergencia.query.filter_by(
                    id_doctor=doc.id_doctor,
                    estado='activa'
                ).first()

                result_doctores.append({
                    'id_doctor': doc.id_doctor,
                    'nombre': doc.nombre,
                    'especialidad': doc.especialidad or 'General',
                    'sala': doc.sala.numero if doc.sala else 'N/A',
                    'id_sala': doc.id_sala,
                    'disponible': doc.disponible,
                    'visita_actual': visita_activa.folio if visita_activa else None
                })

            # Cargar salas dinámicamente (solo activas en cluster)
            query_salas = Sala.query.filter_by(activa=True)
            if active_salas:
                query_salas = query_salas.filter(Sala.id_sala.in_(active_salas))
            salas = query_salas.order_by(Sala.numero).all()

            salas_options = [(f"Sala {s.numero}", s.id_sala) for s in salas]
            salas_filter = [("Todas las salas", "todas")]
            salas_filter.extend([(f"Sala {s.numero}", str(s.id_sala)) for s in salas])

            return {
                'doctores': result_doctores,
                'salas_options': salas_options,
                'salas_filter': salas_filter
            }

    def watch_doctores_data(self, doctores: List[Dict[str, Any]]) -> None:
        """React to changes in doctores data"""
        self.apply_filters()

    def watch_filter_sala(self, sala: str) -> None:
        """React to filter changes"""
        self.apply_filters()

    def watch_filter_disponibilidad(self, disponibilidad: str) -> None:
        """React to filter changes"""
        self.apply_filters()

    def apply_filters(self) -> None:
        """Apply filters to doctores data"""
        # Start with all doctores
        filtered = self.doctores_data.copy()

        # Apply sala filter
        if self.filter_sala != "todas":
            sala_num = int(self.filter_sala)
            filtered = [d for d in filtered if d.get('id_sala') == sala_num]

        # Apply disponibilidad filter
        if self.filter_disponibilidad == "disponible":
            filtered = [d for d in filtered if d.get('disponible')]
        elif self.filter_disponibilidad == "ocupado":
            filtered = [d for d in filtered if not d.get('disponible')]

        self.filtered_doctores = filtered
        self.update_table()

    def update_table(self) -> None:
        """Update DataTable with filtered doctores"""
        table = self.query_one("#doctores-table", DataTable)
        table.clear()

        for doctor in self.filtered_doctores:
            # Create estado with color
            disponible = doctor.get('disponible', False)
            if disponible:
                estado_text = Text("DISPONIBLE", style="bold green")
            else:
                estado_text = Text("OCUPADO", style="bold red")

            # Visita actual
            visita = doctor.get('visita_actual') or '-'

            # Add row to table
            table.add_row(
                str(doctor.get('id_doctor', '')),
                doctor.get('nombre', ''),
                doctor.get('especialidad', ''),
                f"Sala {doctor.get('sala', '')}",
                estado_text,
                visita,
                key=doctor.get('id_doctor', '')
            )

        # Update status bar
        total = len(self.doctores_data)
        showing = len(self.filtered_doctores)

        # Count disponibles
        disponibles = sum(1 for d in self.filtered_doctores if d.get('disponible'))
        ocupados = showing - disponibles

        if total == showing:
            self.update_status(f"📊 {total} doctores | ✅ {disponibles} disponibles | ⛔ {ocupados} ocupados")
        else:
            self.update_status(f"📊 Mostrando {showing} de {total} doctores | ✅ {disponibles} disponibles | ⛔ {ocupados} ocupados")

    def update_status(self, message: str) -> None:
        """Update status bar message"""
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(message)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter select changes"""
        if event.select.id == "filter-sala":
            self.filter_sala = str(event.value)
        elif event.select.id == "filter-disponibilidad":
            self.filter_disponibilidad = str(event.value)

    def action_refresh(self) -> None:
        """Refresh doctores data"""
        self.notify("🔄 Actualizando doctores...", severity="information")
        self.load_doctores()

    def action_create_doctor(self) -> None:
        """Open modal to create a new doctor"""
        if not self.salas_options:
            self.notify("❌ No hay salas disponibles", severity="error")
            return
        self.app.push_screen(CrearDoctorModal(self.salas_options), self._handle_crear_doctor)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "btn-nuevo-doctor":
            self.action_create_doctor()

    def _handle_crear_doctor(self, result: Dict[str, Any] | None) -> None:
        """Handle result from CrearDoctorModal"""
        if result is None:
            return  # Cancelled

        self.notify("⏳ Creando doctor con 2PC...", severity="information")
        self._create_doctor_2pc(result)

    @work(exclusive=True)
    async def _create_doctor_2pc(self, data: Dict[str, Any]) -> None:
        """Create doctor using 2PC"""
        try:
            result = await asyncio.to_thread(self._execute_create_doctor_2pc, data)

            if result.get('success'):
                commit_data = result.get('commit_data', {})
                username = commit_data.get('username', 'N/A')
                password = commit_data.get('password', 'N/A')
                # Mostrar modal con credenciales
                self.app.push_screen(CredencialesModal(
                    tipo="Doctor",
                    nombre=data['nombre'],
                    username=username,
                    password=password
                ))
                self.load_doctores()  # Refresh table
            else:
                self.notify(f"❌ Error: {result.get('error')}", severity="error")

        except Exception as e:
            self.notify(f"❌ Error: {str(e)}", severity="error")

    def _execute_create_doctor_2pc(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute 2PC for creating doctor (runs in thread pool) with distributed lock"""
        with self.flask_app.app_context():
            from bully.two_phase_commit import TwoPhaseCommitCoordinator
            from bully.distributed_locks import solicitar_bloqueo_distribuido, liberar_bloqueo_distribuido
            import logging
            logger = logging.getLogger(__name__)

            # Bloqueo distribuido GLOBAL para serializar creación de doctores
            # Usar recurso único para evitar conflictos de ID entre nodos
            # (antes usábamos SALA_DOCTOR_{sala_id} pero permitía creaciones simultáneas en diferentes salas)
            recurso_tipo = 'DOCTOR_CREATE'
            recurso_id = 0  # Recurso global, no por sala

            logger.warning(f"[DOCTOR-CREATE] Solicitando bloqueo distribuido global DOCTOR_CREATE")
            lock_acquired = solicitar_bloqueo_distribuido(
                self.bully_manager,
                self.flask_app,
                recurso_tipo,
                recurso_id,
                timeout=10.0
            )

            if not lock_acquired:
                logger.warning(f"[DOCTOR-CREATE] No se pudo obtener bloqueo global DOCTOR_CREATE")
                return {'success': False, 'error': 'No se pudo obtener bloqueo para crear doctor (otro nodo creando)'}

            try:
                logger.warning(f"[DOCTOR-CREATE] Bloqueo adquirido, solicitando ID al líder...")

                # Solicitar ID al líder ANTES del 2PC para garantizar unicidad
                from bully.id_manager import request_id_from_leader, generate_fallback_id

                pre_assigned_id = request_id_from_leader(
                    self.bully_manager,
                    self.flask_app,
                    'doctor',
                    timeout=5.0
                )

                if pre_assigned_id is None:
                    # Fallback: generar ID con prefijo de nodo si líder no responde
                    logger.warning(f"[DOCTOR-CREATE] Líder no respondió, usando fallback ID")
                    pre_assigned_id = generate_fallback_id(self.bully_manager.node_id, 'doctor')

                # Agregar ID pre-asignado a los datos para el 2PC
                data['pre_assigned_id'] = pre_assigned_id
                logger.warning(f"[DOCTOR-CREATE] ID pre-asignado: {pre_assigned_id}, iniciando 2PC")

                coordinator = TwoPhaseCommitCoordinator(self.bully_manager, self.flask_app)
                txn_id = coordinator.begin_transaction('CREATE_DOCTOR', data)
                result = coordinator.execute_2pc(txn_id)

                # Get commit data if successful
                if result.get('success'):
                    from models import Doctor
                    # Buscar por ID pre-asignado primero
                    doctor = Doctor.query.get(pre_assigned_id)

                    # Fallback: buscar por nombre si no existe con ese ID
                    if not doctor:
                        doctor = Doctor.query.filter_by(
                            nombre=data['nombre'],
                            id_sala=data['sala_id']
                        ).order_by(Doctor.id_doctor.desc()).first()

                    if doctor:
                        result['commit_data'] = {
                            'id_doctor': doctor.id_doctor,
                            'username': f"doctor{doctor.id_doctor}",
                            'password': f"doctor{doctor.id_doctor}"
                        }

                return result

            finally:
                # Siempre liberar el bloqueo
                logger.warning(f"[DOCTOR-CREATE] Liberando bloqueo global DOCTOR_CREATE")
                liberar_bloqueo_distribuido(
                    self.bully_manager,
                    recurso_tipo,
                    recurso_id
                )


# Export
__all__ = ['DoctoresScreen', 'CrearDoctorModal', 'CredencialesModal']
