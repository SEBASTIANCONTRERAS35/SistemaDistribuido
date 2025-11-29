from functools import wraps
from flask import redirect, url_for, flash, session
from flask_login import LoginManager, current_user
from models import Usuario, db

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para acceder a esta página.'


@login_manager.user_loader
def load_user(user_id):
    """Cargar usuario por ID para Flask-Login"""
    return Usuario.query.get(int(user_id))


def role_required(roles):
    """
    Decorador para requerir roles específicos.

    Uso:
        @role_required('admin')
        @role_required(['doctor', 'admin'])
    """
    if isinstance(roles, str):
        roles = [roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debes iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('login'))

            if current_user.rol not in roles:
                flash('No tienes permisos para acceder a esta página.', 'danger')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def init_default_users():
    """
    Inicializa usuarios por defecto si no existen.
    Debe llamarse al iniciar la aplicación.

    Segun requisitos del proyecto:
    - TRABAJADOR SOCIAL: Crea visitas de emergencia
    - DOCTOR: Cierra visitas (solo las suyas)
    """
    # Usuarios de prueba basados en poblardb.py
    usuarios_prueba = [
        # Trabajadores sociales (1 por sala)
        {'username': 'social1', 'password': '1234', 'rol': 'trabajador_social', 'id_relacionado': 1},
        {'username': 'social2', 'password': '1234', 'rol': 'trabajador_social', 'id_relacionado': 2},
        {'username': 'social3', 'password': '1234', 'rol': 'trabajador_social', 'id_relacionado': 3},
        {'username': 'social4', 'password': '1234', 'rol': 'trabajador_social', 'id_relacionado': 4},
        # Doctores (3 por sala = 12 total, id_relacionado mapea a doctor.id_doctor)
        {'username': 'doctor1', 'password': 'doctor1', 'rol': 'doctor', 'id_relacionado': 1},
        {'username': 'doctor2', 'password': 'doctor2', 'rol': 'doctor', 'id_relacionado': 2},
        {'username': 'doctor3', 'password': 'doctor3', 'rol': 'doctor', 'id_relacionado': 3},
        {'username': 'doctor4', 'password': 'doctor4', 'rol': 'doctor', 'id_relacionado': 4},
        {'username': 'doctor5', 'password': 'doctor5', 'rol': 'doctor', 'id_relacionado': 5},
        {'username': 'doctor6', 'password': 'doctor6', 'rol': 'doctor', 'id_relacionado': 6},
        {'username': 'doctor7', 'password': 'doctor7', 'rol': 'doctor', 'id_relacionado': 7},
        {'username': 'doctor8', 'password': 'doctor8', 'rol': 'doctor', 'id_relacionado': 8},
        {'username': 'doctor9', 'password': 'doctor9', 'rol': 'doctor', 'id_relacionado': 9},
        {'username': 'doctor10', 'password': 'doctor10', 'rol': 'doctor', 'id_relacionado': 10},
        {'username': 'doctor11', 'password': 'doctor11', 'rol': 'doctor', 'id_relacionado': 11},
        {'username': 'doctor12', 'password': 'doctor12', 'rol': 'doctor', 'id_relacionado': 12},
    ]

    for user_data in usuarios_prueba:
        existing = Usuario.query.filter_by(username=user_data['username']).first()
        if not existing:
            user = Usuario(
                username=user_data['username'],
                rol=user_data['rol'],
                id_relacionado=user_data.get('id_relacionado'),
                activo=True
            )
            user.set_password(user_data['password'])
            db.session.add(user)

    db.session.commit()
    print("Usuarios por defecto inicializados.")


def get_user_info(user):
    """
    Obtiene información extendida del usuario según su rol.
    Retorna un diccionario con datos adicionales del doctor o trabajador social.
    """
    if not user or not user.is_authenticated:
        return None

    info = {
        'id': user.id,
        'username': user.username,
        'rol': user.rol,
        'rol_display': get_rol_display(user.rol),
        'id_relacionado': user.id_relacionado  # CRITICAL: ID del doctor/trabajador para permisos
    }

    if user.rol == 'doctor' and user.id_relacionado:
        from models import Doctor
        doctor = Doctor.query.get(user.id_relacionado)
        if doctor:
            info['nombre'] = doctor.nombre
            info['especialidad'] = doctor.especialidad
            info['sala_id'] = doctor.id_sala
            info['disponible'] = doctor.disponible

    elif user.rol == 'trabajador_social' and user.id_relacionado:
        from models import TrabajadorSocial
        trabajador = TrabajadorSocial.query.get(user.id_relacionado)
        if trabajador:
            info['nombre'] = trabajador.nombre
            info['sala_id'] = trabajador.id_sala

    return info


def get_rol_display(rol):
    """Retorna el nombre del rol para mostrar en la UI"""
    roles_display = {
        'doctor': 'Doctor',
        'trabajador_social': 'Trabajador Social'
    }
    return roles_display.get(rol, rol)


def crear_usuario_para_personal(tipo: str, id_relacionado: int, nombre: str = None) -> dict:
    """
    Crea un usuario automáticamente para un doctor o trabajador social.

    Args:
        tipo: 'doctor' o 'trabajador_social'
        id_relacionado: ID del doctor o trabajador en su tabla
        nombre: Nombre para generar username si se desea personalizar

    Returns:
        {'success': bool, 'username': str, 'password': str, 'error': str}
    """
    try:
        if tipo == 'doctor':
            username = f"doctor{id_relacionado}"
            password = f"doctor{id_relacionado}"
            rol = 'doctor'
        elif tipo == 'trabajador_social':
            username = f"social{id_relacionado}"
            password = "1234"
            rol = 'trabajador_social'
        else:
            return {'success': False, 'error': f'Tipo no válido: {tipo}'}

        # Verificar si ya existe
        existing = Usuario.query.filter_by(username=username).first()
        if existing:
            return {'success': True, 'username': username, 'password': password, 'note': 'Usuario ya existía'}

        # Crear usuario
        user = Usuario(
            username=username,
            rol=rol,
            id_relacionado=id_relacionado,
            activo=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return {'success': True, 'username': username, 'password': password}

    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}


def can_access_sala(user, id_sala):
    """
    Verifica si un usuario puede acceder a recursos de una sala específica.
    Doctores y trabajadores sociales solo pueden acceder a su sala asignada.
    """
    if not user or not user.is_authenticated:
        return False

    user_info = get_user_info(user)
    if user_info and 'sala_id' in user_info:
        return user_info['sala_id'] == id_sala

    return False


def init_all_salas_resources():
    """
    Inicializa recursos de TODAS las salas (1-4).
    Cada nodo tiene copia completa de todos los datos.

    Esto implementa la BD distribuida replicada donde:
    - 4 salas de emergencia
    - 3 doctores por sala (12 total)
    - 10 camas por sala (40 total)
    - 1 trabajador social por sala (4 total)
    """
    from models import db, Sala, Doctor, Cama, TrabajadorSocial

    # Solo inicializar si no hay salas
    if Sala.query.count() > 0:
        print("[INIT] Recursos ya existen, saltando inicialización")
        return

    NUM_SALAS = 4  # 4 salas de emergencia

    # Nombres únicos por sala (sin sufijo S#)
    doctores_por_sala = {
        1: [("Dr. Ricardo Mendiola", "Medicina General"),
            ("Dra. Elena Vázquez", "Urgencias"),
            ("Dr. Samuel Kim", "Medicina Interna")],
        2: [("Dr. Carlos Hernández", "Cardiología"),
            ("Dra. María López", "Pediatría"),
            ("Dr. Jorge Ramírez", "Traumatología")],
        3: [("Dr. Fernando García", "Neurología"),
            ("Dra. Ana Martínez", "Ginecología"),
            ("Dr. Luis Pérez", "Oncología")],
        4: [("Dr. Miguel Torres", "Oftalmología"),
            ("Dra. Patricia Sánchez", "Dermatología"),
            ("Dr. Roberto Díaz", "Psiquiatría")],
    }

    trabajadores_por_sala = {
        1: "Lic. Roberto Gómez",
        2: "Lic. María Fernández",
        3: "Lic. Carlos Mendoza",
        4: "Lic. Ana Patricia Ruiz",
    }

    for sala_id in range(1, NUM_SALAS + 1):
        # 1. Crear sala
        sala = Sala(
            id_sala=sala_id,
            numero=sala_id,
            activa=True
        )
        db.session.add(sala)
        db.session.flush()

        # 2. Crear 3 doctores por sala
        for nombre, especialidad in doctores_por_sala[sala_id]:
            doctor = Doctor(
                nombre=nombre,
                especialidad=especialidad,
                id_sala=sala_id,
                disponible=True,
                activo=True
            )
            db.session.add(doctor)

        # 3. Crear 10 camas por sala (101-110, 201-210, etc.)
        for i in range(1, 11):
            cama = Cama(
                numero=sala_id * 100 + i,
                id_sala=sala_id,
                ocupada=False
            )
            db.session.add(cama)

        # 4. Crear 1 trabajador social por sala
        trabajador = TrabajadorSocial(
            nombre=trabajadores_por_sala[sala_id],
            id_sala=sala_id
        )
        db.session.add(trabajador)

    db.session.commit()
    print(f"[INIT] Recursos inicializados: {NUM_SALAS} salas x (3 doctores + 10 camas + 1 TS)")


def init_sala_for_node(node_id: int):
    """
    Crea sala para este nodo si no existe.
    Soporta N nodos = N salas dinámicamente.

    Args:
        node_id: ID del nodo (se usará como id_sala)
    """
    from models import db, Sala, Doctor, Cama, TrabajadorSocial

    # Validación: node_id debe ser un entero válido
    if node_id is None:
        print("[INIT] ERROR: node_id es None, no se puede crear sala")
        return

    if not isinstance(node_id, int) or node_id < 1:
        print(f"[INIT] ERROR: node_id inválido: {node_id}")
        return

    # Verificar si la sala ya existe (usando filter_by para evitar warning con None)
    sala = Sala.query.filter_by(id_sala=node_id).first()
    if sala:
        print(f"[INIT] Sala {node_id} ya existe, usando existente")
        return

    # Crear la sala
    sala = Sala(
        id_sala=node_id,
        numero=node_id,
        activa=True
    )
    db.session.add(sala)
    db.session.flush()

    # Nombres únicos por sala (sin sufijo S#)
    doctores_por_sala = {
        1: [("Dr. Ricardo Mendiola", "Medicina General"),
            ("Dra. Elena Vázquez", "Urgencias"),
            ("Dr. Samuel Kim", "Medicina Interna")],
        2: [("Dr. Carlos Hernández", "Cardiología"),
            ("Dra. María López", "Pediatría"),
            ("Dr. Jorge Ramírez", "Traumatología")],
        3: [("Dr. Fernando García", "Neurología"),
            ("Dra. Ana Martínez", "Ginecología"),
            ("Dr. Luis Pérez", "Oncología")],
        4: [("Dr. Miguel Torres", "Oftalmología"),
            ("Dra. Patricia Sánchez", "Dermatología"),
            ("Dr. Roberto Díaz", "Psiquiatría")],
    }

    # Fallback para nodos > 4
    doctores_default = [
        ("Dr. Médico General", "Medicina General"),
        ("Dra. Especialista", "Urgencias"),
        ("Dr. Residente", "Medicina Interna")
    ]

    doctores = doctores_por_sala.get(node_id, doctores_default)
    for nombre, especialidad in doctores:
        doctor = Doctor(
            nombre=nombre,
            especialidad=especialidad,
            id_sala=node_id,
            disponible=True,
            activo=True
        )
        db.session.add(doctor)

    # Crear 10 camas para esta sala (N01-N10, donde N es el node_id)
    for i in range(1, 11):
        cama = Cama(
            numero=node_id * 100 + i,  # 101-110, 201-210, 501-510, etc.
            id_sala=node_id,
            ocupada=False
        )
        db.session.add(cama)

    # Nombres únicos por sala para trabajadores sociales
    trabajadores_por_sala = {
        1: "Lic. Roberto Gómez",
        2: "Lic. María Fernández",
        3: "Lic. Carlos Mendoza",
        4: "Lic. Ana Patricia Ruiz",
    }

    nombre_trabajador = trabajadores_por_sala.get(node_id, f"Lic. Trabajador Social {node_id}")
    trabajador = TrabajadorSocial(
        nombre=nombre_trabajador,
        id_sala=node_id
    )
    db.session.add(trabajador)

    db.session.commit()

    # Crear usuarios para el personal recién creado
    _crear_usuarios_para_sala(node_id)

    print(f"[INIT] Sala {node_id} creada con 3 doctores, 10 camas, 1 trabajador social")


def _crear_usuarios_para_sala(sala_id: int):
    """Crea usuarios de login para el personal de una sala recién creada."""
    from models import Doctor, TrabajadorSocial

    # Crear usuarios para doctores de esta sala
    doctores = Doctor.query.filter_by(id_sala=sala_id).all()
    for doctor in doctores:
        crear_usuario_para_personal('doctor', doctor.id_doctor, doctor.nombre)

    # Crear usuario para trabajador social de esta sala
    trabajadores = TrabajadorSocial.query.filter_by(id_sala=sala_id).all()
    for trab in trabajadores:
        crear_usuario_para_personal('trabajador_social', trab.id_trabajador, trab.nombre)


def get_active_sala_ids(bully_manager=None):
    """
    Retorna IDs de salas cuyos nodos están activos en el cluster.
    Incluye el nodo actual + todos los nodos en cluster_nodes.

    Args:
        bully_manager: Instancia de BullyNode (opcional)

    Returns:
        List[int]: Lista de IDs de salas activas en el cluster
    """
    from models import Sala

    if bully_manager is None:
        # Sin bully_manager, retornar todas las salas activas de BD
        return [s.id_sala for s in Sala.query.filter_by(activa=True).all()]

    # Incluir nodo actual + todos los nodos conocidos en el cluster
    active_ids = {bully_manager.node_id}
    # Crear copia para thread-safety
    active_ids.update(dict(bully_manager.cluster_nodes).keys())
    return list(active_ids)


def get_all_salas(bully_manager=None):
    """
    Obtiene salas activas de la BD, filtradas por nodos activos del cluster.
    Para uso en selectores dinámicos de UI.

    Args:
        bully_manager: Instancia de BullyNode para filtrar por nodos activos

    Returns:
        List[tuple]: Lista de (label, value) para Select widgets
    """
    from models import Sala

    query = Sala.query.filter_by(activa=True)

    # Filtrar por nodos activos si hay bully_manager
    if bully_manager is not None:
        active_ids = get_active_sala_ids(bully_manager)
        if active_ids:
            query = query.filter(Sala.id_sala.in_(active_ids))

    salas = query.order_by(Sala.numero).all()
    return [(f"Sala {s.numero}", s.id_sala) for s in salas]


def get_all_salas_with_todas(bully_manager=None):
    """
    Obtiene salas activas + opción "Todas las salas", filtradas por nodos activos.
    Para filtros en UI.

    Args:
        bully_manager: Instancia de BullyNode para filtrar por nodos activos

    Returns:
        List[tuple]: Lista de (label, value) para Select widgets
    """
    from models import Sala

    query = Sala.query.filter_by(activa=True)

    # Filtrar por nodos activos si hay bully_manager
    if bully_manager is not None:
        active_ids = get_active_sala_ids(bully_manager)
        if active_ids:
            query = query.filter(Sala.id_sala.in_(active_ids))

    salas = query.order_by(Sala.numero).all()
    options = [("Todas las salas", "todas")]
    options.extend([(f"Sala {s.numero}", str(s.id_sala)) for s in salas])
    return options
