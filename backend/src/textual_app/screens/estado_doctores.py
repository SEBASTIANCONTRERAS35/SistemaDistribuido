"""
Estado de Doctores Screen - Read-only view of all doctors in the system
For doctors to see other doctors' availability across all salas
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


class EstadoDoctoresScreen(Screen):
    """
    Read-only screen showing doctor status across all salas
    Compact design - no toolbar, uses keyboard shortcuts
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("down", "focus_next", show=False),
        Binding("up", "focus_previous", show=False),
    ]

    CSS = """
    EstadoDoctoresScreen {
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
        self.doctores_data: List[Dict] = []

    def compose(self) -> ComposeResult:
        """Compose the screen UI - Compact, no toolbar"""
        with Container(id="header-container"):
            yield Label("DOCTORES (Solo Lectura) | ctrl+r:Actualizar | esc:Volver", id="header-title")

        yield DataTable(id="doctores-table", zebra_stripes=True)
        yield Static("Cargando...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen"""
        table = self.query_one("#doctores-table", DataTable)
        table.add_columns("Nombre", "Especialidad", "Sala", "Estado")
        self.load_doctores()

    def action_refresh(self) -> None:
        """Refresh the data"""
        self.load_doctores()

    @work(exclusive=True)
    async def load_doctores(self) -> None:
        """Load doctors from database"""
        status = self.query_one("#status-bar", Static)
        status.update("Cargando doctores...")

        try:
            data = await asyncio.to_thread(self._fetch_doctores)
            self.doctores_data = data

            table = self.query_one("#doctores-table", DataTable)
            table.clear()

            # Highlight current user's row
            current_doctor_id = self.user_info.get('id_relacionado')

            for doctor in data:
                estado = "DISP" if doctor['disponible'] else "OCUP"
                especialidad = (doctor.get('especialidad') or '-')[:15]

                # Mark current doctor
                nombre = doctor['nombre'][:20]
                if doctor['id_doctor'] == current_doctor_id:
                    nombre = f"* {nombre}"

                table.add_row(
                    nombre,
                    especialidad,
                    f"S{doctor['id_sala']}",
                    estado,
                    key=str(doctor['id_doctor'])
                )

            disponibles = sum(1 for d in data if d['disponible'])
            ocupados = sum(1 for d in data if not d['disponible'])
            status.update(f"Total: {len(data)} doctores | Disponibles: {disponibles} | Ocupados: {ocupados}")

        except Exception as e:
            status.update(f"Error: {str(e)}")

    def _fetch_doctores(self) -> List[Dict]:
        """Fetch doctors from database"""
        with self.flask_app.app_context():
            from models import Doctor
            from auth import get_active_sala_ids

            # Obtener salas de nodos activos en el cluster
            active_salas = get_active_sala_ids(self.bully_manager)

            query = Doctor.query.filter_by(activo=True)
            if active_salas:
                query = query.filter(Doctor.id_sala.in_(active_salas))

            doctores = query.order_by(Doctor.id_sala, Doctor.nombre).all()
            result = []

            for doctor in doctores:
                result.append({
                    'id_doctor': doctor.id_doctor,
                    'nombre': doctor.nombre,
                    'especialidad': doctor.especialidad,
                    'id_sala': doctor.id_sala,
                    'disponible': doctor.disponible
                })

            return result


# Export
__all__ = ['EstadoDoctoresScreen']
