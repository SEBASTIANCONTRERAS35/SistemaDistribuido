"""
Trabajadores Screen - Manage all trabajadores sociales
Full CRUD for trabajador social (self-management)
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
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual import work
from textual.binding import Binding
from rich.text import Text


class CrearTrabajadorModal(ModalScreen[Dict[str, Any]]):
    """Modal para crear un nuevo trabajador social"""

    CSS = """
    CrearTrabajadorModal {
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
            yield Label("➕ CREAR NUEVO TRABAJADOR SOCIAL", id="modal-title")

            yield Label("Nombre:", classes="field-label")
            yield Input(placeholder="Ej: Lic. María García", id="input-nombre")

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
            sala = self.query_one("#select-sala", Select).value

            if not nombre:
                self.notify("❌ El nombre es requerido", severity="error")
                return

            self.dismiss({
                'nombre': nombre,
                'sala_id': sala
            })
        elif event.button.id == "btn-cancelar":
            self.dismiss(None)


class EditarTrabajadorModal(ModalScreen):
    """Modal for editing trabajador social information"""

    CSS = """
    EditarTrabajadorModal {
        align: center middle;
    }

    #edit-container {
        width: 70;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #edit-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        padding-bottom: 1;
        border-bottom: solid $border;
        margin-bottom: 1;
    }

    .field-row {
        height: auto;
        margin: 1 0;
    }

    .field-label {
        width: 20;
        color: $text-secondary;
    }

    .field-input {
        width: 1fr;
    }

    #button-container {
        align: center middle;
        margin-top: 2;
    }

    #save-btn {
        margin: 0 1;
    }

    #cancel-btn {
        margin: 0 1;
    }
    """

    def __init__(self, trabajador: Dict[str, Any], flask_app, salas: List[Dict[str, Any]]):
        super().__init__()
        self.trabajador = trabajador
        self.flask_app = flask_app
        self.salas = salas

    def compose(self) -> ComposeResult:
        """Compose the edit modal UI"""
        with Container(id="edit-container"):
            yield Label(
                f"✏️ EDITAR TRABAJADOR SOCIAL: {self.trabajador.get('nombre', 'N/A')}",
                id="edit-title"
            )

            # Nombre
            with Horizontal(classes="field-row"):
                yield Label("Nombre:", classes="field-label")
                yield Input(
                    value=self.trabajador.get('nombre', ''),
                    placeholder="Nombre completo",
                    id="input-nombre",
                    classes="field-input"
                )

            # Sala asignada
            with Horizontal(classes="field-row"):
                yield Label("Sala asignada:", classes="field-label")

                # Create options from salas
                sala_options = [(f"Sala {s['numero']}", str(s['id_sala'])) for s in self.salas]

                yield Select(
                    options=sala_options,
                    value=str(self.trabajador.get('id_sala', '')),
                    id="select-sala",
                    classes="field-input",
                    allow_blank=False
                )

            # Buttons
            with Horizontal(id="button-container"):
                yield Button("💾 Guardar", variant="success", id="save-btn")
                yield Button("← Cancelar", variant="error", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    @work(exclusive=True)
    async def action_save(self) -> None:
        """Save trabajador changes"""
        # Collect form data
        nombre = self.query_one("#input-nombre", Input).value.strip()
        id_sala = int(self.query_one("#select-sala", Select).value)

        # Validaciones
        if not nombre or len(nombre) < 3:
            self.notify("❌ El nombre debe tener al menos 3 caracteres", severity="error")
            return

        # Save to database
        result = await asyncio.to_thread(
            self._save_to_db,
            nombre, id_sala
        )

        if result['success']:
            self.notify("✓ Trabajador social actualizado exitosamente", severity="information")
            self.dismiss({'action': 'updated', 'id_trabajador': self.trabajador['id_trabajador']})
        else:
            self.notify(f"❌ Error: {result['error']}", severity="error")

    def _save_to_db(self, nombre, id_sala) -> Dict[str, Any]:
        """Save trabajador to database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import db, TrabajadorSocial
            import logging
            logger = logging.getLogger(__name__)

            try:
                trabajador = TrabajadorSocial.query.get(self.trabajador['id_trabajador'])
                if not trabajador:
                    return {'success': False, 'error': 'Trabajador social no encontrado'}

                # Update fields
                trabajador.nombre = nombre
                trabajador.id_sala = id_sala

                db.session.commit()

                logger.info(f"[TRABAJADOR-UPDATE] Trabajador {trabajador.id_trabajador} actualizado")

                return {'success': True}

            except Exception as e:
                db.session.rollback()
                logger.error(f"[TRABAJADOR-UPDATE] Error: {e}")
                return {'success': False, 'error': str(e)}


class TrabajadorDetailModal(ModalScreen):
    """Modal for viewing trabajador social details"""

    CSS = """
    TrabajadorDetailModal {
        align: center middle;
    }

    #detail-container {
        width: 70;
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

    .field-row {
        height: auto;
        margin: 0 0 1 0;
    }

    .field-label {
        color: $text-secondary;
        width: 25;
    }

    .field-value {
        color: $text;
        text-style: bold;
        min-width: 20;
    }

    #button-container {
        align: center middle;
        margin-top: 2;
    }
    """

    def __init__(self, trabajador: Dict[str, Any]):
        super().__init__()
        self.trabajador = trabajador

    def compose(self) -> ComposeResult:
        """Compose the detail modal UI"""
        with Container(id="detail-container"):
            yield Label(
                f"👔 DETALLE DE TRABAJADOR SOCIAL",
                id="detail-title"
            )

            # Trabajador info section
            with Vertical(classes="detail-section"):
                yield Label("INFORMACIÓN", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("ID:", classes="field-label")
                    yield Static(str(self.trabajador.get('id_trabajador', 'N/A')), classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Nombre:", classes="field-label")
                    yield Static(self.trabajador.get('nombre', 'N/A'), classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Sala asignada:", classes="field-label")
                    yield Static(f"Sala {self.trabajador.get('sala', 'N/A')}", classes="field-value")

            # Statistics section
            with Vertical(classes="detail-section"):
                yield Label("ESTADÍSTICAS", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Visitas creadas:", classes="field-label")
                    yield Static(str(self.trabajador.get('visitas_creadas', 0)), classes="field-value")

            # Buttons
            with Horizontal(id="button-container"):
                yield Button("← Cerrar", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "close-btn":
            self.dismiss()


class TrabajadoresScreen(Screen):
    """
    Screen for managing all trabajadores sociales (trabajador social only)
    Features: DataTable, View details, Edit
    """

    BINDINGS = [
        Binding("ctrl+n", "create_trabajador", "Nuevo Trabajador", show=True),
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
    ]

    CSS = """
    TrabajadoresScreen {
        background: $surface;
    }

    #trabajadores-header {
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

    #trabajadores-table {
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
    """

    # Reactive state
    trabajadores_data: reactive[List[Dict[str, Any]]] = reactive([], init=False)
    is_loading: reactive[bool] = reactive(False)

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}
        self.salas: List[Dict[str, Any]] = []

        # Verificar permisos
        if self.user_info.get('rol') != 'trabajador_social':
            self.notify("❌ Acceso denegado: Solo trabajadores sociales", severity="error")

    def compose(self) -> ComposeResult:
        """Compose the trabajadores screen UI"""

        # Header with stats
        with Container(id="trabajadores-header"):
            yield Label("👔 GESTIÓN DE TRABAJADORES SOCIALES", id="header-title")

            # Display user info
            user_display = self.user_info.get('nombre') or self.user_info.get('username', self.username)
            stats_text = f"👤 {user_display} | Nodo {self.bully_manager.node_id}"
            yield Label(stats_text, id="header-stats")

        # Toolbar with create button
        with Horizontal(id="toolbar"):
            yield Button("➕ Nuevo Trabajador", variant="success", id="btn-nuevo-trabajador")

        # DataTable for trabajadores
        yield DataTable(id="trabajadores-table", zebra_stripes=True, cursor_type="row")

        # Status bar
        yield Static("", id="status-bar")

        # Footer with shortcuts
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted"""
        # Setup DataTable columns
        table = self.query_one("#trabajadores-table", DataTable)
        table.add_columns(
            "ID",
            "Nombre",
            "Sala Asignada",
            "Visitas Creadas"
        )

        # Load initial data
        self.load_trabajadores()

    @work(exclusive=True)
    async def load_trabajadores(self) -> None:
        """Load trabajadores from database asynchronously"""
        self.is_loading = True
        self.update_status("⏳ Cargando trabajadores sociales...")

        try:
            # Run DB query in thread pool to avoid blocking UI
            result = await asyncio.to_thread(self._fetch_trabajadores_from_db)

            # Update reactive state (triggers watch_trabajadores_data)
            self.trabajadores_data = result['trabajadores']
            self.salas = result['salas']

            self.update_status(f"✓ {len(self.trabajadores_data)} trabajadores sociales cargados")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            self.notify(f"Error al cargar trabajadores sociales: {str(e)}", severity="error")
        finally:
            self.is_loading = False

    def _fetch_trabajadores_from_db(self) -> Dict[str, Any]:
        """Fetch trabajadores from database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import TrabajadorSocial, VisitaEmergencia, Sala
            from auth import get_active_sala_ids
            from sqlalchemy.orm import joinedload

            # Obtener salas de nodos activos en el cluster
            active_salas = get_active_sala_ids(self.bully_manager)

            # Query con filtro por salas activas
            query = TrabajadorSocial.query.options(
                joinedload(TrabajadorSocial.sala)
            ).filter_by(activo=True)

            if active_salas:
                query = query.filter(TrabajadorSocial.id_sala.in_(active_salas))

            trabajadores = query.order_by(TrabajadorSocial.nombre).all()

            # Also fetch salas for edit modal (solo activas en cluster)
            query_salas = Sala.query.filter_by(activa=True)
            if active_salas:
                query_salas = query_salas.filter(Sala.id_sala.in_(active_salas))
            salas = query_salas.order_by(Sala.numero).all()

            result_trabajadores = []
            for trab in trabajadores:
                # Contar visitas creadas por este trabajador
                visitas_count = VisitaEmergencia.query.filter_by(
                    id_trabajador=trab.id_trabajador
                ).count()

                result_trabajadores.append({
                    'id_trabajador': trab.id_trabajador,
                    'nombre': trab.nombre,
                    'sala': trab.sala.numero if trab.sala else 'N/A',
                    'id_sala': trab.id_sala,
                    'visitas_creadas': visitas_count
                })

            result_salas = [{'id_sala': s.id_sala, 'numero': s.numero} for s in salas]

            return {
                'trabajadores': result_trabajadores,
                'salas': result_salas
            }

    def watch_trabajadores_data(self, trabajadores: List[Dict[str, Any]]) -> None:
        """React to changes in trabajadores data"""
        self.update_table()

    def update_table(self) -> None:
        """Update DataTable with trabajadores"""
        table = self.query_one("#trabajadores-table", DataTable)
        table.clear()

        for trabajador in self.trabajadores_data:
            # Add row to table
            table.add_row(
                str(trabajador.get('id_trabajador', '')),
                trabajador.get('nombre', ''),
                f"Sala {trabajador.get('sala', 'N/A')}",
                str(trabajador.get('visitas_creadas', 0)),
                key=trabajador.get('id_trabajador', '')
            )

        # Update status bar
        total = len(self.trabajadores_data)
        self.update_status(f"📊 {total} trabajadores sociales")

    def update_status(self, message: str) -> None:
        """Update status bar message"""
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(message)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection - show edit modal"""
        if event.row_key:
            # Find the trabajador by id
            trabajador_id = event.row_key.value

            trabajador = next(
                (t for t in self.trabajadores_data if t.get('id_trabajador') == trabajador_id),
                None
            )

            if trabajador:
                # Show edit modal directly
                def handle_edit_result(result):
                    if result and result.get('action') == 'updated':
                        self.notify("✓ Trabajador social actualizado", severity="information")
                        self.load_trabajadores()

                self.app.push_screen(
                    EditarTrabajadorModal(trabajador, self.flask_app, self.salas),
                    handle_edit_result
                )

    def action_refresh(self) -> None:
        """Refresh trabajadores data"""
        self.notify("🔄 Actualizando trabajadores sociales...", severity="information")
        self.load_trabajadores()

    def action_create_trabajador(self) -> None:
        """Open modal to create a new trabajador social"""
        # Convertir salas a formato para Select
        salas_options = [(f"Sala {s['numero']}", s['id_sala']) for s in self.salas]
        if not salas_options:
            self.notify("❌ No hay salas disponibles", severity="error")
            return
        self.app.push_screen(CrearTrabajadorModal(salas_options), self._handle_crear_trabajador)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "btn-nuevo-trabajador":
            self.action_create_trabajador()

    def _handle_crear_trabajador(self, result: Dict[str, Any] | None) -> None:
        """Handle result from CrearTrabajadorModal"""
        if result is None:
            return  # Cancelled

        self.notify("⏳ Creando trabajador social con 2PC...", severity="information")
        self._create_trabajador_2pc(result)

    @work(exclusive=True)
    async def _create_trabajador_2pc(self, data: Dict[str, Any]) -> None:
        """Create trabajador using 2PC"""
        try:
            result = await asyncio.to_thread(self._execute_create_trabajador_2pc, data)

            if result.get('success'):
                commit_data = result.get('commit_data', {})
                username = commit_data.get('username', 'N/A')
                password = commit_data.get('password', 'N/A')
                # Mostrar modal con credenciales
                from textual_app.screens.doctores import CredencialesModal
                self.app.push_screen(CredencialesModal(
                    tipo="Trabajador Social",
                    nombre=data['nombre'],
                    username=username,
                    password=password
                ))
                self.load_trabajadores()  # Refresh table
            else:
                self.notify(f"❌ Error: {result.get('error')}", severity="error")

        except Exception as e:
            self.notify(f"❌ Error: {str(e)}", severity="error")

    def _execute_create_trabajador_2pc(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute 2PC for creating trabajador (runs in thread pool) with distributed lock"""
        with self.flask_app.app_context():
            from bully.two_phase_commit import TwoPhaseCommitCoordinator
            from bully.distributed_locks import solicitar_bloqueo_distribuido, liberar_bloqueo_distribuido
            import logging
            logger = logging.getLogger(__name__)

            # Bloqueo distribuido GLOBAL para serializar creación de trabajadores
            # Usar recurso único para evitar conflictos de ID entre nodos
            # (antes usábamos SALA_TRABAJADOR_{sala_id} pero permitía creaciones simultáneas en diferentes salas)
            recurso_tipo = 'TRABAJADOR_CREATE'
            recurso_id = 0  # Recurso global, no por sala

            logger.warning(f"[TRABAJADOR-CREATE] Solicitando bloqueo distribuido global TRABAJADOR_CREATE")
            lock_acquired = solicitar_bloqueo_distribuido(
                self.bully_manager,
                self.flask_app,
                recurso_tipo,
                recurso_id,
                timeout=10.0
            )

            if not lock_acquired:
                logger.warning(f"[TRABAJADOR-CREATE] No se pudo obtener bloqueo global TRABAJADOR_CREATE")
                return {'success': False, 'error': 'No se pudo obtener bloqueo para crear trabajador (otro nodo creando)'}

            try:
                logger.warning(f"[TRABAJADOR-CREATE] Bloqueo adquirido, solicitando ID al líder...")

                # Solicitar ID al líder ANTES del 2PC para garantizar unicidad
                from bully.id_manager import request_id_from_leader, generate_fallback_id

                pre_assigned_id = request_id_from_leader(
                    self.bully_manager,
                    self.flask_app,
                    'trabajador',
                    timeout=5.0
                )

                if pre_assigned_id is None:
                    # Fallback: generar ID con prefijo de nodo si líder no responde
                    logger.warning(f"[TRABAJADOR-CREATE] Líder no respondió, usando fallback ID")
                    pre_assigned_id = generate_fallback_id(self.bully_manager.node_id, 'trabajador')

                # Agregar ID pre-asignado a los datos para el 2PC
                data['pre_assigned_id'] = pre_assigned_id
                logger.warning(f"[TRABAJADOR-CREATE] ID pre-asignado: {pre_assigned_id}, iniciando 2PC")

                coordinator = TwoPhaseCommitCoordinator(self.bully_manager, self.flask_app)
                txn_id = coordinator.begin_transaction('CREATE_TRABAJADOR', data)
                result = coordinator.execute_2pc(txn_id)

                # Get commit data if successful
                if result.get('success'):
                    from models import TrabajadorSocial
                    # Buscar por ID pre-asignado primero
                    trabajador = TrabajadorSocial.query.get(pre_assigned_id)

                    # Fallback: buscar por nombre si no existe con ese ID
                    if not trabajador:
                        trabajador = TrabajadorSocial.query.filter_by(
                            nombre=data['nombre'],
                            id_sala=data['sala_id']
                        ).order_by(TrabajadorSocial.id_trabajador.desc()).first()

                    if trabajador:
                        result['commit_data'] = {
                            'id_trabajador': trabajador.id_trabajador,
                            'username': f"social{trabajador.id_trabajador}",
                            'password': '1234'
                        }

                return result

            finally:
                # Siempre liberar el bloqueo
                logger.warning(f"[TRABAJADOR-CREATE] Liberando bloqueo global TRABAJADOR_CREATE")
                liberar_bloqueo_distribuido(
                    self.bully_manager,
                    recurso_tipo,
                    recurso_id
                )


# Export
__all__ = ['TrabajadoresScreen', 'TrabajadorDetailModal', 'EditarTrabajadorModal', 'CrearTrabajadorModal']
