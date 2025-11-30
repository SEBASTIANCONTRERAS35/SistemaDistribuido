"""
App Factory para crear Flask app con endpoints de cluster para sincronización distribuida.
Mantiene Flask-SQLAlchemy y agrega API REST para replicación de datos entre nodos.
"""
from flask import Flask, request, jsonify
from config import Config
from models import db, Doctor, Cama, Sala, Paciente, VisitaEmergencia, TrabajadorSocial, Consecutivo
from auth import init_default_users, init_all_salas_resources, init_sala_for_node
import logging
import os
import threading
from datetime import datetime

# Logger global para funciones helper de replicación
cluster_logger = logging.getLogger('cluster.api')


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

    # Registrar endpoints de cluster
    register_cluster_endpoints(app)

    return app


def register_cluster_endpoints(app):
    """
    Registra los endpoints REST para sincronización del cluster distribuido.
    """
    cluster_logger = logging.getLogger('cluster.api')

    # =========================================================================
    # GET /api/cluster/doctors - Obtener doctores de este nodo
    # =========================================================================
    @app.route('/api/cluster/doctors', methods=['GET'])
    def get_cluster_doctors():
        """Retorna doctores de la sala local."""
        cluster_logger.info(f"[API] GET /api/cluster/doctors from {request.remote_addr}")
        try:
            disponible = request.args.get('disponible')
            activo = request.args.get('activo', 'true')

            query = Doctor.query

            if activo is not None:
                activo_bool = activo.lower() == 'true'
                query = query.filter_by(activo=activo_bool)

            if disponible is not None:
                disponible_bool = disponible.lower() == 'true'
                query = query.filter_by(disponible=disponible_bool)

            doctors = query.all()
            result = [{
                'id_doctor': doc.id_doctor,
                'nombre': doc.nombre,
                'especialidad': doc.especialidad,
                'disponible': doc.disponible,
                'activo': doc.activo,
                'id_sala': doc.id_sala
            } for doc in doctors]

            return jsonify({'doctors': result, 'node_id': Config.NODE_ID})

        except Exception as e:
            cluster_logger.error(f"Error getting doctors: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # GET /api/cluster/beds - Obtener camas de este nodo
    # =========================================================================
    @app.route('/api/cluster/beds', methods=['GET'])
    def get_cluster_beds():
        """Retorna camas de la sala local."""
        cluster_logger.info(f"[API] GET /api/cluster/beds from {request.remote_addr}")
        try:
            ocupada = request.args.get('ocupada')

            query = Cama.query

            if ocupada is not None:
                ocupada_bool = ocupada.lower() == 'true'
                query = query.filter_by(ocupada=ocupada_bool)

            beds = query.all()
            result = [{
                'id_cama': cama.id_cama,
                'numero': cama.numero,
                'ocupada': cama.ocupada,
                'id_sala': cama.id_sala,
                'id_paciente': cama.id_paciente,
                'paciente_nombre': cama.paciente_actual.nombre if cama.paciente_actual else None
            } for cama in beds]

            return jsonify({'beds': result, 'node_id': Config.NODE_ID})

        except Exception as e:
            cluster_logger.error(f"Error getting beds: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # GET /api/cluster/stats - Obtener estadísticas del nodo
    # =========================================================================
    @app.route('/api/cluster/stats', methods=['GET'])
    def get_cluster_stats():
        """Retorna estadísticas de este nodo."""
        cluster_logger.info(f"[API] GET /api/cluster/stats from {request.remote_addr}")
        try:
            doctors_available = Doctor.query.filter_by(disponible=True, activo=True).count()
            doctors_total = Doctor.query.filter_by(activo=True).count()
            beds_available = Cama.query.filter_by(ocupada=False).count()
            beds_total = Cama.query.count()
            visits_active = VisitaEmergencia.query.filter_by(estado='activa').count()
            visits_completed = VisitaEmergencia.query.filter_by(estado='completada').count()

            return jsonify({
                'node_id': Config.NODE_ID,
                'doctors_available': doctors_available,
                'doctors_total': doctors_total,
                'beds_available': beds_available,
                'beds_total': beds_total,
                'visits_active': visits_active,
                'visits_completed': visits_completed
            })

        except Exception as e:
            cluster_logger.error(f"Error getting stats: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # POST /api/cluster/replicate-visit - Replicar visita desde líder
    # =========================================================================
    @app.route('/api/cluster/replicate-visit', methods=['POST'])
    def replicate_visit():
        """Recibe y almacena una visita replicada desde el coordinador."""
        cluster_logger.info(f"[API] POST /api/cluster/replicate-visit from {request.remote_addr}")
        try:
            data = request.json
            cluster_logger.debug(f"[API] Replicate visit data: {data}")
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            folio = data.get('folio')
            if not folio:
                return jsonify({'error': 'Folio is required'}), 400

            # Verificar si ya existe (idempotencia)
            existing = VisitaEmergencia.query.filter_by(folio=folio).first()
            if existing:
                cluster_logger.info(f"Visit {folio} already exists, skipping")
                return jsonify({'status': 'already_exists', 'folio': folio}), 200

            # Asegurar que el paciente existe localmente
            paciente_data = data.get('paciente')
            if paciente_data:
                paciente = Paciente.query.filter_by(id_paciente=paciente_data.get('id_paciente')).first()
                if not paciente:
                    paciente = Paciente(
                        id_paciente=paciente_data.get('id_paciente'),
                        nombre=paciente_data.get('nombre'),
                        edad=paciente_data.get('edad'),
                        sexo=paciente_data.get('sexo'),
                        curp=paciente_data.get('curp')
                    )
                    db.session.add(paciente)
                    db.session.flush()

            # Crear la visita con el folio del coordinador (NO generar nuevo)
            cluster_logger.info(f"[RECV] VISITA INSERT: folio={folio}, paciente={data.get('id_paciente')}, doctor={data.get('id_doctor')}, cama={data.get('id_cama')}, sala={data.get('id_sala')}")
            visita = VisitaEmergencia(
                folio=folio,
                id_paciente=data.get('id_paciente'),
                id_doctor=data.get('id_doctor'),
                id_cama=data.get('id_cama'),
                id_sala=data.get('id_sala'),
                id_trabajador=data.get('id_trabajador'),
                sintomas=data.get('sintomas'),
                diagnostico=data.get('diagnostico'),
                estado=data.get('estado', 'activa'),
                timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else datetime.now(),
                fecha_cierre=datetime.fromisoformat(data['fecha_cierre']) if data.get('fecha_cierre') else None
            )

            db.session.add(visita)
            db.session.commit()

            cluster_logger.info(f"[RECV] VISITA INSERTADA: folio={folio}")
            return jsonify({'status': 'replicated', 'folio': folio}), 201

        except Exception as e:
            db.session.rollback()
            cluster_logger.error(f"Error replicating visit: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # GET /api/cluster/full-sync - Sincronización completa para nodos nuevos
    # =========================================================================
    @app.route('/api/cluster/full-sync', methods=['GET'])
    def full_sync():
        """Retorna todos los datos para sincronización inicial de un nodo nuevo."""
        cluster_logger.info(f"[API] GET /api/cluster/full-sync from {request.remote_addr}")
        try:
            # Salas (fallback: si numero es None, usar id_sala)
            salas = [{
                'id_sala': s.id_sala,
                'numero': s.numero if s.numero is not None else s.id_sala,
                'activa': s.activa
            } for s in Sala.query.all()]

            # Doctores
            doctores = [{
                'id_doctor': d.id_doctor,
                'nombre': d.nombre,
                'especialidad': d.especialidad,
                'disponible': d.disponible,
                'activo': d.activo,
                'id_sala': d.id_sala
            } for d in Doctor.query.all()]

            # Camas
            camas = [{
                'id_cama': c.id_cama,
                'numero': c.numero,
                'ocupada': c.ocupada,
                'id_sala': c.id_sala,
                'id_paciente': c.id_paciente
            } for c in Cama.query.all()]

            # Pacientes
            pacientes = [{
                'id_paciente': p.id_paciente,
                'nombre': p.nombre,
                'edad': p.edad,
                'sexo': p.sexo,
                'curp': p.curp
            } for p in Paciente.query.all()]

            # Trabajadores sociales
            trabajadores = [{
                'id_trabajador': t.id_trabajador,
                'nombre': t.nombre,
                'activo': t.activo,
                'id_sala': t.id_sala
            } for t in TrabajadorSocial.query.all()]

            # Visitas activas
            visitas = [{
                'id_visita': v.id_visita,
                'folio': v.folio,
                'id_paciente': v.id_paciente,
                'id_doctor': v.id_doctor,
                'id_cama': v.id_cama,
                'id_sala': v.id_sala,
                'id_trabajador': v.id_trabajador,
                'sintomas': v.sintomas,
                'diagnostico': v.diagnostico,
                'estado': v.estado,
                'timestamp': v.timestamp.isoformat() if v.timestamp else None,
                'fecha_cierre': v.fecha_cierre.isoformat() if v.fecha_cierre else None,
                'paciente': {
                    'id_paciente': v.paciente.id_paciente,
                    'nombre': v.paciente.nombre,
                    'edad': v.paciente.edad,
                    'sexo': v.paciente.sexo,
                    'curp': v.paciente.curp
                } if v.paciente else None
            } for v in VisitaEmergencia.query.all()]

            # Consecutivos (para mantener secuencia de folios)
            consecutivos = [{
                'id': c.id,
                'id_sala': c.id_sala,
                'fecha': c.fecha.isoformat() if c.fecha else None,
                'consecutivo': c.consecutivo
            } for c in Consecutivo.query.all()]

            cluster_logger.info(f"[API] Full-sync response: {len(salas)} salas, {len(doctores)} doctores, "
                               f"{len(camas)} camas, {len(pacientes)} pacientes, {len(visitas)} visitas")
            return jsonify({
                'node_id': Config.NODE_ID,
                'timestamp': datetime.now().isoformat(),
                'data': {
                    'salas': salas,
                    'doctores': doctores,
                    'camas': camas,
                    'pacientes': pacientes,
                    'trabajadores': trabajadores,
                    'visitas': visitas,
                    'consecutivos': consecutivos
                }
            })

        except Exception as e:
            cluster_logger.error(f"[API] Error in full-sync: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # PUT /api/cluster/update-visit - Actualizar visita desde otro nodo
    # =========================================================================
    @app.route('/api/cluster/update-visit', methods=['PUT'])
    def update_visit():
        """Actualiza una visita existente (ej: cerrar visita)."""
        cluster_logger.info(f"[API] PUT /api/cluster/update-visit from {request.remote_addr}")
        try:
            data = request.json
            cluster_logger.debug(f"[API] Update visit data: {data}")
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            folio = data.get('folio')
            if not folio:
                return jsonify({'error': 'Folio is required'}), 400

            # Buscar visita por folio
            visita = VisitaEmergencia.query.filter_by(folio=folio).first()
            if not visita:
                cluster_logger.warning(f"Visit {folio} not found for update")
                return jsonify({'status': 'not_found', 'folio': folio}), 404

            # Actualizar campos
            if 'estado' in data:
                visita.estado = data['estado']
            if 'diagnostico' in data:
                visita.diagnostico = data['diagnostico']
            if data.get('fecha_cierre'):
                visita.fecha_cierre = datetime.fromisoformat(data['fecha_cierre'])

            # Si la visita se cierra, liberar cama y doctor
            if visita.estado == 'completada':
                if visita.cama:
                    visita.cama.ocupada = False
                    visita.cama.id_paciente = None
                if visita.doctor:
                    visita.doctor.disponible = True

            db.session.commit()

            cluster_logger.info(f"Visit {folio} updated successfully")
            return jsonify({'status': 'updated', 'folio': folio}), 200

        except Exception as e:
            db.session.rollback()
            cluster_logger.error(f"Error updating visit: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # POST /api/cluster/replicate-entity - Replicar entidad genérica
    # =========================================================================
    @app.route('/api/cluster/replicate-entity', methods=['POST'])
    def replicate_entity():
        """Replica una entidad genérica (sala, doctor, cama, paciente, etc.)."""
        cluster_logger.info(f"[API] POST /api/cluster/replicate-entity from {request.remote_addr}")
        try:
            data = request.json
            cluster_logger.debug(f"[API] Replicate entity data: {data}")
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            entity_type = data.get('type')
            operation = data.get('operation')  # INSERT, UPDATE, DELETE
            entity_data = data.get('data')

            if not all([entity_type, operation, entity_data]):
                return jsonify({'error': 'type, operation, and data are required'}), 400

            cluster_logger.info(f"Replicating {operation} on {entity_type}")

            if entity_type == 'sala':
                _replicate_sala(operation, entity_data)
            elif entity_type == 'doctor':
                _replicate_doctor(operation, entity_data)
            elif entity_type == 'cama':
                _replicate_cama(operation, entity_data)
            elif entity_type == 'paciente':
                _replicate_paciente(operation, entity_data)
            elif entity_type == 'trabajador':
                _replicate_trabajador(operation, entity_data)
            else:
                return jsonify({'error': f'Unknown entity type: {entity_type}'}), 400

            db.session.commit()
            return jsonify({'status': 'replicated', 'type': entity_type, 'operation': operation}), 200

        except Exception as e:
            db.session.rollback()
            cluster_logger.error(f"Error replicating entity: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # POST /api/cluster/force-resync - Forzar re-sincronización
    # =========================================================================
    @app.route('/api/cluster/force-resync', methods=['POST'])
    def force_resync():
        """Fuerza re-sincronización completa desde otro nodo del cluster."""
        cluster_logger.info(f"[API] POST /api/cluster/force-resync from {request.remote_addr}")
        try:
            from bully.data_sync import get_synchronizer
            sync = get_synchronizer()
            if sync:
                sync._synced = False  # Resetear estado
                result = sync.perform_initial_sync(timeout=15.0)
                return jsonify({
                    'success': result,
                    'message': 'Re-sync completado' if result else 'Re-sync falló'
                })
            return jsonify({'success': False, 'error': 'Sincronizador no disponible'}), 500
        except Exception as e:
            cluster_logger.error(f"Force resync error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500


def _replicate_sala(operation, data):
    """Helper para replicar sala."""
    cluster_logger.info(f"[RECV] SALA {operation}: id_sala={data.get('id_sala')}, numero={data.get('numero')}, activa={data.get('activa')}")
    if operation == 'INSERT':
        existing = Sala.query.filter_by(id_sala=data['id_sala']).first()
        if not existing:
            # Fallback: si numero es None, usar id_sala
            numero_value = data.get('numero') or data['id_sala']
            sala = Sala(id_sala=data['id_sala'], numero=numero_value, activa=data.get('activa', True))
            db.session.add(sala)
            cluster_logger.info(f"[RECV] SALA INSERTADA: id_sala={data['id_sala']}")
        else:
            cluster_logger.info(f"[RECV] SALA ya existe: id_sala={data['id_sala']}")
    elif operation == 'UPDATE':
        sala = Sala.query.filter_by(id_sala=data['id_sala']).first()
        if sala:
            sala.activa = data.get('activa', sala.activa)
            cluster_logger.info(f"[RECV] SALA ACTUALIZADA: id_sala={data['id_sala']}")
    elif operation == 'DELETE':
        sala = Sala.query.filter_by(id_sala=data['id_sala']).first()
        if sala:
            db.session.delete(sala)
            cluster_logger.info(f"[RECV] SALA ELIMINADA: id_sala={data['id_sala']}")


def _replicate_doctor(operation, data):
    """Helper para replicar doctor."""
    cluster_logger.info(f"[RECV] DOCTOR {operation}: id={data.get('id_doctor')}, nombre={data.get('nombre')}, sala={data.get('id_sala')}")
    if operation == 'INSERT':
        existing = Doctor.query.filter_by(id_doctor=data['id_doctor']).first()
        if not existing:
            doctor = Doctor(
                id_doctor=data['id_doctor'],
                nombre=data['nombre'],
                especialidad=data.get('especialidad'),
                disponible=data.get('disponible', True),
                activo=data.get('activo', True),
                id_sala=data['id_sala']
            )
            db.session.add(doctor)
            cluster_logger.info(f"[RECV] DOCTOR INSERTADO: id={data['id_doctor']}, {data['nombre']}")
        else:
            cluster_logger.info(f"[RECV] DOCTOR ya existe: id={data['id_doctor']}")
    elif operation == 'UPDATE':
        doctor = Doctor.query.filter_by(id_doctor=data['id_doctor']).first()
        if doctor:
            doctor.disponible = data.get('disponible', doctor.disponible)
            doctor.activo = data.get('activo', doctor.activo)
            cluster_logger.info(f"[RECV] DOCTOR ACTUALIZADO: id={data['id_doctor']}")
    elif operation == 'DELETE':
        doctor = Doctor.query.filter_by(id_doctor=data['id_doctor']).first()
        if doctor:
            db.session.delete(doctor)
            cluster_logger.info(f"[RECV] DOCTOR ELIMINADO: id={data['id_doctor']}")


def _replicate_cama(operation, data):
    """Helper para replicar cama."""
    cluster_logger.info(f"[RECV] CAMA {operation}: id={data.get('id_cama')}, numero={data.get('numero')}, sala={data.get('id_sala')}")
    if operation == 'INSERT':
        existing = Cama.query.filter_by(id_cama=data['id_cama']).first()
        if not existing:
            cama = Cama(
                id_cama=data['id_cama'],
                numero=data['numero'],
                ocupada=data.get('ocupada', False),
                id_sala=data['id_sala'],
                id_paciente=data.get('id_paciente')
            )
            db.session.add(cama)
            cluster_logger.info(f"[RECV] CAMA INSERTADA: id={data['id_cama']}, numero={data['numero']}")
        else:
            cluster_logger.info(f"[RECV] CAMA ya existe: id={data['id_cama']}")
    elif operation == 'UPDATE':
        cama = Cama.query.filter_by(id_cama=data['id_cama']).first()
        if cama:
            cama.ocupada = data.get('ocupada', cama.ocupada)
            cama.id_paciente = data.get('id_paciente', cama.id_paciente)
            cluster_logger.info(f"[RECV] CAMA ACTUALIZADA: id={data['id_cama']}, ocupada={data.get('ocupada')}")
    elif operation == 'DELETE':
        cama = Cama.query.filter_by(id_cama=data['id_cama']).first()
        if cama:
            db.session.delete(cama)
            cluster_logger.info(f"[RECV] CAMA ELIMINADA: id={data['id_cama']}")


def _replicate_paciente(operation, data):
    """Helper para replicar paciente."""
    cluster_logger.info(f"[RECV] PACIENTE {operation}: id={data.get('id_paciente')}, nombre={data.get('nombre')}")
    if operation == 'INSERT':
        existing = Paciente.query.filter_by(id_paciente=data['id_paciente']).first()
        if not existing:
            paciente = Paciente(
                id_paciente=data['id_paciente'],
                nombre=data['nombre'],
                edad=data.get('edad'),
                sexo=data.get('sexo'),
                curp=data.get('curp')
            )
            db.session.add(paciente)
            cluster_logger.info(f"[RECV] PACIENTE INSERTADO: id={data['id_paciente']}, {data['nombre']}")
        else:
            cluster_logger.info(f"[RECV] PACIENTE ya existe: id={data['id_paciente']}")
    elif operation == 'UPDATE':
        paciente = Paciente.query.filter_by(id_paciente=data['id_paciente']).first()
        if paciente:
            paciente.nombre = data.get('nombre', paciente.nombre)
            paciente.edad = data.get('edad', paciente.edad)
            cluster_logger.info(f"[RECV] PACIENTE ACTUALIZADO: id={data['id_paciente']}")
    elif operation == 'DELETE':
        paciente = Paciente.query.filter_by(id_paciente=data['id_paciente']).first()
        if paciente:
            db.session.delete(paciente)
            cluster_logger.info(f"[RECV] PACIENTE ELIMINADO: id={data['id_paciente']}")


def _replicate_trabajador(operation, data):
    """Helper para replicar trabajador social."""
    cluster_logger.info(f"[RECV] TRABAJADOR {operation}: id={data.get('id_trabajador')}, nombre={data.get('nombre')}, sala={data.get('id_sala')}")
    if operation == 'INSERT':
        existing = TrabajadorSocial.query.filter_by(id_trabajador=data['id_trabajador']).first()
        if not existing:
            trabajador = TrabajadorSocial(
                id_trabajador=data['id_trabajador'],
                nombre=data['nombre'],
                activo=data.get('activo', True),
                id_sala=data['id_sala']
            )
            db.session.add(trabajador)
            cluster_logger.info(f"[RECV] TRABAJADOR INSERTADO: id={data['id_trabajador']}, {data['nombre']}")
        else:
            cluster_logger.info(f"[RECV] TRABAJADOR ya existe: id={data['id_trabajador']}")
    elif operation == 'UPDATE':
        trabajador = TrabajadorSocial.query.filter_by(id_trabajador=data['id_trabajador']).first()
        if trabajador:
            trabajador.activo = data.get('activo', trabajador.activo)
            cluster_logger.info(f"[RECV] TRABAJADOR ACTUALIZADO: id={data['id_trabajador']}")
    elif operation == 'DELETE':
        trabajador = TrabajadorSocial.query.filter_by(id_trabajador=data['id_trabajador']).first()
        if trabajador:
            db.session.delete(trabajador)
            cluster_logger.info(f"[RECV] TRABAJADOR ELIMINADO: id={data['id_trabajador']}")


def start_cluster_api_server(app, host='0.0.0.0', port=None):
    """
    Inicia el servidor Flask API en un thread separado para el cluster.

    Args:
        app: Aplicación Flask
        host: Host donde escuchar (default: 0.0.0.0 para todas las interfaces)
        port: Puerto (default: Config.FLASK_PORT)

    Returns:
        Thread: Thread del servidor Flask
    """
    if port is None:
        port = Config.FLASK_PORT

    def run_server():
        # Desactivar logs de werkzeug para no saturar consola
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.WARNING)

        app.run(host=host, port=port, threaded=True, use_reloader=False)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    logging.getLogger('cluster.api').info(f"Cluster API server started on {host}:{port}")

    return server_thread
