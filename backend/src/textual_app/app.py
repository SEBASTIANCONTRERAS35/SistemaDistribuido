"""
MedicalApp - Main Textual Application
Modern TUI for distributed medical emergency system
"""

import os
from pathlib import Path
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer
from textual.driver import Driver

# Import screens
from .screens.splash import SplashScreen, SimpleSplashScreen
from .screens.login import LoginScreen

# Version
from . import __version__


class MedicalApp(App):
    """
    Sistema Médico Distribuido - Main Textual Application
    
    A modern terminal user interface for managing distributed
    medical emergencies with Bully consensus algorithm.
    """
    
    # App metadata
    TITLE = "Sistema Médico Distribuido"
    SUB_TITLE = f"v{__version__} - Emergency Management System"

    # CSS Theme Path
    CSS_PATH = Path(__file__).parent / "themes" / "medical_blue.tcss"
    
    # Global key bindings
    BINDINGS = [
        Binding("ctrl+c", "quit", "Salir", priority=True),
        Binding("ctrl+d", "toggle_dark", "Tema", show=False),
        Binding("f1", "help", "Ayuda", show=True),
        # Navegación con flechas (sin mouse)
        Binding("down", "focus_next", "↓", show=True),
        Binding("up", "focus_previous", "↑", show=True),
    ]
    
    def __init__(
        self,
        flask_app,
        bully_manager,
        use_simple_splash: bool = False,
        **kwargs
    ):
        """
        Initialize Medical App
        
        Args:
            flask_app: Flask application instance (for DB access)
            bully_manager: BullyNode instance (for cluster management)
            use_simple_splash: Use simplified splash screen (faster, less effects)
        """
        super().__init__(**kwargs)
        
        # Store references
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.use_simple_splash = use_simple_splash
        
        # Current user (set after login)
        self.current_user = None
        
        # Theme mode
        self.dark_mode = True
    
    def on_mount(self) -> None:
        """Called when app is mounted - show splash screen"""
        # Create and push splash screen
        if self.use_simple_splash:
            splash = SimpleSplashScreen(self.flask_app, self.bully_manager)
        else:
            splash = SplashScreen(self.flask_app, self.bully_manager)
        
        self.push_screen(splash)
        
        # Register screens for later use
        self.install_screen(
            LoginScreen(self.flask_app, self.bully_manager),
            name="login"
        )
    
    def action_toggle_dark(self) -> None:
        """Toggle dark/light mode"""
        self.dark_mode = not self.dark_mode
        self.dark = self.dark_mode
        self.notify(
            f"Tema {'oscuro' if self.dark_mode else 'claro'} activado",
            severity="information"
        )
    
    def action_help(self) -> None:
        """Show help dialog"""
        self.notify(
            "F1: Ayuda | Ctrl+D: Cambiar tema | Ctrl+C: Salir",
            title="Atajos de Teclado",
            severity="information",
            timeout=5
        )
    
    def action_quit(self) -> None:
        """Quit the application"""
        # Cleanup Bully manager
        if self.bully_manager:
            self.bully_manager.stop()
        
        self.exit()


# Export
__all__ = ['MedicalApp']
