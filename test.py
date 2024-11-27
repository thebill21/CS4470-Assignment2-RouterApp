import socket
import threading
import time
import json
import struct
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
        self.nodes = []
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = defaultdict(dict)
        self.neighbors = set()
        self.running = True
        self.lock = threading.Lock()
        self.connections = {}

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        threading.Thread(target=self.listen_for_connections).start()
        threading.Thread(target=self.start_periodic_updates).start()
        print("Initialization complete.\n")

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
                if parts[1] == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id][node.id] = 0
            for i in range(2 + num_servers, 2 + num_neighbors + num_servers):
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
        server_socket.bind((self.my_ip, self.my_node.port))
        server_socket.listen(5)
        print(f"Listening on {self.my_ip}:{self.my_node.port}")
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
        """Process incoming routing table updates in binary format."""
        try:
            # Extract header
            num_fields, sender_port = struct.unpack("!HH", message[:4])
            sender_ip = socket.inet_ntoa(message[4:8])

            # Sender details
            sender_id = None
            for node in self.nodes:
                if node.ip == sender_ip and node.port == sender_port:
                    sender_id = node.id
                    break

            if sender_id is None:
                print("Invalid sender details. Ignoring message.")
                return

            # Parse fields
            offset = 8
            updated = False
            with self.lock:
                for _ in range(num_fields):
                    dest_ip = socket.inet_ntoa(message[offset:offset+4])
                    dest_port, dest_id, cost = struct.unpack("!HHH", message[offset+4:offset+10])
                    offset += 10

                    # Update routing table
                    current_cost = self.routing_table[self.my_id].get(dest_id, float('inf'))
                    new_cost = self.routing_table[self.my_id].get(sender_id, float('inf')) + cost
                    if new_cost < current_cost:
                        self.routing_table[self.my_id][dest_id] = new_cost
                        updated = True

            if updated:
                print("[DEBUG] Routing table updated based on received message.")
                self.recalculate_routes()
        except Exception as e:
            print(f"Error processing message: {e}")

    def recalculate_routes(self):
        """Recalculate the best routes."""
        print("[DEBUG] Recalculating routes...")
        self.display_routing_table()

    def display_routing_table(self):
        """Display the routing table with all possible paths."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        print("--------------------------------")
        with self.lock:
            for dest_id in sorted(self.routing_table.keys()):
                for next_hop, cost in self.routing_table[dest_id].items():
                    cost_str = "infinity" if cost == float('inf') else cost
                    print(f"{dest_id:<14}{next_hop:<14}{cost_str}")
        print()

    def step(self):
        """Send routing updates to neighbors using binary format."""
        try:
            message_header = struct.pack(
                "!HH4s", len(self.routing_table[self.my_id]), self.my_node.port, socket.inet_aton(self.my_ip)
            )
            message_body = b""
            for dest_id, cost in self.routing_table[self.my_id].items():
                dest_node = next((node for node in self.nodes if node.id == dest_id), None)
                if dest_node:
                    message_body += struct.pack(
                        "!4sHHH",
                        socket.inet_aton(dest_node.ip),
                        dest_node.port,
                        dest_node.id,
                        int(cost) if cost < float('inf') else 65535,
                    )

            message = message_header + message_body
            for neighbor_id in self.neighbors:
                neighbor = next(node for node in self.nodes if node.id == neighbor_id)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor.ip, neighbor.port))
                    s.sendall(message)
            print("Routing updates sent.")
        except Exception as e:
            print(f"Error during step: {e}")

    def update(self, server1_id, server2_id, new_cost):
        """Update the cost of a link."""
        with self.lock:
            if server1_id == self.my_id or server2_id == self.my_id:
                target_id = server2_id if server1_id == self.my_id else server1_id
                if target_id in self.neighbors:
                    self.routing_table[self.my_id][target_id] = new_cost
                    print(f"[DEBUG] Link cost updated: {self.my_id} <-> {target_id}, Cost: {new_cost}")
                    self.recalculate_routes()
                    self.step()
                else:
                    print("[ERROR] Can only update costs to direct neighbors.")
            else:
                print("[ERROR] This server is not involved in the specified link.")

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

if __name__ == "__main__":
    print("********* Distance Vector Routing Protocol **********")
    print("Use: server -t <topology-file-name> -i <routing-update-interval>")
    command = input("Enter server command: ").strip().split()
    if len(command) == 5 and command[0] == "server" and command[1] == "-t" and command[3] == "-i":
        topology_file = command[2]
        try:
            update_interval = int(command[4])
            if update_interval >= 5:
                router = Router(topology_file, update_interval)
                router.run()
            else:
                print("Routing update interval must be at least 5 seconds.")
        except ValueError:
            print("Invalid routing update interval. Please enter a valid integer.")
    else:
        print("Invalid command. Use the format: server -t <topology-file-name> -i <routing-update-interval>")