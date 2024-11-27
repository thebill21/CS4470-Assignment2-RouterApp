import socket
import selectors
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
    def __init__(self, topology_file, update_interval):
        self.my_ip = self.get_my_ip()
        self.my_id = None
        self.my_node = None
        self.nodes = []  # List of all nodes in the topology
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = set()
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.selector = selectors.DefaultSelector()
        self.number_of_packets_received = 0

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        self.start_server()
        self.start_periodic_updates()
        self.start_health_monitor()
        print("Initialization complete.\n")

    def get_my_ip(self):
        """Get the machine's local IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
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
                if parts[1] == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id] = 0
                    self.next_hop[node.id] = node.id
                else:
                    self.routing_table[node.id] = float('inf')
                    self.next_hop[node.id] = None

            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
                if from_id == self.my_id:
                    neighbor = self.get_node_by_id(to_id)
                    self.neighbors.add(neighbor)
                    self.routing_table[neighbor.id] = cost
                    self.next_hop[neighbor.id] = neighbor.id

        except Exception as e:
            print(f"Error loading topology: {e}")

    def start_server(self):
        """Starts the server to handle incoming messages."""
        def server_task():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.bind((self.my_ip, self.my_node.port))
                server.listen(5)
                server.setblocking(False)
                self.selector.register(server, selectors.EVENT_READ, self.accept_connection)
                print(f"Listening on {self.my_ip}:{self.my_node.port}")
                while self.running:
                    events = self.selector.select(timeout=1)
                    for key, mask in events:
                        callback = key.data
                        callback(key.fileobj)

        threading.Thread(target=server_task, daemon=True).start()

    def accept_connection(self, server):
        """Accepts new client connections."""
        client, addr = server.accept()
        print(f"Accepted connection from {addr}")
        client.setblocking(False)
        self.selector.register(client, selectors.EVENT_READ, self.read_message)

    def read_message(self, client):
        """Reads a message from the client."""
        try:
            message = client.recv(1024).decode()
            if message:
                json_message = json.loads(message)
                self.process_message(json_message)
            else:
                self.selector.unregister(client)
                client.close()
        except Exception as e:
            print(f"Error reading message: {e}")

    def process_message(self, message):
        """Processes incoming routing updates."""
        self.number_of_packets_received += 1
        sender_id = message.get("id")
        received_table = message.get("routing_table", {})
        updated = False

        with self.lock:
            for dest_id, received_cost in received_table.items():
                if dest_id == self.my_id:
                    continue
                current_cost = self.routing_table.get(dest_id, float('inf'))
                new_cost = self.routing_table[sender_id] + received_cost
                if new_cost < current_cost:
                    self.routing_table[dest_id] = new_cost
                    self.next_hop[dest_id] = sender_id
                    updated = True

        if updated:
            print("Routing table updated.")
            self.display_routing_table()

    def start_periodic_updates(self):
        """Periodically sends updates to neighbors."""
        def update_task():
            while self.running:
                self.send_updates()
                time.sleep(self.update_interval)

        threading.Thread(target=update_task, daemon=True).start()

    def start_health_monitor(self):
        """Monitors the health of neighbors."""
        def health_check():
            while self.running:
                with self.lock:
                    for neighbor in self.neighbors:
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.settimeout(2)
                                s.connect((neighbor.ip, neighbor.port))
                        except Exception:
                            print(f"Neighbor {neighbor.id} is unreachable. Marking as offline.")
                            self.routing_table[neighbor.id] = float('inf')
                            self.next_hop[neighbor.id] = None
                time.sleep(5)

        threading.Thread(target=health_check, daemon=True).start()

    def send_updates(self):
        """Sends routing table updates to all neighbors."""
        message = {"id": self.my_id, "routing_table": self.routing_table}
        for neighbor in self.neighbors:
            self.send_message(neighbor, message)

    def send_message(self, neighbor, message):
        """Sends a message to a neighbor."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                s.sendall(json.dumps(message).encode())
        except Exception as e:
            print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")

    def get_node_by_id(self, node_id):
        """Finds a node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def display_routing_table(self):
        """Displays the routing table."""
        print("\nRouting Table:")
        for dest_id, cost in self.routing_table.items():
            next_hop = self.next_hop.get(dest_id, None)
            next_hop_str = next_hop if next_hop else "None"
            cost_str = "infinity" if cost == float('inf') else cost
            print(f"Destination: {dest_id}, Next Hop: {next_hop_str}, Cost: {cost_str}")

    def run(self):
        """Runs the router, handling user commands."""
        print("Router is running. Enter commands:")
        while self.running:
            command = input("Enter command: ").strip().lower()
            if command == "display":
                self.display_routing_table()
            elif command == "packets":
                print(f"Packets received: {self.number_of_packets_received}")
            elif command == "stop":
                self.running = False
                print("Stopping the router...")
            else:
                print("Invalid command.")

if __name__ == "__main__":
    print("********* Distance Vector Routing Protocol **********")
    topology_file = input("Enter topology file: ").strip()
    update_interval = int(input("Enter update interval (seconds): ").strip())
    router = Router(topology_file, update_interval)
    router.run()