# backend/bully/communication.py

import socket
import threading
import json
import time
import logging
import traceback
from dataclasses import dataclass, asdict
from typing import Callable, Dict, Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class Message:
    """Mensaje para comunicación entre nodos (Bully, Bloqueos, Consenso)"""
    type: str           # ELECTION, OK, COORDINATOR, HEARTBEAT, LOCK_REQUEST, etc.
    sender_id: int      # Quién envía
    timestamp: float    # Cuándo se envía
    data: Optional[Dict[str, Any]] = None  # Datos adicionales para bloqueos/consenso

    def to_json(self) -> str:
        """Serializar a JSON"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_data: str) -> 'Message':
        """Deserializar desde JSON"""
        obj = json.loads(json_data)
        return cls(
            type=obj['type'],
            sender_id=obj['sender_id'],
            timestamp=obj['timestamp'],
            data=obj.get('data')
        )

class CommunicationManager:
    """
    Gestiona comunicación TCP/UDP entre nodos.
    
    - TCP: Para mensajes de elección (ELECTION, OK, COORDINATOR)
    - UDP: Para heartbeats (HEARTBEAT)
    """
    
    def __init__(self, node_id: int, tcp_port: int, udp_port: int):
        """
        Inicializa manager de comunicación.
        
        Args:
            node_id: ID de este nodo
            tcp_port: Puerto TCP para elecciones
            udp_port: Puerto UDP para heartbeats
        """
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        
        self.tcp_socket: Optional[socket.socket] = None
        self.udp_socket: Optional[socket.socket] = None
        
        # Handlers de mensajes
        self.tcp_handlers: Dict[str, Callable] = {}
        self.udp_handlers: Dict[str, Callable] = {}
        
        self.running = False
        self.tcp_thread: Optional[threading.Thread] = None
        self.udp_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Inicia servidores TCP y UDP"""
        logger.info(f"[Node-{self.node_id}] [COMM] Starting communication manager")
        self.running = True

        # Iniciar servidor TCP
        self.tcp_thread = threading.Thread(
            target=self._tcp_server_loop,
            daemon=True,
            name=f"TCP-{self.node_id}"
        )
        self.tcp_thread.start()

        # Iniciar servidor UDP
        self.udp_thread = threading.Thread(
            target=self._udp_server_loop,
            daemon=True,
            name=f"UDP-{self.node_id}"
        )
        self.udp_thread.start()

        logger.info(f"[Node-{self.node_id}] [COMM] Started - TCP:{self.tcp_port}, UDP:{self.udp_port}")
    
    def stop(self):
        """Detiene servidores"""
        self.running = False
        if self.tcp_socket:
            self.tcp_socket.close()
        if self.udp_socket:
            self.udp_socket.close()
    
    def _tcp_server_loop(self):
        """Loop del servidor TCP con backlog configurable."""
        from config import Config

        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind(('0.0.0.0', self.tcp_port))

        # Backlog configurable (default 20, antes era 5)
        backlog = getattr(Config, 'TCP_BACKLOG', 20)
        self.tcp_socket.listen(backlog)
        self.tcp_socket.settimeout(1.0)

        logger.info(f"[Node-{self.node_id}] [COMM-TCP] Listening on 0.0.0.0:{self.tcp_port} (backlog={backlog})")
        
        while self.running:
            try:
                client_socket, addr = self.tcp_socket.accept()
                threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client_socket,),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"[Node-{self.node_id}] [COMM-TCP] Server loop error: {type(e).__name__}: {str(e)}")
                    logger.debug(f"[Node-{self.node_id}] [COMM-TCP] Traceback: {traceback.format_exc()}")
                break
    
    def _handle_tcp_client(self, client_socket: socket.socket):
        """Maneja conexión TCP individual"""
        try:
            data = client_socket.recv(4096)
            if not data:
                return
            
            message = Message.from_json(data.decode('utf-8'))
            handler = self.tcp_handlers.get(message.type)
            
            if handler:
                response = handler(message)
                if response:
                    client_socket.send(response.to_json().encode('utf-8'))
        except Exception as e:
            logger.error(f"[Node-{self.node_id}] [COMM-TCP] Client handler error: {type(e).__name__}: {str(e)}")
            logger.debug(f"[Node-{self.node_id}] [COMM-TCP] Traceback: {traceback.format_exc()}")
        finally:
            client_socket.close()
    
    def _udp_server_loop(self):
        """Loop del servidor UDP"""
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind(('0.0.0.0', self.udp_port))
        self.udp_socket.settimeout(1.0)

        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                message = Message.from_json(data.decode('utf-8'))
                logger.info(f"[Node-{self.node_id}] [COMM-UDP] ← Received {message.type} from Node {message.sender_id} ({addr[0]}:{addr[1]})")

                handler = self.udp_handlers.get(message.type)
                if handler:
                    handler(message)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"[Node-{self.node_id}] [COMM-UDP] Receive error: {type(e).__name__}: {str(e)}")
                    logger.debug(f"[Node-{self.node_id}] [COMM-UDP] Traceback: {traceback.format_exc()}")
    
    def send_tcp(self, target_ip: str, target_port: int, 
                  message: Message, timeout: float = 3.0) -> Optional[Message]:
        """
        Envía mensaje TCP y espera respuesta.
        
        Args:
            target_ip: IP destino
            target_port: Puerto TCP destino
            message: Mensaje a enviar
            timeout: Timeout en segundos
            
        Returns:
            Mensaje de respuesta o None
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        try:
            sock.connect((target_ip, target_port))
            sock.sendall(message.to_json().encode('utf-8'))
            
            response_data = sock.recv(4096)
            if response_data:
                return Message.from_json(response_data.decode('utf-8'))
        except Exception as e:
            logger.warning(f"[Node-{self.node_id}] [COMM-TCP] Send failed to {target_ip}:{target_port} - {type(e).__name__}: {str(e)}")
            return None
        finally:
            sock.close()

        return None
    
    def send_udp(self, target_ip: str, target_port: int, message: Message):
        """
        Envía mensaje UDP (fire-and-forget).

        Args:
            target_ip: IP destino
            target_port: Puerto UDP destino
            message: Mensaje a enviar
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            data = message.to_json().encode('utf-8')
            sock.sendto(data, (target_ip, target_port))
            sock.close()
            logger.info(f"[Node-{self.node_id}] [COMM-UDP] ✓ Sent {message.type} to {target_ip}:{target_port}")
        except Exception as e:
            logger.warning(f"[Node-{self.node_id}] [COMM-UDP] ✗ Send failed to {target_ip}:{target_port} - {type(e).__name__}: {str(e)}")
    
    def register_tcp_handler(self, message_type: str, handler: Callable):
        """Registra handler para tipo de mensaje TCP"""
        self.tcp_handlers[message_type] = handler
    
    def register_udp_handler(self, message_type: str, handler: Callable):
        """Registra handler para tipo de mensaje UDP"""
        self.udp_handlers[message_type] = handler
