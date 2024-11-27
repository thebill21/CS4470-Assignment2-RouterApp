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
        self.nodes = []  # Initialize nodes list
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = set()
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.number_of_packets_received = 0  # Correctly initialize it here

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        print("Starting health monitor...")
        self.start_health_monitor()
        self.start_listening()
        self.start_periodic_updates()
        self.connect_neighbors()
        print("Initialization complete.\n")

    def start_health_monitor(self):
        """Starts a thread to monitor the health of neighbors."""
        def health_check():
            while self.running:
                # Check the health of each neighbor
                for neighbor_id in list(self.neighbors):  # Iterate over known neighbors
                    neighbor = self.get_node_by_id(neighbor_id)
                    if neighbor:
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.settimeout(2)  # 2-second timeout for health check
                                s.connect((neighbor.ip, neighbor.port))
                                s.sendall(b"PING")
                                # If neighbor was previously marked as offline, reactivate it
                                if self.routing_table[neighbor_id] == float('inf'):
                                    print(f"Neighbor {neighbor_id} is back online. Marking as active.")
                                    #self.routing_table[neighbor_id] = self.get_initial_cost_to_neighbor(neighbor_id)
                                    self.next_hop[neighbor_id] = neighbor_id
                                    #self.recalculate_routes()  # Update routing table after reactivation
                                else:
                                    print(f"Neighbor {neighbor_id} is alive.")
                        except Exception:
                            # If the neighbor is unresponsive, mark as crashed
                            print(f"Neighbor {neighbor_id} is not responding. Marking as crashed.")
                            with self.lock:
                                self.routing_table[neighbor_id] = float('inf')
                                self.next_hop[neighbor_id] = None
                                # Invalidate routes going through this neighbor
                                for dest_id, next_hop in list(self.next_hop.items()):
                                    if next_hop == neighbor_id:
                                        print(f"Invalidating route to {dest_id} via crashed neighbor {neighbor_id}.")
                                        self.routing_table[dest_id] = float('inf')
                                        self.next_hop[dest_id] = None
                                #self.recalculate_routes()  # Update routing table after crash
                time.sleep(5)  # Check health every 5 seconds

        threading.Thread(target=health_check, daemon=True).start()

    def get_my_ip(self):
        """Get the machine's local IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            print(f"Local IP address determined: {local_ip}")
            return local_ip
        except Exception as e:
            print(f"Error determining local IP address: {e}")
            return "127.0.0.1"  # Fallback to localhost if detection fails

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
                self.nodes.append(node)  # Populate nodes list
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

            print("Nodes list after topology load:")
            for node in self.nodes:
                print(f"Node ID: {node.id}, IP: {node.ip}, Port: {node.port}")

            print("Topology loaded successfully.\n")
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
                    print(f"Accepted connection from {address}")
                    self.handle_client(client_socket)
            except Exception as e:
                print(f"Error in listening thread: {e}")

        threading.Thread(target=listen, daemon=True).start()

    def handle_client(self, client_socket):
        """Handle an incoming client connection."""
        try:
            message = client_socket.recv(1024).decode()
            if message.strip() == "PING":
                # Respond to health check PINGs
                client_socket.sendall(b"PONG")
                print("Responded to PING from a neighbor.")
                return
            elif not message.strip():
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

    def connect_neighbors(self):
        """Attempts to connect to all neighbors."""
        print("Attempting to connect to neighbors...")
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(5)
                        s.connect((neighbor.ip, neighbor.port))
                        print(f"Successfully connected to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
                except Exception as e:
                    print(f"Failed to connect to neighbor {neighbor_id} at {neighbor.ip}:{neighbor.port}: {e}")
            else:
                print(f"Neighbor {neighbor_id} not found in topology.")

    def start_periodic_updates(self):
        """Starts a thread to periodically send updates to neighbors."""
        def periodic_update():
            while self.running:
                time.sleep(self.update_interval)
                self.step()

        threading.Thread(target=periodic_update, daemon=True).start()

    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        print(f"Node {node_id} not found.")
        return None

    def process_message(self, message):
        """Process incoming routing table updates."""
        self.number_of_packets_received += 1  # Increment for each received packet
        print(f"Processing message: {message}")
        sender_id = int(message.get("id"))  # Ensure sender_id is an integer
        received_table = {int(k): v for k, v in message.get("routing_table", {}).items()}  # Convert keys to integers

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

    def send_message(self, neighbor, message):
        """Sends a message to a neighbor."""
        print(f"Sending message to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                formatted_message = json.dumps(message)
                print(f"Sending formatted JSON message: {formatted_message}")
                s.sendall(formatted_message.encode())
                print(f"Message sent successfully to {neighbor.id}.")
        except Exception as e:
            print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")

    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        print("--------------------------------")
        seen = set()
        for dest_id in sorted(self.routing_table.keys(), key=int):  # Ensure sorted by integer
            if dest_id in seen:
                continue  # Skip duplicate entries
            seen.add(dest_id)

            next_hop = self.next_hop.get(dest_id, None)
            cost = self.routing_table[dest_id]
            next_hop_str = next_hop if next_hop is not None else "None"
            cost_str = "infinity" if cost == float('inf') else cost
            print(f"{dest_id:<14}{next_hop_str:<14}{cost_str}")
        print()


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
        print("Routing updates sent.")

    def crash(self):
        """Simulate a crash."""
        print("Disabling all connections.")
        self.running = False

    def run(self):
        """Run the router to process commands and manage periodic updates."""
        # Start periodic updates in a separate thread
        threading.Thread(target=self.start_periodic_updates, daemon=True).start()
        print("Router is running. Enter commands:")
        
        while self.running:
            command_line = input("Enter command: ").strip().split()
            if not command_line:
                continue

            command = command_line[0].lower()
            try:
                if command == "display":
                    self.display_routing_table()
                elif command == "step":
                    print("Manually triggering a routing update.")
                    self.step()
                elif command == "crash":
                    print("Simulating server crash.")
                    self.crash()
                    break
                elif command == "packets":
                    self.display_packets()
                elif command == "update" and len(command_line) == 4:
                    try:
                        server1 = int(command_line[1])
                        server2 = int(command_line[2])
                        new_cost = int(command_line[3])
                        self.update(server1, server2, new_cost)
                    except ValueError:
                        print("Invalid input. Use: update <server1_id> <server2_id> <new_cost>")
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")

    def update(self, server1_id, server2_id, new_cost):
        """Update the cost of a link between two servers."""
        with self.lock:
            if server1_id == self.my_id or server2_id == self.my_id:
                target_id = server2_id if server1_id == self.my_id else server1_id
                if target_id in self.neighbors:
                    self.routing_table[target_id] = new_cost
                    print(f"Updated cost to server {target_id} to {new_cost}")
                    self.step()  # Trigger a step update after cost change
                else:
                    print("Can only update the cost to direct neighbors.")
            else:
                print("This server is not involved in the specified link.")

    def display_packets(self):
        """Display the number of packets received."""
        print(f"Number of packets received: {self.number_of_packets_received}")
        # Optionally, reset the counter if required:
        # self.number_of_packets_received = 0


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