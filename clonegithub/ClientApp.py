#!/usr/bin/python
"""
@File:           ClientApp.py
@Description:    Client Application running Distance Vector Routing algorithm.
@Author:         Chetan Borse
@EMail:          chetanborse2106@gmail.com
@Created_on:     04/23/2017
@License         GNU General Public License
@python_version: 2.7
===============================================================================
"""

import sys
import os
import signal
import argparse

from router import Router
from router import FileNotExistError
from router import RouterError


# Global variables
router = None


# Shut down the router on Ctrl+C or on exiting from application
def shutdown(signal=None, frame=None):
    if router:
        router.stop()
        sys.exit(1)


signal.signal(signal.SIGINT, shutdown)


def ClientApp(**args):
    global router

    # Arguments
    routerName = args["router_name"]
    routerIP = args["router_ip"]
    routerPort = args["router_port"]
    routerInformation = args["router_information"]
    timeout = args["timeout"]
    www = args["www"]

    # Ensure the router information file is in the current directory
    routerInformation = os.path.join(os.getcwd(), routerInformation)

    # Create 'Router' object
    router = Router(routerName, routerIP, routerPort, timeout, www)

    try:
        # Start running the Distance Vector Routing algorithm
        router.start(routerInformation)
    except FileNotExistError as e:
        print("File not found!")
        print(e)
    except RouterError as e:
        print("Unexpected exception in router!")
        print(e)
    except Exception as e:
        print("Unexpected exception!")
        print(e)


if __name__ == "__main__":
    # Argument parser
    parser = argparse.ArgumentParser(description='Distance Vector Routing algorithm',
                                     prog='python ClientApp.py -n <router_id> -i <router_ip> -p <router_port> -f <router_information> -t <timeout> -w <www>')

    parser.add_argument("-n", "--router_name", type=int, required=True,
                        help="Router ID (numeric, from topology file)")
    parser.add_argument("-i", "--router_ip", type=str, default="127.0.0.1",
                        help="Router IP, default: 127.0.0.1")
    parser.add_argument("-p", "--router_port", type=int, default=8080,
                        help="Router port, default: 8080")
    parser.add_argument("-f", "--router_information", type=str, default="a.dat",
                        help="Router information (topology file), default: a.dat")
    parser.add_argument("-t", "--timeout", type=int, default=15,
                        help="Timeout, default: 15")
    parser.add_argument("-w", "--www", type=str, default=os.path.join(os.getcwd(), "data", "scenario-1"),
                        help="Path consisting of router information, default: /<Current Working Directory>/data/scenario-1/")

    # Read user inputs
    args = vars(parser.parse_args())

    # Run Client Application
    ClientApp(**args)