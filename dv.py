# Team 28: 
# Tuan Khai Tran, CIN: 402795338
# Jiahao Li, CIN: <Jiahao will add his CIN at his version of submission>

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
        self.processed_updates = set()  # Set to track processed topology updates
        self.disabled_links = set()  # Track disabled links as tuples (server1_id, server2_id)

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()
        self.connect_neighbors()
        print("Initialization complete.\n")

    # Li Jiahao
    def start_periodic_updates(self):
        """Starts a thread to periodically send routing updates to neighbors."""
        def periodic_update():
            while self.running:
                time.sleep(self.update_interval)
                self.step()  # Trigger routing table update broadcasts

        threading.Thread(target=periodic_update, daemon=True).start()

    # Li Jiahao
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

    # Li Jiahao
    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        print(f"Node {node_id} not found.")
        return None

    # Li Jiahao
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

    # Li Jiahao
    def load_topology(self):
        """Reads the topology file and initializes routing tables."""
        print(f"Loading topology from file: {self.topology_file}")
        try:
            # Step 1: Read and parse the topology file
            self.topology = defaultdict(dict)  # Store topology in memory
            with open(self.topology_file, 'r') as f:
                lines = f.read().strip().split('\n')
            num_servers = int(lines[0])
            num_neighbors = int(lines[1])

            # Step 2: Load servers (nodes)
            for i in range(2, 2 + num_servers):
                parts = lines[i].split()
                node = Node(int(parts[0]), parts[1], int(parts[2]))
                self.nodes.append(node)

                # Check if this is the current server
                if parts[1] == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id] = 0  # Distance to self is 0
                    self.next_hop[node.id] = node.id
                    print(f"[INFO] Identified self as Server {node.id}")
                else:
                    self.routing_table[node.id] = float('inf')  # Initialize distances to infinity
                    self.next_hop[node.id] = None

                print(f"Loaded server {node.id}: IP={node.ip}, Port={node.port}")

            # Step 3: Load links (connections)
            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])

                # Update the topology structure with link costs
                self.topology[from_id][to_id] = cost
                self.topology[to_id][from_id] = cost

                # If this server is directly connected, update neighbors and routing tables
                if from_id == self.my_id:
                    self.neighbors[to_id] = cost
                    self.routing_table[to_id] = cost
                    self.next_hop[to_id] = to_id
                    print(f"[INFO] Added neighbor: Server {to_id} with cost {cost}")
                elif to_id == self.my_id:
                    self.neighbors[from_id] = cost
                    self.routing_table[from_id] = cost
                    self.next_hop[from_id] = from_id
                    print(f"[INFO] Added neighbor: Server {from_id} with cost {cost}")

                print(f"Link loaded: {from_id} <-> {to_id} with cost {cost}")

            # Step 4: Ensure the topology is correctly structured
            print("[DEBUG] Initial topology structure:")
            for from_id, connections in self.topology.items():
                print(f"  Server {from_id}: {connections}")

            # Step 5: Apply Bellman-Ford algorithm to compute initial routing table
            print("Applying Bellman-Ford algorithm for initial routing table computation.")
            self.recompute_routing_table()

            print("Topology loaded successfully.\n")
        except Exception as e:
            print(f"[ERROR] Failed to load topology: {e}")

    # Li Jiahao
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

    # Tuan Khai Tran
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

    # Li Jiahao + Tuan Khai Tran
    def process_message(self, message):
        """Process incoming messages, including routing updates and topology updates."""
        self.number_of_packets_received += 1  # Increment the packet count for statistics

        # Handle topology update command
        if message.get("command") == "server_crash":
            crashed_server_id = message.get("crashed_server_id")
            print(f"[INFO] Received crash notification for Server {crashed_server_id}.")

            with self.lock:
                # Debug: Topology and neighbors before handling the crash
                print(f"[DEBUG] Topology before handling crash: {dict(self.topology)}")
                print(f"[DEBUG] Neighbors before handling crash: {self.neighbors}")

                # Remove the crashed server from topology and neighbors
                if crashed_server_id in self.topology:
                    print(f"[INFO] Removing Server {crashed_server_id} from topology.")
                    del self.topology[crashed_server_id]
                    for node_id in self.topology:
                        if crashed_server_id in self.topology[node_id]:
                            del self.topology[node_id][crashed_server_id]

                if crashed_server_id in self.neighbors:
                    print(f"[INFO] Removing Server {crashed_server_id} from neighbors.")
                    self.neighbors.pop(crashed_server_id, None)

                # Debug: Topology and neighbors after handling the crash
                print(f"[DEBUG] Topology after handling crash: {dict(self.topology)}")
                print(f"[DEBUG] Neighbors after handling crash: {self.neighbors}")

            # Recompute the routing table
            print(f"[INFO] Recomputing routing table after Server {crashed_server_id} crash.")
            self.recompute_routing_table()

            # Debug: Routing table after recomputation
            print(f"[DEBUG] Routing table after recomputation: {self.routing_table}")
            return


        if "command" in message:
            if message["command"] == "update_topology":
                server1_id = int(message["server1_id"])
                server2_id = int(message["server2_id"])
                new_cost = float(message["new_cost"])
                origin_id = message.get("origin_id", None)  # Originating router of the update

                print(f"[INFO] Received topology update command: {server1_id} <-> {server2_id} with cost {new_cost}.")

                # Check if this update has already been processed
                update_key = (server1_id, server2_id, new_cost)
                if update_key in self.processed_updates:
                    print(f"[INFO] Already processed update {update_key}. Skipping.")
                    return

                # Mark the update as processed
                self.processed_updates.add(update_key)

                # Perform the same update command locally
                print(f"[INFO] Performing local update: update {server2_id} <-> {server1_id} with cost {new_cost}")
                self.update(server2_id, server1_id, new_cost)

                return
            
        if "command" in message:
            if message["command"] == "disable_link":
                server1_id = int(message["server1_id"])
                server2_id = int(message["server2_id"])
                origin_id = int(message.get("origin_id", -1))

                print(f"[INFO] Received disable command for link: {server1_id} <-> {server2_id}.")

                if (server1_id, server2_id) in self.disabled_links:
                    print(f"[INFO] Already processed disable for link ({server1_id}, {server2_id}). Skipping.")
                    return

                # Add to disabled links and update topology
                with self.lock:
                    self.disabled_links.add((server1_id, server2_id))
                    self.disabled_links.add((server2_id, server1_id))
                    self.topology[server1_id][server2_id] = float('inf')
                    self.topology[server2_id][server1_id] = float('inf')
                    print(f"[DEBUG] Updated topology to reflect disabled link: {dict(self.topology)}")

                # Forward the disable command
                if origin_id != self.my_id:
                    print(f"[INFO] Forwarding disable command for link {server1_id} <-> {server2_id}.")
                    self.broadcast_topology_update(server1_id, server2_id, float('inf'), origin_id)

                # Recompute routing table
                print("[INFO] Recomputing routing table after disabling the link.")
                self.recompute_routing_table()
                return

        # Handle routing table updates
        if "id" in message and "routing_table" in message:
            sender_id = int(message["id"])  # Sender's ID
            
            # Ignore updates from disabled neighbors
            if sender_id in self.neighbors and self.neighbors[sender_id] == float('inf'):
                print(f"[INFO] Ignoring updates from disabled neighbor {sender_id}.")
                return

            # Process received routing table updates
            received_table = {int(k): float(v) for k, v in message["routing_table"].items()}

            print(f"[INFO] Received routing update from Router {sender_id}: {received_table}")

            updated = False
            with self.lock:
                for dest_id, received_cost in received_table.items():
                    if dest_id == self.my_id:
                        continue  # Skip routes to self

                    # Calculate new cost through the sender
                    cost_to_sender = self.routing_table.get(sender_id, float('inf'))
                    new_cost = cost_to_sender + received_cost

                    # Update if the new route is better
                    if new_cost < self.routing_table.get(dest_id, float('inf')):
                        print(f"[DEBUG] Updating route to {dest_id}: "
                            f"cost {self.routing_table.get(dest_id)} -> {new_cost}, Next Hop={sender_id}")
                        self.routing_table[dest_id] = new_cost
                        self.next_hop[dest_id] = sender_id
                        updated = True

            if updated:
                print("[INFO] Routing table updated based on received routing update.")
                self.display_routing_table()
                self.step()  # Propagate updated routing table to neighbors
            return

        # Handle unrecognized or unsupported commands
        print("[ERROR] Unknown or unsupported command received. Ignoring message.")

    # Tuan Khai Tran
    def broadcast_topology_update(self, server1_id, server2_id, new_cost, origin_id):
        """Broadcast topology update to all neighbors except the origin."""
        update_message = {
            "command": "update_topology",
            "server1_id": server1_id,
            "server2_id": server2_id,
            "new_cost": new_cost,
            "origin_id": origin_id or self.my_id  # Set origin_id if not provided
        }
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor and neighbor_id != origin_id:  # Avoid sending back to the origin
                print(f"Forwarding topology update to neighbor {neighbor.id}.")
                self.send_message(neighbor, update_message)

    # Li Jiahao
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

    # Li Jiahao
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

    # Tuan Khai Tran
    def update(self, server1_id, server2_id, new_cost):
        """Update a link cost bi-directionally and broadcast to the entire network."""
        print(f"[INFO] Received update command: Updating edge {server1_id} <-> {server2_id} with new cost {new_cost}.")

        # Treat 'inf' as disabling the link
        if new_cost == float('inf'):
            print(f"[INFO] Setting cost to 'inf' effectively disables the link {server1_id} <-> {server2_id}.")
            with self.lock:
                self.topology[server1_id][server2_id] = new_cost
                self.topology[server2_id][server1_id] = new_cost
                self.disabled_links.add((server1_id, server2_id))
                self.disabled_links.add((server2_id, server1_id))

                # If the current router is involved, update its neighbors
                if server1_id == self.my_id or server2_id == self.my_id:
                    neighbor_id = server2_id if server1_id == self.my_id else server1_id
                    if neighbor_id in self.neighbors:
                        print(f"[INFO] Removing {neighbor_id} from neighbors.")
                        del self.neighbors[neighbor_id]

            # Broadcast the disable command to all other neighbors
            disable_message = {
                "command": "disable_link",
                "server1_id": server1_id,
                "server2_id": server2_id,
                "origin_id": self.my_id,
            }
            for neighbor_id in self.neighbors:
                neighbor = self.get_node_by_id(neighbor_id)
                if neighbor:
                    print(f"[DEBUG] Broadcasting disable to neighbor {neighbor.id}.")
                    self.send_message(neighbor, disable_message)

            # Recompute the routing table after disabling the link
            print("[INFO] Recomputing routing table after disabling the link.")
            self.recompute_routing_table()
            return

        # Handle regular cost updates
        with self.lock:
            self.topology[server1_id][server2_id] = new_cost
            self.topology[server2_id][server1_id] = new_cost
            print(f"[DEBUG] Updated local in-memory topology: {dict(self.topology)}")

        if server1_id == self.my_id or server2_id == self.my_id:
            neighbor_id = server2_id if server1_id == self.my_id else server1_id
            with self.lock:
                self.neighbors[neighbor_id] = new_cost
                self.routing_table[neighbor_id] = new_cost
                self.next_hop[neighbor_id] = neighbor_id
                print(f"[DEBUG] Updated local neighbor cost: {dict(self.neighbors)}")
        else:
            print(f"[INFO] This router is not directly connected to edge {server1_id} <-> {server2_id}.")

        # Broadcast the edge update to all neighbors
        update_message = {
            "command": "update_topology",
            "server1_id": server1_id,
            "server2_id": server2_id,
            "new_cost": new_cost,
            "origin_id": self.my_id  # Include origin to prevent rebroadcasting loops
        }
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                print(f"[DEBUG] Broadcasting edge update to neighbor {neighbor.id}.")
                self.send_message(neighbor, update_message)

        # Recompute the routing table after applying the update
        print("[INFO] Recomputing routing table after local topology update.")
        self.recompute_routing_table()

    # Tuan Khai Tran -> Currently not in use
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

    # Tuan Khai Tran
    def recompute_routing_table(self):
        """Recompute the routing table using the Bellman-Ford algorithm."""
        print("[INFO] Recomputing routing table...")

        with self.lock:
            # Reset the routing table and next hops
            for node in self.nodes:
                if node.id == self.my_id:
                    # Distance to self is 0, next hop is self
                    self.routing_table[node.id] = 0
                    self.next_hop[node.id] = self.my_id
                else:
                    # Initialize other distances to infinity and next hops to None
                    self.routing_table[node.id] = float('inf')
                    self.next_hop[node.id] = None

            # Perform Bellman-Ford iterations
            for _ in range(len(self.nodes) - 1):  # At most (number of nodes - 1) iterations
                for from_id, neighbors in self.topology.items():
                    for to_id, cost in neighbors.items():
                        if cost == float('inf'):  # Skip disabled links
                            continue

                        # Calculate the cost to the destination via this link
                        new_cost = self.routing_table[from_id] + cost

                        # If the new cost is better, update the routing table and next hop
                        if new_cost < self.routing_table[to_id]:
                            self.routing_table[to_id] = new_cost
                            # Update next hop: use the direct neighbor if it's reachable
                            self.next_hop[to_id] = (
                                to_id if self.my_id == from_id else self.next_hop[from_id]
                            )

            # Handle unreachable nodes by ensuring next hop is None
            for dest_id in self.routing_table:
                if self.routing_table[dest_id] == float('inf'):
                    self.next_hop[dest_id] = None

            # Display the updated routing table
            self.display_routing_table()     

    # Li Jiahao
    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        for dest_id, cost in self.routing_table.items():
            next_hop = self.next_hop.get(dest_id, None)
            # Handle None for next_hop gracefully
            next_hop_display = next_hop if next_hop is not None else "None"
            print(f"     {dest_id:<14}{next_hop_display:<14}{cost}")
        print()

    # Tuan Khai Tran
    def disable(self, server_id):
        """Disable a link to a given server."""
        if server_id not in self.neighbors:
            print(f"[ERROR] Server {server_id} is not a neighbor. Cannot disable link.")
            return

        print(f"[COMMAND] Disabling link to Server {server_id}.")
        print(f"[INFO] Disabling link: Server {self.my_id} <-> Server {server_id}.")

        # Update topology and add to disabled links
        with self.lock:
            self.topology[self.my_id][server_id] = float('inf')
            self.topology[server_id][self.my_id] = float('inf')
            self.disabled_links.add((self.my_id, server_id))
            self.disabled_links.add((server_id, self.my_id))  # Add both directions
            print(f"[DEBUG] Updated topology to reflect disabled link: {dict(self.topology)}")

        # Remove from neighbors
        if server_id in self.neighbors:
            print(f"[INFO] Removing Server {server_id} from neighbors.")
            del self.neighbors[server_id]

        # Broadcast disable command
        disable_message = {
            "command": "disable_link",
            "server1_id": self.my_id,
            "server2_id": server_id,
            "origin_id": self.my_id,
        }
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                print(f"[DEBUG] Broadcasting disable to neighbor {neighbor.id}.")
                self.send_message(neighbor, disable_message)

        # Recompute routing table
        print("[INFO] Recomputing routing table after disabling the link.")
        self.recompute_routing_table()

    # Tuan Khai Tran
    def crash(self):
        """Simulate server crash by closing all connections."""
        print("[COMMAND] Simulating server crash. Closing all connections.")

        # Notify all neighbors about the crash
        for neighbor_id in list(self.neighbors.keys()):
            print(f"[INFO] Notifying neighbor {neighbor_id} of server crash.")
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                message = {
                    "command": "server_crash",
                    "crashed_server_id": self.my_id
                }
                self.send_message(neighbor, message)

        # Stop the server
        print("[INFO] Clearing local data structures and stopping the server.")
        self.running = False
        self.neighbors.clear()
        self.routing_table.clear()
        self.next_hop.clear()
        print("[INFO] Server crash simulated. Exiting...")

    # Li Jiahao + Tuan Khai Tran
    def run(self):
        """Process commands."""
        while self.running:
            # Accept user command as input
            command = input("Enter command: ").strip().split()
            if not command:
                continue

            # Parse the command and its arguments
            cmd = command[0].lower()
            try:
                if cmd == "display":
                    self.display_routing_table()  # Show the routing table
                    print("display SUCCESS")  # Success response for the display command
                elif cmd == "update" and len(command) == 4:
                    server1_id = int(command[1])  # Parse server1 ID
                    server2_id = int(command[2])  # Parse server2 ID
                    new_cost = float('inf') if command[3].lower() == "inf" else float(command[3])  # Parse cost
                    self.update(server1_id, server2_id, new_cost)  # Execute the update command
                elif cmd == "step":
                    self.step()  # Send routing updates
                    print("step SUCCESS")  # Success response for the step command
                elif cmd == "packets":
                    # Show the total packets received
                    print(f"packets SUCCESS\nTotal packets received: {self.number_of_packets_received}")
                elif cmd == "disable" and len(command) == 2:
                    server_id = int(command[1])  # Parse the server ID to disable
                    self.disable(server_id)  # Execute the disable command
                elif cmd == "crash":
                    print("crash SUCCESS")  # Notify that crash was initiated
                    self.crash()  # Crash the server
                    break
                else:
                    # Handle unknown commands
                    print("[ERROR] Unknown command. Available commands: display, update, step, packets, disable, crash.")
            except ValueError as e:
                # Handle invalid input errors
                print(f"{cmd} ERROR: Invalid input. {str(e)}")

# Li Jiahao + Tuan Khai Tran
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