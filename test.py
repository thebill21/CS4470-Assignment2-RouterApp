import socket
import threading
import time
import json
from collections import defaultdict
from functools import total_ordering

@total_ordering
class Node:
    """Represents a node in the network."""
    def __init__(self, node_id, ip, port):
        self.id = node_id
        self.ip = ip
        self.port = port

    def __hash__(self):
        return hash((self.id, self.ip, self.port))

    def __eq__(self, other):
        return (self.id, self.ip, self.port) == (other.id, other.ip, other.port)

    def __lt__(self, other):
        return self.id < other.id


class Router:
    """Distance Vector Routing Protocol Router."""
    def __init__(self, topology_file, update_interval):
        self.my_ip = self.get_my_ip()
        self.my_id = None
        self.my_node = None
        self.nodes = []  # Node list
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.next_hop = {}
        self.neighbors = set()
        self.number_of_packets_received = 0
        self.running = True
        self.lock = threading.Lock()

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()
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
                    if neighbor:
                        self.neighbors.add(neighbor)
                        self.routing_table[to_id] = cost
                        self.next_hop[to_id] = to_id
                elif to_id == self.my_id:
                    neighbor = self.get_node_by_id(from_id)
                    if neighbor:
                        self.neighbors.add(neighbor)
                        self.routing_table[from_id] = cost
                        self.next_hop[from_id] = from_id

        except Exception as e:
            print(f"Error loading topology: {e}")

    def start_listening(self):
        """Start a server socket to listen for incoming connections."""
        def listen():
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.bind((self.my_ip, self.my_node.port))
                server_socket.listen(5)
                print(f"Listening on {self.my_ip}:{self.my_node.port}")
                while self.running:
                    client_socket, address = server_socket.accept()
                    self.handle_client(client_socket)
            except Exception as e:
                print(f"Error in listening thread: {e}")

        threading.Thread(target=listen, daemon=True).start()

    def handle_client(self, client_socket):
        """Handle an incoming client connection."""
        try:
            message = client_socket.recv(1024).decode()
            if message.strip():
                json_message = json.loads(message)
                self.process_message(json_message)
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def start_periodic_updates(self):
        """Starts a thread to periodically send updates to neighbors."""
        def periodic_update():
            while self.running:
                self.step()
                time.sleep(self.update_interval)

        threading.Thread(target=periodic_update, daemon=True).start()

    def step(self):
        """Send routing updates to neighbors."""
        print("Sending updates to neighbors...")
        message = {
            "id": self.my_id,
            "routing_table": self.routing_table
        }
        for neighbor in self.neighbors:
            self.send_message(neighbor, message)

    def send_message(self, neighbor, message):
        """Send a routing update message to a neighbor."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                s.sendall(json.dumps(message).encode())
        except Exception as e:
            print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")

    def update(self, server1_id, server2_id, new_cost):
        """Update the cost of a link between two servers."""
        with self.lock:
            if server1_id == self.my_id or server2_id == self.my_id:
                target_id = server2_id if server1_id == self.my_id else server1_id
                target_node = self.get_node_by_id(target_id)
                if target_node in self.neighbors:
                    self.routing_table[target_id] = new_cost
                    self.next_hop[target_id] = target_id
                    print(f"Updated cost to server {target_id} to {new_cost}")
                    self.step()
                else:
                    print("Can only update cost to direct neighbors.")
            else:
                print("This server is not involved in the specified link.")

    def disable(self, server_id):
        """Disable the connection with a neighbor."""
        with self.lock:
            target_node = self.get_node_by_id(server_id)
            if target_node and target_node in self.neighbors:
                self.neighbors.remove(target_node)
                self.routing_table[target_node.id] = float('inf')
                self.next_hop[target_node.id] = None
                print(f"Connection with server {server_id} disabled.")
            else:
                print("Cannot disable: specified server is not a neighbor.")

    def process_message(self, message):
        """Process incoming routing table updates."""
        self.number_of_packets_received += 1  # Increment for each received packet
        print(f"Processing message: {message}")

        try:
            sender_id = int(message.get("id"))  # Ensure sender_id is an integer
            received_table = {int(k): float(v) for k, v in message.get("routing_table", {}).items()}  # Convert keys and values
        except (ValueError, TypeError) as e:
            print(f"Error processing message: {e}")
            return

        if sender_id is None or received_table is None:
            print("Message missing required fields: 'id' or 'routing_table'.")
            return

        updated = False
        with self.lock:
            for dest_id, received_cost in received_table.items():
                if dest_id == self.my_id:
                    continue

                # Calculate new cost via sender
                cost_to_sender = self.routing_table.get(sender_id, float('inf'))
                new_cost = cost_to_sender + received_cost

                # Update only if new cost is better
                if new_cost < self.routing_table.get(dest_id, float('inf')):
                    print(f"Updating route to {dest_id}: cost {self.routing_table.get(dest_id, float('inf'))} -> {new_cost}, next hop: {sender_id}")
                    self.routing_table[dest_id] = new_cost
                    self.next_hop[dest_id] = sender_id
                    updated = True

        if updated:
            print("Routing table updated based on received message.")
            self.display_routing_table()
            self.step()  # Send updates to neighbors after a change

    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def display_routing_table(self):
        """Display the routing table with valid routes."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        print("--------------------------------")

        displayed = set()  # To avoid duplicates

        for dest_id in sorted(self.routing_table.keys(), key=int):  # Sort by destination ID
            if dest_id == self.my_id:
                print(f"{dest_id:<14}{self.my_id:<14}0")
                continue

            for neighbor in sorted(self.neighbors, key=lambda n: n.id):  # Sort neighbors by node ID
                cost = self.routing_table.get(dest_id, float('inf'))
                if neighbor.id == self.next_hop.get(dest_id, None) and (dest_id, neighbor.id) not in displayed:
                    cost_str = cost if cost != float('inf') else "infinity"
                    print(f"{dest_id:<14}{neighbor.id:<14}{cost_str}")
                    displayed.add((dest_id, neighbor.id))

    def run(self):
        """Runs the router and handles user commands."""
        while self.running:
            command = input("Enter command: ").strip().lower()
            parts = command.split()
            if parts[0] == "display":
                self.display_routing_table()
            elif parts[0] == "step":
                self.step()
            elif parts[0] == "update" and len(parts) == 4:
                try:
                    server1_id = int(parts[1])
                    server2_id = int(parts[2])
                    new_cost = int(parts[3])
                    self.update(server1_id, server2_id, new_cost)
                except ValueError:
                    print("Invalid input. Use: update <server1_id> <server2_id> <new_cost>")
            elif parts[0] == "disable" and len(parts) == 2:
                try:
                    server_id = int(parts[1])
                    self.disable(server_id)
                except ValueError:
                    print("Invalid input. Use: disable <server_id>")
            elif parts[0] == "packets":
                print(f"Packets received: {self.number_of_packets_received}")
            elif parts[0] == "crash":
                self.running = False
                print("Router stopped.")
            else:
                print("Invalid command.")

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
            print("Invalid routing update interval. Please provide a valid integer.")
    else:
        print("Invalid command. Use the format: server -t <topology-file-name> -i <routing-update-interval>")