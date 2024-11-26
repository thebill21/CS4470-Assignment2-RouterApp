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

    def load_topology(self):
        with open(self.topology_file, 'r') as file:
            lines = file.readlines()
        
        num_servers = int(lines[0].strip())
        num_neighbors = int(lines[1].strip())

        # Load nodes
        for i in range(2, 2 + num_servers):
            node_info = lines[i].strip().split()
            node_id, ip, port = int(node_info[0]), node_info[1], int(node_info[2])
            self.nodes.append({"id": node_id, "ip": ip, "port": port})
            if ip == socket.gethostbyname(socket.gethostname()):  # Detect self
                self.my_id = node_id
                self.my_node = {"id": node_id, "ip": ip, "port": port}

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

    def handle_commands(self):
        while self.running:
            command = input("Enter command: ").strip().lower()
            if command == "display":
                self.display_routing_table()
            elif command == "packets":
                print(f"Packets received: {self.packet_counter}")
                self.packet_counter = 0
            elif command == "crash":
                self.running = False
            elif command.startswith("update"):
                _, server1, server2, new_cost = command.split()
                self.update_link(int(server1), int(server2), int(new_cost))
            else:
                print("Invalid command.")

    def update_link(self, server1, server2, cost):
        if self.my_id in [server1, server2]:
            neighbor_id = server2 if server1 == self.my_id else server1
            if neighbor_id in self.neighbors:
                self.routing_table[neighbor_id] = cost
                self.next_hop[neighbor_id] = neighbor_id
                self.send_updates()
            else:
                print("Can only update cost to direct neighbors.")
        else:
            print("This server is not involved in the link update.")


if __name__ == "__main__":
    command = input("server -t <topology-file> -i <update-interval>: ").strip().split()
    if len(command) == 5 and command[0] == "server" and command[1] == "-t" and command[3] == "-i":
        topology_file = command[2]
        update_interval = int(command[4])
        router = Router(topology_file, update_interval)
        router.handle_commands()