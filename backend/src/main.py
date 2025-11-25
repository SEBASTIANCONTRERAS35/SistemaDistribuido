#!/usr/bin/env python3
"""
Sistema Médico Distribuido v2.0 - Textual TUI
Entry point for the modern Textual-based medical system

Usage:
    python3 main_textual.py
    NODE_ID=1 python3 main_textual.py
    CLUSTER_MODE=dynamic python3 main_textual.py
"""

import os
import sys
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging BEFORE any other imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('textual_app.log'),
        # Don't log to console since Textual owns the terminal
    ]
)

logger = logging.getLogger(__name__)


def setup_environment():
    """Setup environment variables and configuration"""
    # Set default NODE_ID if not provided
    if 'NODE_ID' not in os.environ and 'CLUSTER_MODE' not in os.environ:
        logger.warning("No NODE_ID or CLUSTER_MODE set, using CLUSTER_MODE=dynamic")
        os.environ['CLUSTER_MODE'] = 'dynamic'
    
    # Flask configuration (without web server)
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = '0'  # No debug in TUI mode
    
    logger.info(f"Environment configured - NODE_ID: {os.environ.get('NODE_ID', 'AUTO')}, CLUSTER_MODE: {os.environ.get('CLUSTER_MODE', 'static')}")


def create_flask_app():
    """Create Flask app context for database access"""
    from app_factory import create_app
    
    logger.info("Creating Flask app context...")
    app = create_app()
    
    # Initialize database
    with app.app_context():
        from models import db
        db.create_all()
        logger.info("Database initialized")
    
    return app


def create_bully_manager(app):
    """Initialize Bully consensus manager"""
    from bully.bully_node import BullyNode
    from config import Config
    from bully.id_generator import get_or_create_node_id

    logger.info("Initializing Bully manager...")

    # CRITICAL FIX: Initialize Config with proper ports based on NODE_ID
    Config.initialize_node_id()
    logger.info(f"Config initialized - TCP_PORT: {Config.TCP_PORT}, UDP_PORT: {Config.UDP_PORT}")

    # Get configuration from environment
    cluster_mode = os.environ.get('CLUSTER_MODE', 'static')
    node_id_str = os.environ.get('NODE_ID')

    # Determine node_id
    if cluster_mode == 'dynamic':
        # Dynamic mode: auto-generate ID
        node_id = get_or_create_node_id()
        logger.info(f"Dynamic mode - Auto-generated Node ID: {node_id}")

        bully_manager = BullyNode(
            node_id=node_id,
            tcp_port=Config.TCP_PORT,
            udp_port=Config.UDP_PORT,
            use_discovery=True,
            multicast_group=Config.MULTICAST_GROUP,
            multicast_port=Config.MULTICAST_PORT
        )
    else:
        # Static mode: use provided NODE_ID
        if not node_id_str:
            raise ValueError("NODE_ID must be set in static mode")

        node_id = int(node_id_str)

        # Build cluster_nodes dict (simplified for now)
        cluster_nodes = {}
        # TODO: Load from config file or environment

        bully_manager = BullyNode(
            node_id=node_id,
            cluster_nodes=cluster_nodes,
            tcp_port=Config.TCP_PORT,
            udp_port=Config.UDP_PORT,
            use_discovery=False
        )

    # Start Bully system
    bully_manager.start()
    logger.info(f"Bully manager started - Node ID: {bully_manager.node_id}, Mode: {cluster_mode}")

    return bully_manager


def main():
    """Main entry point"""
    try:
        # Setup
        setup_environment()
        
        # Create Flask app context
        app = create_flask_app()
        
        # Create Bully manager
        bully_manager = create_bully_manager(app)

        # Import Textual app
        from textual_app import MedicalApp

        logger.info("Launching Textual Medical App...")

        # Create and run the Textual application
        medical_app = MedicalApp(
            flask_app=app,
            bully_manager=bully_manager,
            use_simple_splash=False  # Set to True for faster startup
        )

        # Run the app (this blocks until app exits)
        medical_app.run()

        logger.info("Application exited normally")
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
