"""
Módulo de descubrimiento dinámico de nodos via multicast UDP.

Permite que los nodos se descubran automáticamente en la red sin
configuración previa. Ideal para clusters dinámicos donde los nodos
pueden unirse/salir en cualquier momento.

Incluye:
- Descubrimiento via multicast UDP
- Fallback via broadcast UDP (para redes sin multicast)
- Resolución automática de colisiones de ID
- Detección robusta de IP local
"""
import socket
import struct
import threading
import time
import json
import logging
import subprocess
from typing import Dict, Callable, Tuple, Optional

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """
    Detecta IP local robustamente para VMs con múltiples interfaces.

    FASE 9: Mejorado para evitar IPs compartidas (.11, .1, etc.)

    Prioridad:
    1. IP usada para routing externo (8.8.8.8) - más confiable
    2. Primera IP válida de hostname -I (filtrando .1, .11, .255)
    3. IP de hostname
    4. Fallback a 127.0.0.1

    Returns:
        str: IP local detectada (única para esta VM)
    """
    # 1. Via routing (MÁS CONFIABLE para VMs)
    # Esta es la IP que realmente se usa para comunicación de red
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith('127.'):
            logger.info(f"[DISCOVERY] Detected IP via routing: {ip}")
            return ip
    except Exception:
        pass

    # 2. Via hostname -I (Linux) - preferir IPs que NO sean compartidas
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        ips = result.stdout.strip().split()

        # Filtrar IPs no deseadas
        valid_ips = []
        for ip in ips:
            if ip and not ip.startswith('127.') and '.' in ip:
                last_octet = ip.split('.')[-1]
                # Evitar IPs comunes de gateway (.1) o compartidas (.11)
                # Estas IPs suelen ser iguales en múltiples VMs
                if last_octet not in ('1', '11', '255', '0'):
                    valid_ips.append(ip)

        # Si hay IPs válidas, usar la primera
        if valid_ips:
            logger.info(f"[DISCOVERY] Detected IP via hostname -I (filtered): {valid_ips[0]}")
            return valid_ips[0]

        # Si no hay IPs filtradas, usar cualquier IP no-loopback
        for ip in ips:
            if ip and not ip.startswith('127.') and '.' in ip:
                logger.info(f"[DISCOVERY] Detected IP via hostname -I (fallback): {ip}")
                return ip
    except Exception:
        pass

    # 3. Via hostname
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith('127.'):
            logger.info(f"[DISCOVERY] Detected IP via hostname: {ip}")
            return ip
    except Exception:
        pass

    # 4. Fallback
    logger.warning("[DISCOVERY] Could not detect valid IP, using 127.0.0.1")
    return "127.0.0.1"


class NodeDiscovery:
    """
    Maneja el descubrimiento automático de nodos usando multicast UDP.

    Protocolo:
    - ANNOUNCE: Nodo anuncia su presencia periódicamente
    - NODE_INFO: Respuesta con información del nodo (IP, puertos, ID)
    - HEARTBEAT: Confirmación de que el nodo sigue activo
    """

    def __init__(
        self,
        node_id: int,
        tcp_port: int,
        udp_port: int,
        multicast_group: str = '224.0.0.100',
        multicast_port: int = 5005,
        announce_interval: int = 5,
        node_timeout: int = 15,
        use_broadcast_fallback: bool = True,
        multicast_ttl: int = 4
    ):
        """
        Inicializa el módulo de descubrimiento.

        Args:
            node_id: ID único del nodo
            tcp_port: Puerto TCP para mensajes Bully
            udp_port: Puerto UDP para heartbeats
            multicast_group: Grupo multicast para descubrimiento
            multicast_port: Puerto multicast
            announce_interval: Intervalo entre anuncios (segundos)
            node_timeout: Tiempo para considerar nodo muerto (segundos)
            use_broadcast_fallback: Si True, también envía broadcast UDP como fallback
            multicast_ttl: TTL para paquetes multicast (default 4 para redes complejas)
        """
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.announce_interval = announce_interval
        self.node_timeout = node_timeout
        self.use_broadcast_fallback = use_broadcast_fallback
        self.multicast_ttl = multicast_ttl

        # Detectar IP local automáticamente
        self.local_ip = get_local_ip()

        # Diccionario de nodos descubiertos: {node_id: {'host': ip, 'tcp_port': ..., 'udp_port': ..., 'last_seen': timestamp}}
        self.discovered_nodes: Dict[int, dict] = {}
        self.lock = threading.Lock()

        # Sockets
        self.send_socket: Optional[socket.socket] = None
        self.recv_socket: Optional[socket.socket] = None
        self.broadcast_socket: Optional[socket.socket] = None

        # Control de threads
        self.running = False
        self.announce_thread: Optional[threading.Thread] = None
        self.listen_thread: Optional[threading.Thread] = None
        self.cleanup_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_node_discovered: Optional[Callable] = None
        self.on_node_lost: Optional[Callable] = None
        self.on_id_collision: Optional[Callable] = None  # Callback para colisión de IDs
        self.on_collision_regenerate: Optional[Callable] = None  # Callback para regenerar ID

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Initialized")
        logger.info(f"[Node-{self.node_id}] [DISCOVERY]   Local IP: {self.local_ip}")
        logger.info(f"[Node-{self.node_id}] [DISCOVERY]   Multicast: {multicast_group}:{multicast_port} (TTL={multicast_ttl})")
        logger.info(f"[Node-{self.node_id}] [DISCOVERY]   Broadcast fallback: {use_broadcast_fallback}")

    def start(self):
        """Inicia el servicio de descubrimiento."""
        if self.running:
            logger.warning(f"[Node-{self.node_id}] [DISCOVERY] Already running")
            return

        self.running = True

        # Crear socket de envío (multicast) con TTL configurable
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.multicast_ttl)

        # Crear socket de recepción (multicast)
        self.recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # En macOS/BSD, también necesitamos SO_REUSEPORT para multicast
        try:
            self.recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        # Bind al puerto multicast
        self.recv_socket.bind(('', self.multicast_port))

        # FASE 9: Unirse al grupo multicast en TODAS las interfaces
        self._join_multicast_all_interfaces()

        # Crear socket de broadcast si está habilitado
        if self.use_broadcast_fallback:
            try:
                self.broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Broadcast socket created")
            except Exception as e:
                logger.warning(f"[Node-{self.node_id}] [DISCOVERY] Failed to create broadcast socket: {e}")
                self.broadcast_socket = None

        # Iniciar threads
        self.announce_thread = threading.Thread(target=self._announce_loop, daemon=True)
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)

        self.announce_thread.start()
        self.listen_thread.start()
        self.cleanup_thread.start()

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Service started")

    def _join_multicast_all_interfaces(self):
        """
        FASE 9: Une al grupo multicast en todas las interfaces de red.

        Esto es crítico para VMs con múltiples interfaces (bridge + NAT),
        ya que asegura que los mensajes multicast se reciban en cualquier interfaz.
        """
        joined_count = 0

        # Intentar obtener todas las IPs locales
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
            ips = result.stdout.strip().split()

            for ip in ips:
                if ip and not ip.startswith('127.') and '.' in ip:
                    try:
                        mreq = struct.pack("4s4s",
                            socket.inet_aton(self.multicast_group),
                            socket.inet_aton(ip)
                        )
                        self.recv_socket.setsockopt(
                            socket.IPPROTO_IP,
                            socket.IP_ADD_MEMBERSHIP,
                            mreq
                        )
                        joined_count += 1
                        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Joined multicast on interface {ip}")
                    except Exception as e:
                        logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Failed to join multicast on {ip}: {e}")

        except Exception as e:
            logger.warning(f"[Node-{self.node_id}] [DISCOVERY] Failed to enumerate interfaces: {e}")

        # Si no pudimos unir a ninguna interfaz, usar fallback INADDR_ANY
        if joined_count == 0:
            try:
                mreq = struct.pack("4sl",
                    socket.inet_aton(self.multicast_group),
                    socket.INADDR_ANY
                )
                self.recv_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                logger.info(f"[Node-{self.node_id}] [DISCOVERY] Joined multicast on INADDR_ANY (fallback)")
            except Exception as e:
                logger.error(f"[Node-{self.node_id}] [DISCOVERY] Failed to join multicast: {e}")

    def _ip_to_int(self, ip: str) -> int:
        """
        FASE 9: Convierte IP a entero para comparación numérica.

        Args:
            ip: Dirección IP en formato string (ej: "192.168.1.100")

        Returns:
            int: Representación numérica de la IP
        """
        try:
            parts = ip.split('.')
            return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])
        except (ValueError, IndexError):
            return 0

    def stop(self):
        """Detiene el servicio de descubrimiento."""
        if not self.running:
            return

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Stopping service...")
        self.running = False

        # Enviar mensaje de salida
        self._send_leave_message()

        # Cerrar sockets
        if self.send_socket:
            self.send_socket.close()
        if self.recv_socket:
            self.recv_socket.close()
        if self.broadcast_socket:
            self.broadcast_socket.close()

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Service stopped")

    def _announce_loop(self):
        """Thread que anuncia presencia periódicamente via multicast + broadcast."""
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Announce thread started")

        while self.running:
            try:
                # Enviar via multicast
                self._send_announce()

                # También enviar via broadcast como fallback
                if self.use_broadcast_fallback and self.broadcast_socket:
                    self._send_announce_broadcast()

                time.sleep(self.announce_interval)
            except Exception as e:
                logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error in announce loop: {e}")

    def _listen_loop(self):
        """Thread que escucha mensajes multicast."""
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Listen thread started")
        self.recv_socket.settimeout(1.0)  # Timeout para poder verificar self.running

        while self.running:
            try:
                data, addr = self.recv_socket.recvfrom(1024)
                self._handle_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error in listen loop: {e}")

    def _cleanup_loop(self):
        """Thread que limpia nodos inactivos."""
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Cleanup thread started")

        while self.running:
            try:
                current_time = time.time()
                nodes_to_remove = []

                with self.lock:
                    for node_id, info in self.discovered_nodes.items():
                        time_since_seen = current_time - info['last_seen']
                        if time_since_seen > self.node_timeout:
                            nodes_to_remove.append(node_id)
                            logger.warning(f"[Node-{self.node_id}] [DISCOVERY] Node {node_id} timeout ({time_since_seen:.1f}s)")

                # Remover nodos muertos
                for node_id in nodes_to_remove:
                    self._remove_node(node_id)

                time.sleep(self.announce_interval)
            except Exception as e:
                logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error in cleanup loop: {e}")

    def _send_announce(self):
        """Envía mensaje ANNOUNCE por multicast."""
        message = {
            'type': 'ANNOUNCE',
            'node_id': self.node_id,
            'tcp_port': self.tcp_port,
            'udp_port': self.udp_port,
            'timestamp': time.time()
        }

        data = json.dumps(message).encode('utf-8')
        self.send_socket.sendto(data, (self.multicast_group, self.multicast_port))
        logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Sent ANNOUNCE (multicast)")

    def _send_announce_broadcast(self):
        """
        Envía mensaje ANNOUNCE via broadcast UDP como fallback.
        Útil cuando multicast no funciona en la red.
        """
        if not self.broadcast_socket:
            return

        message = {
            'type': 'ANNOUNCE',
            'node_id': self.node_id,
            'tcp_port': self.tcp_port,
            'udp_port': self.udp_port,
            'timestamp': time.time()
        }

        data = json.dumps(message).encode('utf-8')

        # Calcular dirección broadcast de la subred (asume /24)
        try:
            ip_parts = self.local_ip.split('.')
            if len(ip_parts) == 4:
                broadcast_ip = '.'.join(ip_parts[:3]) + '.255'
                self.broadcast_socket.sendto(data, (broadcast_ip, self.multicast_port))
                logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Sent ANNOUNCE (broadcast to {broadcast_ip})")
        except Exception as e:
            logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Broadcast failed: {e}")

    def _send_leave_message(self):
        """Envía mensaje LEAVE al salir."""
        message = {
            'type': 'LEAVE',
            'node_id': self.node_id,
            'timestamp': time.time()
        }

        try:
            data = json.dumps(message).encode('utf-8')
            self.send_socket.sendto(data, (self.multicast_group, self.multicast_port))
            logger.info(f"[Node-{self.node_id}] [DISCOVERY] Sent LEAVE message")
        except Exception as e:
            logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error sending LEAVE: {e}")

    def _handle_message(self, data: bytes, addr: Tuple[str, int]):
        """Procesa mensaje recibido."""
        try:
            message = json.loads(data.decode('utf-8'))
            msg_type = message.get('type')
            sender_id = message.get('node_id')

            # Detectar colisión de ID: otro nodo con mi mismo ID
            if sender_id == self.node_id:
                sender_ip = addr[0]

                # Verificar si es un mensaje de loopback (mismo host)
                # Incluimos nuestra IP local en la verificación
                is_loopback = (
                    sender_ip == '127.0.0.1' or
                    sender_ip == 'localhost' or
                    sender_ip == '::1' or  # IPv6 localhost
                    sender_ip.startswith('127.') or  # Cualquier IP en 127.0.0.0/8
                    sender_ip == '0.0.0.0' or
                    sender_ip == self.local_ip  # Es mi propia IP
                )

                # Si NO es loopback, entonces es una colisión real de ID
                if not is_loopback:
                    logger.warning(f"[Node-{self.node_id}] [DISCOVERY] ⚠️  ID COLLISION detected! Node {sender_id} at {sender_ip}")

                    # Resolver colisión automáticamente
                    self._handle_id_collision(sender_id, sender_ip)

                    # Notificar callback de colisión (para logging/debug)
                    if self.on_id_collision:
                        threading.Thread(
                            target=self.on_id_collision,
                            args=(sender_id, sender_ip),
                            daemon=True
                        ).start()

                # Ignorar el mensaje (loopback o colisión) - no procesarlo como nodo diferente
                return

            if msg_type == 'ANNOUNCE':
                self._handle_announce(message, addr)
            elif msg_type == 'LEAVE':
                self._handle_leave(message)
            elif msg_type == 'ID_QUERY':
                # FASE 9: Responder a queries de nuevos nodos
                self._handle_id_query(addr)
            else:
                logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Unknown message type: {msg_type}")

        except Exception as e:
            logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error handling message: {e}")

    def _handle_id_collision(self, conflicting_id: int, conflicting_ip: str):
        """
        FASE 9: Resuelve colisión de IDs usando comparación numérica de IPs.

        Estrategia: El nodo con IP mayor (numéricamente) conserva el ID.
        El nodo con IP menor debe regenerar un nuevo ID y reiniciar.

        Args:
            conflicting_id: El ID en conflicto (mismo que self.node_id)
            conflicting_ip: IP del otro nodo con el mismo ID
        """
        my_ip = self.local_ip
        my_ip_int = self._ip_to_int(my_ip)
        their_ip_int = self._ip_to_int(conflicting_ip)

        logger.warning(f"[Node-{self.node_id}] [COLLISION] My IP={my_ip} ({my_ip_int}) vs {conflicting_ip} ({their_ip_int})")

        # Comparar IPs numéricamente (más preciso que lexicográfico)
        if my_ip_int > their_ip_int:
            logger.info(f"[Node-{self.node_id}] [COLLISION] My IP is higher - KEEPING ID {conflicting_id}")
            return  # No hacer nada, mantener mi ID

        if my_ip_int == their_ip_int:
            # Mismo IP detectado - esto no debería pasar
            # Usar PID como tiebreaker
            import os
            logger.warning(f"[Node-{self.node_id}] [COLLISION] Same IP detected! This is a bug in IP detection.")
            logger.warning(f"[Node-{self.node_id}] [COLLISION] Keeping ID (will retry collision later)")
            return

        # Mi IP es menor, debo regenerar un nuevo ID
        logger.warning(f"[Node-{self.node_id}] [COLLISION] My IP is lower - MUST REGENERATE ID")

        # Notificar al BullyNode para que regenere ID y reinicie
        if self.on_collision_regenerate:
            logger.info(f"[Node-{self.node_id}] [COLLISION] Triggering ID regeneration callback...")
            threading.Thread(
                target=self.on_collision_regenerate,
                daemon=True
            ).start()
        else:
            logger.error(f"[Node-{self.node_id}] [COLLISION] No regeneration callback set! Node will have duplicate ID!")

    def _handle_id_query(self, addr: Tuple[str, int]):
        """
        FASE 9: Responde a ID_QUERY de nodos que están arrancando.

        Cuando un nuevo nodo hace discovery, envía ID_QUERY para provocar
        respuestas inmediatas de nodos existentes. Esto asegura que el
        nuevo nodo detecte todos los IDs en uso.

        Args:
            addr: Dirección (IP, puerto) del nodo que pregunta
        """
        try:
            # Enviar ID_RESPONSE inmediatamente
            response = {
                'type': 'ID_RESPONSE',
                'node_id': self.node_id,
                'tcp_port': self.tcp_port,
                'udp_port': self.udp_port,
                'timestamp': time.time()
            }
            data = json.dumps(response).encode('utf-8')

            # Responder via multicast para que todos los nuevos nodos lo vean
            self.send_socket.sendto(data, (self.multicast_group, self.multicast_port))
            logger.info(f"[Node-{self.node_id}] [DISCOVERY] 📤 Sent ID_RESPONSE to query from {addr[0]}")

        except Exception as e:
            logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error responding to ID_QUERY: {e}")

    def _handle_announce(self, message: dict, addr: Tuple[str, int]):
        """Maneja mensaje ANNOUNCE de otro nodo."""
        sender_id = message['node_id']
        tcp_port = message['tcp_port']
        udp_port = message['udp_port']
        sender_ip = addr[0]

        with self.lock:
            is_new = sender_id not in self.discovered_nodes

            self.discovered_nodes[sender_id] = {
                'host': sender_ip,
                'tcp_port': tcp_port,
                'udp_port': udp_port,
                'last_seen': time.time()
            }

            if is_new:
                logger.info(f"[Node-{self.node_id}] [DISCOVERY] ✓ Discovered new node {sender_id} at {sender_ip}:{tcp_port}")

                # Notificar callback
                if self.on_node_discovered:
                    threading.Thread(
                        target=self.on_node_discovered,
                        args=(sender_id, sender_ip, tcp_port, udp_port),
                        daemon=True
                    ).start()
            else:
                logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Updated node {sender_id}")

    def _handle_leave(self, message: dict):
        """Maneja mensaje LEAVE de nodo que sale gracefully."""
        sender_id = message['node_id']
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Node {sender_id} left gracefully")
        self._remove_node(sender_id)

    def _remove_node(self, node_id: int):
        """Remueve nodo de la lista de descubiertos."""
        with self.lock:
            if node_id in self.discovered_nodes:
                node_info = self.discovered_nodes.pop(node_id)
                logger.warning(f"[Node-{self.node_id}] [DISCOVERY] ✗ Removed node {node_id} (was at {node_info['host']})")

                # Notificar callback
                if self.on_node_lost:
                    threading.Thread(
                        target=self.on_node_lost,
                        args=(node_id,),
                        daemon=True
                    ).start()

    def get_discovered_nodes(self) -> Dict[int, Tuple[str, int, int]]:
        """
        Retorna nodos descubiertos en formato compatible con BullyNode.

        Returns:
            Dict con formato: {node_id: (host, tcp_port, udp_port)}
        """
        with self.lock:
            return {
                node_id: (info['host'], info['tcp_port'], info['udp_port'])
                for node_id, info in self.discovered_nodes.items()
            }

    def get_node_count(self) -> int:
        """Retorna número de nodos descubiertos (excluyendo este nodo)."""
        with self.lock:
            return len(self.discovered_nodes)

    def set_callbacks(
        self,
        on_discovered: Callable = None,
        on_lost: Callable = None,
        on_collision: Callable = None,
        on_collision_regenerate: Callable = None
    ):
        """
        Configura callbacks para eventos de descubrimiento.

        Args:
            on_discovered: Callback cuando se descubre nuevo nodo (node_id, host, tcp_port, udp_port)
            on_lost: Callback cuando se pierde un nodo (node_id)
            on_collision: Callback cuando se detecta colisión de ID (conflicting_node_id, conflicting_host)
            on_collision_regenerate: Callback para regenerar ID cuando este nodo debe ceder (sin args)
        """
        self.on_node_discovered = on_discovered
        self.on_node_lost = on_lost
        self.on_id_collision = on_collision
        self.on_collision_regenerate = on_collision_regenerate
