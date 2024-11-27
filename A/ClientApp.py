import sys
import os
import signal
import atexit
from router import Router


# Global variable to hold the router instance
router_instance = None


def shutdown(signal=None, frame=None):
    """
    Gracefully shutdown the router.
    """
    if router_instance:
        router_instance.running = False
        print("Router shutting down...")
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)


def main():
    """
    Main function to run the client application.
    """
    print("********* Distance Vector Routing Protocol **********")
    print("Type 'server -t <topology-file-name> -i <update-interval>' to start.")
    print("Type 'exit' to shut down the router.")

    global router_instance

    while True:
        # Wait for user input
        command_line = input("Enter command: ").strip().split()

        if not command_line:
            continue

        command = command_line[0].lower()

        # Exit command
        if command == "exit":
            shutdown()

        # Server initialization command
        elif command == "server":
            if len(command_line) == 5 and command_line[1] == "-t" and command_line[3] == "-i":
                topology_file = command_line[2]
                try:
                    update_interval = int(command_line[4])
                    if update_interval < 5:
                        print("Error: Update interval must be at least 5 seconds.")
                        continue

                    # Create and run the router
                    if router_instance:
                        print("Error: Router is already running.")
                    else:
                        router_instance = Router(topology_file, update_interval)
                        router_instance.run()

                except ValueError:
                    print("Error: Invalid update interval. Please enter a valid integer.")
            else:
                print("Error: Invalid command. Use the format: server -t <topology-file-name> -i <update-interval>")

        # If router is running, pass commands to it
        elif router_instance:
            try:
                if command == "display":
                    router_instance.display_routing_table()
                elif command == "step":
                    router_instance.step()
                elif command.startswith("update") and len(command_line) == 4:
                    server1_id = int(command_line[1])
                    server2_id = int(command_line[2])
                    new_cost = float(command_line[3])
                    router_instance.update(server1_id, server2_id, new_cost)
                elif command == "packets":
                    router_instance.display_packets()
                else:
                    print("Invalid command.")
            except Exception as e:
                print(f"Error processing command: {e}")

        else:
            print("Error: Router is not running. Use 'server -t <topology-file-name> -i <update-interval>' to start.")


if __name__ == "__main__":
    atexit.register(shutdown)
    main()