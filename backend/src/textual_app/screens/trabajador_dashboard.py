"""
Trabajador Social Dashboard - Main navigation hub
Provides access to all trabajador social features
"""

from typing import Dict, Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Label, Static
from textual.containers import Container, Vertical, Grid
from textual.binding import Binding


class TrabajadorDashboard(Screen):
    """
    Dashboard principal para Trabajador Social
    Provides navigation to all trabajador social features
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Cerrar Sesión", show=True),
        Binding("ctrl+b", "show_cluster", "Cluster Bully", show=True),
    ]

    CSS = """
    TrabajadorDashboard {
        background: $surface;
    }

    #dashboard-header {
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

    #header-info {
        color: $surface;
        text-align: center;
        margin-top: 1;
    }

    #main-container {
        width: 100%;
        height: 1fr;
        align: center middle;
    }

    #menu-grid {
        width: 70;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 3;
    }

    .menu-button {
        width: 100%;
        height: 5;
        margin: 1 0;
    }

    #footer-info {
        background: $panel;
        color: $text-muted;
        padding: 0 2;
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
        if self.user_info.get('rol') != 'trabajador_social':
            self.notify("❌ Acceso denegado: Solo trabajadores sociales", severity="error")

    def compose(self) -> ComposeResult:
        """Compose the dashboard UI"""

        # Header
        with Container(id="dashboard-header"):
            yield Label("🏥 PANEL DE TRABAJADOR SOCIAL", id="header-title")

            # Display user info
            user_display = self.user_info.get('nombre') or self.user_info.get('username', self.username)
            node_info = f"👤 {user_display} | Nodo {self.bully_manager.node_id} | {self.bully_manager.state.value.upper()}"
            yield Label(node_info, id="header-info")

        # Main container with menu
        with Container(id="main-container"):
            with Vertical(id="menu-grid"):
                yield Label("Seleccione una opción:", classes="section-title")

                # Main menu buttons
                yield Button(
                    "📋 Visitas de Emergencia",
                    variant="primary",
                    id="btn-visitas",
                    classes="menu-button"
                )

                yield Button(
                    "👥 Gestionar Pacientes",
                    variant="primary",
                    id="btn-pacientes",
                    classes="menu-button"
                )

                yield Button(
                    "👨‍⚕️ Estado de Doctores",
                    variant="primary",
                    id="btn-doctores",
                    classes="menu-button"
                )

                yield Button(
                    "🛏️ Estado de Camas",
                    variant="primary",
                    id="btn-camas",
                    classes="menu-button"
                )

                yield Button(
                    "👔 Gestionar Trabajadores",
                    variant="primary",
                    id="btn-trabajadores",
                    classes="menu-button"
                )

                # Separator
                yield Static("")

                yield Button(
                    "← Cerrar Sesión",
                    variant="error",
                    id="btn-logout",
                    classes="menu-button"
                )

        # Footer
        yield Static(
            "Utilice las teclas de navegación o haga clic en los botones | Ctrl+B: Ver Cluster Bully",
            id="footer-info"
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id

        if button_id == "btn-visitas":
            self.action_visitas()
        elif button_id == "btn-pacientes":
            self.action_pacientes()
        elif button_id == "btn-doctores":
            self.action_doctores()
        elif button_id == "btn-camas":
            self.action_camas()
        elif button_id == "btn-trabajadores":
            self.action_trabajadores()
        elif button_id == "btn-logout":
            self.action_logout()

    def action_visitas(self) -> None:
        """Navigate to Visitas screen"""
        from .visitas import VisitasScreen
        self.app.push_screen(
            VisitasScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_pacientes(self) -> None:
        """Navigate to Pacientes screen"""
        from .pacientes import PacientesScreen
        self.app.push_screen(
            PacientesScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_doctores(self) -> None:
        """Navigate to Doctores screen"""
        from .doctores import DoctoresScreen
        self.app.push_screen(
            DoctoresScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_camas(self) -> None:
        """Navigate to Camas screen"""
        from .camas import CamasScreen
        self.app.push_screen(
            CamasScreen(
                self.flask_app,
                self.bully_manager,
                self.username,
                self.user_info
            )
        )

    def action_trabajadores(self) -> None:
        """Navigate to Trabajadores screen"""
        from .trabajadores import TrabajadoresScreen
        self.app.push_screen(
            TrabajadoresScreen(
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
__all__ = ['TrabajadorDashboard']
