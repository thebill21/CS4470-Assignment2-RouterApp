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
        self.my_ip = self.get_local_ip()
        self.my_id = None
        self.my_node = None
        self.nodes = []
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}
        self.next_hop = {}
        self.running = True
        self.lock = threading.Lock()
        self.packet_count = 0

        self.load_topology()
        self.start_listening()
        self.start_periodic_updates()

    def get_local_ip(self):
        """Get the machine's network-facing IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception as e:
            print(f"Error determining local IP: {e}")
            return "127.0.0.1"

    def load_topology(self):
        """Reads the topology file and initializes routing tables."""
        try:
            with open(self.topology_file, 'r') as f:
                lines = f.readlines()

            num_servers = int(lines[0].strip())
            num_neighbors = int(lines[1].strip())

            # Parse nodes
            for i in range(2, 2 + num_servers):
                node_info = lines[i].strip().split()
                node = Node(int(node_info[0]), node_info[1], int(node_info[2]))
                self.nodes.append(node)
                if node.ip == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node.id] = 0
                    self.next_hop[node.id] = node.id
                else:
                    self.routing_table[node.id] = float('inf')
                    self.next_hop[node.id] = None

            if not self.my_node:
                raise ValueError(f"Local IP {self.my_ip} not found in topology file.")

            # Parse neighbors
            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                link_info = lines[i].strip().split()
                from_id, to_id, cost = int(link_info[0]), int(link_info[1]), int(link_info[2])
                if from_id == self.my_id:
                    self.neighbors[to_id] = cost
                    self.routing_table[to_id] = cost
                    self.next_hop[to_id] = to_id
                elif to_id == self.my_id:
                    self.neighbors[from_id] = cost
                    self.routing_table[from_id] = cost
                    self.next_hop[from_id] = from_id

        except Exception as e:
            print(f"Error loading topology: {e}")
            raise

    def start_listening(self):
        """Start a server socket to listen for incoming connections."""
        def listen():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.bind((self.my_ip, self.my_node.port))
                server_socket.listen(5)
                print(f"Listening on {self.my_ip}:{self.my_node.port}")
                while self.running:
                    client_socket, _ = server_socket.accept()
                    threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()

        threading.Thread(target=listen, daemon=True).start()

    def handle_client(self, client_socket):
        """Handle incoming messages from neighbors."""
        try:
            message = client_socket.recv(1024).decode()
            if not message.strip():
                return
            self.process_message(json.loads(message))
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def process_message(self, message):
        """Process received routing table updates."""
        sender_id = message["id"]
        sender_table = message["routing_table"]

        updated = False
        with self.lock:
            for dest_id, cost_to_dest in sender_table.items():
                if dest_id == self.my_id:
                    continue
                new_cost = self.routing_table[sender_id] + cost_to_dest
                if new_cost < self.routing_table.get(dest_id, float('inf')):
                    self.routing_table[dest_id] = new_cost
                    self.next_hop[dest_id] = sender_id
                    updated = True

        if updated:
            self.send_updates()

    def send_updates(self):
        """Send routing table updates to neighbors."""
        message = {
            "id": self.my_id,
            "routing_table": self.routing_table
        }
        for neighbor_id in self.neighbors:
            neighbor = next(node for node in self.nodes if node.id == neighbor_id)
            self.send_message(neighbor, message)

    def send_message(self, neighbor, message):
        """Send a message to a specific neighbor."""
        retries = 3
        while retries > 0:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor.ip, neighbor.port))
                    s.sendall(json.dumps(message).encode())
                    return
            except Exception as e:
                print(f"Error sending message to {neighbor.ip}:{neighbor.port}: {e}")
                retries -= 1
                time.sleep(1)
        print(f"Failed to send message to {neighbor.ip}:{neighbor.port} after retries.")

    def display_routing_table(self):
        """Display the current routing table."""
        print("\nRouting Table:")
        print("Destination\tNext Hop\tCost")
        for dest_id in sorted(map(int, self.routing_table.keys())):  # Ensure keys are sorted as integers
            cost = self.routing_table[dest_id]
            next_hop = self.next_hop.get(dest_id, "None")
            print(f"{dest_id}\t\t{next_hop}\t\t{cost if cost != float('inf') else 'Infinity'}")

    def run(self):
        """Main loop to process commands."""
        while self.running:
            command = input("Enter command: ").strip().lower()
            if command == "display":
                self.display_routing_table()
            elif command == "crash":
                self.running = False
                print("Router crashed.")
            elif command == "packets":
                print(f"Packets received: {self.packet_count}")
                self.packet_count = 0
            elif command.startswith("update"):
                _, server1, server2, cost = command.split()
                self.update_link(int(server1), int(server2), int(cost))
            elif command.startswith("disable"):
                _, server_id = command.split()
                self.disable_link(int(server_id))
            else:
                print("Invalid command.")

    def update_link(self, server1, server2, cost):
        """Update the cost of a link between two nodes."""
        if server1 == self.my_id or server2 == self.my_id:
            target_id = server2 if server1 == self.my_id else server1
            if target_id in self.neighbors:
                self.routing_table[target_id] = cost
                self.next_hop[target_id] = target_id
                self.send_updates()
            else:
                print("Can only update costs to direct neighbors.")

    def disable_link(self, server_id):
        """Disable a link to a neighbor."""
        if server_id in self.neighbors:
            self.routing_table[server_id] = float('inf')
            self.next_hop[server_id] = None
            self.send_updates()
        else:
            print(f"Server {server_id} is not a direct neighbor.")

    def start_periodic_updates(self):
        """Send periodic updates."""
        def periodic_updates():
            while self.running:
                time.sleep(self.update_interval)
                self.send_updates()

        threading.Thread(target=periodic_updates, daemon=True).start()


if __name__ == "__main__":
    command = input("server -t <topology-file> -i <update-interval>: ").strip().split()
    if len(command) == 5 and command[0] == "server" and command[1] == "-t" and command[3] == "-i":
        topology_file = command[2]
        update_interval = int(command[4])
        router = Router(topology_file, update_interval)
        router.run()
    else:
        print("Invalid command format. Use: server -t <topology-file> -i <update-interval>")