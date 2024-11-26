import socket
import threading
import time
import json
import queue
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
        self.update_queue = queue.Queue()  # Queue for scheduling updates
        self.step_in_progress = False  # Track step execution

        print(f"Initializing router with topology file: {topology_file} and update interval: {update_interval}s.")
        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()
        self.connect_neighbors()
        self.start_step_processor()  # Start step processor thread
        print("Initialization complete.\n")

    def start_step_processor(self):
        """Start a background thread to process step updates."""
        def process_queue():
            while self.running:
                # Block until there's something in the queue
                try:
                    self.update_queue.get(timeout=1)  # Wait for an update request
                    self._process_step()  # Perform the step
                except queue.Empty:
                    continue

        threading.Thread(target=process_queue, daemon=True).start()

    def queue_step(self):
        """Add a step request to the queue."""
        if not self.step_in_progress:  # Avoid flooding the queue
            self.update_queue.put(1)

    def _process_step(self):
        """Process a step request."""
        if self.step_in_progress:
            return  # Avoid overlapping executions
        self.step_in_progress = True
        try:
            print("DEBUG: Entering step function...")
            with self.lock:
                print("DEBUG: Acquired lock in step function.")
                message = {
                    "id": self.my_id,
                    "routing_table": self.routing_table
                }
                for neighbor_id in self.neighbors:
                    neighbor = self.get_node_by_id(neighbor_id)
                    if neighbor:
                        print(f"DEBUG: Sending message to neighbor {neighbor.id}.")
                        self.send_message(neighbor, message)
                print("DEBUG: Routing updates sent successfully.")
        except Exception as e:
            print(f"Error in step: {e}")
        finally:
            self.step_in_progress = False
            print("DEBUG: Exiting step function.")

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
        threads = []
        for neighbor_id in self.neighbors:
            neighbor = self.get_node_by_id(neighbor_id)
            if neighbor:
                thread = threading.Thread(target=self._connect_to_neighbor, args=(neighbor,))
                thread.daemon = True
                threads.append(thread)
                thread.start()

        # Ensure all threads complete or timeout
        for thread in threads:
            thread.join(timeout=5)

    def _connect_to_neighbor(self, neighbor):
        """Helper function to connect to a single neighbor."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((neighbor.ip, neighbor.port))
                print(f"Successfully connected to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
        except Exception as e:
            print(f"Failed to connect to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}: {e}")

    def start_periodic_updates(self):
        """Starts a thread to periodically send updates to neighbors."""
        def periodic_update():
            while self.running:
                if not self.step_in_progress:  # Avoid overlap
                    self.step()
                time.sleep(self.update_interval)

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
        self.number_of_packets_received += 1
        print(f"Processing message: {message}")
        sender_id = int(message.get("id"))  # Ensure sender_id is an integer
        received_table = {int(k): v for k, v in message.get("routing_table", {}).items()}

        if sender_id is None or received_table is None:
            print("Message missing required fields: 'id' or 'routing_table'.")
            return

        updated = False
        with self.lock:
            for dest_id, received_cost in received_table.items():
                if dest_id == self.my_id:  # Skip self
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
            self.queue_step()  # Queue the step for execution

    def send_message(self, neighbor, message):
        """Sends a message to a neighbor with retries."""
        retries = 3
        while retries > 0:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(5)
                    s.connect((neighbor.ip, neighbor.port))
                    s.sendall(json.dumps(message).encode())
                    print(f"Message sent successfully to neighbor {neighbor.id} at {neighbor.ip}:{neighbor.port}")
                    return  # Exit on success
            except socket.error as e:
                print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")
                retries -= 1
                time.sleep(1)
        print(f"Failed to send message to neighbor {neighbor.id} after retries.")

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
        print()

    def display_routing_table(self):
        """Display the routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        for dest_id in sorted(self.routing_table.keys()):
            cost = self.routing_table[dest_id]
            next_hop = self.next_hop.get(dest_id, "None")
            cost_str = cost if cost != float('inf') else "Infinity"
            print(f"{dest_id}\t\t{next_hop}\t\t{cost_str}")


    def step(self):
        """Send routing updates to neighbors."""
        if self.step_in_progress:
            print("DEBUG: Skipping step - already in progress.")
            return

        self.step_in_progress = True
        try:
            print("DEBUG: Entering step function...")
            with self.lock:
                print("DEBUG: Acquired lock in step function.")
                message = {
                    "id": self.my_id,
                    "routing_table": self.routing_table
                }
                for neighbor_id in self.neighbors:
                    neighbor = self.get_node_by_id(neighbor_id)
                    if neighbor:
                        print(f"DEBUG: Sending message to neighbor {neighbor.id}.")
                        self.send_message(neighbor, message)
                print("DEBUG: Routing updates sent successfully.")
        except Exception as e:
            print(f"Error in step: {e}")
        finally:
            self.step_in_progress = False
            print("DEBUG: Exiting step function.")

    def disable_link(self, server_id):
        """Disables a link to a neighbor."""
        with self.lock:
            if server_id in self.neighbors:
                # Set cost to infinity and update routing table
                self.routing_table[server_id] = float('inf')
                self.next_hop[server_id] = None
                print(f"Disabled link to neighbor {server_id}.")
                self.step()  # Propagate the update
            else:
                print(f"Cannot disable: Server {server_id} is not a direct neighbor.")

    def crash(self):
        """Simulate a crash and clean shutdown."""
        print("Simulating crash. Stopping all operations.")
        self.running = False
        time.sleep(1)  # Allow threads to finish gracefully
        print("Router has stopped.")

    def run(self):
        """Run the router to process commands and manage periodic updates."""
        threading.Thread(target=self.start_periodic_updates, daemon=True).start()
        print("Router is running. Enter commands:")

        while self.running:
            try:
                print("DEBUG: Waiting for user input...")
                command_line = input("Enter command: ").strip().split()
                if not command_line:
                    continue

                command = command_line[0].lower()
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
                    server1, server2, cost = map(int, command_line[1:])
                    self.update(server1, server2, cost)
                elif command == "disable" and len(command_line) == 2:
                    server_id = int(command_line[1])
                    self.disable_link(server_id)
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")

    def update(self, server1_id, server2_id, new_cost):
        """Update the cost of a link between two servers."""
        try:
            with self.lock:
                if server1_id == self.my_id or server2_id == self.my_id:
                    target_id = server2_id if server1_id == self.my_id else server1_id
                    if target_id in self.neighbors:
                        print(f"Updated cost to server {target_id} to {new_cost}")
                        self.routing_table[target_id] = new_cost
                        self.next_hop[target_id] = target_id
                        self.recalculate_routes()
                        print("Routing table after update:")
                        self.display_routing_table()
                    else:
                        print(f"Cannot update: Server {target_id} is not a direct neighbor.")
                else:
                    print("This server is not involved in the specified link.")
        except Exception as e:
            print(f"Error during update: {e}")
        finally:
            self.queue_step()  # Queue the step for execution

    def _safe_step(self):
        """Safely trigger a single step without overlapping."""
        if not self.step_in_progress:
            self.step()

    def recalculate_routes(self):
        """Recalculate routing table using Bellman-Ford logic."""
        updated = False
        with self.lock:
            print("Recalculating routes using Bellman-Ford logic...")

            # Iterate over all possible destinations
            for dest_id in self.routing_table.keys():
                if dest_id == self.my_id:
                    continue  # Skip self

                # Initialize to the current best cost and next hop
                best_cost = self.routing_table[dest_id]
                best_next_hop = self.next_hop.get(dest_id)

                # Evaluate routes through all neighbors
                for neighbor_id in self.neighbors:
                    cost_to_neighbor = self.routing_table.get(neighbor_id, float('inf'))
                    neighbor_cost_to_dest = self.get_neighbor_cost_to_dest(neighbor_id, dest_id)

                    # Skip if neighbor is unreachable
                    if cost_to_neighbor == float('inf') or neighbor_cost_to_dest == float('inf'):
                        continue

                    # Compute total cost via this neighbor
                    total_cost = cost_to_neighbor + neighbor_cost_to_dest

                    # Update if this route is better
                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_next_hop = neighbor_id

                # Apply updates to the routing table if necessary
                if best_cost != self.routing_table[dest_id] or best_next_hop != self.next_hop.get(dest_id):
                    print(f"Updated route to {dest_id}: cost {self.routing_table[dest_id]} -> {best_cost}, next hop: {best_next_hop}")
                    self.routing_table[dest_id] = best_cost
                    self.next_hop[dest_id] = best_next_hop
                    updated = True

            if updated:
                print("Routing table updated after recalculation.")
                self.display_routing_table()
            else:
                print("No changes in routing table after recalculation.")

    def get_neighbor_cost_to_dest(self, neighbor_id, dest_id):
        """Retrieve the cost from a neighbor to a destination."""
        # Simulate retrieving a neighbor's cost to a destination
        # This should be based on the most recent routing table received from the neighbor
        neighbor_node = self.get_node_by_id(neighbor_id)
        if not neighbor_node:
            return float('inf')  # If the neighbor is not found, return infinity

        # Placeholder for getting the actual routing table of the neighbor
        # In real implementation, you'd store the last received routing table from the neighbor
        return self.routing_table.get(dest_id, float('inf'))


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