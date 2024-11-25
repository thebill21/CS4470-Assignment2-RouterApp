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
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = set()
        self.next_hop = {}
        self.number_of_packets_received = 0
        self.running = True
        self.lock = threading.Lock()

        # Load the topology
        self.load_topology()

    def get_my_ip(self):
        """Gets the current machine's IP address."""
        return socket.gethostbyname(socket.gethostname())

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
                self.routing_table[node] = float('inf')
                if parts[1] == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node] = 0
                    self.next_hop[node] = node

            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
                if from_id == self.my_id:
                    neighbor_node = self.get_node_by_id(to_id)
                    self.routing_table[neighbor_node] = cost
                    self.neighbors.add(neighbor_node)
                    self.next_hop[neighbor_node] = neighbor_node
                elif to_id == self.my_id:
                    neighbor_node = self.get_node_by_id(from_id)
                    self.routing_table[neighbor_node] = cost
                    self.neighbors.add(neighbor_node)
                    self.next_hop[neighbor_node] = neighbor_node

            print("Topology loaded successfully.")
        except Exception as e:
            print(f"Error reading topology file: {e}")
            exit(1)

    def get_node_by_id(self, node_id):
        """Fetches a node by its ID."""
        for node in self.routing_table.keys():
            if node.id == node_id:
                return node
        return None

    def update(self, server_id1, server_id2, cost):
        """Updates the link cost between two servers."""
        with self.lock:
            if server_id1 == self.my_id or server_id2 == self.my_id:
                target_id = server_id2 if server_id1 == self.my_id else server_id1
                target_node = self.get_node_by_id(target_id)
                if target_node in self.neighbors:
                    self.routing_table[target_node] = cost
                    print(f"Updated cost to {target_id} to {cost}")
                    self.step()
                else:
                    print("Can only update the cost to neighbors.")
            else:
                print("This server is not involved in the specified link.")

    def step(self):
        """Sends a routing update to all neighbors."""
        with self.lock:
            if self.neighbors:
                message = self.make_message()
                for neighbor in self.neighbors:
                    self.send_message(neighbor, message)
                print("Step completed.")
            else:
                print("No neighbors to send updates to.")

    def make_message(self):
        """Creates a routing table message."""
        message = {node.id: cost for node, cost in self.routing_table.items()}
        return json.dumps(message)

    def send_message(self, neighbor, message, retries=3):
        """Sends a message to a neighbor with retries."""
        attempt = 0
        while attempt < retries:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((neighbor.ip, neighbor.port))
                    s.sendall(message.encode())
                    print(f"Message successfully sent to {neighbor.ip}.")
                    return
            except Exception as e:
                attempt += 1
                print(f"Attempt {attempt}: Error sending message to {neighbor.ip}: {e}")
                time.sleep(1)
        print(f"Failed to send message to {neighbor.ip} after {retries} attempts.")

    def display_routing_table(self):
        """Displays the routing table with better formatting."""
        print(f"{'Destination':<15}{'Next Hop':<15}{'Cost':<10}")
        print("-" * 40)
        for node in sorted(self.routing_table.keys(), key=lambda n: n.id):
            cost = self.routing_table[node]
            next_hop_node = self.next_hop.get(node)
            next_hop_id = next_hop_node.id if next_hop_node else "None"
            cost_str = "infinity" if cost == float("inf") else cost
            print(f"{node.id:<15}{next_hop_id:<15}{cost_str:<10}")

    def disable(self, server_id):
        """Disables a link to a specific neighbor."""
        with self.lock:
            target_node = self.get_node_by_id(server_id)
            if target_node in self.neighbors:
                self.neighbors.remove(target_node)
                self.routing_table[target_node] = float('inf')
                self.next_hop[target_node] = None
                print(f"Disabled connection with server {server_id}.")
            else:
                print("Cannot disable a non-neighbor link.")

    def crash(self):
        """Simulates a server crash by disabling all links."""
        with self.lock:
            for neighbor in list(self.neighbors):
                self.disable(neighbor.id)
            self.running = False
            print("Server crashed.")

    def periodic_updates(self):
        """Sends periodic updates to neighbors."""
        while self.running:
            time.sleep(self.update_interval)
            self.step()

    def run(self):
        """Runs the router."""
        threading.Thread(target=self.periodic_updates, daemon=True).start()
        while self.running:
            command_line = input("Enter command: ").strip().split()
            if not command_line:
                continue

            command = command_line[0].lower()
            try:
                if command == "update" and len(command_line) == 4:
                    self.update(int(command_line[1]), int(command_line[2]), int(command_line[3]))
                elif command == "step":
                    self.step()
                elif command == "display":
                    self.display_routing_table()
                elif command == "disable" and len(command_line) == 2:
                    self.disable(int(command_line[1]))
                elif command == "crash":
                    self.crash()
                    break
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")


if __name__ == "__main__":
    print("********* Distance Vector Routing Protocol **********")
    print("Help Menu")
    print("--> Commands you can use")
    print("1. server <topology-file> -i <time-interval-in-seconds>")
    print("2. update <server-id1> <server-id2> <new-cost>")
    print("3. step")
    print("4. display")
    print("5. disable <server-id>")
    print("6. crash")
    
    topology_file = input("Enter topology file name: ")
    update_interval = int(input("Enter update interval in seconds: "))
    router = Router(topology_file, update_interval)
    router.run()