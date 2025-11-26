"""
Módulo para generación automática de IDs únicos para nodos en el cluster.

FASE 9: IDs secuenciales desde 1 con discovery previo.

Estrategia:
1. Delay desincronizado basado en IP (1-10s, evita arranque simultáneo)
2. Discovery ACTIVO de 3 segundos (detecta IDs existentes con queries)
3. Tomar menor ID libre desde 1
4. Resolución de colisiones por IP como fallback
"""
import time
import random
import os
import json
import logging
import fcntl
import atexit
import socket
import struct

logger = logging.getLogger(__name__)

# Variable global para mantener locks activos durante la vida del proceso
_active_locks = {}


def _is_port_available(port: int, host: str = '0.0.0.0') -> bool:
    """
    Verifica si un puerto está disponible intentando bind temporal.

    Args:
        port: Puerto a verificar
        host: Dirección IP para bind (default: 0.0.0.0)

    Returns:
        bool: True si el puerto está libre, False si está ocupado
    """
    import socket

    # Probar TCP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError:
        return False

    # Probar UDP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError:
        return False

    return True


# ============================================================================
# FASE 9: Funciones para IDs secuenciales con discovery previo
# ============================================================================

def get_startup_delay() -> float:
    """
    Calcula delay inicial basado en último octeto de IP.

    FASE 9 FIX: Delays mínimos pero suficientes para evitar colisiones.
    El primer nodo debe terminar discovery Y empezar a enviar ANNOUNCE
    antes de que el segundo termine su discovery.

    Ejemplos:
        IP .12 → delay ~3s (1 + 2*1)
        IP .16 → delay ~7s (1 + 6*1)
        Diferencia de 4s + discovery 3s = VM2 detecta VM1

    Returns:
        float: Delay en segundos (1.0 a 10.0)
    """
    try:
        # Detectar IP local
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()

        last_octet = int(ip.split('.')[-1])
        # Delay ultra-corto: 0.1-1.0s
        # IP .12 → 0.2s, IP .16 → 0.6s, IP .20 → 1.0s
        delay = 0.1 + (last_octet % 10) * 0.1
        logger.info(f"[ID_GEN] IP={ip}, last_octet={last_octet}, calculated delay={delay:.1f}s")
        return delay
    except Exception as e:
        # Fallback: delay aleatorio
        delay = random.uniform(0.1, 0.5)
        logger.warning(f"[ID_GEN] Could not detect IP, using random delay={delay:.2f}s: {e}")
        return delay


def discover_existing_ids(timeout: float = 1.0) -> set:
    """
    Discovery ultra-rápido con queries agresivos cada 100ms.
    Termina early si detecta nodos (0.5s después de primer nodo).

    Args:
        timeout: Tiempo máximo de discovery (default 1.0s)

    Returns:
        set: Conjunto de IDs ya en uso
    """
    existing_ids = set()
    multicast_group = '224.0.0.100'
    multicast_port = 5005

    try:
        # Socket para escuchar Y enviar
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        sock.bind(('', multicast_port))
        sock.settimeout(0.05)  # 50ms timeout para recv (permite queries frecuentes)

        # Unirse a grupo multicast
        try:
            mreq = struct.pack("4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception as e:
            logger.warning(f"[ID_GEN] Could not join multicast: {e}")

        # Configurar TTL para envío multicast
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)

        logger.info(f"[ID_GEN] 🔍 Ultra-fast discovery ({timeout}s max, early exit enabled)...")

        # Query agresivo
        query_msg = json.dumps({
            'type': 'ID_QUERY',
            'timestamp': time.time()
        }).encode()

        start_time = time.time()
        last_query = 0
        first_node_found_at = None

        while True:
            current_time = time.time()
            elapsed = current_time - start_time

            # Timeout principal
            if elapsed >= timeout:
                break

            # Early exit: 0.5s después de encontrar primer nodo
            if first_node_found_at and (current_time - first_node_found_at) >= 0.5:
                logger.info(f"[ID_GEN] Early exit after 0.5s - found {len(existing_ids)} node(s)")
                break

            # Enviar query cada 100ms (10 queries por segundo)
            if current_time - last_query >= 0.1:
                try:
                    sock.sendto(query_msg, (multicast_group, multicast_port))
                    last_query = current_time
                except:
                    pass

            # Escuchar respuestas
            try:
                data, addr = sock.recvfrom(1024)
                msg = json.loads(data.decode())

                # Aceptar ANNOUNCE, ID_RESPONSE o HEARTBEAT
                if msg.get('node_id'):
                    msg_type = msg.get('type', '')
                    if msg_type in ('ANNOUNCE', 'ID_RESPONSE', 'HEARTBEAT'):
                        node_id = msg['node_id']
                        if node_id not in existing_ids:
                            existing_ids.add(node_id)
                            logger.info(f"[ID_GEN] ✓ Found node ID={node_id} (via {msg_type})")

                            # Marcar cuando encontramos el primer nodo
                            if first_node_found_at is None:
                                first_node_found_at = current_time

            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.debug(f"[ID_GEN] Discovery recv error: {e}")
                continue

        sock.close()

    except Exception as e:
        logger.warning(f"[ID_GEN] Discovery failed: {e}")

    if existing_ids:
        logger.info(f"[ID_GEN] Discovery complete: found {len(existing_ids)} node(s) - IDs {sorted(existing_ids)}")
    else:
        logger.info("[ID_GEN] Discovery complete: no existing nodes found")

    return existing_ids


def get_next_available_id(existing_ids: set, start_from: int = 1) -> int:
    """
    Obtiene el siguiente ID disponible comenzando desde start_from.

    Args:
        existing_ids: IDs ya en uso
        start_from: ID inicial (default 1)

    Returns:
        int: Menor ID libre >= start_from

    Raises:
        RuntimeError: Si no hay IDs disponibles
    """
    candidate = start_from
    while candidate in existing_ids:
        candidate += 1
        if candidate > 254:  # Límite práctico
            raise RuntimeError("No hay IDs disponibles (cluster lleno)")
    return candidate


def get_or_create_node_id_v2(persist_file: str = None, force_new: bool = False) -> int:
    """
    Genera NODE_ID secuencial (1, 2, 3...) con discovery previo.

    IMPORTANTE: Para clusters dinámicos, SIEMPRE hace discovery primero.
    NO usa persistencia para evitar conflictos entre VMs.

    Proceso:
    1. Aplicar delay desincronizado basado en IP
    2. Escuchar por 3 segundos para descubrir nodos existentes
    3. Tomar el menor ID libre (empezando desde 1)
    4. Verificar puertos disponibles

    Args:
        persist_file: No usado (mantenido para compatibilidad)
        force_new: No usado (siempre genera nuevo ID con discovery)

    Returns:
        int: NODE_ID único secuencial desde 1

    Examples:
        VM1 arranca primero → ID=1
        VM2 arranca después → ID=2
        VM3 arranca después → ID=3
    """
    # FIX FASE 9: NO usar persistencia en clusters dinámicos
    # La persistencia causa colisiones cuando múltiples VMs arrancan
    # porque el check de puertos solo verifica LOCAL, no otros nodos

    # 1. Delay desincronizado basado en IP
    delay = get_startup_delay()
    logger.info(f"[ID_GEN] ⏳ Startup delay: {delay:.2f}s (desynchronizing with other VMs)")
    time.sleep(delay)

    # 2. Discovery ultra-rápido (1s max, early exit enabled)
    logger.info("[ID_GEN] 🔍 Discovering existing nodes...")
    existing_ids = discover_existing_ids(timeout=1.0)

    if existing_ids:
        logger.info(f"[ID_GEN] Found {len(existing_ids)} existing node(s): {sorted(existing_ids)}")
    else:
        logger.info("[ID_GEN] No existing nodes found - this will be the first node")

    # 3. Obtener menor ID libre desde 1
    new_id = get_next_available_id(existing_ids, start_from=1)
    logger.info(f"[ID_GEN] 🎯 Selected NODE_ID={new_id}")

    # 4. Verificar puertos disponibles
    tcp_port = 5555 + (new_id % 1000)
    udp_port = 6000 + (new_id % 1000)

    attempts = 0
    while not _is_port_available(tcp_port) or not _is_port_available(udp_port):
        logger.warning(f"[ID_GEN] Ports for ID {new_id} in use (TCP:{tcp_port}, UDP:{udp_port}), trying next...")
        existing_ids.add(new_id)
        new_id = get_next_available_id(existing_ids, start_from=new_id + 1)
        tcp_port = 5555 + (new_id % 1000)
        udp_port = 6000 + (new_id % 1000)
        attempts += 1
        if attempts > 50:
            raise RuntimeError("Could not find available ports after 50 attempts")

    logger.info(f"[ID_GEN] ✅ Final NODE_ID={new_id} (TCP:{tcp_port}, UDP:{udp_port})")

    # NO persistir - cada arranque hace discovery fresco para evitar colisiones
    return new_id


def _release_all_locks():
    """Libera todos los locks activos al cerrar el proceso."""
    global _active_locks
    for node_id, lock_file in list(_active_locks.items()):
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            logger.debug(f"Released lock for node ID {node_id}")
        except Exception as e:
            logger.warning(f"Failed to release lock for node ID {node_id}: {e}")
    _active_locks.clear()

# Registrar cleanup al salir del proceso
atexit.register(_release_all_locks)


def release_node_id_lock(node_id: int) -> bool:
    """
    Libera el lock de un NODE_ID específico.

    Args:
        node_id: ID del nodo cuyo lock se quiere liberar

    Returns:
        bool: True si se liberó exitosamente
    """
    global _active_locks
    if node_id in _active_locks:
        try:
            lock_file = _active_locks[node_id]
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            del _active_locks[node_id]
            logger.info(f"Released lock for node ID {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to release lock for node ID {node_id}: {e}")
            return False
    return False


def generate_node_id(start_id: int = 1, max_attempts: int = 100) -> int:
    """
    Genera un ID de nodo único usando file locking atómico.

    Utiliza fcntl.flock() para garantizar que solo un proceso puede
    obtener cada ID, incluso si múltiples VMs arrancan simultáneamente.

    Estrategia:
    1. Intentar ID candidato (empezando desde start_id)
    2. Intentar obtener lock exclusivo en archivo /tmp/bully_node_locks/node_N.lock
    3. Si obtiene lock, verificar que puertos estén libres
    4. Si todo OK, mantener lock y retornar ID
    5. Si no, liberar lock y probar siguiente ID

    Args:
        start_id: ID inicial para comenzar búsqueda (default: 1)
        max_attempts: Máximo número de intentos (default: 100)

    Returns:
        int: ID único disponible (rango: 1-100+)

    Raises:
        RuntimeError: Si no se encuentra ID libre después de max_attempts
    """
    global _active_locks

    # Directorio para locks (usar /tmp para que sea compartido entre VMs si usan NFS,
    # o local si no - en ambos casos funciona)
    lock_dir = '/tmp/bully_node_locks'
    os.makedirs(lock_dir, exist_ok=True)

    for attempt in range(max_attempts):
        candidate_id = start_id + attempt

        # Calcular puertos basados en el ID candidato
        tcp_port = 5555 + (candidate_id % 1000)
        udp_port = 6000 + (candidate_id % 1000)

        lock_file_path = os.path.join(lock_dir, f'node_{candidate_id}.lock')

        try:
            # Abrir/crear archivo de lock
            lock_file = open(lock_file_path, 'w')

            # Intentar obtener lock EXCLUSIVO y NO-BLOQUEANTE
            # Si otro proceso tiene el lock, lanza BlockingIOError inmediatamente
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Tenemos el lock! Ahora verificar que puertos estén libres
            if _is_port_available(tcp_port) and _is_port_available(udp_port):
                # Escribir info del proceso que tiene el lock
                lock_file.write(f"pid={os.getpid()}\n")
                lock_file.write(f"timestamp={time.time()}\n")
                lock_file.write(f"node_id={candidate_id}\n")
                lock_file.flush()

                # IMPORTANTE: Mantener archivo abierto para mantener el lock
                _active_locks[candidate_id] = lock_file

                logger.info(f"Acquired NODE_ID {candidate_id} with lock (TCP:{tcp_port}, UDP:{udp_port})")
                return candidate_id
            else:
                # Puertos ocupados pero lock estaba libre - liberar lock
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                logger.debug(f"ID {candidate_id} locked but ports in use, trying next")

        except BlockingIOError:
            # Otro proceso ya tiene el lock para este ID
            logger.debug(f"ID {candidate_id} locked by another process")
            try:
                lock_file.close()
            except:
                pass
            continue

        except Exception as e:
            logger.debug(f"ID {candidate_id} failed: {e}")
            try:
                lock_file.close()
            except:
                pass
            continue

    # No se encontró ID libre
    raise RuntimeError(
        f"No available node ID found after {max_attempts} attempts. "
        f"Cluster may be full or ports are blocked."
    )


def get_persistent_id_file(use_process_unique: bool = True) -> str:
    """
    Retorna la ruta al archivo donde se persiste el node ID.

    Args:
        use_process_unique: Si True, usa un archivo único por proceso (PID-based)
                           para evitar colisiones en clusters dinámicos.
                           Si False, usa un archivo compartido (solo para nodo único).

    El archivo se guarda en ../data/node_ids/ para mantener
    el mismo ID entre reinicios del nodo.

    Returns:
        str: Ruta absoluta al archivo de persistencia
    """
    # Directorio del módulo actual
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Subir dos niveles y entrar a data/node_ids/
    data_dir = os.path.join(current_dir, '..', '..', 'data', 'node_ids')

    # Crear directorio si no existe
    os.makedirs(data_dir, exist_ok=True)

    if use_process_unique:
        # Archivo único por proceso usando PID
        # Esto previene colisiones cuando múltiples nodos inician simultáneamente
        pid = os.getpid()
        return os.path.join(data_dir, f'node_pid_{pid}.json')
    else:
        # Archivo compartido (solo para un único nodo persistente)
        return os.path.join(data_dir, 'node_id.json')


def save_node_id(node_id: int, persist_file: str = None, use_process_unique: bool = True) -> None:
    """
    Guarda el node ID en un archivo para persistencia.

    Args:
        node_id: ID del nodo a guardar
        persist_file: Ruta al archivo (opcional, usa default si no se proporciona)
        use_process_unique: Si True, usa archivo único por proceso
    """
    if persist_file is None:
        persist_file = get_persistent_id_file(use_process_unique=use_process_unique)

    try:
        data = {
            'node_id': node_id,
            'generated_at': time.time(),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        with open(persist_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved node ID {node_id} to {persist_file}")

    except Exception as e:
        logger.error(f"Failed to save node ID to file: {e}")
        # No es crítico, el nodo puede seguir funcionando sin persistencia


def load_node_id(persist_file: str = None, use_process_unique: bool = True) -> int:
    """
    Carga el node ID desde el archivo de persistencia.

    Args:
        persist_file: Ruta al archivo (opcional, usa default si no se proporciona)
        use_process_unique: Si True, usa archivo único por proceso

    Returns:
        int: Node ID guardado, o None si no existe o no se puede leer
    """
    if persist_file is None:
        persist_file = get_persistent_id_file(use_process_unique=use_process_unique)

    if not os.path.exists(persist_file):
        logger.debug(f"No persistent ID file found at {persist_file}")
        return None

    try:
        with open(persist_file, 'r') as f:
            data = json.load(f)

        node_id = data.get('node_id')

        if node_id is not None:
            logger.info(f"Loaded node ID {node_id} from {persist_file}")
            return int(node_id)
        else:
            logger.warning(f"Invalid data in persistent ID file: {persist_file}")
            return None

    except Exception as e:
        logger.error(f"Failed to load node ID from file: {e}")
        return None


def get_or_create_node_id_DEPRECATED_DO_NOT_USE(persist_file: str = None, force_new: bool = False, use_process_unique: bool = True) -> int:
    """
    DEPRECATED: Use get_or_create_node_id_v2() instead.

    Obtiene el node ID persistido o genera uno nuevo secuencial si no existe.

    Este es el método principal que deberían usar las aplicaciones.
    Genera IDs secuenciales (1, 2, 3...) verificando disponibilidad de puertos.

    Args:
        persist_file: Ruta al archivo de persistencia (opcional)
        force_new: Si True, siempre genera un nuevo ID ignorando el persistido
        use_process_unique: Si True, usa archivo único por proceso (recomendado para clusters dinámicos)

    Returns:
        int: Node ID (existente o nuevo secuencial 1-100+)

    Examples:
        >>> # Cluster vacío - primera ejecución
        >>> id1 = get_or_create_node_id()  # Retorna 1
        >>> # Segunda ejecución en MISMO proceso - usa el mismo ID
        >>> id2 = get_or_create_node_id()
        >>> id1 == id2  # True
        True
        >>> # Nuevo proceso con nodo 1 corriendo
        >>> # id3 = get_or_create_node_id()  # Retorna 2
        >>> # Nuevo proceso con nodos 1,2 corriendo
        >>> # id4 = get_or_create_node_id()  # Retorna 3
    """
    if not force_new:
        # Intentar cargar ID existente
        existing_id = load_node_id(persist_file, use_process_unique=use_process_unique)
        if existing_id is not None:
            return existing_id

    # Generar nuevo ID secuencial (1, 2, 3...)
    new_id = generate_node_id()

    # Guardar para próximas ejecuciones
    save_node_id(new_id, persist_file, use_process_unique=use_process_unique)

    return new_id


def validate_node_id(node_id: int) -> bool:
    """
    Valida que un node ID sea válido.

    Un ID válido debe ser:
    - Un entero positivo
    - Mayor que 0
    - Menor que 2^31 (límite práctico para evitar overflow)

    Args:
        node_id: ID a validar

    Returns:
        bool: True si el ID es válido, False en caso contrario
    """
    if not isinstance(node_id, int):
        return False

    if node_id <= 0:
        return False

    if node_id >= 2**31:  # ~2 billones
        return False

    return True


def clear_persistent_id(persist_file: str = None, use_process_unique: bool = True) -> bool:
    """
    Elimina el archivo de persistencia del node ID.

    Útil para testing o para forzar regeneración de ID.

    Args:
        persist_file: Ruta al archivo (opcional)
        use_process_unique: Si True, usa archivo único por proceso

    Returns:
        bool: True si se eliminó exitosamente, False en caso contrario
    """
    if persist_file is None:
        persist_file = get_persistent_id_file(use_process_unique=use_process_unique)

    try:
        if os.path.exists(persist_file):
            os.remove(persist_file)
            logger.info(f"Cleared persistent ID file: {persist_file}")
            return True
        else:
            logger.debug(f"No persistent ID file to clear at {persist_file}")
            return False

    except Exception as e:
        logger.error(f"Failed to clear persistent ID file: {e}")
        return False
