"""
Visitas Screen - Main screen for viewing and managing emergency visits
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any

from textual.app import ComposeResult
from textual.screen import Screen
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


class VisitasScreen(Screen):
    """
    Main screen for viewing all emergency visits
    Features: DataTable, Search, Filter, Detail view
    """

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("ctrl+n", "new_visit", "Nueva Visita", show=True),
        Binding("ctrl+b", "show_cluster", "Cluster Bully", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
        # Navegación con flechas (sin mouse)
        Binding("down", "focus_next", "↓", show=False),
        Binding("up", "focus_previous", "↑", show=False),
        Binding("left", "focus_previous", "←", show=False),
        Binding("right", "focus_next", "→", show=False),
    ]

    CSS = """
    VisitasScreen {
        background: $surface;
    }

    #visitas-header {
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
        width: 40;
        margin-right: 2;
    }

    #filter-select {
        width: 20;
        margin-right: 2;
    }

    #new-visit-btn {
        min-width: 20;
    }

    #visitas-table {
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

    .estado-activa {
        color: $success;
        text-style: bold;
    }

    .estado-completada {
        color: $text-muted;
    }

    .estado-cancelada {
        color: $error;
        text-style: bold;
    }
    """

    # Reactive state
    visitas_data: reactive[List[Dict[str, Any]]] = reactive([], init=False)
    search_query: reactive[str] = reactive("")
    filter_estado: reactive[str] = reactive("todas")
    is_loading: reactive[bool] = reactive(False)

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}
        self.filtered_visitas: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Compose the visitas screen UI"""

        # Título personalizado según rol (solo doctor y trabajador_social)
        rol = self.user_info.get('rol', '')
        if rol == 'doctor':
            title = "📋 VISITAS DE EMERGENCIA"
        else:  # trabajador_social
            title = "📋 GESTIÓN DE VISITAS DE EMERGENCIA"

        # Header with stats
        with Container(id="visitas-header"):
            yield Label(title, id="header-title")
            # Display user with role if available (fallback to username if nombre not found)
            if self.user_info:
                user_display = self.user_info.get('nombre') or self.user_info.get('username', self.username)
                rol_display = f" ({self.user_info.get('rol_display', '')})" if self.user_info.get('rol_display') else ""
            else:
                user_display = self.username
                rol_display = ""
            stats_text = f"👤 {user_display}{rol_display} | Nodo {self.bully_manager.node_id} | {self.bully_manager.state.value.upper()}"
            yield Label(stats_text, id="header-stats")

        # Toolbar with search, filter, and new visit button (role-based)
        with Horizontal(id="toolbar"):
            yield Input(
                placeholder="🔍 Buscar por folio, paciente o doctor...",
                id="search-input"
            )
            # Build filter options based on role
            filter_options = [
                ("Todas", "todas"),
                ("Activas", "activa"),
                ("Completadas", "completada"),
                ("Canceladas", "cancelada"),
            ]
            # Add "Mis Visitas" option for doctors
            if rol == 'doctor':
                filter_options.insert(1, ("Mis Visitas", "mis_visitas"))

            yield Select(
                options=filter_options,
                value="mis_visitas" if rol == 'doctor' else "todas",
                id="filter-select",
                allow_blank=False
            )
            # Solo trabajador social puede crear visitas
            if rol == 'trabajador_social':
                yield Button("➕ Nueva Visita", variant="primary", id="new-visit-btn")

        # DataTable for visits
        yield DataTable(id="visitas-table", zebra_stripes=True, cursor_type="row")

        # Status bar
        yield Static("", id="status-bar")

        # Footer with shortcuts
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted"""
        # Setup DataTable columns
        table = self.query_one("#visitas-table", DataTable)
        table.add_columns(
            "Folio",
            "Paciente",
            "Doctor",
            "Sala",
            "Cama",
            "Estado",
            "Fecha/Hora"
        )

        # Load initial data
        self.load_visitas()

    @work(exclusive=True)
    async def load_visitas(self) -> None:
        """Load visits from database asynchronously"""
        self.is_loading = True
        self.update_status("⏳ Cargando visitas...")

        try:
            # Run DB query in thread pool to avoid blocking UI
            visitas = await asyncio.to_thread(self._fetch_visitas_from_db)

            # Update reactive state (triggers watch_visitas_data)
            self.visitas_data = visitas

            self.update_status(f"✓ {len(visitas)} visitas cargadas")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            self.notify(f"Error al cargar visitas: {str(e)}", severity="error")
        finally:
            self.is_loading = False

    def _fetch_visitas_from_db(self) -> List[Dict[str, Any]]:
        """Fetch visits from database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import VisitaEmergencia
            from sqlalchemy.orm import joinedload

            # Eager load todas las relaciones necesarias para to_dict()
            visitas = VisitaEmergencia.query.options(
                joinedload(VisitaEmergencia.paciente),
                joinedload(VisitaEmergencia.doctor),
                joinedload(VisitaEmergencia.cama),
                joinedload(VisitaEmergencia.sala),
                joinedload(VisitaEmergencia.trabajador_social)
            ).order_by(VisitaEmergencia.timestamp.desc()).all()

            return [v.to_dict() for v in visitas]

    def watch_visitas_data(self, visitas: List[Dict[str, Any]]) -> None:
        """React to changes in visitas data"""
        self.apply_filters()

    def watch_search_query(self, query: str) -> None:
        """React to search query changes"""
        self.apply_filters()

    def watch_filter_estado(self, estado: str) -> None:
        """React to filter changes"""
        self.apply_filters()

    def apply_filters(self) -> None:
        """Apply search and filter to visitas data"""
        # Start with all visitas
        filtered = self.visitas_data.copy()

        # Apply estado filter
        if self.filter_estado == "mis_visitas":
            # Filter by doctor's assigned visits (only for doctors)
            doctor_id = self.user_info.get('id_relacionado')
            if doctor_id:
                filtered = [v for v in filtered if v.get('id_doctor') == doctor_id]
        elif self.filter_estado != "todas":
            filtered = [v for v in filtered if v.get('estado') == self.filter_estado]

        # Apply search query
        query = self.search_query.lower().strip()
        if query:
            filtered = [
                v for v in filtered
                if (
                    query in str(v.get('folio', '')).lower() or
                    query in str(v.get('paciente', '')).lower() or
                    query in str(v.get('doctor', '')).lower()
                )
            ]

        self.filtered_visitas = filtered
        self.update_table()

    def update_table(self) -> None:
        """Update DataTable with filtered visitas"""
        table = self.query_one("#visitas-table", DataTable)
        table.clear()

        for visita in self.filtered_visitas:
            # Format timestamp
            timestamp_str = ""
            if visita.get('timestamp'):
                try:
                    dt = datetime.fromisoformat(visita['timestamp'].replace('Z', '+00:00'))
                    timestamp_str = dt.strftime('%d/%m %H:%M')
                except:
                    timestamp_str = visita['timestamp'][:16]

            # Create estado with color
            estado = visita.get('estado', 'desconocido')
            estado_text = Text(estado.upper())

            if estado == 'activa':
                estado_text.stylize("bold green")
            elif estado == 'completada':
                estado_text.stylize("dim")
            elif estado == 'cancelada':
                estado_text.stylize("bold red")

            # Add row to table
            table.add_row(
                visita.get('folio', ''),
                visita.get('paciente', ''),
                visita.get('doctor', ''),
                str(visita.get('sala', '')),
                str(visita.get('cama', '')),
                estado_text,
                timestamp_str,
                key=visita.get('id_visita', '')
            )

        # Update status bar
        total = len(self.visitas_data)
        showing = len(self.filtered_visitas)

        if total == showing:
            self.update_status(f"📊 Mostrando {total} visitas")
        else:
            self.update_status(f"📊 Mostrando {showing} de {total} visitas")

    def update_status(self, message: str) -> None:
        """Update status bar message"""
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(message)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        if event.input.id == "search-input":
            self.search_query = event.value

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter select changes"""
        if event.select.id == "filter-select":
            self.filter_estado = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "new-visit-btn":
            self.action_new_visit()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection - show detail modal"""
        import logging
        logger = logging.getLogger(__name__)

        if event.row_key:
            # Find the visita by id
            visita_id = event.row_key.value
            logger.warning(f"[DETALLE] Buscando visita con id: {visita_id}")

            visita = next(
                (v for v in self.filtered_visitas if v.get('id_visita') == visita_id),
                None
            )

            if visita:
                logger.warning(f"[DETALLE] Visita encontrada: {visita.get('folio')}")
                logger.warning(f"[DETALLE] Datos completos: paciente={visita.get('paciente')}, doctor={visita.get('doctor')}, sala={visita.get('sala')}, cama={visita.get('cama')}")

                # Import here to avoid circular dependency
                from .visita_detail import VisitDetailModal
                self.app.push_screen(
                    VisitDetailModal(
                        visita=visita,
                        flask_app=self.flask_app,
                        bully_manager=self.bully_manager,
                        username=self.username,
                        user_info=self.user_info
                    )
                )
            else:
                logger.error(f"[DETALLE] No se encontró visita con id {visita_id}")

    def action_refresh(self) -> None:
        """Refresh visitas data"""
        self.notify("🔄 Actualizando visitas...", severity="information")
        self.load_visitas()

    def action_new_visit(self) -> None:
        """Create new visit - only for trabajador_social"""
        # Verificar permisos
        if self.user_info.get('rol') != 'trabajador_social':
            self.notify("❌ No tienes permiso para crear visitas", severity="error")
            return

        from .simple_create_visit import SimpleCreateVisitScreen

        def handle_result(result):
            """Handle visit creation result"""
            if result and result.get('success'):
                self.notify(
                    f"✓ Visita {result['folio']} creada\nSala: {result.get('sala', '?')}\nDoctor: {result['doctor']}\nCama: {result['cama']}",
                    title="Visita Creada",
                    severity="information",
                    timeout=5
                )
                # Refresh table
                self.load_visitas()

        screen = SimpleCreateVisitScreen(self.flask_app, self.bully_manager, self.username, self.user_info)
        self.app.push_screen(screen, handle_result)

    def action_show_cluster(self) -> None:
        """Show Bully cluster visualization"""
        from .bully_cluster import BullyClusterScreen
        self.app.push_screen(BullyClusterScreen(self.bully_manager))


# Export
__all__ = ['VisitasScreen']
