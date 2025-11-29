"""
Camas Screen - View all beds across all salas
Read-only view for trabajador social to monitor bed status
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


class CamasScreen(Screen):
    """
    Screen for viewing all beds (trabajador social only)
    Features: DataTable, Filters by sala and occupancy status
    """

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
    ]

    CSS = """
    CamasScreen {
        background: $surface;
    }

    #camas-header {
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

    #filter-estado {
        width: 20;
        margin-right: 2;
    }

    #camas-table {
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

    .libre {
        color: $success;
        text-style: bold;
    }

    .ocupada {
        color: $error;
        text-style: bold;
    }
    """

    # Reactive state
    camas_data: reactive[List[Dict[str, Any]]] = reactive([], init=False)
    filter_sala: reactive[str] = reactive("todas")
    filter_estado: reactive[str] = reactive("todos")
    is_loading: reactive[bool] = reactive(False)

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}
        self.filtered_camas: List[Dict[str, Any]] = []

        # Verificar permisos
        if self.user_info.get('rol') != 'trabajador_social':
            self.notify("❌ Acceso denegado: Solo trabajadores sociales", severity="error")

    def compose(self) -> ComposeResult:
        """Compose the camas screen UI"""

        # Header with stats
        with Container(id="camas-header"):
            yield Label("🛏️ ESTADO DE CAMAS - TODAS LAS SALAS", id="header-title")

            # Display user info
            user_display = self.user_info.get('nombre') or self.user_info.get('username', self.username)
            stats_text = f"👤 {user_display} | Nodo {self.bully_manager.node_id}"
            yield Label(stats_text, id="header-stats")

        # Toolbar with filters
        with Horizontal(id="toolbar"):
            # Selector dinámico de salas - se popula en load_camas
            yield Select(
                options=[("Todas las salas", "todas")],  # Placeholder, se actualiza dinámicamente
                value="todas",
                id="filter-sala",
                allow_blank=False
            )

            yield Select(
                options=[
                    ("Todos", "todos"),
                    ("Libre", "libre"),
                    ("Ocupada", "ocupada"),
                ],
                value="todos",
                id="filter-estado",
                allow_blank=False
            )

        # DataTable for beds
        yield DataTable(id="camas-table", zebra_stripes=True, cursor_type="row")

        # Status bar
        yield Static("", id="status-bar")

        # Footer with shortcuts
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted"""
        # Setup DataTable columns
        table = self.query_one("#camas-table", DataTable)
        table.add_columns(
            "Sala",
            "Cama #",
            "Estado",
            "Paciente Actual",
            "Visita"
        )

        # Load initial data
        self.load_camas()

    @work(exclusive=True)
    async def load_camas(self) -> None:
        """Load beds from database asynchronously"""
        self.is_loading = True
        self.update_status("⏳ Cargando camas...")

        try:
            # Run DB query in thread pool to avoid blocking UI
            result = await asyncio.to_thread(self._fetch_camas_from_db)

            # Actualizar el selector de filtro dinámicamente
            filter_sala = self.query_one("#filter-sala", Select)
            filter_sala.set_options(result['salas_filter'])

            # Update reactive state (triggers watch_camas_data)
            self.camas_data = result['camas']

            self.update_status(f"✓ {len(result['camas'])} camas cargadas")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            self.notify(f"Error al cargar camas: {str(e)}", severity="error")
        finally:
            self.is_loading = False

    def _fetch_camas_from_db(self) -> Dict[str, Any]:
        """Fetch beds and salas from database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import Cama, Paciente, VisitaEmergencia, Sala
            from auth import get_active_sala_ids
            from sqlalchemy.orm import joinedload

            # Obtener salas de nodos activos en el cluster
            active_salas = get_active_sala_ids(self.bully_manager)

            # Query con filtro por salas activas
            query = Cama.query.options(
                joinedload(Cama.sala),
                joinedload(Cama.paciente_actual)
            )

            if active_salas:
                query = query.filter(Cama.id_sala.in_(active_salas))

            camas = query.order_by(Cama.id_sala, Cama.numero).all()

            result_camas = []
            for cama in camas:
                # Buscar visita activa en esta cama
                visita_activa = None
                if cama.ocupada and cama.id_paciente:
                    visita_activa = VisitaEmergencia.query.filter_by(
                        id_cama=cama.id_cama,
                        estado='activa'
                    ).first()

                result_camas.append({
                    'id_cama': cama.id_cama,
                    'sala': cama.sala.numero if cama.sala else 'N/A',
                    'id_sala': cama.id_sala,
                    'numero': cama.numero,
                    'ocupada': cama.ocupada,
                    'paciente': cama.paciente_actual.nombre if cama.paciente_actual else None,
                    'visita': visita_activa.folio if visita_activa else None
                })

            # Cargar salas dinámicamente para el filtro (solo activas en cluster)
            query_salas = Sala.query.filter_by(activa=True)
            if active_salas:
                query_salas = query_salas.filter(Sala.id_sala.in_(active_salas))
            salas = query_salas.order_by(Sala.numero).all()

            salas_filter = [("Todas las salas", "todas")]
            salas_filter.extend([(f"Sala {s.numero}", str(s.id_sala)) for s in salas])

            return {
                'camas': result_camas,
                'salas_filter': salas_filter
            }

    def watch_camas_data(self, camas: List[Dict[str, Any]]) -> None:
        """React to changes in camas data"""
        self.apply_filters()

    def watch_filter_sala(self, sala: str) -> None:
        """React to filter changes"""
        self.apply_filters()

    def watch_filter_estado(self, estado: str) -> None:
        """React to filter changes"""
        self.apply_filters()

    def apply_filters(self) -> None:
        """Apply filters to camas data"""
        # Start with all camas
        filtered = self.camas_data.copy()

        # Apply sala filter
        if self.filter_sala != "todas":
            sala_num = int(self.filter_sala)
            filtered = [c for c in filtered if c.get('id_sala') == sala_num]

        # Apply estado filter
        if self.filter_estado == "libre":
            filtered = [c for c in filtered if not c.get('ocupada')]
        elif self.filter_estado == "ocupada":
            filtered = [c for c in filtered if c.get('ocupada')]

        self.filtered_camas = filtered
        self.update_table()

    def update_table(self) -> None:
        """Update DataTable with filtered camas"""
        table = self.query_one("#camas-table", DataTable)
        table.clear()

        for cama in self.filtered_camas:
            # Create estado with color
            ocupada = cama.get('ocupada', False)
            if ocupada:
                estado_text = Text("🔴 OCUPADA", style="bold red")
            else:
                estado_text = Text("🟢 LIBRE", style="bold green")

            # Paciente y visita
            paciente = cama.get('paciente') or '-'
            visita = cama.get('visita') or '-'

            # Add row to table
            table.add_row(
                f"Sala {cama.get('sala', '')}",
                f"#{cama.get('numero', '')}",
                estado_text,
                paciente,
                visita,
                key=cama.get('id_cama', '')
            )

        # Update status bar
        total = len(self.camas_data)
        showing = len(self.filtered_camas)

        # Count libres/ocupadas
        libres = sum(1 for c in self.filtered_camas if not c.get('ocupada'))
        ocupadas = showing - libres

        if total == showing:
            self.update_status(f"📊 {total} camas | 🟢 {libres} libres | 🔴 {ocupadas} ocupadas")
        else:
            self.update_status(f"📊 Mostrando {showing} de {total} camas | 🟢 {libres} libres | 🔴 {ocupadas} ocupadas")

    def update_status(self, message: str) -> None:
        """Update status bar message"""
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(message)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter select changes"""
        if event.select.id == "filter-sala":
            self.filter_sala = str(event.value)
        elif event.select.id == "filter-estado":
            self.filter_estado = str(event.value)

    def action_refresh(self) -> None:
        """Refresh camas data"""
        self.notify("🔄 Actualizando camas...", severity="information")
        self.load_camas()


# Export
__all__ = ['CamasScreen']
