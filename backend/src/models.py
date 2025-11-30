from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import bcrypt

db = SQLAlchemy()

class Sala(db.Model):
    __tablename__ = 'SALAS'

    id_sala = db.Column('id_sala', db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False)
    ip_address = db.Column(db.String(50))
    puerto = db.Column(db.Integer)
    es_maestro = db.Column(db.Boolean, default=False)
    activa = db.Column(db.Boolean, default=True)

    # Relaciones
    doctores = db.relationship('Doctor', backref='sala', lazy=True)
    trabajadores = db.relationship('TrabajadorSocial', backref='sala', lazy=True)
    camas = db.relationship('Cama', backref='sala', lazy=True)
    visitas = db.relationship('VisitaEmergencia', backref='sala', lazy=True)

    def __repr__(self):
        return f'<Sala {self.numero}>'


class Paciente(db.Model):
    __tablename__ = 'PACIENTES'

    id_paciente = db.Column('id_paciente', db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    edad = db.Column(db.Integer)
    sexo = db.Column(db.String(1))  # 'M' o 'F'
    curp = db.Column(db.String(18), unique=True)
    telefono = db.Column(db.String(20))
    contacto_emergencia = db.Column(db.String(200))
    activo = db.Column(db.Integer, default=1, nullable=False)

    # Relaciones
    visitas = db.relationship('VisitaEmergencia', backref='paciente', lazy=True)

    def __repr__(self):
        return f'<Paciente {self.nombre}>'

    def to_dict(self):
        """Convierte el paciente a diccionario para JSON"""
        return {
            'id_paciente': self.id_paciente,
            'nombre': self.nombre,
            'edad': self.edad,
            'sexo': self.sexo,
            'curp': self.curp,
            'telefono': self.telefono,
            'contacto_emergencia': self.contacto_emergencia,
            'activo': self.activo
        }


class Doctor(db.Model):
    __tablename__ = 'DOCTORES'

    id_doctor = db.Column('id_doctor', db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    especialidad = db.Column(db.String(100))
    id_sala = db.Column(db.Integer, db.ForeignKey('SALAS.id_sala'), nullable=False)
    disponible = db.Column(db.Boolean, default=True)
    activo = db.Column(db.Boolean, default=True)

    # Relaciones
    visitas = db.relationship('VisitaEmergencia', backref='doctor', lazy=True)

    def __repr__(self):
        return f'<Doctor {self.nombre} - {self.especialidad}>'

    def to_dict(self):
        """Convierte el doctor a diccionario para JSON"""
        return {
            'id_doctor': self.id_doctor,
            'nombre': self.nombre,
            'especialidad': self.especialidad,
            'id_sala': self.id_sala,
            'disponible': self.disponible,
            'activo': self.activo
        }


class TrabajadorSocial(db.Model):
    __tablename__ = 'TRABAJADORES_SOCIALES'

    id_trabajador = db.Column('id_trabajador', db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    id_sala = db.Column(db.Integer, db.ForeignKey('SALAS.id_sala'), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    # Relaciones
    visitas = db.relationship('VisitaEmergencia', backref='trabajador_social', lazy=True)

    def __repr__(self):
        return f'<TrabajadorSocial {self.nombre}>'

    def to_dict(self):
        """Convierte el trabajador social a diccionario para JSON"""
        return {
            'id_trabajador': self.id_trabajador,
            'nombre': self.nombre,
            'id_sala': self.id_sala,
            'activo': self.activo
        }


class Cama(db.Model):
    __tablename__ = 'CAMAS'

    id_cama = db.Column('id_cama', db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False)
    id_sala = db.Column(db.Integer, db.ForeignKey('SALAS.id_sala'), nullable=False)
    ocupada = db.Column(db.Boolean, default=False)
    id_paciente = db.Column(db.Integer, db.ForeignKey('PACIENTES.id_paciente'))

    # Relaciones
    visitas = db.relationship('VisitaEmergencia', backref='cama', lazy=True)
    paciente_actual = db.relationship('Paciente', foreign_keys=[id_paciente])

    def __repr__(self):
        return f'<Cama {self.numero} - Sala {self.id_sala}>'

    def to_dict(self):
        """Convierte la cama a diccionario para JSON"""
        return {
            'id_cama': self.id_cama,
            'numero': self.numero,
            'id_sala': self.id_sala,
            'ocupada': self.ocupada,
            'id_paciente': self.id_paciente
        }


class VisitaEmergencia(db.Model):
    __tablename__ = 'VISITAS_EMERGENCIA'

    id_visita = db.Column('id_visita', db.Integer, primary_key=True)
    folio = db.Column(db.String(50), unique=True)  # Generado por trigger
    id_paciente = db.Column(db.Integer, db.ForeignKey('PACIENTES.id_paciente'), nullable=False)
    id_doctor = db.Column(db.Integer, db.ForeignKey('DOCTORES.id_doctor'), nullable=False)
    id_cama = db.Column(db.Integer, db.ForeignKey('CAMAS.id_cama'), nullable=False)
    id_trabajador = db.Column(db.Integer, db.ForeignKey('TRABAJADORES_SOCIALES.id_trabajador'), nullable=False)
    id_sala = db.Column(db.Integer, db.ForeignKey('SALAS.id_sala'), nullable=False)
    sintomas = db.Column(db.Text)
    diagnostico = db.Column(db.Text)
    estado = db.Column(db.String(20), default='activa')  # 'activa', 'completada', 'cancelada'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_cierre = db.Column(db.DateTime)

    def __repr__(self):
        return f'<VisitaEmergencia {self.folio} - {self.estado}>'

    def to_dict(self):
        """Convierte la visita a diccionario para JSON"""
        return {
            'id_visita': self.id_visita,
            'folio': self.folio,
            'id_paciente': self.id_paciente,
            'paciente': self.paciente.nombre if self.paciente else 'N/A',
            'id_doctor': self.id_doctor,
            'doctor': self.doctor.nombre if self.doctor else 'N/A',
            'id_cama': self.id_cama,
            'cama': self.cama.numero if self.cama else 'N/A',
            'id_sala': self.id_sala,
            'sala': self.sala.numero if self.sala else 'N/A',
            'sintomas': self.sintomas,
            'diagnostico': self.diagnostico,
            'estado': self.estado,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'fecha_cierre': self.fecha_cierre.isoformat() if self.fecha_cierre else None
        }


class Consecutivo(db.Model):
    __tablename__ = 'CONSECUTIVOS'

    id = db.Column(db.Integer, primary_key=True)
    id_sala = db.Column(db.Integer, db.ForeignKey('SALAS.id_sala'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    consecutivo = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<Consecutivo Sala {self.id_sala} - {self.fecha}: {self.consecutivo}>'


def get_next_consecutivo(id_sala):
    """
    Obtiene el siguiente consecutivo para una sala.

    IMPORTANTE: Esta función NO hace flush/commit porque puede ser llamada
    desde un evento before_insert donde la sesión ya está flushing.

    Args:
        id_sala: ID de la sala

    Returns:
        int: Próximo número consecutivo
    """
    from sqlalchemy import func
    hoy = datetime.utcnow().date()

    # Buscar consecutivo para hoy
    consecutivo = Consecutivo.query.filter_by(
        id_sala=id_sala,
        fecha=hoy
    ).first()

    if not consecutivo:
        # Crear nuevo consecutivo para hoy
        consecutivo = Consecutivo(
            id_sala=id_sala,
            fecha=hoy,
            consecutivo=1
        )
        db.session.add(consecutivo)
        # NO flush aquí - se hará con el commit principal
        return 1
    else:
        # Incrementar consecutivo
        consecutivo.consecutivo += 1
        # NO flush aquí - se hará con el commit principal
        return consecutivo.consecutivo


class Usuario(UserMixin, db.Model):
    """Modelo para autenticación con Flask-Login"""
    __tablename__ = 'USUARIOS'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(30), nullable=False)  # 'doctor', 'trabajador_social', 'paciente'
    id_relacionado = db.Column(db.Integer)  # id_doctor, id_trabajador o id_paciente según rol
    activo = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        """Hash de la contraseña con bcrypt"""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        """Verificar contraseña"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def get_id(self):
        """Requerido por Flask-Login"""
        return str(self.id)

    def __repr__(self):
        return f'<Usuario {self.username} - {self.rol}>'


# Funciones de utilidad para queries comunes

def get_doctores_disponibles(id_sala=None, active_salas=None):
    """
    Obtiene doctores disponibles, opcionalmente filtrados por sala.

    Args:
        id_sala: Filtrar por sala específica
        active_salas: Lista de IDs de salas activas (nodos del cluster)
    """
    query = Doctor.query.filter_by(disponible=True, activo=True)
    if id_sala:
        query = query.filter_by(id_sala=id_sala)
    if active_salas is not None:
        query = query.filter(Doctor.id_sala.in_(active_salas))
    return query.all()


def get_camas_disponibles(id_sala=None, active_salas=None):
    """
    Obtiene camas disponibles, opcionalmente filtradas por sala.

    Args:
        id_sala: Filtrar por sala específica
        active_salas: Lista de IDs de salas activas (nodos del cluster)
    """
    query = Cama.query.filter_by(ocupada=False)
    if id_sala:
        query = query.filter_by(id_sala=id_sala)
    if active_salas is not None:
        query = query.filter(Cama.id_sala.in_(active_salas))
    return query.all()


def get_visitas_activas(id_doctor=None, id_sala=None):
    """Obtiene visitas activas, opcionalmente filtradas por doctor o sala"""
    query = VisitaEmergencia.query.filter_by(estado='activa')
    if id_doctor:
        query = query.filter_by(id_doctor=id_doctor)
    if id_sala:
        query = query.filter_by(id_sala=id_sala)
    return query.order_by(VisitaEmergencia.timestamp.desc()).all()


def elegir_sala_menos_carga(active_salas=None):
    """
    Evalúa carga de todas las salas y retorna la mejor opción.
    Criterio: sala con menos visitas activas Y camas/doctores disponibles.

    Usado por el MAESTRO para balancear carga entre salas.

    Args:
        active_salas: Lista de IDs de salas activas (nodos del cluster)

    Returns:
        int: ID de la sala con menos carga, o None si no hay sala disponible
    """
    salas_stats = []

    query = Sala.query.filter_by(activa=True)
    if active_salas is not None:
        query = query.filter(Sala.id_sala.in_(active_salas))

    for sala in query.all():
        visitas_activas = VisitaEmergencia.query.filter_by(
            id_sala=sala.id_sala, estado='activa'
        ).count()

        camas_libres = Cama.query.filter_by(
            id_sala=sala.id_sala, ocupada=False
        ).count()

        doctores_libres = Doctor.query.filter_by(
            id_sala=sala.id_sala, disponible=True, activo=True
        ).count()

        # Solo considerar salas con recursos disponibles
        if camas_libres > 0 and doctores_libres > 0:
            salas_stats.append({
                'id_sala': sala.id_sala,
                'visitas_activas': visitas_activas,
                'camas_libres': camas_libres,
                'doctores_libres': doctores_libres
            })

    if not salas_stats:
        return None  # No hay sala con recursos disponibles

    # Ordenar por: menos visitas activas, más camas libres
    salas_stats.sort(key=lambda x: (x['visitas_activas'], -x['camas_libres']))

    return salas_stats[0]['id_sala']


def get_metricas_dashboard(id_sala=None):
    """Obtiene métricas para el dashboard (OPTIMIZADO - UNA SOLA QUERY)"""
    from sqlalchemy import func, case, and_

    # Query única optimizada con agregaciones
    hoy = datetime.utcnow().date()

    # Subquery para visitas
    visitas_stats = db.session.query(
        func.count().filter(VisitaEmergencia.estado == 'activa').label('visitas_activas'),
        func.count().filter(func.date(VisitaEmergencia.timestamp) == hoy).label('visitas_hoy'),
        func.count().filter(and_(
            VisitaEmergencia.estado == 'activa',
            VisitaEmergencia.id_sala == id_sala if id_sala else True
        )).label('visitas_activas_sala')
    ).first()

    # Counts optimizados
    doctores_disponibles = Doctor.query.filter_by(disponible=True, activo=True).count()
    camas_disponibles = Cama.query.filter_by(ocupada=False).count()

    metricas = {
        'visitas_activas': visitas_stats.visitas_activas or 0,
        'doctores_disponibles': doctores_disponibles,
        'camas_disponibles': camas_disponibles,
        'visitas_hoy': visitas_stats.visitas_hoy or 0
    }

    if id_sala:
        metricas['visitas_activas_sala'] = visitas_stats.visitas_activas_sala or 0
        metricas['doctores_sala'] = Doctor.query.filter_by(
            id_sala=id_sala, disponible=True, activo=True
        ).count()
        metricas['camas_sala'] = Cama.query.filter_by(
            id_sala=id_sala, ocupada=False
        ).count()

    return metricas


# Evento para generar folio automáticamente
from sqlalchemy import event

@event.listens_for(VisitaEmergencia, 'before_insert')
def generate_folio(mapper, connection, target):
    """
    Genera el folio automáticamente antes de insertar la visita.

    Formato requerido: IDPACIENTE+IDDOCTOR+SALADEEMERGENCIA+IDconsecutivoVISITA
    Formato implementado: P{id_paciente}-D{id_doctor}-S{id_sala}-{consecutivo:04d}
    Ejemplo: P15-D3-S1-0001
    """
    if not target.folio:
        # Usar consecutivo por sala (para unicidad dentro de cada sala)
        consecutivo = get_next_consecutivo(id_sala=target.id_sala)

        # Generar folio con formato: P{paciente}-D{doctor}-S{sala}-{consecutivo}
        target.folio = f"P{target.id_paciente}-D{target.id_doctor}-S{target.id_sala}-{consecutivo:04d}"


# Flag global para evitar bucles de replicación
_is_replicating = False


@event.listens_for(VisitaEmergencia, 'after_update')
def propagate_visit_update(mapper, connection, target):
    """
    Propaga actualizaciones de visitas (ej: cerrar visita) a otros nodos.

    Solo se propaga si:
    - No estamos en medio de una replicación (evita bucles)
    - La visita tiene folio (ya fue sincronizada)
    """
    global _is_replicating
    if _is_replicating:
        return

    # Solo propagar si la visita fue cerrada (activa cambió a False)
    if not target.activa and target.folio:
        try:
            from bully.data_sync import get_synchronizer
            sync = get_synchronizer()
            if sync and sync.bully_manager:
                _is_replicating = True

                # Propagar actualización vía HTTP
                visita_data = {
                    'folio': target.folio,
                    'activa': target.activa,
                    'fecha_salida': target.fecha_salida.isoformat() if target.fecha_salida else None,
                    'diagnostico': target.diagnostico,
                    'tratamiento': target.tratamiento
                }

                sync.propagate_to_cluster('visita', 'UPDATE', visita_data)
                _is_replicating = False
        except Exception as e:
            _is_replicating = False
            # No fallar la transacción local por errores de propagación
            pass


# ============================================================================
# CONSULTAS DISTRIBUIDAS - Agregación de datos del cluster completo
# ============================================================================

import requests
import logging

cluster_logger = logging.getLogger(__name__)


def get_cluster_nodes_info(bully_manager):
    """
    Obtiene información de todos los nodos del cluster desde bully_manager.

    Args:
        bully_manager: Instancia de BullyNode

    Returns:
        list: Lista de tuplas (node_id, host, tcp_port)
    """
    nodes_info = []

    if not bully_manager:
        return nodes_info

    # Obtener nodos del cluster desde bully_manager
    for node_id, (host, tcp_port, udp_port) in bully_manager.cluster_nodes.items():
        nodes_info.append((node_id, host, tcp_port))

    return nodes_info


def get_all_cluster_doctors(bully_manager, disponible=None, activo=True):
    """
    Consulta doctores de TODAS las salas del cluster.

    Args:
        bully_manager: Instancia de BullyNode
        disponible: (opcional) True/False/None para filtrar disponibilidad
        activo: (opcional) True/False para filtrar estado activo

    Returns:
        list: Lista de dict con información de doctores de todas las salas
    """
    all_doctors = []

    # Agregar doctores locales
    query = Doctor.query.filter_by(activo=activo)
    if disponible is not None:
        query = query.filter_by(disponible=disponible)

    local_doctors = query.all()
    for doc in local_doctors:
        all_doctors.append({
            'id_doctor': doc.id_doctor,
            'nombre': doc.nombre,
            'especialidad': doc.especialidad,
            'disponible': doc.disponible,
            'activo': doc.activo,
            'id_sala': doc.id_sala,
            'source': 'local'
        })

    # Consultar doctores de otros nodos
    nodes_info = get_cluster_nodes_info(bully_manager)

    for node_id, host, tcp_port in nodes_info:
        # Saltear nodo local
        from config import Config
        if node_id == Config.NODE_ID:
            continue

        try:
            # Construir URL
            url = f"http://{host}:{tcp_port}/api/cluster/doctors"
            params = {}
            if disponible is not None:
                params['disponible'] = 'true' if disponible else 'false'
            if activo is not None:
                params['activo'] = 'true' if activo else 'false'

            response = requests.get(url, params=params, timeout=2)

            if response.ok:
                data = response.json()
                for doc in data.get('doctors', []):
                    doc['source'] = f'node_{node_id}'
                    all_doctors.append(doc)
            else:
                cluster_logger.warning(f"Node {node_id} returned status {response.status_code}")

        except requests.exceptions.Timeout:
            cluster_logger.warning(f"Timeout connecting to node {node_id}")
        except requests.exceptions.ConnectionError:
            cluster_logger.warning(f"Connection error to node {node_id} (may be down)")
        except Exception as e:
            cluster_logger.error(f"Error querying node {node_id}: {e}")

    return all_doctors


def get_all_cluster_beds(bully_manager, ocupada=None):
    """
    Consulta camas de TODAS las salas del cluster.

    Args:
        bully_manager: Instancia de BullyNode
        ocupada: (opcional) True/False/None para filtrar ocupación

    Returns:
        list: Lista de dict con información de camas de todas las salas
    """
    all_beds = []

    # Agregar camas locales
    query = Cama.query
    if ocupada is not None:
        query = query.filter_by(ocupada=ocupada)

    local_beds = query.all()
    for cama in local_beds:
        all_beds.append({
            'id_cama': cama.id_cama,
            'numero': cama.numero,
            'ocupada': cama.ocupada,
            'id_sala': cama.id_sala,
            'id_paciente': cama.id_paciente,
            'paciente_nombre': cama.paciente_actual.nombre if cama.paciente_actual else None,
            'source': 'local'
        })

    # Consultar camas de otros nodos
    nodes_info = get_cluster_nodes_info(bully_manager)

    for node_id, host, tcp_port in nodes_info:
        from config import Config
        if node_id == Config.NODE_ID:
            continue

        try:
            url = f"http://{host}:{tcp_port}/api/cluster/beds"
            params = {}
            if ocupada is not None:
                params['ocupada'] = 'true' if ocupada else 'false'

            response = requests.get(url, params=params, timeout=2)

            if response.ok:
                data = response.json()
                for bed in data.get('beds', []):
                    bed['source'] = f'node_{node_id}'
                    all_beds.append(bed)

        except Exception as e:
            cluster_logger.warning(f"Error querying beds from node {node_id}: {e}")

    return all_beds


def get_all_cluster_stats(bully_manager):
    """
    Obtiene estadísticas agregadas de TODO el cluster.

    Args:
        bully_manager: Instancia de BullyNode

    Returns:
        dict: Estadísticas agregadas del cluster completo
    """
    cluster_stats = {
        'nodes': [],
        'total_doctors_available': 0,
        'total_doctors': 0,
        'total_beds_available': 0,
        'total_beds': 0,
        'total_visits_active': 0,
        'total_visits_completed': 0
    }

    # Estadísticas locales
    from config import Config
    local_stats = {
        'node_id': Config.NODE_ID,
        'status': 'local',
        'doctors_available': Doctor.query.filter_by(id_sala=Config.NODE_ID, disponible=True, activo=True).count(),
        'doctors_total': Doctor.query.filter_by(id_sala=Config.NODE_ID, activo=True).count(),
        'beds_available': Cama.query.filter_by(id_sala=Config.NODE_ID, ocupada=False).count(),
        'beds_total': Cama.query.filter_by(id_sala=Config.NODE_ID).count(),
        'visits_active': VisitaEmergencia.query.filter_by(id_sala=Config.NODE_ID, estado='activa').count(),
        'visits_completed': VisitaEmergencia.query.filter_by(id_sala=Config.NODE_ID, estado='completada').count()
    }
    cluster_stats['nodes'].append(local_stats)

    # Agregar a totales
    cluster_stats['total_doctors_available'] += local_stats['doctors_available']
    cluster_stats['total_doctors'] += local_stats['doctors_total']
    cluster_stats['total_beds_available'] += local_stats['beds_available']
    cluster_stats['total_beds'] += local_stats['beds_total']
    cluster_stats['total_visits_active'] += local_stats['visits_active']
    cluster_stats['total_visits_completed'] += local_stats['visits_completed']

    # Consultar otros nodos
    nodes_info = get_cluster_nodes_info(bully_manager)

    for node_id, host, tcp_port in nodes_info:
        if node_id == Config.NODE_ID:
            continue

        try:
            url = f"http://{host}:{tcp_port}/api/cluster/stats"
            response = requests.get(url, timeout=2)

            if response.ok:
                data = response.json()
                node_stats = {
                    'node_id': node_id,
                    'status': 'online',
                    'doctors_available': data['doctors']['available'],
                    'doctors_total': data['doctors']['total'],
                    'beds_available': data['beds']['available'],
                    'beds_total': data['beds']['total'],
                    'visits_active': data['visits']['active'],
                    'visits_completed': data['visits']['completed']
                }
                cluster_stats['nodes'].append(node_stats)

                # Agregar a totales
                cluster_stats['total_doctors_available'] += node_stats['doctors_available']
                cluster_stats['total_doctors'] += node_stats['doctors_total']
                cluster_stats['total_beds_available'] += node_stats['beds_available']
                cluster_stats['total_beds'] += node_stats['beds_total']
                cluster_stats['total_visits_active'] += node_stats['visits_active']
                cluster_stats['total_visits_completed'] += node_stats['visits_completed']
            else:
                cluster_stats['nodes'].append({'node_id': node_id, 'status': 'error'})

        except Exception as e:
            cluster_logger.warning(f"Error querying stats from node {node_id}: {e}")
            cluster_stats['nodes'].append({'node_id': node_id, 'status': 'offline'})

    return cluster_stats


# ============================================================================
# FUNCIONES DE REPLICACIÓN DISTRIBUIDA - Creación de visitas
# ============================================================================

def get_node_flask_url(node_id, host='localhost'):
    """
    Calcula la URL del servidor Flask de un nodo basado en su NODE_ID.

    Args:
        node_id: ID del nodo
        host: Hostname del nodo (default: localhost)

    Returns:
        str: URL completa del Flask server (ej: http://localhost:5001)
    """
    from config import Config
    flask_port = 5000 + node_id % 1000
    return f"http://{host}:{flask_port}"


def get_leader_flask_url(bully_manager):
    """
    Obtiene la URL del servidor Flask del nodo líder actual.

    Args:
        bully_manager: Instancia de BullyNode

    Returns:
        tuple: (leader_id, leader_url) o (None, None) si no hay líder
    """
    if not bully_manager:
        cluster_logger.error("bully_manager is None")
        return None, None

    leader_id = bully_manager.get_current_leader()
    if not leader_id:
        cluster_logger.error("No leader elected yet")
        return None, None

    # Obtener host del líder desde cluster_nodes
    if leader_id in bully_manager.cluster_nodes:
        host, _, _ = bully_manager.cluster_nodes[leader_id]
    else:
        host = 'localhost'

    leader_url = get_node_flask_url(leader_id, host)
    return leader_id, leader_url


def replicate_visit_to_cluster(bully_manager, visita_data, exclude_node_id=None):
    """
    Replica una visita a todos los nodos del cluster (excepto el excluido).

    Usado por el nodo LÍDER para propagar una visita recién creada.

    Args:
        bully_manager: Instancia de BullyNode
        visita_data: Diccionario con datos de la visita a replicar
        exclude_node_id: ID del nodo a excluir (opcional, para no replicar al líder mismo)

    Returns:
        dict: {
            'success_count': int,
            'failed_nodes': [node_ids],
            'total_nodes': int
        }
    """
    from config import Config

    nodes_info = get_cluster_nodes_info(bully_manager)
    success_count = 0
    failed_nodes = []

    for node_id, host, tcp_port in nodes_info:
        # Saltar nodo actual y nodo excluido
        if node_id == Config.NODE_ID or node_id == exclude_node_id:
            continue

        try:
            url = get_node_flask_url(node_id, host)
            endpoint = f"{url}/api/cluster/replicate-visit"

            response = requests.post(endpoint, json=visita_data, timeout=3)

            if response.ok:
                success_count += 1
                cluster_logger.info(f"Visit replicated successfully to node {node_id}")
            else:
                failed_nodes.append(node_id)
                cluster_logger.warning(f"Node {node_id} rejected replication: {response.status_code}")

        except requests.exceptions.Timeout:
            failed_nodes.append(node_id)
            cluster_logger.warning(f"Timeout replicating to node {node_id}")
        except requests.exceptions.ConnectionError:
            failed_nodes.append(node_id)
            cluster_logger.warning(f"Connection error to node {node_id} (may be down)")
        except Exception as e:
            failed_nodes.append(node_id)
            cluster_logger.error(f"Error replicating to node {node_id}: {e}")

    total_nodes = len(nodes_info) - (1 if Config.NODE_ID in [n[0] for n in nodes_info] else 0)
    if exclude_node_id:
        total_nodes -= 1

    return {
        'success_count': success_count,
        'failed_nodes': failed_nodes,
        'total_nodes': total_nodes
    }
