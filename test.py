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
    def __init__(self, topology_file, update_interval):
        self.my_ip = self.get_my_ip()
        self.my_id = None
        self.my_node = None
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = set()
        self.next_hop = {}
        self.number_of_packets_received = 0
        self.running = True
        self.lock = threading.Lock()

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        # Load topology and connect to neighbors
        self.load_topology()
        self.connect_neighbors()
        print("Initialization complete.\n")

    def get_my_ip(self):
        """Get the current machine's IP address."""
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print(f"Local IP address determined: {ip}")
            return ip
        except Exception as e:
            print(f"Error getting local IP: {e}")
            return None

    def load_topology(self):
        """Reads the topology file and initializes routing tables."""
        print(f"Loading topology from file: {self.topology_file}")
        try:
            with open(self.topology_file, 'r') as f:
                lines = f.read().strip().split('\n')
            num_servers = int(lines[0])
            num_neighbors = int(lines[1])

            for i in range(2, 2 + num_servers):
                parts = lines[i].split()
                node = Node(int(parts[0]), parts[1], int(parts[2]))
                if parts[1] == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id] = 0
                    self.next_hop[node.id] = node.id
                else:
                    self.routing_table[node.id] = float('inf')
                    self.next_hop[node.id] = None
                print(f"Loaded server {node.id}: IP={node.ip}, Port={node.port}")

            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
                if from_id == self.my_id:
                    self.neighbors.add(to_id)
                    self.routing_table[to_id] = cost
                    self.next_hop[to_id] = to_id
                elif to_id == self.my_id:
                    self.neighbors.add(from_id)
                    self.routing_table[from_id] = cost
                    self.next_hop[from_id] = from_id
                print(f"Link loaded: {from_id} <-> {to_id} with cost {cost}")

            print("Topology loaded successfully.\n")
        except Exception as e:
            print(f"Error loading topology: {e}")

    def connect_neighbors(self):
        """Attempts to connect to all neighbors."""
        print("Attempting to connect to neighbors...")
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor.ip, neighbor.port))
                        print(f"Successfully connected to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
                except Exception as e:
                    print(f"Failed to connect to neighbor {neighbor_id} at {neighbor.ip}:{neighbor.port}: {e}")
            else:
                print(f"Neighbor {neighbor_id} not found in topology.")

    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        print(f"Node {node_id} not found.")
        return None

    def update(self, server_id1, server_id2, cost):
        """Updates the link cost between two servers."""
        with self.lock:
            if server_id1 == self.my_id or server_id2 == self.my_id:
                target_id = server_id2 if server_id1 == self.my_id else server_id1
                if target_id in self.neighbors:
                    self.routing_table[target_id] = cost
                    print(f"Updated cost to {target_id} to {cost}")
                    self.step()
                else:
                    print("Can only update the cost to neighbors.")
            else:
                print("This server is not involved in the specified link.")

    def step(self):
        """Sends a routing update to all neighbors."""
        with self.lock:
            if self.neighbors:
                print("Sending updates to neighbors...")
                message = self.make_message()
                for neighbor_id in self.neighbors:
                    neighbor = self.get_node_by_id(neighbor_id)
                    if neighbor:
                        self.send_message(neighbor, message)
                print("Step completed.\n")
            else:
                print("No neighbors to send updates to.\n")

    def make_message(self):
        """Creates a routing table message."""
        message = {"id": self.my_id, "routing_table": self.routing_table}
        print(f"Message created: {message}")
        return json.dumps(message)

    def send_message(self, neighbor, message):
        """Sends a message to a neighbor."""
        print(f"Sending message to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                s.sendall(message.encode())
                print(f"Message sent successfully to {neighbor.id}.")
        except Exception as e:
            print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")

    def display_routing_table(self):
        """Displays the routing table."""
        print("\nRouting Table:")
        print("Destination    Next Hop       Cost")
        print("----------------------------------")
        for dest_id in sorted(self.routing_table.keys()):
            next_hop = self.next_hop.get(dest_id, None)
            cost = self.routing_table[dest_id]
            next_hop_str = next_hop if next_hop is not None else "None"
            cost_str = "infinity" if cost == float('inf') else cost
            print(f"{dest_id:<14} {next_hop_str:<14} {cost_str}")
        print()

    def disable(self, server_id):
        """Disables a link to a specific neighbor."""
        with self.lock:
            if server_id in self.neighbors:
                self.neighbors.remove(server_id)
                self.routing_table[server_id] = float('inf')
                self.next_hop[server_id] = None
                print(f"Disabled connection with server {server_id}.")
            else:
                print("Cannot disable a non-neighbor link.")

    def crash(self):
        """Simulates a server crash by disabling all links."""
        print("Simulating server crash. Disabling all links...")
        with self.lock:
            self.running = False
            for neighbor_id in list(self.neighbors):
                self.disable(neighbor_id)
            print("Server has crashed. All links disabled.\n")

    def periodic_updates(self):
        """Sends periodic updates to neighbors."""
        while self.running:
            time.sleep(self.update_interval)
            self.step()

    def run(self):
        """Runs the router."""
        threading.Thread(target=self.periodic_updates, daemon=True).start()
        while self.running:
            command_line = input("Enter command: ").strip().split()
            if not command_line:
                continue

            command = command_line[0].lower()
            try:
                if command == "update" and len(command_line) == 4:
                    self.update(int(command_line[1]), int(command_line[2]), int(command_line[3]))
                elif command == "step":
                    self.step()
                elif command == "display":
                    self.display_routing_table()
                elif command == "disable" and len(command_line) == 2:
                    self.disable(int(command_line[1]))
                elif command == "crash":
                    self.crash()
                    break
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")


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