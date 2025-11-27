"""
Doctor Dashboard - Main navigation hub for doctors
Provides read-only access to system resources and ability to close own visits
Optimized for small terminals (min 1/4 screen height)
"""

from typing import Dict, Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Label, Static
from textual.containers import Container, Vertical, Grid
from textual.binding import Binding


class DoctorDashboard(Screen):
    """
    Dashboard principal para Doctores
    Provides read-only views and ability to close own visits
    Compact design for small terminals
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Cerrar Sesion", show=True),
        Binding("ctrl+b", "show_cluster", "Cluster Bully", show=True),
        Binding("f1", "help", "Ayuda", show=True),
        Binding("down", "focus_next", show=False),
        Binding("up", "focus_previous", show=False),
        Binding("tab", "focus_next", show=False),
        Binding("shift+tab", "focus_previous", show=False),
    ]

    CSS = """
    DoctorDashboard {
        background: $surface;
    }

    #dashboard-header {
        background: $success;
        color: $surface;
        padding: 0 2;
        dock: top;
        height: 3;
    }

    #header-title {
        text-style: bold;
        color: $surface;
        text-align: center;
    }

    #main-container {
        width: 100%;
        height: 1fr;
        align: center middle;
    }

    #menu-grid {
        width: 60;
        height: auto;
        background: $panel;
        border: solid $success;
        padding: 1;
        grid-size: 2;
        grid-gutter: 1;
    }

    .menu-button {
        width: 100%;
        height: 3;
    }

    #footer-info {
        background: $panel;
        color: $text-muted;
        padding: 0 1;
        dock: bottom;
        height: 1;
    }
    """

    def __init__(self, flask_app, bully_manager, username: str, user_info: Dict[str, Any] = None):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
        self.user_info = user_info or {}

        # Verificar permisos
        if self.user_info.get('rol') != 'doctor':
            self.notify("Acceso denegado: Solo doctores", severity="error")

    def compose(self) -> ComposeResult:
        """Compose the dashboard UI - Compact layout for small terminals"""

        # Compact Header - single line with all info
        with Container(id="dashboard-header"):
            user_display = self.user_info.get('nombre') or self.username
            node_state = self.bully_manager.state.value.upper()
            header_text = f"PANEL DEL DOCTOR | {user_display} | Nodo {self.bully_manager.node_id} ({node_state})"
            yield Label(header_text, id="header-title")

        # Main container with compact grid menu (2 columns)
        with Container(id="main-container"):
            with Grid(id="menu-grid"):
                # Row 1
                yield Button("Mis Visitas", variant="success", id="btn-visitas", classes="menu-button")
                yield Button("Camas", variant="primary", id="btn-camas", classes="menu-button")

                # Row 2
                yield Button("Doctores", variant="primary", id="btn-doctores", classes="menu-button")
                yield Button("Pacientes", variant="primary", id="btn-pacientes", classes="menu-button")

                # Row 3
                yield Button("Trabajadores", variant="primary", id="btn-trabajadores", classes="menu-button")
                yield Button("Salir", variant="error", id="btn-logout", classes="menu-button")

        # Compact Footer
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "btn-visitas":
            self.action_visitas()
        elif button_id == "btn-camas":
            self.action_camas()
        elif button_id == "btn-doctores":
            self.action_doctores()
        elif button_id == "btn-pacientes":
            self.action_pacientes()
        elif button_id == "btn-trabajadores":
            self.action_trabajadores()
        elif button_id == "btn-logout":
            self.action_logout()

    def action_visitas(self) -> None:
        """Navigate to Visitas screen (can close own visits)"""
        from .visitas import VisitasScreen
        self.app.push_screen(
            VisitasScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_camas(self) -> None:
        """Navigate to Camas screen (read-only)"""
        from .estado_camas import EstadoCamasScreen
        self.app.push_screen(
            EstadoCamasScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_doctores(self) -> None:
        """Navigate to Doctores screen (read-only)"""
        from .estado_doctores import EstadoDoctoresScreen
        self.app.push_screen(
            EstadoDoctoresScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_pacientes(self) -> None:
        """Navigate to Pacientes screen (read-only)"""
        from .lista_pacientes import ListaPacientesScreen
        self.app.push_screen(
            ListaPacientesScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_trabajadores(self) -> None:
        """Navigate to Trabajadores screen (read-only)"""
        from .lista_trabajadores import ListaTrabajadoresScreen
        self.app.push_screen(
            ListaTrabajadoresScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_logout(self) -> None:
        """Logout and return to login screen"""
        self.app.pop_screen()

    def action_show_cluster(self) -> None:
        """Show Bully cluster visualization"""
        from .bully_cluster import BullyClusterScreen
        self.app.push_screen(BullyClusterScreen(self.bully_manager))


# Export
__all__ = ['DoctorDashboard']
