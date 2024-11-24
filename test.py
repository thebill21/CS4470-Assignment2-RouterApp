import socket
import selectors
import threading
import time
import json
import sys
from collections import defaultdict
from threading import Lock

# Globals
time_interval = 0
open_channels = []
my_ip = ""
my_id = float('inf')
my_node = None
nodes = []
routing_table = {}
neighbors = set()
number_of_packets_received = 0
next_hop = {}
read_selector = selectors.DefaultSelector()
write_selector = selectors.DefaultSelector()
neighbors_lock = Lock()


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


def get_my_ip():
    """Get the current machine's IP address."""
    return socket.gethostbyname(socket.gethostname())


def main():
    global my_ip, time_interval
    my_ip = get_my_ip()

    # Main loop to process commands
    while True:
        print("\n*********Distance Vector Routing Protocol**********")
        print("Help Menu")
        print("--> Commands you can use")
        print("1. server <topology-file> -i <time-interval-in-seconds>")
        print("2. update <server-id1> <server-id2> <new-cost>")
        print("3. step")
        print("4. display")
        print("5. disable <server-id>")
        print("6. crash")
        command_line = input("Enter command: ").strip().split()

        if not command_line:
            continue

        command = command_line[0]

        try:
            if command == "server" and len(command_line) == 4:
                # Initialize the server
                topology_file = command_line[1]
                time_interval = int(command_line[3])
                if time_interval < 15:
                    print("Please input routing update interval above 15 seconds.")
                    continue

                read_topology(topology_file)
                threading.Thread(target=periodic_updates, daemon=True).start()
                print("Server started with periodic updates.")

            elif command == "update" and len(command_line) == 4:
                update(int(command_line[1]), int(command_line[2]), int(command_line[3]))

            elif command == "step":
                step()

            elif command == "packets":
                print(f"Number of packets received: {number_of_packets_received}")

            elif command == "display":
                display()

            elif command == "disable" and len(command_line) == 2:
                disable(int(command_line[1]))

            elif command == "crash":
                crash()
                break

            else:
                print("Invalid command.")
        except Exception as e:
            print(f"Error processing command: {e}")


def periodic_updates():
    """Sends periodic updates to neighbors."""
    while True:
        time.sleep(time_interval)
        step()


def read_topology(filename):
    """Reads the topology file and initializes routing tables."""
    global my_id, my_node, my_ip, routing_table, next_hop, neighbors

    try:
        with open(filename, 'r') as f:
            lines = f.read().strip().split('\n')
        num_servers = int(lines[0])
        num_neighbors = int(lines[1])

        for i in range(2, 2 + num_servers):
            parts = lines[i].split()
            node = Node(int(parts[0]), parts[1], int(parts[2]))
            nodes.append(node)
            cost = float('inf')
            if parts[1] == my_ip:
                my_id = node.id
                my_node = node
                cost = 0
                next_hop[node] = node
            else:
                next_hop[node] = None
            routing_table[node] = cost

        for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
            parts = lines[i].split()
            from_id, to_id, cost = int(parts[0]), int(parts[1]), int(parts[2])
            if from_id == my_id:
                neighbor_node = get_node_by_id(to_id)
                routing_table[neighbor_node] = cost
                neighbors.add(neighbor_node)
                next_hop[neighbor_node] = neighbor_node
            elif to_id == my_id:
                neighbor_node = get_node_by_id(from_id)
                routing_table[neighbor_node] = cost
                neighbors.add(neighbor_node)
                next_hop[neighbor_node] = neighbor_node

        print("Topology file read successfully.")
    except Exception as e:
        print(f"Error reading topology file: {e}")
        sys.exit(1)


def get_node_by_id(node_id):
    """Fetches a node by its ID."""
    for node in nodes:
        if node.id == node_id:
            return node
    return None


def update(server_id1, server_id2, cost):
    """Updates the link cost between two servers."""
    with neighbors_lock:
        if server_id1 == my_id or server_id2 == my_id:
            target_id = server_id2 if server_id1 == my_id else server_id1
            target_node = get_node_by_id(target_id)
            if target_node in neighbors:
                routing_table[target_node] = cost
                print(f"Updated cost to {target_id} to {cost}")
                step()
            else:
                print("Can only update the cost to neighbors.")
        else:
            print("This server is not involved in the specified link.")


def step():
    """Sends a routing update to all neighbors."""
    with neighbors_lock:
        if neighbors:
            message = make_message()
            for neighbor in neighbors:
                send_message(neighbor, message)
                print(f"Message sent to {neighbor.ip}.")
            print("Step completed.")
        else:
            print("No neighbors to send updates to.")


def make_message():
    """Creates a routing table message."""
    message = {node.id: cost for node, cost in routing_table.items()}
    return json.dumps(message)


def send_message(neighbor, message):
    """Sends a message to a neighbor."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((neighbor.ip, neighbor.port))
            s.sendall(message.encode())
    except Exception as e:
        print(f"Error sending message to {neighbor.ip}: {e}")


def process_message(message):
    """Processes incoming routing updates."""
    global routing_table, next_hop
    try:
        received_table = json.loads(message)
        updated = False
        for node_id, cost in received_table.items():
            target_node = get_node_by_id(node_id)
            if target_node and cost < routing_table.get(target_node, float('inf')):
                routing_table[target_node] = cost
                next_hop[target_node] = target_node
                updated = True
        if updated:
            print("Routing table updated.")
    except Exception as e:
        print(f"Error processing message: {e}")


def display():
    """Displays the routing table."""
    print("Destination\tNext Hop\tCost")
    for node in sorted(routing_table, key=lambda n: n.id):
        cost = routing_table[node]
        next_hop_node = next_hop.get(node)
        next_hop_id = next_hop_node.id if next_hop_node else "None"
        cost_str = "infinity" if cost == float('inf') else cost
        print(f"{node.id}\t\t{next_hop_id}\t\t{cost_str}")


def disable(server_id):
    """Disables a link to a specific neighbor."""
    with neighbors_lock:
        target_node = get_node_by_id(server_id)
        if target_node in neighbors:
            neighbors.remove(target_node)
            routing_table[target_node] = float('inf')
            next_hop[target_node] = None
            print(f"Disabled connection with server {server_id}.")
        else:
            print("Cannot disable a non-neighbor link.")


def crash():
    """Simulates a server crash by disabling all links."""
    with neighbors_lock:
        for neighbor in list(neighbors):
            disable(neighbor.id)
        print("Server crashed.")


if __name__ == "__main__":
    main()