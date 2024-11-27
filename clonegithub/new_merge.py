#!/usr/bin/python
"""
Distance Vector Routing Protocol Implementation
Merged from router.py and ClientApp.py for single execution.
"""

import os
import sys
import time
import logging
import socket
import struct
import select
import signal
import argparse
from collections import namedtuple
from threading import Thread, Lock, Event
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


# Set logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s DISTANCE VECTOR ROUTING [%(levelname)s] %(message)s',)
log = logging.getLogger()

LOCK = Lock()  # Lock for synchronized access to 'RoutingTable'


class FileNotExistError(Exception):
    pass


class RouterError(Exception):
    pass


class Router:
    def __init__(self, routerName, routerIP="127.0.0.1", routerPort=8080,
                 timeout=15, www=os.path.join(os.getcwd(), "data", "scenario-1")):
        self.routerName = routerName
        self.routerIP = routerIP
        self.routerPort = routerPort
        self.timeout = timeout
        self.www = www

    def open(self):
        try:
            self.routerSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.routerSocket.bind((self.routerIP, self.routerPort))
            self.routerSocket.setblocking(0)
        except Exception as e:
            log.error("Could not create UDP socket!")
            log.debug(e)
            raise RouterError(f"Creating UDP socket {self.routerIP}:{self.routerPort} failed!")

    def start(self, routerInformation):
        log.info("Running Distance Vector Routing at router: %s", self.routerName)
        self.open()

        routerInformation = os.path.join(self.www, routerInformation)
        if not os.path.exists(routerInformation):
            raise FileNotExistError(f"File does not exist: {routerInformation.rsplit(os.sep, 1)[1]}")

        routingTable = RoutingTable(self.routerName, routerInformation)

        self.protocolHandler = DistanceVectorRouting(self.routerName, self.routerSocket,
                                                     self.routerIP, self.routerPort,
                                                     routingTable, self.timeout)

        self.routerLinkHandler = RouterLinkMonitor(self.routerName, routerInformation, routingTable)

        log.info("Starting thread execution")
        self.protocolHandler.start()
        self.routerLinkHandler.start()

        while True:
            time.sleep(1)

    def stop(self, timeout=5):
        log.info("Shutting down the router: %s", self.routerName)
        try:
            self.protocolHandler.terminate(timeout + self.timeout)
        except Exception as e:
            log.error("Could not terminate thread: %s!", self.protocolHandler.threadName)
            log.debug(e)
            raise RouterError(f"Shutting down the router '{self.routerName}' failed!")

        try:
            self.routerLinkHandler.terminate(timeout)
        except Exception as e:
            log.error("Could not terminate thread: %s!", self.protocolHandler.threadName)
            log.debug(e)
            raise RouterError(f"Shutting down the router '{self.routerName}' failed!")

        try:
            self.close()
        except Exception as e:
            log.error("Could not shut down the socket!")
            log.debug(e)
            raise RouterError(f"Shutting down the router '{self.routerName}' failed!")

    def close(self):
        try:
            if self.routerSocket:
                self.routerSocket.close()
        except Exception as e:
            log.error("Could not close UDP socket!")
            log.debug(e)
            raise RouterError(f"Closing UDP socket {self.routerIP}:{self.routerPort} failed!")


class RoutingTable:
    def __init__(self, sourceRouter, routerInformation):
        self.sourceRouter = sourceRouter
        self.routerInformation = routerInformation
        self.neighbours = {}
        self.totalNeighbours = 0
        self.routingTable = {}
        self.load_router_information()
        self._init_distance_vector()

    def load_router_information(self):
        with open(self.routerInformation, "r") as f:
            for info in f.readlines():
                info = list(filter(None, info.split()))
                if len(info) == 1:
                    self.totalNeighbours = int(info[0])
                elif len(info) == 4:
                    if info[0] not in self.neighbours:
                        self.neighbours[info[0]] = {}
                    self.neighbours[info[0]]['ipv4'] = info[2]
                    self.neighbours[info[0]]['port'] = int(info[3])
                    self.neighbours[info[0]]['link_cost'] = float(info[1])

    def _init_distance_vector(self):
        for router in [self.sourceRouter] + list(self.neighbours.keys()):
            self.routingTable[router] = {}
            self.routingTable[router][router] = {'distance': 0, 'nextHopRouter': router}

        for neighbourRouter, routerAddress in self.neighbours.items():
            sourceDV = self.routingTable[self.sourceRouter]
            sourceDV[neighbourRouter] = {
                'distance': routerAddress['link_cost'],
                'nextHopRouter': neighbourRouter
            }

    def isNeighbourRouter(self, routerAddress):
        for k, v in self.neighbours.items():
            if v['ipv4'] == routerAddress[0] and v['port'] == routerAddress[1]:
                return True
        return False

    def get_distance_vector(self):
        return self.routingTable[self.sourceRouter]

    def get_neighbour_routers(self):
        return self.neighbours


class DistanceVectorRouting(Thread):
    PACKET = namedtuple("Packet", ["Router", "Checksum", "DistanceVector", "PoisonReverse", "Payload"])

    def __init__(self, routerName, routerSocket, routerIP, routerPort, routingTable,
                 timeout=15, threadName="DistanceVectorRouting", bufferSize=2048):
        Thread.__init__(self)
        self._stopevent = Event()
        self.routerName = routerName
        self.routerSocket = routerSocket
        self.routerIP = routerIP
        self.routerPort = routerPort
        self.routingTable = routingTable
        self.timeout = timeout
        self.threadName = threadName
        self.bufferSize = bufferSize

    def run(self):
        sequence_no = 1
        while not self._stopevent.isSet():
            log.info("[%s] Sending distance vector to neighbour routers", self.threadName)
            self.send_distance_vector()

            start_time = time.time()
            while True:
                if (time.time() - start_time) > self.timeout:
                    break
                ready = select.select([self.routerSocket], [], [], self.timeout)
                if not ready[0]:
                    break
                try:
                    receivedPacket, receiverAddress = self.routerSocket.recvfrom(self.bufferSize)
                except Exception as e:
                    log.error("[%s] Could not receive UDP packet!", self.threadName)
                    log.debug(e)
                    continue
                if not self.routingTable.isNeighbourRouter(receiverAddress):
                    log.warning("[%s] Discarding packet received from wrong router!", self.threadName)
                    continue
                receivedPacket = self.parse(receivedPacket)
                if self.corrupt(receivedPacket):
                    log.warning("[%s] Discarding corrupt received packet!", self.threadName)
                    continue
                self.update_routing_table(receivedPacket)
            sequence_no += 1

    def send_distance_vector(self):
        neighbourRouters = self.routingTable.get_neighbour_routers()
        distanceVector = self.routingTable.get_distance_vector()
        for neighbourRouter, routerAddress in neighbourRouters.items():
            poisonReverse = {destRouter: 1 if destRouter != self.routerName and
                             destRouter != neighbourRouter and
                             neighbourRouter == info['nextHopRouter'] else 0
                             for destRouter, info in distanceVector.items()}
            pkt = DistanceVectorRouting.PACKET(
                Router=self.routerName, Checksum=None,
                DistanceVector=distanceVector, PoisonReverse=poisonReverse, Payload=None)
            self.rdt_send(pkt, routerAddress)

    def rdt_send(self, packet, routerAddress):
        rawPacket = self.make_pkt(packet)
        self.udt_send(rawPacket, routerAddress)

    def make_pkt(self, packet):
        payload = [f"{dest}:{info['distance']}:{info['nextHopRouter']}:{packet.PoisonReverse[dest]}"
                   for dest, info in packet.DistanceVector.items()]
        payload = ','.join(payload)
        router = struct.pack('=1s', packet.Router.encode())
        payloadSize = struct.pack('=I', len(payload))
        checksum = struct.pack('=H', self.checksum(payload))
        payload = struct.pack(f'={len(payload)}s', payload.encode())
        return router + payloadSize + checksum + payload

    def udt_send(self, packet, routerAddress):
        try:
            self.routerSocket.sendto(packet, (routerAddress['ipv4'], routerAddress['port']))
        except Exception as e:
            log.error("[%s] Could not send UDP packet!", self.threadName)
            log.debug(e)

    def update_routing_table(self, receivedPacket):
        router = receivedPacket.Router
        distanceVector = receivedPacket.DistanceVector
        poisonReverse = receivedPacket.PoisonReverse
        self.routingTable.update(router, distanceVector, poisonReverse, "update_distance_vector")

    def parse(self, receivedPacket):
        router = struct.unpack('=1s', receivedPacket[0:1])[0].decode()
        payloadSize = struct.unpack('=I', receivedPacket[1:5])[0]
        checksum = struct.unpack('=H', receivedPacket[5:7])[0]
        payload = struct.unpack(f'={payloadSize}s', receivedPacket[7:])[0].decode()

        content = [entry.split(':') for entry in payload.split(',') if len(entry.split(':')) == 4]
        distanceVector = [(entry[0], float(entry[1]), entry[2]) for entry in content]
        poisonReverse = {entry[0]: int(entry[3]) for entry in content}

        return DistanceVectorRouting.PACKET(
            Router=router, Checksum=checksum, DistanceVector=distanceVector,
            PoisonReverse=poisonReverse, Payload=payload
        )

    def corrupt(self, receivedPacket):
        computedChecksum = self.checksum(receivedPacket.Payload)
        return computedChecksum != receivedPacket.Checksum

    def checksum(self, data):
        if len(data) % 2 != 0:
            data += "0"
        sum = 0
        for i in range(0, len(data), 2):
            data16 = ord(data[i]) + (ord(data[i + 1]) << 8)
            sum = self.carry_around_add(sum, data16)
        return ~sum & 0xffff

    def carry_around_add(self, sum, data16):
        sum += data16
        return (sum & 0xffff) + (sum >> 16)

    def terminate(self, timeout=5):
        self._stopevent.set()
        Thread.join(self, timeout)


class RouterLinkEventHandler(PatternMatchingEventHandler):
    def on_modified(self, event):
        log.info("Router information file modified.")
        self.update_link()

    def update_link(self):
        self.routingTable.load_router_information()


class RouterLinkMonitor(Thread):
    def __init__(self, routerName, routerInformation, routingTable, threadName="RouterLinkMonitor"):
        Thread.__init__(self)
        self._stopevent = Event()
        self.routerName = routerName
        self.routerInformation = routerInformation
        self.routerInformationPath = os.path.split(routerInformation)[0]
        self.routingTable = routingTable
        self.threadName = threadName

    def run(self):
        log.info("[%s] Monitoring links for router: %s", self.threadName, self.routerName)
        eventHandler = RouterLinkEventHandler(
            patterns=[self.routerInformation], ignore_patterns=[], ignore_directories=True)
        eventHandler.routingTable = self.routingTable
        eventHandler.threadName = self.threadName

        self.observer = Observer()
        self.observer.schedule(eventHandler, self.routerInformationPath, recursive=False)
        self.observer.start()

        while not self._stopevent.isSet():
            time.sleep(1)
        self._stop()

    def _stop(self):
        self.observer.stop()
        self.observer.join()

    def terminate(self, timeout=5):
        self._stopevent.set()
        Thread.join(self, timeout)


def shutdown(signal=None, frame=None):
    if router:
        router.stop()
        sys.exit(1)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)

    parser = argparse.ArgumentParser(
        description="Distance Vector Routing Protocol",
        prog="python ClientApp.py -n <router_name> -i <router_ip> -p <router_port> -f <router_information> -t <timeout> -w <www>"
    )
    parser.add_argument("-n", "--router_name", type=str, default="a", help="Router name, default: a")
    parser.add_argument("-i", "--router_ip", type=str, default="127.0.0.1", help="Router IP, default: 127.0.0.1")
    parser.add_argument("-p", "--router_port", type=int, default=8080, help="Router port, default: 8080")
    parser.add_argument("-f", "--router_information", type=str, default="a.dat",
                        help="Router information file, default: a.dat")
    parser.add_argument("-t", "--timeout", type=int, default=15, help="Timeout, default: 15 seconds")
    parser.add_argument("-w", "--www", type=str, default=os.path.join(os.getcwd(), "data", "scenario-1"),
                        help="Path containing router information, default: ./data/scenario-1/")

    args = vars(parser.parse_args())
    router = Router(args["router_name"], args["router_ip"], args["router_port"], args["timeout"], args["www"])
    try:
        router.start(args["router_information"])
    except FileNotExistError as e:
        log.error("File not found: %s", e)
    except RouterError as e:
        log.error("Router error: %s", e)
    except Exception as e:
        log.error("Unexpected error: %s", e)