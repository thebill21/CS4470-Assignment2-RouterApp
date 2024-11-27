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
        self.nodes = []  # All nodes in the network
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}  # {neighbor_id: cost}
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.number_of_packets_received = 0  # For statistics

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()
        print("Initialization complete.\n")

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
                    print(f"Accepted connection from {address}")
                    self.handle_client(client_socket)
            except Exception as e:
                print(f"Error in listening thread: {e}")

        threading.Thread(target=listen, daemon=True).start()

    def handle_client(self, client_socket):
        """Handle an incoming client connection."""
        try:
            message = client_socket.recv(1024).decode()
            if not message.strip():  # Check for empty or whitespace-only message
                print("Received empty message from client.")
                return
            print(f"Received raw message: {message}")
            try:
                json_message = json.loads(message)
                self.process_message(json_message)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON message: {e}")
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def process_message(self, message):
        """Process incoming routing table updates or commands."""
        self.number_of_packets_received += 1
        print(f"Processing message: {message}")
        
        if message.get("command") == "update":
            server1_id = int(message["server1_id"])
            server2_id = int(message["server2_id"])
            new_cost = float(message["new_cost"])
            print(f"Received update command: Update link between {server1_id} and {server2_id} to {new_cost}")
            self.update(server1_id, server2_id, new_cost)
            return

        sender_id = int(message.get("id"))
        received_table = {int(k): v for k, v in message.get("routing_table", {}).items()}

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
            self.step()

    def update(self, server1_id, server2_id, new_cost):
        """
        Update the cost of a link between two servers and propagate the change bi-directionally.
        """
        print(f"Updating link cost between {server1_id} and {server2_id} to {new_cost}...")
        with self.lock:
            if server1_id == self.my_id or server2_id == self.my_id:
                # Determine the neighbor ID for the link
                neighbor_id = server2_id if server1_id == self.my_id else server1_id
                
                # Update the cost in the routing table and neighbors
                if neighbor_id in self.neighbors:
                    self.neighbors[neighbor_id] = new_cost
                    self.routing_table[neighbor_id] = new_cost
                    self.next_hop[neighbor_id] = neighbor_id
                    
                    print(f"Link cost updated locally. New cost to server {neighbor_id}: {new_cost}")
                    
                    # Notify the neighbor to update its view of the link
                    self.notify_neighbor_update(neighbor_id, server1_id, server2_id, new_cost)
                    
                    # Trigger an immediate update to neighbors
                    self.step()
                else:
                    print(f"Error: Link between {self.my_id} and {neighbor_id} does not exist.")
            else:
                print(f"Error: Link between {server1_id} and {server2_id} does not involve this router.")

    def notify_neighbor_update(self, neighbor_id, server1_id, server2_id, new_cost):
        """
        Notify the neighbor to update the cost of the link bi-directionally.
        """
        neighbor = self.get_node_by_id(neighbor_id)
        if not neighbor:
            print(f"Error: Neighbor {neighbor_id} not found.")
            return

        message = {
            "command": "update",
            "server1_id": server1_id,
            "server2_id": server2_id,
            "new_cost": new_cost
        }
        print(f"Notifying neighbor {neighbor_id} to update link cost...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                s.sendall(json.dumps(message).encode())
        except Exception as e:
            print(f"Error notifying neighbor {neighbor_id}: {e}")

    def start_periodic_updates(self):
        """Starts a thread to periodically send updates to neighbors."""
        def periodic_update():
            while self.running:
                time.sleep(self.update_interval)
                self.step()

        threading.Thread(target=periodic_update, daemon=True).start()

    def step(self):
        """Send routing updates to neighbors."""
        print("Sending updates to neighbors...")
        message = {
            "id": self.my_id,
            "routing_table": self.routing_table
        }
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                self.send_message(neighbor, message)

    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def send_message(self, neighbor, message):
        """Sends a message to a neighbor."""
        print(f"Sending message to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                formatted_message = json.dumps(message)
                s.sendall(formatted_message.encode())
        except Exception as e:
            print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")

    def get_my_ip(self):
        """Get the machine's local IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception as e:
            print(f"Error determining local IP address: {e}")
            return "127.0.0.1"

    def load_topology(self):
        """Reads the topology file and initializes routing tables."""
        print(f"Loading topology from file: {self.topology_file}")
        try:
            with open(self.topology_file, 'r') as f:
                lines = f.read().strip().split('\n')

            num_servers = int(lines[0])  # Number of servers
            num_links = int(lines[1])  # Number of links

            # Parse servers
            for i in range(2, 2 + num_servers):
                parts = lines[i].split()
                node_id, ip, port = int(parts[0]), parts[1], int(parts[2])
                node = Node(node_id, ip, port)
                self.nodes.append(node)
                if ip == self.my_ip:
                    self.my_id = node_id
                    self.my_node = node
                    self.routing_table[node_id] = 0  # Cost to self is 0
                    self.next_hop[node_id] = node_id  # Next hop to self is self
                else:
                    self.routing_table[node_id] = float('inf')
                    self.next_hop[node_id] = None

            # Parse links
            for i in range(2 + num_servers, 2 + num_servers + num_links):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), float(parts[2])
                if from_id == self.my_id:
                    self.neighbors[to_id] = cost
                    self.routing_table[to_id] = cost
                    self.next_hop[to_id] = to_id
                elif to_id == self.my_id:
                    self.neighbors[from_id] = cost
                    self.routing_table[from_id] = cost
                    self.next_hop[from_id] = from_id

            print("Topology loaded successfully.\n")
        except Exception as e:
            print(f"Error loading topology: {e}")

    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        print("--------------------------------")
        for dest_id in sorted(self.routing_table.keys()):
            next_hop = self.next_hop.get(dest_id)
            cost = self.routing_table[dest_id]
            next_hop_str = str(next_hop) if next_hop is not None else "None"
            cost_str = "infinity" if cost == float('inf') else f"{cost:.1f}"
            print(f"{dest_id:<14}{next_hop_str:<14}{cost_str}")
        print()
    # Other methods (start_listening, process_message, display_routing_table, etc.) remain unchanged.

    def run(self):
        """Run the router to process commands."""
        print("Router is running. Available commands:")
        print("  display        - Display the current routing table")
        print("  step           - Send a routing update to neighbors")
        print("  update         - Update the cost of a link (e.g., 'update <server1_id> <server2_id> <new_cost>')")
        print("  packets        - Display the number of packets received")
        print("  exit           - Exit the router")
        
        while self.running:
            command_line = input("Enter command: ").strip().split()
            if not command_line:
                continue

            command = command_line[0].lower()
            try:
                if command == "display":
                    self.display_routing_table()
                elif command == "step":
                    self.step()
                elif command == "update":
                    if len(command_line) == 4:
                        try:
                            server1_id = int(command_line[1])
                            server2_id = int(command_line[2])
                            new_cost = float(command_line[3])
                            self.update(server1_id, server2_id, new_cost)
                        except ValueError:
                            print("Invalid input. Use: update <server1_id> <server2_id> <new_cost>")
                    else:
                        print("Invalid syntax. Use: update <server1_id> <server2_id> <new_cost>")
                elif command == "packets":
                    print(f"Number of packets received: {self.number_of_packets_received}")
                elif command == "exit":
                    self.running = False
                    print("Exiting router...")
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