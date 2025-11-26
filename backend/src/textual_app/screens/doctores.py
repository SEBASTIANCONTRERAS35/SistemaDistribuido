"""
Doctores Screen - View all doctors across all salas
Read-only view for trabajador social to monitor doctor status
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


class DoctoresScreen(Screen):
    """
    Screen for viewing all doctors (trabajador social only)
    Features: DataTable, Filters by sala and availability
    """

    BINDINGS = [
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
            yield Select(
                options=[
                    ("Todas las salas", "todas"),
                    ("Sala 1", "1"),
                    ("Sala 2", "2"),
                    ("Sala 3", "3"),
                    ("Sala 4", "4"),
                ],
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
            doctores = await asyncio.to_thread(self._fetch_doctores_from_db)

            # Update reactive state (triggers watch_doctores_data)
            self.doctores_data = doctores

            self.update_status(f"✓ {len(doctores)} doctores cargados")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            self.notify(f"Error al cargar doctores: {str(e)}", severity="error")
        finally:
            self.is_loading = False

    def _fetch_doctores_from_db(self) -> List[Dict[str, Any]]:
        """Fetch doctors from database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import Doctor, VisitaEmergencia
            from sqlalchemy.orm import joinedload

            # Eager load sala
            doctores = Doctor.query.options(
                joinedload(Doctor.sala)
            ).filter_by(activo=True).order_by(Doctor.nombre).all()

            result = []
            for doc in doctores:
                # Buscar visita activa del doctor
                visita_activa = VisitaEmergencia.query.filter_by(
                    id_doctor=doc.id_doctor,
                    estado='activa'
                ).first()

                result.append({
                    'id_doctor': doc.id_doctor,
                    'nombre': doc.nombre,
                    'especialidad': doc.especialidad or 'General',
                    'sala': doc.sala.numero if doc.sala else 'N/A',
                    'id_sala': doc.id_sala,
                    'disponible': doc.disponible,
                    'visita_actual': visita_activa.folio if visita_activa else None
                })

            return result

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


# Export
__all__ = ['DoctoresScreen']
