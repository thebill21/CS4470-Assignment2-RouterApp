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
        self.neighbors = {}  # Neighbors with link costs
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.number_of_packets_received = 0  # Correctly initialize it here

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()
        self.connect_neighbors()
        print("Initialization complete.\n")

    def start_periodic_updates(self):
        """Starts a thread to periodically send routing updates to neighbors."""
        def periodic_update():
            while self.running:
                time.sleep(self.update_interval)
                self.step()  # Trigger routing table update broadcasts

        threading.Thread(target=periodic_update, daemon=True).start()

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

    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        print(f"Node {node_id} not found.")
        return None

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
            self.topology = defaultdict(dict)  # Store topology in memory
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
                    self.routing_table[node.id] = 0  # Distance to self is 0
                    self.next_hop[node.id] = node.id
                else:
                    self.routing_table[node.id] = float('inf')
                    self.next_hop[node.id] = None
                print(f"Loaded server {node.id}: IP={node.ip}, Port={node.port}")

            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
                self.topology[from_id][to_id] = cost  # Store in-memory topology
                self.topology[to_id][from_id] = cost  # Ensure symmetry

                if from_id == self.my_id:
                    self.neighbors[to_id] = cost
                    self.routing_table[to_id] = cost
                    self.next_hop[to_id] = to_id
                elif to_id == self.my_id:
                    self.neighbors[from_id] = cost
                    self.routing_table[from_id] = cost
                    self.next_hop[from_id] = from_id
                print(f"Link loaded: {from_id} <-> {to_id} with cost {cost}")

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

    # def process_message(self, message):
    #     """Process incoming messages, including routing updates and link update commands."""
    #     self.number_of_packets_received += 1  # Increment packet count for statistics

    #     if "command" in message:
    #         # Handle specific commands, such as 'update'
    #         if message["command"] == "update":
    #             server1_id = int(message["server1_id"])
    #             server2_id = int(message["server2_id"])
    #             new_cost = float(message["new_cost"])
    #             print(f"Received update command: Updating link {server1_id} <-> {server2_id} to cost {new_cost}.")
                
    #             if self.my_id in (server1_id, server2_id):
    #                 # Update local routing table and neighbors
    #                 neighbor_id = server2_id if server1_id == self.my_id else server1_id
    #                 with self.lock:
    #                     self.neighbors[neighbor_id] = new_cost
    #                     self.routing_table[neighbor_id] = new_cost
    #                     self.next_hop[neighbor_id] = neighbor_id
    #                     print(f"Updated cost to neighbor {neighbor_id} to {new_cost}.")
    #                 self.step()  # Propagate the updated routing table
    #             return

    #     # Process routing table updates from neighbors
    #     sender_id = int(message.get("id"))  # Ensure the sender ID is an integer
    #     received_table = {int(k): float(v) for k, v in message.get("routing_table", {}).items()}  # Convert keys and values

    #     print(f"Processing routing update from Router {sender_id}. Received table: {received_table}")

    #     updated = False  # Track whether the routing table was updated
    #     with self.lock:
    #         for dest_id, received_cost in received_table.items():
    #             if dest_id == self.my_id:
    #                 continue  # Skip routes to self

    #             # Calculate new cost via the sender
    #             cost_to_sender = self.routing_table.get(sender_id, float('inf'))
    #             new_cost = cost_to_sender + received_cost

    #             # Update only if the new cost is better
    #             if new_cost < self.routing_table.get(dest_id, float('inf')):
    #                 print(f"Updating route to {dest_id}: cost {self.routing_table.get(dest_id)} -> {new_cost}, next hop: {sender_id}")
    #                 self.routing_table[dest_id] = new_cost
    #                 self.next_hop[dest_id] = sender_id
    #                 updated = True

    #     if updated:
    #         print("Routing table updated based on received message.")
    #         self.display_routing_table()  # Display the updated routing table
    #         self.step()  # Trigger routing updates to neighbors

    def process_message(self, message):
        """Process incoming messages, including routing updates and link update commands."""
        self.number_of_packets_received += 1  # Increment packet count for statistics

        if "command" in message:
            # Handle specific commands, such as 'update'
            if message["command"] == "update":
                server1_id = int(message["server1_id"])
                server2_id = int(message["server2_id"])
                new_cost = float(message["new_cost"])
                print(f"Received update command: Updating link {server1_id} <-> {server2_id} to cost {new_cost}.")

                # Update the local topology
                with self.lock:
                    if server1_id == self.my_id or server2_id == self.my_id:
                        neighbor_id = server2_id if server1_id == self.my_id else server1_id
                        self.neighbors[neighbor_id] = new_cost
                        self.routing_table[neighbor_id] = new_cost
                        self.next_hop[neighbor_id] = neighbor_id
                        print(f"Updated cost to neighbor {neighbor_id} to {new_cost}.")

                # Propagate the change to neighbors
                self.step()

                # Recompute routing table after topology update
                self.recompute_routing_table()
                return

        # Process routing table updates from neighbors
        sender_id = int(message.get("id"))  # Ensure the sender ID is an integer
        received_table = {int(k): float(v) for k, v in message.get("routing_table", {}).items()}  # Convert keys and values

        print(f"Processing routing update from Router {sender_id}. Received table: {received_table}")

        updated = False  # Track whether the routing table was updated
        with self.lock:
            for dest_id, received_cost in received_table.items():
                if dest_id == self.my_id:
                    continue  # Skip routes to self

                # Calculate new cost via the sender
                cost_to_sender = self.routing_table.get(sender_id, float('inf'))
                new_cost = cost_to_sender + received_cost

                # Update only if the new cost is better
                if new_cost < self.routing_table.get(dest_id, float('inf')):
                    print(f"Updating route to {dest_id}: cost {self.routing_table.get(dest_id)} -> {new_cost}, next hop: {sender_id}")
                    self.routing_table[dest_id] = new_cost
                    self.next_hop[dest_id] = sender_id
                    updated = True

        if updated:
            print("Routing table updated based on received message.")
            self.display_routing_table()  # Display the updated routing table
            self.step()  # Trigger routing updates to neighbors

    def step(self):
        """Send routing updates to neighbors."""
        print("\n[STEP] Triggering routing updates to neighbors.")
        message = {
            "id": self.my_id,
            "routing_table": self.routing_table
        }

        for neighbor_id, cost in self.neighbors.items():
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                print(f"[STEP] Preparing to send routing table to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}.")
                self.send_message(neighbor, message)
            else:
                print(f"[STEP] Neighbor {neighbor_id} not found in node list. Skipping.")
        print("[STEP] Routing updates broadcasted.\n")

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

    # def update(self, server1_id, server2_id, new_cost):
    #     """Update a link cost bi-directionally."""
    #     with self.lock:
    #         # Update local view of the link
    #         if server1_id == self.my_id or server2_id == self.my_id:
    #             neighbor_id = server2_id if server1_id == self.my_id else server1_id
    #             self.neighbors[neighbor_id] = new_cost
    #             self.routing_table[neighbor_id] = new_cost
    #             self.next_hop[neighbor_id] = neighbor_id
    #             print(f"Updated local link cost to {neighbor_id} to {new_cost}.")
    #         else:
    #             print(f"This router is not involved in the link between {server1_id} and {server2_id}.")

    #     # Send an update message to the other router involved
    #     target_router_id = server2_id if server1_id == self.my_id else server1_id
    #     neighbor = self.get_node_by_id(target_router_id)

    #     if neighbor:
    #         update_message = {
    #             "command": "update",
    #             "server1_id": server1_id,
    #             "server2_id": server2_id,
    #             "new_cost": new_cost
    #         }
    #         print(f"Notifying neighbor {target_router_id} about the link update.")
    #         self.send_message(neighbor, update_message)

    #     # Trigger routing table propagation
    #     self.step()

    def update(self, server1_id, server2_id, new_cost):
        """Update a link cost bi-directionally and implement the five-step approach."""
        print(f"Received update command: Updating edge {server1_id} <-> {server2_id} with new cost {new_cost}.")
        
        # Step 1: Update the local in-memory topology.
        with self.lock:
            self.topology[server1_id][server2_id] = new_cost
            self.topology[server2_id][server1_id] = new_cost
            print(f"Updated in-memory topology for edge {server1_id} <-> {server2_id} to cost {new_cost}.")

        # Step 2: If this router is directly involved, update its local neighbor view.
        if server1_id == self.my_id or server2_id == self.my_id:
            neighbor_id = server2_id if server1_id == self.my_id else server1_id
            with self.lock:
                self.neighbors[neighbor_id] = new_cost
                self.routing_table[neighbor_id] = new_cost
                self.next_hop[neighbor_id] = neighbor_id
                print(f"Updated local link cost to neighbor {neighbor_id} to {new_cost}.")
        else:
            print(f"This router is not directly connected to edge {server1_id} <-> {server2_id}.")

        # Step 3: Broadcast the edge update to all neighbors.
        update_message = {
            "command": "update_edge",
            "server1_id": server1_id,
            "server2_id": server2_id,
            "new_cost": new_cost
        }
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                print(f"Broadcasting edge update to neighbor {neighbor.id}.")
                self.send_message(neighbor, update_message)

        # Step 4: Roll back the current routing table to the topology state.
        print("Rolling back routing table to match updated topology.")
        self.recompute_routing_table()

        # Step 5: Apply the Bellman-Ford algorithm for route recalculation.
        print("Applying Bellman-Ford algorithm to recalculate routes.")
        self.step()  # Re-broadcast routing table updates.

    def apply_update(self, server1_id, server2_id, new_cost):
        """Apply the edge update and recompute routing table."""
        with self.lock:
            # Update topology if directly connected
            if server1_id == self.my_id or server2_id == self.my_id:
                neighbor_id = server2_id if server1_id == self.my_id else server1_id
                self.neighbors[neighbor_id] = new_cost
                self.routing_table[neighbor_id] = new_cost
                self.next_hop[neighbor_id] = neighbor_id
                self.topology[server1_id][server2_id] = new_cost
                self.topology[server2_id][server1_id] = new_cost
                print(f"Updated local topology: {server1_id} <-> {server2_id} to cost {new_cost}.")
            else:
                print(f"Edge {server1_id} <-> {server2_id} is not directly connected to this router.")

            # Rollback to the original topology and reapply Bellman-Ford
            self.recompute_routing_table()

    def recompute_routing_table(self):
        """Recompute the routing table from scratch after a topology update."""
        print("Recomputing routing table...")
        with self.lock:
            # Reset routing table entries
            for node in self.nodes:
                if node.id == self.my_id:
                    self.routing_table[node.id] = 0  # Cost to self is 0
                    self.next_hop[node.id] = self.my_id
                elif node.id in self.neighbors:
                    self.routing_table[node.id] = self.neighbors[node.id]  # Direct neighbors
                    self.next_hop[node.id] = node.id
                else:
                    self.routing_table[node.id] = float('inf')  # All others are unreachable
                    self.next_hop[node.id] = None

            # Reapply the Bellman-Ford algorithm
            self.step()

        print("Routing table recomputed.")
        self.display_routing_table()

    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        for dest_id, cost in self.routing_table.items():
            next_hop = self.next_hop.get(dest_id, None)
            print(f"{dest_id:<14}{next_hop:<14}{cost}")
        print()

    def run(self):
        """Process commands."""
        while self.running:
            command = input("Enter command: ").strip().split()
            if not command:
                continue
            
            # Command parsing
            cmd = command[0].lower()
            if cmd == "display":
                print("[COMMAND] Displaying routing table.")
                self.display_routing_table()
            elif cmd == "update" and len(command) == 4:
                try:
                    server1_id = int(command[1])
                    server2_id = int(command[2])
                    new_cost = int(command[3])
                    print(f"[COMMAND] Updating edge {server1_id} <-> {server2_id} with cost {new_cost}.")
                    self.update(server1_id, server2_id, new_cost)
                except ValueError:
                    print("[ERROR] Invalid input. Use: update <server1_id> <server2_id> <new_cost>")
            elif cmd == "step":
                print("[COMMAND] Manually triggering routing updates.")
                self.step()
            elif cmd == "crash":
                print("[COMMAND] Stopping the router.")
                self.running = False
            else:
                print("[ERROR] Unknown command. Available commands: display, update, step, crash.")


if __name__ == "__main__":
    topology_file = "test.txt"  # Replace with your file
    update_interval = 15
    router = Router(topology_file, update_interval)
    router.run()