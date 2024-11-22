def process_update_message(self, message):
    """ Process incoming routing table updates """
    print(f"Processing update message: {message}")
    parts = message.split()
    num_entries = int(parts[0])
    sender_port = int(parts[1])
    sender_ip = parts[2]

    updated = False
    for i in range(num_entries):
        idx = 3 + i * 3
        dest_id = int(parts[idx])
        next_hop = int(parts[idx + 1])
        cost = float(parts[idx + 2])

        # Direct neighbor updates always take precedence
        if dest_id in self.neighbors and next_hop == self.server_id:
            if self.routing_table[dest_id]['cost'] != cost:
                self.routing_table[dest_id] = {'next_hop': dest_id, 'cost': cost}
                updated = True
        # Update routing table if the new cost is lower (indirect routes)
        elif dest_id not in self.routing_table or cost < self.routing_table[dest_id]['cost']:
            self.routing_table[dest_id] = {'next_hop': next_hop, 'cost': cost}
            updated = True

    if updated:
        print(f"Updated routing table: {self.routing_table}")
        self.send_update()