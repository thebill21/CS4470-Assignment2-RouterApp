import socket
import threading
import time
import sys

class Router:
    # Remember to change your topology file for each server
    def __init__(self, server_id, update_interval, topology_file="server1_init.txt"):
        self.server_id = server_id
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}
        self.load_topology(topology_file)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))
        
    def load_topology(self, topology_file):
        """ Load and initialize routing table and neighbors from topology file """
        with open(topology_file, 'r') as f:
            lines = f.readlines()
            num_servers = int(lines[0].strip())
            num_neighbors = int(lines[1].strip())
            
            # Process each server's ID, IP, and port
            for i in range(2, 2 + num_servers):
                line = lines[i].strip().split()
                sid, sip, sport = int(line[0]), line[1], int(line[2])
                if sid == self.server_id:
                    self.ip, self.port = sip, sport
                else:
                    self.routing_table[sid] = {'next_hop': sid, 'cost': float('inf')}
            
            # Process neighbors
            for i in range(2 + num_servers, 2 + num_neighbors):
                line = lines[i].strip().split()
                sid1, sid2, cost = int(line[0]), int(line[1]), int(line[2])
                if sid1 == self.server_id:
                    self.neighbors[sid2] = {'cost': cost}
                    self.routing_table[sid2] = {'next_hop': sid2, 'cost': cost}

    def send_update(self):
        """ Send distance vector updates to all neighbors """
        update_message = self.create_update_message()
        for neighbor_id in self.neighbors:
            neighbor_ip, neighbor_port = self.get_neighbor_address(neighbor_id)
            self.sock.sendto(update_message.encode(), (neighbor_ip, neighbor_port))
        print("Routing update sent.")

    def create_update_message(self):
        """ Create a message to send the routing table to neighbors """
        message = f"{len(self.routing_table)} {self.port} {self.ip} "
        for dest_id, data in self.routing_table.items():
            message += f"{dest_id} {data['next_hop']} {data['cost']} "
        return message

    def get_neighbor_address(self, neighbor_id):
        """ Returns the IP and port of a neighbor """
        neighbor = self.neighbors.get(neighbor_id)
        return neighbor['ip'], neighbor['port']

    def listen_for_updates(self):
        """ Listen for incoming updates from other routers """
        while True:
            data, addr = self.sock.recvfrom(1024)
            print(f"RECEIVED A MESSAGE FROM SERVER at {addr}")
            # Process incoming update here...
            # (This part will parse the update message and apply Bellman-Ford updates)

    def update_routing_table(self, neighbor_id, new_cost):
        """ Manually update link cost to a neighbor and adjust routing table """
        if neighbor_id in self.neighbors:
            self.neighbors[neighbor_id]['cost'] = new_cost
            self.routing_table[neighbor_id] = {'next_hop': neighbor_id, 'cost': new_cost}
            print(f"update {self.server_id} {neighbor_id} SUCCESS")
        else:
            print(f"update {self.server_id} {neighbor_id} FAILED: Not a neighbor")

    def run_periodic_updates(self):
        """ Periodically send routing updates based on the specified interval """
        while True:
            time.sleep(self.update_interval)
            self.send_update()

    def run(self):
        """ Start server: Listen for incoming updates and run periodic updates """
        threading.Thread(target=self.listen_for_updates).start()
        threading.Thread(target=self.run_periodic_updates).start()


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 dv.py <server-ID> <routing-update-interval>")
        sys.exit(1)

    server_id = int(sys.argv[1])  # Server ID provided as an argument
    update_interval = int(sys.argv[2])  # Update interval in seconds

    router = Router(server_id, update_interval)
    router.run()


if __name__ == "__main__":
    main()