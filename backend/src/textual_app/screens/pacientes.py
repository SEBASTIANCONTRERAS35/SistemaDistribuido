"""
Pacientes Screen - Manage all patients
Full CRUD for trabajador social
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


class EditarPacienteModal(ModalScreen):
    """Modal for editing patient information"""

    CSS = """
    EditarPacienteModal {
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

    def __init__(self, paciente: Dict[str, Any], flask_app):
        super().__init__()
        self.paciente = paciente
        self.flask_app = flask_app

    def compose(self) -> ComposeResult:
        """Compose the edit modal UI"""
        with Container(id="edit-container"):
            yield Label(
                f"✏️ EDITAR PACIENTE: {self.paciente.get('nombre', 'N/A')}",
                id="edit-title"
            )

            # Nombre
            with Horizontal(classes="field-row"):
                yield Label("Nombre:", classes="field-label")
                yield Input(
                    value=self.paciente.get('nombre', ''),
                    placeholder="Nombre completo",
                    id="input-nombre",
                    classes="field-input"
                )

            # Edad
            with Horizontal(classes="field-row"):
                yield Label("Edad:", classes="field-label")
                yield Input(
                    value=str(self.paciente.get('edad', '')),
                    placeholder="Edad (0-120)",
                    id="input-edad",
                    classes="field-input",
                    type="integer"
                )

            # Sexo
            with Horizontal(classes="field-row"):
                yield Label("Sexo:", classes="field-label")
                yield Select(
                    options=[
                        ("Masculino", "M"),
                        ("Femenino", "F"),
                        ("Otro", "O"),
                    ],
                    value=self.paciente.get('sexo', 'M'),
                    id="select-sexo",
                    classes="field-input",
                    allow_blank=False
                )

            # CURP
            with Horizontal(classes="field-row"):
                yield Label("CURP:", classes="field-label")
                yield Input(
                    value=self.paciente.get('curp', ''),
                    placeholder="CURP (18 caracteres)",
                    id="input-curp",
                    classes="field-input",
                    max_length=18
                )

            # Teléfono
            with Horizontal(classes="field-row"):
                yield Label("Teléfono:", classes="field-label")
                yield Input(
                    value=self.paciente.get('telefono', ''),
                    placeholder="Teléfono",
                    id="input-telefono",
                    classes="field-input"
                )

            # Contacto de emergencia
            with Horizontal(classes="field-row"):
                yield Label("Contacto emergencia:", classes="field-label")
                yield Input(
                    value=self.paciente.get('contacto_emergencia', ''),
                    placeholder="Nombre y teléfono de contacto",
                    id="input-contacto",
                    classes="field-input"
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
        """Save patient changes"""
        # Collect form data
        nombre = self.query_one("#input-nombre", Input).value.strip()
        edad_str = self.query_one("#input-edad", Input).value.strip()
        sexo = self.query_one("#select-sexo", Select).value
        curp = self.query_one("#input-curp", Input).value.strip()
        telefono = self.query_one("#input-telefono", Input).value.strip()
        contacto = self.query_one("#input-contacto", Input).value.strip()

        # Validaciones
        if not nombre or len(nombre) < 3:
            self.notify("❌ El nombre debe tener al menos 3 caracteres", severity="error")
            return

        # Validar edad
        try:
            edad = int(edad_str) if edad_str else None
            if edad is not None and (edad < 0 or edad > 120):
                self.notify("❌ La edad debe estar entre 0 y 120", severity="error")
                return
        except ValueError:
            self.notify("❌ La edad debe ser un número", severity="error")
            return

        # Validar CURP (opcional, pero si se proporciona debe tener 18 caracteres)
        if curp and len(curp) != 18:
            self.notify("❌ El CURP debe tener exactamente 18 caracteres", severity="error")
            return

        # Save to database
        result = await asyncio.to_thread(
            self._save_to_db,
            nombre, edad, sexo, curp, telefono, contacto
        )

        if result['success']:
            self.notify("✓ Paciente actualizado exitosamente", severity="information")
            self.dismiss({'action': 'updated', 'id_paciente': self.paciente['id_paciente']})
        else:
            self.notify(f"❌ Error: {result['error']}", severity="error")

    def _save_to_db(self, nombre, edad, sexo, curp, telefono, contacto) -> Dict[str, Any]:
        """Save patient to database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import db, Paciente
            import logging
            logger = logging.getLogger(__name__)

            try:
                paciente = Paciente.query.get(self.paciente['id_paciente'])
                if not paciente:
                    return {'success': False, 'error': 'Paciente no encontrado'}

                # Update fields
                paciente.nombre = nombre
                paciente.edad = edad
                paciente.sexo = sexo
                paciente.curp = curp if curp else None
                paciente.telefono = telefono if telefono else None
                paciente.contacto_emergencia = contacto if contacto else None

                db.session.commit()

                logger.info(f"[PACIENTE-UPDATE] Paciente {paciente.id_paciente} actualizado por trabajador social")

                return {'success': True}

            except Exception as e:
                db.session.rollback()
                logger.error(f"[PACIENTE-UPDATE] Error: {e}")
                return {'success': False, 'error': str(e)}


class PacienteDetailModal(ModalScreen):
    """Modal for viewing patient details"""

    CSS = """
    PacienteDetailModal {
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

    def __init__(self, paciente: Dict[str, Any]):
        super().__init__()
        self.paciente = paciente

    def compose(self) -> ComposeResult:
        """Compose the detail modal UI"""
        with Container(id="detail-container"):
            yield Label(
                f"👤 DETALLE DE PACIENTE",
                id="detail-title"
            )

            # Patient info section
            with Vertical(classes="detail-section"):
                yield Label("INFORMACIÓN PERSONAL", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("ID:", classes="field-label")
                    yield Static(str(self.paciente.get('id_paciente', 'N/A')), classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Nombre:", classes="field-label")
                    yield Static(self.paciente.get('nombre', 'N/A'), classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Edad:", classes="field-label")
                    yield Static(f"{self.paciente.get('edad', 'N/A')} años", classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Sexo:", classes="field-label")
                    sexo = self.paciente.get('sexo', 'N/A')
                    sexo_text = {'M': 'Masculino', 'F': 'Femenino', 'O': 'Otro'}.get(sexo, sexo)
                    yield Static(sexo_text, classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("CURP:", classes="field-label")
                    yield Static(self.paciente.get('curp', 'N/A'), classes="field-value")

            # Contact info section
            with Vertical(classes="detail-section"):
                yield Label("INFORMACIÓN DE CONTACTO", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Teléfono:", classes="field-label")
                    yield Static(self.paciente.get('telefono', 'N/A'), classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Contacto de emergencia:", classes="field-label")
                    yield Static(self.paciente.get('contacto_emergencia', 'N/A'), classes="field-value")

            # Buttons
            with Horizontal(id="button-container"):
                yield Button("← Cerrar", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "close-btn":
            self.dismiss()


class PacientesScreen(Screen):
    """
    Screen for managing all patients (trabajador social only)
    Features: DataTable, Search, View details, Edit
    """

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
    ]

    CSS = """
    PacientesScreen {
        background: $surface;
    }

    #pacientes-header {
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

    #search-input {
        width: 50;
        margin-right: 2;
    }

    #pacientes-table {
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
    pacientes_data: reactive[List[Dict[str, Any]]] = reactive([], init=False)
    search_query: reactive[str] = reactive("")
    is_loading: reactive[bool] = reactive(False)

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}
        self.filtered_pacientes: List[Dict[str, Any]] = []

        # Verificar permisos
        if self.user_info.get('rol') != 'trabajador_social':
            self.notify("❌ Acceso denegado: Solo trabajadores sociales", severity="error")

    def compose(self) -> ComposeResult:
        """Compose the pacientes screen UI"""

        # Header with stats
        with Container(id="pacientes-header"):
            yield Label("👥 GESTIÓN DE PACIENTES", id="header-title")

            # Display user info
            user_display = self.user_info.get('nombre') or self.user_info.get('username', self.username)
            stats_text = f"👤 {user_display} | Nodo {self.bully_manager.node_id}"
            yield Label(stats_text, id="header-stats")

        # Toolbar with search
        with Horizontal(id="toolbar"):
            yield Input(
                placeholder="🔍 Buscar por nombre o CURP...",
                id="search-input"
            )

        # DataTable for patients
        yield DataTable(id="pacientes-table", zebra_stripes=True, cursor_type="row")

        # Status bar
        yield Static("", id="status-bar")

        # Footer with shortcuts
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted"""
        # Setup DataTable columns
        table = self.query_one("#pacientes-table", DataTable)
        table.add_columns(
            "ID",
            "Nombre",
            "Edad",
            "Sexo",
            "CURP",
            "Teléfono"
        )

        # Load initial data
        self.load_pacientes()

    @work(exclusive=True)
    async def load_pacientes(self) -> None:
        """Load patients from database asynchronously"""
        self.is_loading = True
        self.update_status("⏳ Cargando pacientes...")

        try:
            # Run DB query in thread pool to avoid blocking UI
            pacientes = await asyncio.to_thread(self._fetch_pacientes_from_db)

            # Update reactive state (triggers watch_pacientes_data)
            self.pacientes_data = pacientes

            self.update_status(f"✓ {len(pacientes)} pacientes cargados")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            self.notify(f"Error al cargar pacientes: {str(e)}", severity="error")
        finally:
            self.is_loading = False

    def _fetch_pacientes_from_db(self) -> List[Dict[str, Any]]:
        """Fetch patients from database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import Paciente

            pacientes = Paciente.query.filter_by(activo=1).order_by(Paciente.nombre).all()

            return [{
                'id_paciente': p.id_paciente,
                'nombre': p.nombre,
                'edad': p.edad,
                'sexo': p.sexo,
                'curp': p.curp,
                'telefono': p.telefono,
                'contacto_emergencia': p.contacto_emergencia
            } for p in pacientes]

    def watch_pacientes_data(self, pacientes: List[Dict[str, Any]]) -> None:
        """React to changes in pacientes data"""
        self.apply_filters()

    def watch_search_query(self, query: str) -> None:
        """React to search query changes"""
        self.apply_filters()

    def apply_filters(self) -> None:
        """Apply search to pacientes data"""
        # Start with all pacientes
        filtered = self.pacientes_data.copy()

        # Apply search query
        query = self.search_query.lower().strip()
        if query:
            filtered = [
                p for p in filtered
                if (
                    query in str(p.get('nombre', '')).lower() or
                    query in str(p.get('curp', '')).lower()
                )
            ]

        self.filtered_pacientes = filtered
        self.update_table()

    def update_table(self) -> None:
        """Update DataTable with filtered pacientes"""
        table = self.query_one("#pacientes-table", DataTable)
        table.clear()

        for paciente in self.filtered_pacientes:
            # Add row to table
            table.add_row(
                str(paciente.get('id_paciente', '')),
                paciente.get('nombre', ''),
                str(paciente.get('edad', 'N/A')),
                paciente.get('sexo', 'N/A'),
                paciente.get('curp', 'N/A') or '-',
                paciente.get('telefono', 'N/A') or '-',
                key=paciente.get('id_paciente', '')
            )

        # Update status bar
        total = len(self.pacientes_data)
        showing = len(self.filtered_pacientes)

        if total == showing:
            self.update_status(f"📊 Mostrando {total} pacientes")
        else:
            self.update_status(f"📊 Mostrando {showing} de {total} pacientes")

    def update_status(self, message: str) -> None:
        """Update status bar message"""
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(message)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        if event.input.id == "search-input":
            self.search_query = event.value

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection - show detail or edit modal"""
        if event.row_key:
            # Find the paciente by id
            paciente_id = event.row_key.value

            paciente = next(
                (p for p in self.filtered_pacientes if p.get('id_paciente') == paciente_id),
                None
            )

            if paciente:
                # Show edit modal directly
                def handle_edit_result(result):
                    if result and result.get('action') == 'updated':
                        self.notify("✓ Paciente actualizado", severity="information")
                        self.load_pacientes()

                self.app.push_screen(
                    EditarPacienteModal(paciente, self.flask_app),
                    handle_edit_result
                )

    def action_refresh(self) -> None:
        """Refresh pacientes data"""
        self.notify("🔄 Actualizando pacientes...", severity="information")
        self.load_pacientes()


# Export
__all__ = ['PacientesScreen', 'PacienteDetailModal', 'EditarPacienteModal']
