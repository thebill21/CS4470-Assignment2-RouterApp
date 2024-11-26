import socket
import threading
import time
import json


class Router:
    def __init__(self, topology_file, update_interval):
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.my_id = None
        self.my_node = None
        self.nodes = []
        self.routing_table = {}
        self.neighbors = {}
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.packet_counter = 0

        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()

    def get_local_ip(self):
        """Get the machine's network-facing IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))  # Use an external IP to determine the interface
                local_ip = s.getsockname()[0]
            return local_ip
        except Exception as e:
            print(f"Error determining local IP: {e}")
            return "127.0.0.1"  # Fallback to loopback

    def load_topology(self):
        machine_ip = self.get_local_ip()
        print(f"Detected machine IP: {machine_ip}")

        with open(self.topology_file, 'r') as file:
            lines = file.readlines()
        
        num_servers = int(lines[0].strip())
        num_neighbors = int(lines[1].strip())

        # Load nodes
        for i in range(2, 2 + num_servers):
            node_info = lines[i].strip().split()
            node_id, ip, port = int(node_info[0]), node_info[1], int(node_info[2])
            self.nodes.append({"id": node_id, "ip": ip, "port": port})

            if ip == machine_ip:
                self.my_id = node_id
                self.my_node = {"id": node_id, "ip": ip, "port": port}
        
        if self.my_node is None:
            raise ValueError(f"Machine IP {machine_ip} not found in topology file. Ensure it matches an entry.")

        # Load neighbors
        for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
            edge_info = lines[i].strip().split()
            from_id, to_id, cost = int(edge_info[0]), int(edge_info[1]), int(edge_info[2])
            if from_id == self.my_id or to_id == self.my_id:
                neighbor_id = to_id if from_id == self.my_id else from_id
                self.neighbors[neighbor_id] = cost
                self.routing_table[neighbor_id] = cost
                self.next_hop[neighbor_id] = neighbor_id

        # Initialize routing table
        for node in self.nodes:
            node_id = node["id"]
            if node_id not in self.routing_table:
                self.routing_table[node_id] = float('inf')
                self.next_hop[node_id] = None

        print("Topology loaded successfully.")

    def start_listening(self):
        def listen():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.bind((self.my_node["ip"], self.my_node["port"]))
                server_socket.listen(5)
                while self.running:
                    client_socket, _ = server_socket.accept()
                    threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()

        threading.Thread(target=listen, daemon=True).start()

    def handle_client(self, client_socket):
        try:
            data = client_socket.recv(1024).decode()
            message = json.loads(data)
            self.process_message(message)
        finally:
            client_socket.close()

    def start_periodic_updates(self):
        def periodic_update():
            while self.running:
                time.sleep(self.update_interval)
                self.send_updates()

        threading.Thread(target=periodic_update, daemon=True).start()

    def send_updates(self):
        update_message = {
            "id": self.my_id,
            "routing_table": self.routing_table
        }
        for neighbor_id in self.neighbors:
            neighbor = next(node for node in self.nodes if node["id"] == neighbor_id)
            self.send_message(neighbor, update_message)

    def send_message(self, neighbor, message):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((neighbor["ip"], neighbor["port"]))
            s.sendall(json.dumps(message).encode())

    def process_message(self, message):
        self.packet_counter += 1
        sender_id = message["id"]
        sender_table = message["routing_table"]

        updated = False
        for dest_id, cost_to_dest in sender_table.items():
            if dest_id == self.my_id:
                continue
            new_cost = self.routing_table[sender_id] + cost_to_dest
            if new_cost < self.routing_table[dest_id]:
                self.routing_table[dest_id] = new_cost
                self.next_hop[dest_id] = sender_id
                updated = True

        if updated:
            self.send_updates()

    def display_routing_table(self):
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        for dest_id in sorted(self.routing_table.keys()):
            next_hop = self.next_hop.get(dest_id, "None")
            cost = self.routing_table[dest_id]
            print(f"{dest_id}\t\t{next_hop}\t\t{cost}")

    def disable_link(self, server_id):
        """Disable the link to a given server."""
        with self.lock:
            if server_id in self.neighbors:
                # Set link cost to infinity and remove from neighbors
                self.routing_table[server_id] = float('inf')
                self.next_hop[server_id] = None
                self.neighbors.pop(server_id, None)
                print(f"Link to server {server_id} disabled.")
                self.send_updates()
            else:
                print(f"Server {server_id} is not a direct neighbor.")

    def monitor_neighbors(self):
        """Monitor neighbors and detect failures based on update intervals."""
        missed_updates = {neighbor: 0 for neighbor in self.neighbors}

        while self.running:
            time.sleep(self.update_interval)
            with self.lock:
                for neighbor_id in list(missed_updates.keys()):
                    missed_updates[neighbor_id] += 1
                    if missed_updates[neighbor_id] >= 3:
                        print(f"Neighbor {neighbor_id} considered unreachable. Marking link as failed.")
                        self.disable_link(neighbor_id)
                        missed_updates.pop(neighbor_id, None)

    def crash(self):
        """Simulate a crash and notify neighbors."""
        print("Simulating crash: disabling all connections.")
        with self.lock:
            self.running = False
            for neighbor_id in list(self.neighbors.keys()):
                self.disable_link(neighbor_id)

    def handle_commands(self):
        """Handle user input commands."""
        while self.running:
            command = input("Enter command: ").strip().lower()
            if command == "display":
                self.display_routing_table()
            elif command == "packets":
                print(f"Packets received: {self.packet_counter}")
                self.packet_counter = 0  # Reset counter
            elif command == "crash":
                self.crash()
            elif command.startswith("disable"):
                _, server_id = command.split()
                self.disable_link(int(server_id))
            elif command.startswith("update"):
                try:
                    _, server1, server2, cost = command.split()
                    self.update_link(int(server1), int(server2), int(cost))
                except ValueError:
                    print("Invalid input. Use: update <server1_id> <server2_id> <cost>")
            else:
                print("Invalid command.")

    def update_link(self, server1, server2, cost):
        """Update the cost of a link between two servers."""
        with self.lock:
            if self.my_id in [server1, server2]:
                neighbor_id = server2 if server1 == self.my_id else server1
                if neighbor_id in self.neighbors:
                    self.routing_table[neighbor_id] = cost
                    self.next_hop[neighbor_id] = neighbor_id
                    print(f"Updated link cost to server {neighbor_id} to {cost}.")
                    self.send_updates()
                else:
                    print("Can only update cost to direct neighbors.")
            else:
                print("This server is not involved in the specified link.")

    def monitor_and_command(self):
        """Start monitoring neighbors and accept commands."""
        threading.Thread(target=self.monitor_neighbors, daemon=True).start()
        self.handle_commands()


if __name__ == "__main__":
    command = input("server -t <topology-file> -i <update-interval>: ").strip().split()
    if len(command) == 5 and command[0] == "server" and command[1] == "-t" and command[3] == "-i":
        topology_file = command[2]
        update_interval = int(command[4])
        router = Router(topology_file, update_interval)
        router.handle_commands()