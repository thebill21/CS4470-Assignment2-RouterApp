import socket
import threading
import time
import sys

class Router:
    def __init__(self, server_id, update_interval, topology_file):
        self.server_id = server_id
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}
        self.packet_counter = 0
        self.running = True
        self.load_topology(topology_file)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))

    def load_topology(self, topology_file):
        """ Load and initialize routing table and neighbors from topology file """
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

            # Debug output for initialization
            print(f"Server {self.server_id} neighbors: {self.neighbors}")
            print(f"Server {self.server_id} routing table: {self.routing_table}")
            print(f"Server {self.server_id} IP: {self.ip}, Port: {self.port}")

    def send_update(self):
        """ Send distance vector updates to all neighbors """
        update_message = self.create_update_message()
        for neighbor_id, neighbor_info in self.neighbors.items():
            neighbor_ip = neighbor_info['ip']
            neighbor_port = neighbor_info['port']
            self.sock.sendto(update_message.encode(), (neighbor_ip, neighbor_port))
            print(f"Sent update to Server {neighbor_id} at {neighbor_ip}:{neighbor_port}")
            print(f"Update content: {update_message}")

    def create_update_message(self):
        """ Create a message to send the routing table to neighbors """
        message = f"{len(self.routing_table)} {self.port} {self.ip} "
        for dest_id, data in self.routing_table.items():
            message += f"{dest_id} {data['next_hop']} {data['cost']} "
        return message

    def listen_for_updates(self):
        """ Listen for incoming updates from other routers """
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                print(f"RECEIVED A MESSAGE FROM SERVER {addr}")
                print(f"Message Content: {data.decode()}")
                self.process_update_message(data.decode())
                self.packet_counter += 1
            except socket.error as e:
                if not self.running:
                    break
                print(f"Socket error: {e}")

    def recalculate_routing_table(self):
        """ Recalculate the entire routing table using the current neighbors and their costs """
        print("Recalculating routing table...")
        # Reset all non-direct neighbor routes
        for dest_id in self.routing_table.keys():
            if dest_id != self.server_id and dest_id not in self.neighbors:
                self.routing_table[dest_id] = {'next_hop': None, 'cost': float('inf')}

        # Recalculate routes for all destinations
        for dest_id in self.routing_table.keys():
            if dest_id == self.server_id:
                continue  # Skip self

            best_cost = float('inf')
            best_hop = None

            for neighbor_id, neighbor_info in self.neighbors.items():
                if neighbor_id in self.routing_table:
                    neighbor_cost = neighbor_info['cost']
                    route_cost = self.routing_table[neighbor_id]['cost']
                    total_cost = neighbor_cost + route_cost

                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_hop = neighbor_id

            if best_cost < float('inf'):
                self.routing_table[dest_id] = {'next_hop': best_hop, 'cost': best_cost}

        print(f"Routing table recalculated: {self.routing_table}")

    def process_update_message(self, message):
        """ Process incoming routing table updates """
        print(f"Processing update message: {message}")
        parts = message.split()
        num_entries = int(parts[0])
        sender_port = int(parts[1])
        sender_ip = parts[2]

        # Identify the sender ID from the neighbors list
        sender_id = None
        for neighbor_id, info in self.neighbors.items():
            if info['ip'] == sender_ip and info['port'] == sender_port:
                sender_id = neighbor_id
                break

        if sender_id is None:
            print(f"Received message from unknown server: {sender_ip}:{sender_port}")
            return

        sender_cost = self.routing_table[sender_id]['cost']
        updated = False

        for i in range(num_entries):
            idx = 3 + i * 3
            dest_id = int(parts[idx])
            next_hop = int(parts[idx + 1])
            cost_from_sender = float(parts[idx + 2])

            if dest_id == sender_id:
                continue

            if dest_id == self.server_id:
                if self.routing_table[sender_id]['cost'] != cost_from_sender:
                    self.routing_table[sender_id] = {'next_hop': sender_id, 'cost': cost_from_sender}
                    updated = True
                continue

            new_cost = sender_cost + cost_from_sender
            if dest_id not in self.routing_table or new_cost < self.routing_table[dest_id]['cost']:
                self.routing_table[dest_id] = {'next_hop': sender_id, 'cost': new_cost}
                updated = True

        if updated:
            print(f"Updated routing table: {self.routing_table}")
            self.recalculate_routing_table()
            self.send_update()

    def update_routing_table(self, neighbor_id, new_cost):
        """ Update link cost to a neighbor and adjust routing table """
        if neighbor_id in self.neighbors:
            self.neighbors[neighbor_id]['cost'] = new_cost
            self.routing_table[neighbor_id] = {'next_hop': neighbor_id, 'cost': new_cost}
            self.recalculate_routing_table()
            self.send_update()
        else:
            print(f"update {self.server_id} {neighbor_id} FAILED: Not a neighbor")

    def step(self):
        """ Send immediate routing updates """
        self.send_update()
        print("step SUCCESS")

    def packets(self):
        """ Display and reset the number of received packets """
        print(f"packets: {self.packet_counter}")
        self.packet_counter = 0

    def display(self):
        """ Display the current routing table """
        print("Routing Table:")
        for dest_id in sorted(self.routing_table.keys()):
            route = self.routing_table[dest_id]
            print(f"{dest_id} {route['next_hop']} {route['cost']}")
        print("display SUCCESS")

    def disable(self, neighbor_id):
        """ Disable the link to a given neighbor """
        if neighbor_id in self.neighbors:
            self.neighbors[neighbor_id]['cost'] = float('inf')
            self.routing_table[neighbor_id]['cost'] = float('inf')
            self.recalculate_routing_table()
            print(f"disable {neighbor_id} SUCCESS")
        else:
            print(f"disable {neighbor_id} FAILED: Not a neighbor")

    def crash(self):
        """ Simulate a server crash by disabling all connections """
        for neighbor_id in self.neighbors:
            self.disable(neighbor_id)
        print("crash SUCCESS")

    def run_periodic_updates(self):
        """ Periodically send routing updates """
        while self.running:
            time.sleep(self.update_interval)
            self.send_update()

    def handle_commands(self):
        """ Continuously read user commands from the terminal """
        try:
            while self.running:
                command = input("Enter command: ").strip().split()
                if not command:
                    continue

                cmd = command[0].lower()
                if cmd == "update" and len(command) == 4:
                    self.update_routing_table(int(command[2]), int(command[3]))
                elif cmd == "step":
                    self.step()
                elif cmd == "packets":
                    self.packets()
                elif cmd == "display":
                    self.display()
                elif cmd == "disable" and len(command) == 2:
                    self.disable(int(command[1]))
                elif cmd == "crash":
                    self.crash()
                elif cmd == "exit":
                    self.running = False
                else:
                    print("Invalid command")
        except KeyboardInterrupt:
            print("\nCTRL+C pressed. Exiting program...")
            self.running = False

    def run(self):
        """ Start server """
        threading.Thread(target=self.listen_for_updates, daemon=True).start()
        threading.Thread(target=self.run_periodic_updates, daemon=True).start()
        self.handle_commands()


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