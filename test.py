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
        print("[DEBUG] Entering Router.__init__")
        
        # Basic property initialization
        self.my_ip = self.get_my_ip()
        self.my_id = None
        self.my_node = None
        self.nodes = []
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = set()
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.number_of_packets_received = 0

        # Debug info
        print(f"[DEBUG] Router initialized with IP: {self.my_ip}")
        print(f"[DEBUG] Topology file: {topology_file}, Update interval: {update_interval}s")
        
        # Load topology
        print("[DEBUG] Loading topology...")
        self.load_topology()
        
        # Ensure topology loaded successfully
        if self.my_id is None or self.my_node is None:
            print("[ERROR] Failed to identify self in the topology. Check the topology file.")
            raise ValueError("Self not identified in topology.")
        
        # Start health monitoring before listening or connecting
        print("[DEBUG] Starting health monitor...")
        self.start_health_monitor()

        # Start listening for incoming connections
        print("[DEBUG] Starting server listening...")
        self.start_listening()

        # Start periodic updates
        print("[DEBUG] Starting periodic updates...")
        self.start_periodic_updates()

        # Connect to neighbors
        print("[DEBUG] Connecting to neighbors...")
        self.connect_neighbors()

        print("[DEBUG] Router initialization complete.")
        print("[DEBUG] Exiting Router.__init__")

    def start_health_monitor(self):
        """Starts a thread to monitor the health of neighbors."""
        print("[DEBUG] Entering start_health_monitor")
        def health_check():
            while self.running:
                # Iterate over all known neighbors
                print("[DEBUG] Starting health check for neighbors...")
                for neighbor_id in list(self.routing_table.keys()):  # Includes all nodes in routing table
                    neighbor = self.get_node_by_id(neighbor_id)
                    if neighbor and neighbor_id != self.my_id:  # Skip self
                        print(f"[DEBUG] Checking health for Neighbor ID: {neighbor_id}, IP: {neighbor.ip}, Port: {neighbor.port}")
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.settimeout(2)  # Timeout for health check
                                s.connect((neighbor.ip, neighbor.port))
                                s.sendall(b"PING")
                                if self.routing_table[neighbor_id] == float('inf'):  # Reactivate if marked offline
                                    print(f"[DEBUG] Neighbor {neighbor_id} is back online. Marking as active.")
                                    self.mark_as_reactivated(neighbor_id)
                                else:
                                    print(f"[DEBUG] Neighbor {neighbor_id} is alive.")
                        except Exception as e:
                            print(f"[DEBUG] Neighbor {neighbor_id} is not responding. Marking as crashed. Exception: {e}")
                            self.mark_as_crashed(neighbor_id)
                # Recalculate routes and propagate update
                self.recalculate_routes()
                self.step()
                time.sleep(5)  # Run health checks every 5 seconds
        threading.Thread(target=health_check, daemon=True).start()
        print("[DEBUG] Exiting start_health_monitor")

    def mark_as_crashed(self, neighbor_id):
        """Mark a neighbor as crashed and update routing table."""
        print(f"[DEBUG] Entering mark_as_crashed for neighbor {neighbor_id}")
        with self.lock:
            if neighbor_id in self.routing_table:
                # Mark neighbor as unreachable
                print(f"[DEBUG] Marking Neighbor ID {neighbor_id} as crashed...")
                self.routing_table[neighbor_id] = float('inf')
                self.next_hop[neighbor_id] = None
                self.neighbors.discard(neighbor_id)  # Remove from neighbors if present

                # Invalidate routes going through the crashed neighbor
                for dest_id, next_hop in list(self.next_hop.items()):
                    if next_hop == neighbor_id:  # If next hop is the crashed node
                        print(f"[DEBUG] Invalidating route to Destination ID {dest_id} via Neighbor {neighbor_id}.")
                        self.routing_table[dest_id] = float('inf')  # Invalidate the route
                        self.next_hop[dest_id] = None
            else:
                print(f"[DEBUG] Neighbor {neighbor_id} was not found in the routing table.")
        print(f"[DEBUG] Exiting mark_as_crashed for neighbor {neighbor_id}")

    def mark_as_reactivated(self, neighbor_id):
        """Mark a previously crashed neighbor as reactivated and update routing table."""
        print(f"[DEBUG] Entering mark_as_reactivated for neighbor {neighbor_id}")
        with self.lock:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                print(f"[DEBUG] Reactivating Neighbor {neighbor_id}.")
                # Restore the link cost from the topology
                initial_cost = self.get_initial_cost_to_neighbor(neighbor_id)
                self.routing_table[neighbor_id] = initial_cost
                self.next_hop[neighbor_id] = neighbor_id
                self.neighbors.add(neighbor_id)
                
                # Log the restored cost
                print(f"[DEBUG] Restored link cost to Neighbor {neighbor_id}: {initial_cost}")
                
                # Recalculate routes and propagate updates
                # self.recalculate_routes()
                # self.step()  # Notify neighbors about the updated routing table
            else:
                print(f"[DEBUG] Neighbor {neighbor_id} not found for reactivation.")
        print(f"[DEBUG] Exiting mark_as_reactivated for neighbor {neighbor_id}")

    def get_initial_cost_to_neighbor(self, neighbor_id):
        print(f"[DEBUG] Entering get_initial_cost_to_neighbor for neighbor {neighbor_id}")
        for neighbor in self.nodes:
            if neighbor.id == neighbor_id:
                return self.routing_table.get(neighbor_id, float('inf'))
        print(f"[DEBUG] Exiting get_initial_cost_to_neighbor for neighbor {neighbor_id}")
        return float('inf')

    def recalculate_routes(self):
        print("[DEBUG] Entering recalculate_routes")
        updated = False
        with self.lock:
            for dest_id in self.routing_table.keys():
                if dest_id == self.my_id:
                    continue
                best_cost = float('inf')
                best_next_hop = None
                for neighbor_id in self.neighbors:
                    cost_to_neighbor = self.routing_table.get(neighbor_id, float('inf'))
                    neighbor_cost_to_dest = self.get_neighbor_cost_to_dest(neighbor_id, dest_id)
                    if cost_to_neighbor == float('inf') or neighbor_cost_to_dest == float('inf'):
                        continue
                    total_cost = cost_to_neighbor + neighbor_cost_to_dest
                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_next_hop = neighbor_id
                if best_cost != self.routing_table[dest_id] or best_next_hop != self.next_hop.get(dest_id):
                    self.routing_table[dest_id] = best_cost
                    self.next_hop[dest_id] = best_next_hop
                    updated = True
            if updated:
                print("[DEBUG] Routing table updated after recalculation.")
                self.display_routing_table()
            else:
                print("[DEBUG] No changes in routing table after recalculation.")
        print("[DEBUG] Exiting recalculate_routes")

    def get_neighbor_cost_to_dest(self, neighbor_id, dest_id):
        print(f"[DEBUG] Entering get_neighbor_cost_to_dest for neighbor {neighbor_id} and destination {dest_id}")
        if neighbor_id not in self.neighbors:
            return float('inf')
        return self.routing_table.get(dest_id, float('inf'))

    def get_my_ip(self):
        print("[DEBUG] Entering get_my_ip")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            print("[DEBUG] Exiting get_my_ip")
            return local_ip
        except Exception as e:
            print(f"[DEBUG] Error determining local IP address: {e}")
            return "127.0.0.1"

    def load_topology(self):
        print("[DEBUG] Entering load_topology")
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
                    self.neighbors.add(to_id)
                    self.routing_table[to_id] = cost
                    self.next_hop[to_id] = to_id
                elif to_id == self.my_id:
                    self.neighbors.add(from_id)
                    self.routing_table[from_id] = cost
                    self.next_hop[from_id] = from_id
        except Exception as e:
            print(f"[DEBUG] Error loading topology: {e}")
        print("[DEBUG] Exiting load_topology")

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

    def connect_neighbors(self):
        """Attempts to connect to all neighbors."""
        print("Attempting to connect to neighbors...")
        for neighbor_id in list(self.neighbors):  # Iterate over active neighbors
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(5)
                        s.connect((neighbor.ip, neighbor.port))
                        print(f"Successfully connected to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
                except Exception:
                    print(f"Failed to connect to neighbor {neighbor_id} at {neighbor.ip}:{neighbor.port}")
                    self.mark_as_crashed(neighbor_id)  # Mark the neighbor as crashed if unreachable

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

    # def display_routing_table(self):
    #     """Display the routing table."""
    #     print("\nRouting Table:")
    #     print("Destination\tNext Hop\tCost")
    #     print("--------------------------------")
    #     seen = set()
    #     for dest_id in sorted(self.routing_table.keys(), key=int):  # Ensure sorted by integer
    #         if dest_id in seen:
    #             continue  # Skip duplicate entries
    #         seen.add(dest_id)

    #         next_hop = self.next_hop.get(dest_id, None)
    #         cost = self.routing_table[dest_id]
    #         next_hop_str = next_hop if next_hop is not None else "None"
    #         cost_str = "infinity" if cost == float('inf') else cost
    #         print(f"{dest_id:<14}{next_hop_str:<14}{cost_str}")
    #     print()

    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost\tStatus")
        for dest_id in sorted(self.routing_table.keys()):
            cost = self.routing_table[dest_id]
            next_hop = self.next_hop.get(dest_id, "None")
            status = "OFFLINE" if cost == float('inf') else "ONLINE"
            cost_str = cost if cost != float('inf') else "Inf"
            print(f"{dest_id}\t\t{next_hop}\t\t{cost_str}\t{status}")

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