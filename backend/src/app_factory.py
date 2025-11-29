"""
App Factory para crear Flask app sin iniciar servidor web.
Mantiene Flask-SQLAlchemy pero no inicia routes ni SocketIO.
"""
from flask import Flask
from config import Config
from models import db
from auth import init_default_users, init_all_salas_resources, init_sala_for_node
import logging
import os

def create_app():
    """
    Crea aplicación Flask para uso en consola (sin servidor web).

    Returns:
        Flask: Aplicación Flask configurada con SQLAlchemy
    """
    # Crear app sin templates ni static (no son necesarios para consola)
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializar SQLAlchemy (mantener setup existente sin cambios)
    db.init_app(app)

    # Asegurar que existe el directorio de datos
    data_dir = os.path.join(os.path.dirname(__file__), '../data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # Asegurar que existe el directorio de logs
    log_dir = os.path.join(os.path.dirname(__file__), '../logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Crear tablas, usuarios y recursos por defecto
    with app.app_context():
        db.create_all()
        init_default_users()  # Usuarios de prueba (doctor1, trabajador1, etc.)

        # Asegurar que NODE_ID está inicializado antes de crear la sala
        node_id = Config.NODE_ID
        if node_id is None:
            # Si NODE_ID aún no se inicializó, usar valor por defecto temporal
            # El NODE_ID real se asignará en main.py con initialize_node_id()
            node_id = Config.initialize_node_id()

        # Salas dinámicas: cada nodo crea su propia sala si no existe
        init_sala_for_node(node_id)  # Crea sala N para nodo N

    return app
