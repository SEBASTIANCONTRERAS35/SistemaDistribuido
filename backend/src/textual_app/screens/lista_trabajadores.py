"""
Lista de Trabajadores Sociales Screen - Read-only view of all social workers
For doctors to see social workers in the system
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


class ListaTrabajadoresScreen(Screen):
    """
    Read-only screen showing all social workers
    Compact design - no toolbar, uses keyboard shortcuts
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("r", "refresh", "Actualizar", show=True),
        Binding("down", "focus_next", show=False),
        Binding("up", "focus_previous", show=False),
    ]

    CSS = """
    ListaTrabajadoresScreen {
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
        self.trabajadores_data: List[Dict] = []

    def compose(self) -> ComposeResult:
        """Compose the screen UI - Compact, no toolbar"""
        with Container(id="header-container"):
            yield Label("TRABAJADORES SOCIALES | r:Actualizar | esc:Volver", id="header-title")

        yield DataTable(id="trabajadores-table", zebra_stripes=True)
        yield Static("Cargando...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen"""
        table = self.query_one("#trabajadores-table", DataTable)
        table.add_columns("Nombre", "Sala", "Estado")
        self.load_trabajadores()

    def action_refresh(self) -> None:
        """Refresh the data"""
        self.load_trabajadores()

    @work(exclusive=True)
    async def load_trabajadores(self) -> None:
        """Load social workers from database"""
        status = self.query_one("#status-bar", Static)
        status.update("Cargando trabajadores sociales...")

        try:
            data = await asyncio.to_thread(self._fetch_trabajadores)
            self.trabajadores_data = data

            table = self.query_one("#trabajadores-table", DataTable)
            table.clear()

            for trabajador in data:
                estado = "ACT" if trabajador['activo'] else "INACT"

                table.add_row(
                    trabajador['nombre'][:25],
                    f"S{trabajador['id_sala']}",
                    estado,
                    key=str(trabajador['id_trabajador'])
                )

            activos = sum(1 for t in data if t['activo'])
            status.update(f"Total: {len(data)} trabajadores sociales | Activos: {activos}")

        except Exception as e:
            status.update(f"Error: {str(e)}")

    def _fetch_trabajadores(self) -> List[Dict]:
        """Fetch social workers from database"""
        with self.flask_app.app_context():
            from models import TrabajadorSocial
            from auth import get_active_sala_ids

            # Obtener salas de nodos activos en el cluster
            active_salas = get_active_sala_ids(self.bully_manager)

            query = TrabajadorSocial.query
            if active_salas:
                query = query.filter(TrabajadorSocial.id_sala.in_(active_salas))

            trabajadores = query.order_by(TrabajadorSocial.id_sala, TrabajadorSocial.nombre).all()
            result = []

            for trabajador in trabajadores:
                result.append({
                    'id_trabajador': trabajador.id_trabajador,
                    'nombre': trabajador.nombre,
                    'id_sala': trabajador.id_sala,
                    'activo': trabajador.activo
                })

            return result


# Export
__all__ = ['ListaTrabajadoresScreen']
