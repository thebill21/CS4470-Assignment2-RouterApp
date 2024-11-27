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
        self.nodes = []  # List of all nodes
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}  # {neighbor_id: cost}
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.number_of_packets_received = 0  # Packet counter
        self.global_graph = defaultdict(dict)  # For Bellman-Ford
        self.next_door_model = {}  # {neighbor_id: {destination_id: cost}}

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
        except Exception as e:
            print(f"Error determining local IP address: {e}")
            return "127.0.0.1"

    def load_topology(self):
        """Reads the topology file and initializes routing tables."""
        print(f"Loading topology from file: {self.topology_file}")
        try:
            with open(self.topology_file, 'r') as f:
                lines = f.read().strip().split('\n')
            num_servers = int(lines[0])
            num_neighbors = int(lines[1])

            # Parse nodes
            for i in range(2, 2 + num_servers):
                parts = lines[i].split()
                node = Node(int(parts[0]), parts[1], int(parts[2]))
                self.nodes.append(node)
                if parts[1] == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id] = 0
                    self.next_hop[node.id] = node.id

            # Parse neighbors and populate `next_door_model`
            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), float(parts[2])
                self.global_graph[from_id][to_id] = cost
                self.global_graph[to_id][from_id] = cost

                if from_id == self.my_id:
                    self.neighbors[to_id] = cost
                    self.next_door_model[to_id] = {self.my_id: cost}  # Initialize with direct cost
                elif to_id == self.my_id:
                    self.neighbors[from_id] = cost
                    self.next_door_model[from_id] = {self.my_id: cost}  # Initialize with direct cost

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
                    client_socket, _ = server_socket.accept()
                    threading.Thread(target=self.handle_client, args=(client_socket,)).start()
            except Exception as e:
                print(f"Error in listening thread: {e}")

        threading.Thread(target=listen, daemon=True).start()

    def handle_client(self, client_socket):
        """Handle an incoming client connection."""
        try:
            message = client_socket.recv(1024).decode()
            if message:
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
                time.sleep(self.update_interval)
                self.step()

        threading.Thread(target=periodic_update, daemon=True).start()

    def process_message(self, message):
        """Process incoming routing table updates."""
        try:
            self.number_of_packets_received += 1
            sender_id = message['id']
            received_table = message['routing_table']

            print(f"[DEBUG] Processing message from server {sender_id}: {received_table}")

            with self.lock:
                # Update next_door_model for the sender
                if sender_id in self.neighbors:
                    self.next_door_model[sender_id] = {
                        dest_id: float(cost) for dest_id, cost in received_table.items() if dest_id != self.my_id
                    }

            # Recalculate routes after incorporating the message
            self.recalculate_routes()
        except Exception as e:
            print(f"Error processing message: {e}")

    def recalculate_routes(self):
        """Recalculate the best routes using next-door neighbors."""
        print("[DEBUG] Recalculating routes...")

        with self.lock:
            updated_table = {}
            updated_next_hops = {}

            for dest_id in self.routing_table:
                if dest_id == self.my_id:
                    updated_table[dest_id] = 0
                    updated_next_hops[dest_id] = self.my_id
                    continue

                best_cost = float('inf')
                best_next_hop = None

                for neighbor_id, edge_cost in self.neighbors.items():
                    if neighbor_id not in self.next_door_model:
                        continue

                    # Calculate cost via this neighbor
                    neighbor_table = self.next_door_model[neighbor_id]
                    cost_via_neighbor = edge_cost + neighbor_table.get(dest_id, float('inf'))

                    # Check if this path is better
                    if cost_via_neighbor < best_cost:
                        best_cost = cost_via_neighbor
                        best_next_hop = neighbor_id

                updated_table[dest_id] = best_cost
                updated_next_hops[dest_id] = best_next_hop

            # Update the routing table and next hop map
            self.routing_table = updated_table
            self.next_hop = updated_next_hops

        self.display_routing_table()

    
    def bellman_ford(self, graph, source):
        """Bellman-Ford algorithm to compute shortest paths and honor next hop rules."""
        distances = {node: float('inf') for node in graph}
        next_hops = {}
        distances[source] = 0

        for _ in range(len(graph) - 1):
            for u in graph:
                for v in graph[u]:
                    new_cost = distances[u] + graph[u][v]
                    if new_cost < distances[v]:
                        distances[v] = new_cost
                        # Only update next hop if no next hop exists or the path is shorter
                        if v not in self.next_hop or self.next_hop[v] == u or new_cost < self.routing_table[v]:
                            next_hops[v] = u if u == source else next_hops.get(u, u)

        return distances, next_hops

    def step(self):
        """Send routing updates to neighbors."""
        print("Sending updates to neighbors...")
        message = {
            "id": self.my_id,
            "routing_table": self.routing_table
        }
        for neighbor_id, cost in self.neighbors.items():
            neighbor = next((node for node in self.nodes if node.id == neighbor_id), None)
            if neighbor:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((neighbor.ip, neighbor.port))
                        s.sendall(json.dumps(message).encode())
                except Exception as e:
                    print(f"Error sending updates to neighbor {neighbor_id}: {e}")

    # def update(self, server1_id, server2_id, new_cost):
    #     """Update the cost of a link between two servers and propagate the change."""
    #     with self.lock:
    #         if server1_id in self.global_graph and server2_id in self.global_graph[server1_id]:
    #             self.global_graph[server1_id][server2_id] = new_cost
    #             self.global_graph[server2_id][server1_id] = new_cost
    #             print(f"Updated link cost between {server1_id} and {server2_id} to {new_cost}.")
    #             self.step()  # Notify neighbors of the update
    #         else:
    #             print(f"Error: Link between {server1_id} and {server2_id} does not exist.")

    def update(self, server1_id, server2_id, new_cost):
        """Update the cost of a link between two servers."""
        with self.lock:
            if server1_id == self.my_id or server2_id == self.my_id:
                target_id = server2_id if server1_id == self.my_id else server1_id
                self.global_graph[server1_id][server2_id] = new_cost
                self.global_graph[server2_id][server1_id] = new_cost

                # Update the next_door_model for the updated neighbor
                if target_id in self.neighbors:
                    self.next_door_model[target_id] = {self.my_id: new_cost}

                print(f"Updated link cost between {server1_id} and {server2_id} to {new_cost}.")
                self.step()  # Notify neighbors of the update
            else:
                print(f"Error: Link between {server1_id} and {server2_id} does not exist.")

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

    def run(self):
        """Run the router command interface."""
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
                elif command == "update" and len(command_line) == 4:
                    server1_id = int(command_line[1])
                    server2_id = int(command_line[2])
                    new_cost = float(command_line[3])
                    self.update(server1_id, server2_id, new_cost)
                    time.sleep(2)
                    self.update(server1_id, server2_id, new_cost)
                    time.sleep(2)
                    self.update(server1_id, server2_id, new_cost)
                    time.sleep(2)
                    self.update(server1_id, server2_id, new_cost)
                    time.sleep(2)
                    self.update(server1_id, server2_id, new_cost)
                        
                elif command == "exit":
                    self.running = False
                    print("Exiting...")
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")

    def exit_router(self):
        """Gracefully exit the router."""
        self.running = False
        print("Router is shutting down. Goodbye!")
        # Perform any necessary cleanup here

    def display_packets(self):
        """Display the number of packets received."""
        print(f"Number of packets received: {self.number_of_packets_received}")

# Main execution block
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