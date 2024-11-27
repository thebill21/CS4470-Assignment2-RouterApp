import socket
import threading
import time
import json
from collections import defaultdict

class Node:
    """Represents a node in the network."""
    def __init__(self, node_id, ip, port):
        self.id = node_id
        self.ip = ip
        self.port = port

    def __hash__(self):
        return hash((self.id, self.ip, self.port))

    def __eq__(self, other):
        return (self.id, self.ip, self.port) == (other.id, other.ip)

class Router:
    """Distance Vector Routing Protocol Router."""
    def __init__(self, topology_file, update_interval, port):
        self.my_ip = self.get_my_ip()
        self.my_id = None
        self.my_node = None
        self.nodes = []  # Initialize nodes list
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = defaultdict(dict)  # Nested dictionary for complete routing info
        self.neighbors = set()
        self.running = True
        self.lock = threading.Lock()
        self.server_port = port
        self.connections = {}  # {connection_id: (socket, (ip, port))}
        self.connection_id_counter = 1
        self.available_ids = []

        print(f"Initializing router with topology file: {topology_file}, update interval: {update_interval}s, port: {port}.")
        self.load_topology()
        threading.Thread(target=self.listen_for_connections).start()
        threading.Thread(target=self.start_periodic_updates).start()

    def get_my_ip(self):
        """Retrieve the machine's local IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception as e:
            print(f"Error retrieving IP address: {e}")
            return "127.0.0.1"

    def load_topology(self):
        """Reads the topology file and initializes routing tables."""
        try:
            with open(self.topology_file, 'r') as f:
                lines = f.read().strip().split('\n')
            num_servers = int(lines[0])
            num_neighbors = int(lines[1])
            for i in range(2, 2 + num_servers):
                parts = lines[i].split()
                node = Node(int(parts[0]), parts[1], int(parts[2]))
                self.nodes.append(node)
                if parts[1] == self.my_ip and int(parts[2]) == self.server_port:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id][node.id] = 0  # Cost to self is 0
            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
                if from_id == self.my_id or to_id == self.my_id:
                    neighbor_id = to_id if from_id == self.my_id else from_id
                    self.routing_table[self.my_id][neighbor_id] = cost
                    self.neighbors.add(neighbor_id)
        except Exception as e:
            print(f"Error loading topology: {e}")

    def listen_for_connections(self):
        """Start a server socket to accept incoming connections."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.my_ip, self.server_port))
        server_socket.listen(5)
        print(f"Listening on {self.my_ip}:{self.server_port}")
        while self.running:
            client_socket, client_address = server_socket.accept()
            threading.Thread(target=self.handle_connection, args=(client_socket, client_address)).start()

    def handle_connection(self, client_socket, client_address):
        """Handle incoming connections and exchange routing tables."""
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if message:
                data = json.loads(message)
                if 'routing_table' in data:
                    self.process_message(data)
        except Exception as e:
            print(f"Error handling connection: {e}")
        finally:
            client_socket.close()

    def start_periodic_updates(self):
        """Periodically send routing table updates to neighbors."""
        while self.running:
            time.sleep(self.update_interval)
            self.step()

    def process_message(self, message):
        """Process incoming routing table updates."""
        sender_id = message['id']
        received_table = message['routing_table']
        updated = False
        with self.lock:
            for dest, cost in received_table.items():
                dest = int(dest)
                cost = float(cost)
                if dest not in self.routing_table[sender_id] or cost < self.routing_table[sender_id].get(dest, float('inf')):
                    self.routing_table[sender_id][dest] = cost
                    updated = True
        if updated:
            self.recalculate_routes()

    def recalculate_routes(self):
        """Recalculate the best routes."""
        print("[DEBUG] Recalculating routes...")
        # Logic for recomputing the routing table
        self.display_routing_table()

    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        print("--------------------------------")
        for dest, next_hops in self.routing_table.items():
            for next_hop, cost in next_hops.items():
                cost_str = "infinity" if cost == float('inf') else cost
                print(f"{dest:<14}{next_hop:<14}{cost_str}")
        print()

    def step(self):
        """Send routing updates to neighbors."""
        message = {
            "id": self.my_id,
            "routing_table": self.routing_table[self.my_id]
        }
        for neighbor_id in self.neighbors:
            neighbor = next(node for node in self.nodes if node.id == neighbor_id)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor.ip, neighbor.port))
                    s.sendall(json.dumps(message).encode())
            except Exception as e:
                print(f"Error sending updates to neighbor {neighbor_id}: {e}")

    def run(self):
        """Run the router command interface."""
        while True:
            command = input(">> ").strip().split()
            if not command:
                continue
            if command[0] == "display":
                self.display_routing_table()
            elif command[0] == "step":
                self.step()
            elif command[0] == "update" and len(command) == 4:
                try:
                    server1, server2, new_cost = map(int, command[1:])
                    self.update(server1, server2, new_cost)
                except ValueError:
                    print("Invalid update command.")
            elif command[0] == "exit":
                self.running = False
                break

    def update(self, server1_id, server2_id, new_cost):
        """Update link cost."""
        with self.lock:
            if server1_id == self.my_id or server2_id == self.my_id:
                target_id = server2_id if server1_id == self.my_id else server1_id
                if target_id in self.neighbors:
                    self.routing_table[self.my_id][target_id] = new_cost
                    self.recalculate_routes()
                else:
                    print("Can only update direct neighbors.")

if __name__ == "__main__":
    print("********* Distance Vector Routing Protocol **********")
    print("Use: server -t <topology-file-name> -i <routing-update-interval>")
    topology_file = input("Enter topology file: ")
    update_interval = int(input("Enter update interval (seconds): "))
    port = int(input("Enter port: "))
    router = Router(topology_file, update_interval, port)
    router.run()