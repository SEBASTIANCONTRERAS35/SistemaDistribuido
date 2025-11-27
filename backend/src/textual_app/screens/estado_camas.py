"""
Estado de Camas Screen - Read-only view of all beds in the system
For doctors to see bed availability across all salas
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


class EstadoCamasScreen(Screen):
    """
    Read-only screen showing bed status across all salas
    Compact design - no toolbar, uses keyboard shortcuts
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("r", "refresh", "Actualizar", show=True),
        Binding("down", "focus_next", show=False),
        Binding("up", "focus_previous", show=False),
    ]

    CSS = """
    EstadoCamasScreen {
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
        self.camas_data: List[Dict] = []

    def compose(self) -> ComposeResult:
        """Compose the screen UI - Compact, no toolbar"""
        with Container(id="header-container"):
            yield Label("CAMAS (Solo Lectura) | r:Actualizar | esc:Volver", id="header-title")

        yield DataTable(id="camas-table", zebra_stripes=True)
        yield Static("Cargando...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen"""
        table = self.query_one("#camas-table", DataTable)
        table.add_columns("Num", "Sala", "Estado", "Paciente")
        self.load_camas()

    def action_refresh(self) -> None:
        """Refresh the data"""
        self.load_camas()

    @work(exclusive=True)
    async def load_camas(self) -> None:
        """Load beds from database"""
        status = self.query_one("#status-bar", Static)
        status.update("Cargando camas...")

        try:
            data = await asyncio.to_thread(self._fetch_camas)
            self.camas_data = data

            table = self.query_one("#camas-table", DataTable)
            table.clear()

            for cama in data:
                estado = "OCUP" if cama['ocupada'] else "LIBRE"
                paciente = cama.get('paciente_nombre', '-') or '-'
                table.add_row(
                    str(cama['numero']),
                    f"S{cama['id_sala']}",
                    estado,
                    paciente[:20] if paciente else '-',
                    key=str(cama['id_cama'])
                )

            libres = sum(1 for c in data if not c['ocupada'])
            ocupadas = sum(1 for c in data if c['ocupada'])
            status.update(f"Total: {len(data)} camas | Libres: {libres} | Ocupadas: {ocupadas}")

        except Exception as e:
            status.update(f"Error: {str(e)}")

    def _fetch_camas(self) -> List[Dict]:
        """Fetch beds from database"""
        with self.flask_app.app_context():
            from models import Cama, Paciente

            camas = Cama.query.order_by(Cama.id_sala, Cama.numero).all()
            result = []

            for cama in camas:
                paciente_nombre = None
                if cama.id_paciente:
                    paciente = Paciente.query.get(cama.id_paciente)
                    if paciente:
                        paciente_nombre = paciente.nombre

                result.append({
                    'id_cama': cama.id_cama,
                    'numero': cama.numero,
                    'id_sala': cama.id_sala,
                    'ocupada': cama.ocupada,
                    'paciente_nombre': paciente_nombre
                })

            return result


# Export
__all__ = ['EstadoCamasScreen']
