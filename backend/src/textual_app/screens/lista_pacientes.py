"""
Lista de Pacientes Screen - Read-only view of all patients in the system
For doctors to see patient information
Compact design for small terminals
"""

import asyncio
from typing import Dict, Any, List

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Label, Static, DataTable
from textual.containers import Container
from textual.binding import Binding
from textual import work


class ListaPacientesScreen(Screen):
    """
    Read-only screen showing all patients
    Compact design - no toolbar, uses keyboard shortcuts
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("r", "refresh", "Actualizar", show=True),
        Binding("down", "focus_next", show=False),
        Binding("up", "focus_previous", show=False),
    ]

    CSS = """
    ListaPacientesScreen {
        background: $surface;
    }

    #header-container {
        background: $primary;
        color: $surface;
        padding: 0 2;
        dock: top;
        height: 1;
    }

    #header-title {
        text-style: bold;
        color: $surface;
    }

    #status-bar {
        height: 1;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
        dock: bottom;
    }

    DataTable {
        height: 1fr;
    }
    """

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}
        self.pacientes_data: List[Dict] = []

    def compose(self) -> ComposeResult:
        """Compose the screen UI - Compact, no toolbar"""
        with Container(id="header-container"):
            yield Label("PACIENTES (Solo Lectura) | r:Actualizar | esc:Volver", id="header-title")

        yield DataTable(id="pacientes-table", zebra_stripes=True)
        yield Static("Cargando...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen"""
        table = self.query_one("#pacientes-table", DataTable)
        table.add_columns("Nombre", "Edad", "Sexo", "Visitas")
        self.load_pacientes()

    def action_refresh(self) -> None:
        """Refresh the data"""
        self.load_pacientes()

    @work(exclusive=True)
    async def load_pacientes(self) -> None:
        """Load patients from database"""
        status = self.query_one("#status-bar", Static)
        status.update("Cargando pacientes...")

        try:
            data = await asyncio.to_thread(self._fetch_pacientes)
            self.pacientes_data = data

            table = self.query_one("#pacientes-table", DataTable)
            table.clear()

            for paciente in data:
                sexo_display = "M" if paciente['sexo'] == 'M' else "F"
                visitas_activas = paciente.get('visitas_activas', 0)

                table.add_row(
                    paciente['nombre'][:25],
                    str(paciente['edad']) if paciente['edad'] else '-',
                    sexo_display,
                    str(visitas_activas),
                    key=str(paciente['id_paciente'])
                )

            con_visitas = sum(1 for p in data if p.get('visitas_activas', 0) > 0)
            status.update(f"Total: {len(data)} pacientes | Con visitas activas: {con_visitas}")

        except Exception as e:
            status.update(f"Error: {str(e)}")

    def _fetch_pacientes(self) -> List[Dict]:
        """Fetch patients from database"""
        with self.flask_app.app_context():
            from models import Paciente, VisitaEmergencia

            pacientes = Paciente.query.filter_by(activo=True).order_by(Paciente.nombre).all()
            result = []

            for paciente in pacientes:
                # Count active visits
                visitas_activas = VisitaEmergencia.query.filter_by(
                    id_paciente=paciente.id_paciente,
                    estado='activa'
                ).count()

                result.append({
                    'id_paciente': paciente.id_paciente,
                    'nombre': paciente.nombre,
                    'edad': paciente.edad,
                    'sexo': paciente.sexo,
                    'visitas_activas': visitas_activas
                })

            return result


# Export
__all__ = ['ListaPacientesScreen']
