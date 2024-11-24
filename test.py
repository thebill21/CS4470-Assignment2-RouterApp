import socket
import threading
import time
import json
import sys


class Router:
    HEARTBEAT_THRESHOLD = 3  # Number of missed updates before marking a neighbor as unreachable

    def __init__(self, server_id, update_interval, topology_file):
        self.server_id = server_id
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}
        self.open_channels = {}
        self.packet_counter = 0
        self.running = True
        self.missed_updates = {}  # Initialize missed updates dictionary
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.load_topology(topology_file)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(5)
        self.last_update_time = time.time()  # Initialize the last update timestamp

    def load_topology(self, topology_file):
        """Load and initialize routing table and neighbors from topology file."""
        with open(topology_file, 'r') as f:
            lines = [line.split('#')[0].strip() for line in f if line.strip()]
            num_servers = int(lines[0])
            num_neighbors = int(lines[1])

            # Initialize self in routing table
            self.routing_table[self.server_id] = {'next_hop': self.server_id, 'cost': 0.0}

            # Process server details and assign self IP/Port
            for i in range(2, 2 + num_servers):
                sid, sip, sport = lines[i].split()
                sid, sport = int(sid), int(sport)
                if sid == self.server_id:
                    self.ip = sip
                    self.port = sport
                else:
                    self.routing_table[sid] = {'next_hop': sid, 'cost': float('inf')}

            # Process neighbors
            for i in range(2 + num_servers, 2 + num_servers + num_neighbors):
                sid1, sid2, cost = map(int, lines[i].split())
                if sid1 == self.server_id:
                    neighbor_ip, neighbor_port = None, None
                    for line in lines[2:2 + num_servers]:
                        sid, sip, sport = line.split()
                        if int(sid) == sid2:
                            neighbor_ip, neighbor_port = sip, int(sport)
                            break
                    if neighbor_ip and neighbor_port:
                        self.neighbors[sid2] = {'cost': cost, 'ip': neighbor_ip, 'port': neighbor_port}
                        self.routing_table[sid2] = {'next_hop': sid2, 'cost': cost}
                        self.missed_updates[sid2] = 0  # Initialize missed updates counter

            print(f"Server {self.server_id} neighbors: {self.neighbors}")
            print(f"Server {self.server_id} routing table: {self.routing_table}")
            print(f"Server {self.server_id} IP: {self.ip}, Port: {self.port}")

        # Establish TCP connections to neighbors
        self.connect_to_neighbors()

    def connect_to_neighbors(self):
        """Establish TCP connections to neighbors."""
        for neighbor_id, neighbor_info in self.neighbors.items():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((neighbor_info['ip'], neighbor_info['port']))
                self.open_channels[neighbor_id] = s
                print(f"Connected to neighbor {neighbor_id} at {neighbor_info['ip']}:{neighbor_info['port']}")
            except Exception as e:
                print(f"Failed to connect to neighbor {neighbor_id}: {e}")

    def listen_for_updates(self):
        """Listen for incoming updates from neighbors."""
        while self.running:
            try:
                client_sock, _ = self.sock.accept()
                threading.Thread(target=self.handle_incoming_message, args=(client_sock,), daemon=True).start()
            except Exception as e:
                if not self.running:
                    break
                print(f"Error in listen_for_updates: {e}")

    def handle_incoming_message(self, client_sock):
        """Handle an incoming message from a neighbor."""
        try:
            data = client_sock.recv(1024)
            if data:
                self.process_update_message(data.decode())
                self.packet_counter += 1
        except Exception as e:
            print(f"Error processing incoming message: {e}")
        finally:
            client_sock.close()

    def send_update(self, force=False):
        """Send distance vector updates to all neighbors."""
        if not force and time.time() - self.last_update_time < self.update_interval:
            return  # Throttle updates based on update_interval

        update_message = self.create_update_message()
        for neighbor_id, channel in self.open_channels.items():
            try:
                channel.sendall(update_message.encode())
                print(f"Sent update to Server {neighbor_id}")
            except Exception as e:
                print(f"Failed to send update to Server {neighbor_id}: {e}")

        self.last_update_time = time.time()  # Update the last update timestamp

    def create_update_message(self):
        """Create a message to send the routing table to neighbors."""
        message = {"server_id": self.server_id, "routing_table": self.routing_table}
        return json.dumps(message)

    def process_update_message(self, message):
        """Process incoming routing table updates."""
        try:
            data = json.loads(message)
            sender_id = data.get("server_id")
            received_table = data.get("routing_table")
            updated = False

            for dest_id, route_info in received_table.items():
                current_cost = self.routing_table.get(dest_id, {}).get("cost", float("inf"))
                new_cost = route_info["cost"] + self.neighbors[sender_id]["cost"]

                if new_cost < current_cost:
                    self.routing_table[dest_id] = {"next_hop": sender_id, "cost": new_cost}
                    updated = True

            if updated:
                print("Routing table updated:")
                self.display()
                self.send_update(force=True)
        except Exception as e:
            print(f"Failed to process update message: {e}")

    def disable(self, neighbor_id):
        """Disable the link to a given neighbor."""
        if neighbor_id in self.neighbors:
            # Remove the neighbor from neighbors list
            self.neighbors.pop(neighbor_id)
            # Mark the routing table entry as infinite cost
            if neighbor_id in self.routing_table:
                self.routing_table[neighbor_id]['cost'] = float('inf')
                self.routing_table[neighbor_id]['next_hop'] = None
            # Close the connection if it exists
            if neighbor_id in self.open_channels:
                try:
                    self.open_channels[neighbor_id].close()
                except Exception as e:
                    print(f"Failed to close connection with neighbor {neighbor_id}: {e}")
                del self.open_channels[neighbor_id]
            print(f"Disabled connection with neighbor {neighbor_id}.")
        else:
            print(f"Cannot disable non-existent neighbor {neighbor_id}.")

    def crash(self):
        """Simulate a server crash by disabling all connections."""
        self.running = False
        for channel in self.open_channels.values():
            try:
                channel.close()
            except Exception as e:
                print(f"Error closing channel: {e}")
        self.open_channels.clear()
        print("Server crashed. All connections closed.")

    def display(self):
        """Display the current routing table."""
        print("Routing Table:")
        for dest_id, route_info in self.routing_table.items():
            next_hop = route_info['next_hop']
            cost = route_info['cost']
            print(f"Destination: {dest_id}, Next Hop: {next_hop}, Cost: {cost}")

    def run(self):
        """Start server."""
        threading.Thread(target=self.listen_for_updates, daemon=True).start()
        self.handle_commands()

    def handle_commands(self):
        """Handle user commands."""
        while self.running:
            try:
                print("\n********* Distance Vector Routing Protocol **********")
                print("Help Menu")
                print("--> Commands you can use")
                print("1. server <topology-file> -i <time-interval-in-seconds>")
                print("2. update <server-id1> <server-id2> <new-cost>")
                print("3. step")
                print("4. display")
                print("5. disable <server-id>")
                print("6. crash")
                command = input("Enter command: ").strip().split()
                if not command:
                    continue

                cmd = command[0].lower()
                if cmd == "display":
                    self.display()
                elif cmd == "disable" and len(command) == 2:
                    self.disable(int(command[1]))
                elif cmd == "step":
                    self.send_update(force=True)
                elif cmd == "crash":
                    self.crash()
                    break
                else:
                    print("Invalid command")
            except KeyboardInterrupt:
                print("Exiting program")
                self.running = False


def main():
    if len(sys.argv) != 4:
        print("Usage: python3 RouterServer.py <server-ID> <routing-update-interval> <topology-file>")
        sys.exit(1)

    server_id = int(sys.argv[1])
    update_interval = int(sys.argv[2])
    topology_file = sys.argv[3]

    router = Router(server_id, update_interval, topology_file)
    router.run()


if __name__ == "__main__":
    main()