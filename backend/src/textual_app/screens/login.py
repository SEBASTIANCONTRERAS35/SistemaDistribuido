"""
Login Screen - User authentication with real database validation
"""

import asyncio
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Button, Label, Footer
from textual.containers import Container, Vertical, Horizontal, Center
from textual.binding import Binding
from textual import work
from rich.text import Text
from rich.panel import Panel


class LoginScreen(Screen):
    """
    Login screen for user authentication with real database validation
    Validates credentials against Usuario table with bcrypt password hashing
    """

    # Navegación con flechas y Enter
    BINDINGS = [
        Binding("down", "focus_next", "↓ Siguiente", show=False),
        Binding("up", "focus_previous", "↑ Anterior", show=False),
        Binding("enter", "submit_login", "Ingresar", show=False),
        Binding("left", "focus_previous", "←", show=False),
        Binding("right", "focus_next", "→", show=False),
    ]

    CSS = """
    LoginScreen {
        align: center middle;
        background: $surface;
    }
    
    #login-container {
        width: 60;
        height: auto;
        border: heavy $primary;
        background: $panel;
        padding: 2;
    }
    
    #login-title {
        width: 100%;
        content-align: center middle;
        color: $primary;
        text-style: bold;
        margin-bottom: 2;
    }
    
    .input-label {
        margin-top: 1;
        color: $text;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    #button-container {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 2;
    }
    
    Button {
        margin: 0 1;
    }
    
    #status-message {
        width: 100%;
        content-align: center middle;
        margin-top: 1;
        min-height: 1;
    }
    
    #node-info {
        width: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: dim;
        margin-top: 2;
    }
    """
    
    def __init__(self, flask_app, bully_manager):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
    
    def compose(self) -> ComposeResult:
        """Compose the login screen"""
        with Center():
            with Container(id="login-container"):
                yield Label("🏥 SISTEMA MÉDICO", id="login-title")
                
                yield Label("Usuario:", classes="input-label")
                yield Input(placeholder="Ingrese su usuario", id="username-input")
                
                yield Label("Contraseña:", classes="input-label")
                yield Input(
                    placeholder="Ingrese su contraseña",
                    password=True,
                    id="password-input"
                )
                
                with Horizontal(id="button-container"):
                    yield Button("Ingresar", variant="primary", id="login-button")
                    yield Button("Salir", variant="error", id="exit-button")
                
                yield Static("", id="status-message")
                
                # Node info
                node_id = self.bully_manager.node_id
                state = self.bully_manager.state.value
                cluster_size = len(self.bully_manager.cluster_nodes) + 1
                
                node_info = f"Nodo {node_id} | {state.upper()} | {cluster_size} nodo(s) activo(s)"
                yield Label(node_info, id="node-info")

                # Instrucciones de navegación
                yield Label(
                    "[dim]↑↓: Navegar | Enter: Ingresar | Ctrl+C: Salir[/dim]",
                    id="nav-hints"
                )

            # Footer para mostrar atajos
            yield Footer()

    def on_mount(self) -> None:
        """Auto-focus username input when screen loads"""
        self.query_one("#username-input", Input).focus()

    def action_submit_login(self) -> None:
        """Enter key submits login from anywhere"""
        self.attempt_login()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "login-button":
            self.attempt_login()
        elif event.button.id == "exit-button":
            self.app.exit()
    
    @work(exclusive=True)
    async def attempt_login(self) -> None:
        """
        Attempt to log in the user with real database validation
        Validates username and password against Usuario table
        """
        username_input = self.query_one("#username-input", Input)
        password_input = self.query_one("#password-input", Input)
        status = self.query_one("#status-message", Static)

        username = username_input.value.strip()
        password = password_input.value.strip()

        # Client-side validation
        if not username or not password:
            status.update("[red]⚠ Por favor ingrese usuario y contraseña[/red]")
            return

        status.update("[yellow]⏳ Validando credenciales...[/yellow]")

        # Authenticate in thread pool to avoid blocking UI
        result = await asyncio.to_thread(
            self._validate_credentials,
            username,
            password
        )

        if result['success']:
            user_info = result['user_info']
            # Use nombre if available, otherwise use username
            display_name = user_info.get('nombre', user_info.get('username', 'Usuario'))
            status.update(f"[green]✓ Bienvenido, {display_name}! ({user_info['rol_display']})[/green]")

            # Small delay to show success message
            await asyncio.sleep(0.5)

            # Navigate based on user role
            rol = user_info.get('rol', '')

            if rol == 'trabajador_social':
                # Trabajador social -> Dashboard with all features
                from .trabajador_dashboard import TrabajadorDashboard
                self.app.push_screen(
                    TrabajadorDashboard(
                        self.flask_app,
                        self.bully_manager,
                        username,
                        user_info=user_info
                    )
                )
            else:
                # Doctor -> DoctorDashboard with read-only views
                from .doctor_dashboard import DoctorDashboard
                self.app.push_screen(
                    DoctorDashboard(
                        self.flask_app,
                        self.bully_manager,
                        username,
                        user_info=user_info
                    )
                )
        else:
            status.update(f"[red]❌ {result['error']}[/red]")
            # Clear password field on error
            password_input.value = ""

    def _validate_credentials(self, username: str, password: str) -> dict:
        """
        Validate user credentials against database (runs in thread pool)

        Returns:
            dict: {
                'success': bool,
                'user_info': dict or None,
                'error': str or None
            }
        """
        with self.flask_app.app_context():
            from models import Usuario
            from auth import get_user_info

            try:
                # Query user from database
                user = Usuario.query.filter_by(username=username).first()

                if not user:
                    return {
                        'success': False,
                        'error': 'Usuario no encontrado'
                    }

                # Check if user is active
                if not user.activo:
                    return {
                        'success': False,
                        'error': 'Usuario inactivo. Contacte al administrador.'
                    }

                # Verify password
                if not user.check_password(password):
                    return {
                        'success': False,
                        'error': 'Contraseña incorrecta'
                    }

                # Get extended user info
                user_info = get_user_info(user)

                return {
                    'success': True,
                    'user_info': user_info,
                    'error': None
                }

            except Exception as e:
                return {
                    'success': False,
                    'error': f'Error de autenticación: {str(e)}'
                }


class PlaceholderDashboard(Screen):
    """
    Temporary dashboard placeholder
    Will be replaced with real dashboard in FASE 4
    """
    
    def __init__(self, flask_app, bully_manager, username):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username
    
    def compose(self) -> ComposeResult:
        """Compose placeholder dashboard"""
        message = Text()
        message.append("\n\n")
        message.append(f"    ✓ Sesión iniciada: {self.username}\n\n", style="bold green")
        message.append(f"    Nodo: {self.bully_manager.node_id}\n", style="cyan")
        message.append(f"    Estado: {self.bully_manager.state.value}\n", style="yellow")
        message.append(f"    Cluster: {len(self.bully_manager.cluster_nodes) + 1} nodos\n\n", style="blue")
        message.append("    🚧 Dashboard en construcción\n", style="bold magenta")
        message.append("    Próximamente: FASE 4-12\n\n", style="dim")
        message.append("    Presiona Ctrl+C para salir", style="dim italic")
        
        from rich.align import Align
        yield Static(Align.center(message))


# Export
__all__ = ['LoginScreen', 'PlaceholderDashboard']
