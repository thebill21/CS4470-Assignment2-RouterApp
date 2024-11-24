import socket
import threading
import time
import json
from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
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

    def to_dict(self):
        return {"id": self.id, "ip": self.ip, "port": self.port}


class DistanceVector:
    def __init__(self):
        self.time_interval = 0
        self.my_ip = self.get_my_ip()
        self.my_id = float("inf")
        self.my_node = None
        self.nodes = []
        self.routing_table = {}
        self.neighbors = set()
        self.open_channels = []
        self.selector = DefaultSelector()
        self.next_hop = {}
        self.number_of_packets_received = 0
        self.running = True

    @staticmethod
    def get_my_ip():
        """Retrieve the current machine's IP address."""
        return socket.gethostbyname(socket.gethostname())

    def main(self):
        print("\n********* Distance Vector Routing Protocol **********")
        print("Help Menu")
        print("--> Commands you can use")
        print("1. server <topology-file> -i <time-interval-in-seconds>")
        print("2. update <server-id1> <server-id2> <new-cost>")
        print("3. step")
        print("4. display")
        print("5. disable <server-id>")
        print("6. crash")

        while self.running:
            command = input("Enter command: ").strip().split()
            if not command:
                continue
            try:
                if command[0] == "server" and len(command) == 4:
                    self.start_server(command[1], int(command[3]))
                elif command[0] == "update" and len(command) == 4:
                    self.update_link(int(command[1]), int(command[2]), int(command[3]))
                elif command[0] == "step":
                    self.send_updates()
                elif command[0] == "display":
                    self.display_routing_table()
                elif command[0] == "disable" and len(command) == 2:
                    self.disable_link(int(command[1]))
                elif command[0] == "crash":
                    self.crash()
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")

    def start_server(self, topology_file, interval):
        if interval < 15:
            print("Please input routing update interval above 15 seconds.")
            return
        self.time_interval = interval
        self.load_topology(topology_file)
        threading.Thread(target=self.periodic_updates, daemon=True).start()
        print("Server started with periodic updates.")

    def load_topology(self, filename):
        try:
            with open(filename, 'r') as f:
                lines = f.read().strip().split('\n')
            num_servers = int(lines[0])
            num_neighbors = int(lines[1])

            for i in range(2, 2 + num_servers):
                parts = lines[i].split()
                node = Node(int(parts[0]), parts[1], int(parts[2]))
                self.nodes.append(node)
                self.routing_table[node] = float("inf")
                if node.ip == self.my_ip:
                    self.my_id = node.id
                    self.my_node = node
                    self.routing_table[node] = 0
                    self.next_hop[node] = node

            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                parts = lines[i].split()
                from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
                if from_id == self.my_id:
                    neighbor = self.get_node_by_id(to_id)
                    self.neighbors.add(neighbor)
                    self.routing_table[neighbor] = cost
                    self.next_hop[neighbor] = neighbor

            print("Topology loaded successfully.")
        except Exception as e:
            print(f"Error loading topology: {e}")

    def periodic_updates(self):
        while self.running:
            time.sleep(self.time_interval)
            self.send_updates()

    def send_updates(self):
        if self.neighbors:
            for neighbor in self.neighbors:
                message = self.create_routing_message()
                self.send_message(neighbor, message)
                print(f"Message sent to {neighbor.ip}.")
        else:
            print("No neighbors to send updates to.")

    def create_routing_message(self):
        return json.dumps(
            {node.id: {"cost": cost, "next_hop": self.next_hop.get(node).id if self.next_hop.get(node) else None}
             for node, cost in self.routing_table.items()})

    def send_message(self, neighbor, message):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbor.ip, neighbor.port))
                s.sendall(message.encode())
        except Exception as e:
            print(f"Error sending message to {neighbor.ip}: {e}")

    def update_link(self, server_id1, server_id2, cost):
        if self.my_id in {server_id1, server_id2}:
            target_id = server_id2 if server_id1 == self.my_id else server_id1
            target_node = self.get_node_by_id(target_id)
            if target_node in self.neighbors:
                self.routing_table[target_node] = cost
                print(f"Updated link cost to {target_id} as {cost}.")
                self.send_updates()
            else:
                print("Can only update cost to neighbors.")
        else:
            print("This server is not involved in the link.")

    def display_routing_table(self):
        print("Destination\tNext Hop\tCost")
        for node in sorted(self.routing_table, key=lambda n: n.id):
            cost = self.routing_table[node]
            next_hop = self.next_hop.get(node)
            next_hop_id = next_hop.id if next_hop else "None"
            cost_str = "infinity" if cost == float("inf") else cost
            print(f"{node.id}\t\t{next_hop_id}\t\t{cost_str}")

    def disable_link(self, server_id):
        target_node = self.get_node_by_id(server_id)
        if target_node in self.neighbors:
            self.neighbors.remove(target_node)
            self.routing_table[target_node] = float("inf")
            self.next_hop[target_node] = None
            print(f"Disabled connection with server {server_id}.")
        else:
            print("Cannot disable a non-neighbor link.")

    def crash(self):
        self.running = False
        for neighbor in list(self.neighbors):
            self.disable_link(neighbor.id)
        print("Server crashed.")

    def get_node_by_id(self, node_id):
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None


if __name__ == "__main__":
    dv = DistanceVector()
    dv.main()