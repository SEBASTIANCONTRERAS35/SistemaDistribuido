"""
Bully Cluster Screen - Visual diagram of Bully consensus cluster
"""

import time
from datetime import datetime
from typing import Dict, List, Tuple, Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Label, Footer
from textual.containers import Container, Vertical, Horizontal, Grid
from textual.reactive import reactive
from textual import work
from textual.binding import Binding
from rich.text import Text


class ClusterNodeCard(Static):
    """Card widget to display a single cluster node"""

    # Reactive properties - these will trigger re-render when changed
    is_leader: reactive[bool] = reactive(False)
    is_current: reactive[bool] = reactive(False)
    last_seen: reactive[float] = reactive(0.0)

    def __init__(
        self,
        node_id: int,
        is_leader: bool,
        is_current: bool,
        tcp_port: int,
        udp_port: int,
        last_seen: float,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.udp_port = udp_port

        # Set reactive properties (will trigger initial render)
        self.is_leader = is_leader
        self.is_current = is_current
        self.last_seen = last_seen

    def on_mount(self) -> None:
        """Start auto-refresh when card is mounted"""
        # IMPORTANT FIX: Auto-refresh every second to update "Last seen: Xs ago" counter
        # This makes the time counter update in real-time instead of being static
        self.set_interval(1.0, self.refresh)

    def render(self) -> Text:
        """Render the node card"""
        # Calculate time since last seen
        time_ago = time.time() - self.last_seen if self.last_seen else 999
        is_stale = time_ago > 10  # Stale if not seen in 10 seconds

        # Build the card content
        content = Text()

        # Header: Node ID with badges
        header = f"Node {self.node_id}"
        if self.is_leader:
            header += " 👑"
        if self.is_current:
            header += " 🔵"
        if is_stale:
            header += " ⚠"

        content.append(header + "\n", style="bold")

        # State
        if self.is_leader:
            content.append("LEADER", style="bold green")
        else:
            content.append("FOLLOWER", style="cyan")

        content.append("\n\n")

        # Ports
        content.append(f"TCP: {self.tcp_port}\n", style="dim")
        content.append(f"UDP: {self.udp_port}\n", style="dim")

        content.append("\n")

        # Last seen
        if self.is_current:
            content.append("Active (You)", style="bold yellow")
        elif is_stale:
            content.append(f"Last seen:\n{int(time_ago)}s ago", style="dim red")
        else:
            content.append(f"Last seen:\n{int(time_ago)}s ago", style="dim")

        return content


class BullyClusterScreen(Screen):
    """
    Screen to visualize the Bully consensus cluster
    Shows all nodes, their states, and cluster information
    """

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Actualizar", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
        # Navegación con flechas (sin mouse)
        Binding("down", "focus_next", "↓", show=False),
        Binding("up", "focus_previous", "↑", show=False),
        Binding("left", "focus_previous", "←", show=False),
        Binding("right", "focus_next", "→", show=False),
    ]

    CSS = """
    BullyClusterScreen {
        background: $surface;
    }

    #cluster-header {
        background: $primary;
        color: $surface;
        padding: 1 2;
        dock: top;
        height: 7;
    }

    #header-title {
        text-style: bold;
        color: $surface;
        text-align: center;
        padding-bottom: 1;
    }

    #cluster-info {
        color: $surface;
        text-align: center;
    }

    #nodes-container {
        padding: 2;
        height: 1fr;
    }

    #nodes-grid {
        grid-size: 3;
        grid-gutter: 1 2;
        padding: 1;
    }

    ClusterNodeCard {
        height: 12;
        border: solid $primary;
        background: $panel;
        padding: 1 2;
        text-align: center;
    }

    .node-leader {
        border: solid $success;
        background: rgba(40, 167, 69, 0.1);
    }

    .node-current {
        border: solid $warning;
    }

    .node-stale {
        border: solid #8F9BB3;
        background: rgba(143, 155, 179, 0.1);
        opacity: 0.7;
    }

    #status-bar {
        background: $panel;
        color: $text-secondary;
        padding: 0 2;
        dock: bottom;
        height: 3;
        text-align: center;
    }

    #election-warning {
        background: $warning;
        color: $text-primary;
        padding: 0 2;
        text-align: center;
        text-style: bold;
    }
    """

    # Reactive state
    cluster_data: reactive[Dict[str, Any]] = reactive({}, init=False)
    refresh_interval: int = 2  # seconds

    def __init__(self, bully_manager):
        super().__init__()
        self.bully_manager = bully_manager

        # Cache of node cards to avoid recreating them on every update
        # Maps node_id -> ClusterNodeCard widget
        self.node_cards: Dict[int, ClusterNodeCard] = {}

    def compose(self) -> ComposeResult:
        """Compose the cluster visualization UI"""

        # Header with cluster info
        with Container(id="cluster-header"):
            yield Label("🌐 CLUSTER BULLY - CONSENSO DISTRIBUIDO", id="header-title")
            yield Static("", id="cluster-info")

        # Election warning (hidden by default)
        yield Static("", id="election-warning")

        # Nodes grid container
        with Vertical(id="nodes-container"):
            yield Grid(id="nodes-grid")

        # Status bar
        yield Static("", id="status-bar")

        # Footer
        yield Footer()

    def on_mount(self) -> None:
        """Initialize when screen is mounted"""
        # Load initial data
        self.load_cluster_data()

        # Start auto-refresh
        self.set_interval(self.refresh_interval, self.load_cluster_data)

    def load_cluster_data(self) -> None:
        """Load cluster data from Bully manager"""
        try:
            # Get current cluster state
            current_node = self.bully_manager.node_id
            current_leader = self.bully_manager.current_leader
            state = self.bully_manager.state.value
            cluster_nodes = self.bully_manager.cluster_nodes
            node_last_seen = self.bully_manager.node_last_seen
            election_in_progress = self.bully_manager.election_in_progress
            current_term = self.bully_manager.current_term
            use_discovery = self.bully_manager.use_discovery

            # CRITICAL FIX: Create deep copies of mutable dictionaries
            # This ensures Textual's reactive system detects changes
            # Without this, cluster_nodes and node_last_seen are references to the same objects,
            # so Textual won't trigger watch_cluster_data() when they're modified
            self.cluster_data = {
                'current_node': current_node,
                'current_leader': current_leader,
                'state': state,
                'cluster_nodes': dict(cluster_nodes),  # Create new dict copy
                'node_last_seen': dict(node_last_seen),  # Create new dict copy
                'election_in_progress': election_in_progress,
                'current_term': current_term,
                'use_discovery': use_discovery,
                'tcp_port': self.bully_manager.tcp_port,
                'udp_port': self.bully_manager.udp_port,
            }

        except Exception as e:
            self.notify(f"Error loading cluster data: {str(e)}", severity="error")

    def watch_cluster_data(self, data: Dict[str, Any]) -> None:
        """React to cluster data changes"""
        if not data:
            return

        # Update header info
        self.update_header_info(data)

        # Update election warning
        self.update_election_warning(data)

        # Update nodes grid
        self.update_nodes_grid(data)

        # Update status bar
        self.update_status_bar(data)

    def update_header_info(self, data: Dict[str, Any]) -> None:
        """Update cluster info in header"""
        info_widget = self.query_one("#cluster-info", Static)

        mode = "DYNAMIC" if data['use_discovery'] else "STATIC"
        term = data['current_term']
        election = "Yes ⚡" if data['election_in_progress'] else "No"

        info_text = Text()
        info_text.append(f"Mode: {mode}", style="bold")
        info_text.append(" | ")
        info_text.append(f"Term: {term}", style="bold cyan")
        info_text.append(" | ")
        info_text.append("Election: ", style="bold")

        if data['election_in_progress']:
            info_text.append(election, style="bold yellow")
        else:
            info_text.append(election, style="bold green")

        info_widget.update(info_text)

    def update_election_warning(self, data: Dict[str, Any]) -> None:
        """Show/hide election warning banner"""
        warning = self.query_one("#election-warning", Static)

        if data['election_in_progress']:
            warning.update("⚡ ELECCIÓN EN PROGRESO ⚡")
            warning.display = True
        else:
            warning.display = False

    def update_nodes_grid(self, data: Dict[str, Any]) -> None:
        """Update the nodes grid with current cluster state using incremental updates"""
        grid = self.query_one("#nodes-grid", Grid)

        # Build list of all nodes (current + cluster)
        all_nodes: Dict[int, Tuple[str, int, int]] = {}

        # Add current node
        all_nodes[data['current_node']] = (
            'localhost',
            data['tcp_port'],
            data['udp_port']
        )

        # Add cluster nodes
        for node_id, (ip, tcp, udp) in data['cluster_nodes'].items():
            all_nodes[node_id] = (ip, tcp, udp)

        # OPTIMIZATION: Incremental update instead of full recreation
        # Step 1: Remove cards for nodes that disappeared
        nodes_to_remove = set(self.node_cards.keys()) - set(all_nodes.keys())
        for node_id in nodes_to_remove:
            card = self.node_cards.pop(node_id)
            card.remove()

        # Step 2: Update existing cards and create new ones
        for node_id, (ip, tcp_port, udp_port) in all_nodes.items():
            is_leader = (node_id == data['current_leader'])
            is_current = (node_id == data['current_node'])

            # Get last seen time
            if is_current:
                last_seen = time.time()  # Current node is always active
            else:
                last_seen = data['node_last_seen'].get(node_id, 0)

            # Check if card already exists
            if node_id in self.node_cards:
                # Update existing card's reactive properties
                card = self.node_cards[node_id]
                card.is_leader = is_leader
                card.is_current = is_current
                card.last_seen = last_seen

                # Update CSS classes dynamically
                card.set_class(is_leader, "node-leader")
                card.set_class(is_current, "node-current")

                # Check if stale
                time_ago = time.time() - last_seen if last_seen else 999
                card.set_class(time_ago > 10 and not is_current, "node-stale")
            else:
                # Create new card
                card = ClusterNodeCard(
                    node_id=node_id,
                    is_leader=is_leader,
                    is_current=is_current,
                    tcp_port=tcp_port,
                    udp_port=udp_port,
                    last_seen=last_seen
                )

                # Add CSS classes
                if is_leader:
                    card.add_class("node-leader")
                if is_current:
                    card.add_class("node-current")

                # Check if stale
                time_ago = time.time() - last_seen if last_seen else 999
                if time_ago > 10 and not is_current:
                    card.add_class("node-stale")

                # Mount and cache the card
                grid.mount(card)
                self.node_cards[node_id] = card

    def update_status_bar(self, data: Dict[str, Any]) -> None:
        """Update status bar with cluster summary"""
        status_bar = self.query_one("#status-bar", Static)

        leader_text = f"Node {data['current_leader']}" if data['current_leader'] else "None"
        cluster_size = len(data['cluster_nodes']) + 1  # +1 for current node
        your_state = data['state'].upper()

        status_text = Text()
        status_text.append("Leader: ", style="dim")
        status_text.append(leader_text, style="bold green")
        status_text.append(" | ", style="dim")
        status_text.append("Cluster Size: ", style="dim")
        status_text.append(f"{cluster_size} nodes", style="bold cyan")
        status_text.append(" | ", style="dim")
        status_text.append("Your State: ", style="dim")

        if data['state'] == 'leader':
            status_text.append(your_state, style="bold green")
        else:
            status_text.append(your_state, style="bold cyan")

        status_text.append("\n")
        status_text.append(f"Last updated: {datetime.now().strftime('%H:%M:%S')}", style="dim italic")

        status_bar.update(status_text)

    def action_refresh(self) -> None:
        """Manually refresh cluster data"""
        self.load_cluster_data()
        self.notify("🔄 Cluster data refreshed", severity="information")


# Export
__all__ = ['BullyClusterScreen']
