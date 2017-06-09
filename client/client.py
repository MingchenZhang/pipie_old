import argparse
import sys
import websocket
import json
import socket
import random
import time
import selectors
import errno

DEBUG = True
CONTROL_SERVER = 'ws://104.236.245.187/'
TRAVERSAL_SERVER = ('104.236.245.187', 3735)
RELAY_SERVER = ('104.236.245.187', 4396)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def debug(*args, **kwargs):
    if DEBUG:
        eprint(*args, **kwargs)


def tcp_traversal(exchange_token, role='not given'):
    peerInfo = TRAVERSAL_SERVER
    serverSocket = socket.create_connection(peerInfo)
    localInfo = serverSocket.getsockname()
    # send local port info to server
    serverSocket.send(
        json.dumps({'sourcePort': localInfo[1], 'exchangeToken': str(exchange_token), 'role': role}).encode())
    msg = json.loads(serverSocket.recv(1024).decode())
    debug('from traversal helper server:' + str(msg))

    serverSocket.close()

    if msg['peerPortPreserve']:  # remote is port preservation nat (good)
        peerInfo = (msg['peerPublicIP'], int(msg['peerPublicPort']))
        debug('Instructed to directly connect. Connecting to: ')
        debug(peerInfo)
        debug('local bind to '+str(localInfo))
        retry_time = 1
        if msg['myPortPreserve']:  # local nat is a port preservation nat, we could try multiple times
            retry_time = 50
            # if local is not port preservation nat, only one try is needed (more connection would use other port)
            # and if remote computer reject the connection right away, there is no way to establish tcp connection.
        for i in range(0, retry_time):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            success = False
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(localInfo)
                sock.connect(peerInfo)
                debug("connect")
                success = True
                return sock
            except socket.error as e:
                debug('port ' + str(msg['peerPublicPort']) + ' failed to connect')
                # traceback.print_exc()
                time.sleep(random.random() / 5.0)
                continue
            finally:
                if not success:
                    sock.close()
    else:  # remote nat has some algorithm involved, need some guessing
        initialPort = int(msg['peerPublicPort'])
        scanning_range = 100
        debug('Instructed to scan ports. Scanning ports [' + str(initialPort) + ', ' +
              str(initialPort + scanning_range) + ']')
        for i in range(0, scanning_range):
            remotePort = initialPort + i
            debug('trying port: ' + str(remotePort))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(localInfo)
            success = False
            try:
                sock.settimeout(1)
                sock.connect((msg['peerPublicIP'], remotePort))
                sock.settimeout(60)
                debug("connected")
                success = True
                return sock
            except socket.error as e:
                debug('port ' + str(remotePort) + ' failed to connect')
                # traceback.print_exc()
            finally:
                if not success:
                    sock.close()
    return None

parser = argparse.ArgumentParser(description='pipie, a program help you pipe data across networks')

parser.add_argument('-m', dest='mode', action="store", help='specify working mode (pipe)')
parser.add_argument('--mode', dest='mode', action="store", help='specify working mode (pipe)')
parser.add_argument('--role', dest='role', action="store", help='specify role (client or host)')
parser.add_argument('--name', dest='name', action="store", help='specify name')
parser.add_argument('--password', dest='password', action="store", help='specify password')

arguments = parser.parse_args()
if arguments.name is None or arguments.password is None:
    eprint('name and password must be given')
    exit(1)

try:
    if arguments.mode == 'pipe':
        if arguments.role == 'client':
            ws = websocket.create_connection(CONTROL_SERVER)
            request = {'type': 'start_pipe_request', 'connectTo': arguments.name, "accessPassword": arguments.password}
            ws.send(json.dumps(request))
            eprint('attempt to connect to ' + str(arguments.name))
            response = json.loads(ws.recv())
            if response["type"] == "error":
                eprint('server returned error, error: ' + str(response["message"]))
                exit(1)
            if response["type"] != "start_pipe":
                eprint('server response abnormal, error: ' + str(response))
                exit(1)
            eprint('attempt to traverse to ' + str(arguments.name))
            # now attempt traversal using helper server
            tcp_socket = tcp_traversal(response["exchangeToken"], role='client')
            if tcp_socket is None:
                eprint('traversal failed, abort action')
                exit(1)
            # client reads stdin and forwards to socket
            while True:
                data = sys.stdin.read()
                if len(data) == 0:  # no data will be available
                    break
                try:
                    tcp_socket.send(data)
                except OSError:
                    debug("socket write fail")
                    break
            tcp_socket.close()
            eprint("(tcp socket is closed)")
            eprint("exiting...")
            exit(0)
        elif arguments.role == 'host':
            ws = websocket.create_connection(CONTROL_SERVER)
            request = {'type': 'register', 'accessPassword': arguments.password}
            if arguments.name is not None:
                request['name'] = arguments.name
            ws.send(json.dumps(request))
            eprint('trying to register')
            response = json.loads(ws.recv())
            if response["type"] != 'registered':
                eprint('unable to register, error: ' + str(response["message"]))
                exit(1)
            # save name
            registerName = response["name"]
            registerPassword = arguments.password
            eprint("successfully registered as " + str(registerName))
            eprint("Now waiting for requests...")
            while True:
                response = json.loads(ws.recv())
                eprint("received request")
                debug(response)
                if response["type"] == 'start_pipe':
                    eprint("start_pipe request received")
                    if response["connectTo"] != registerName or response["accessPassword"] != registerPassword:
                        eprint('name or password received from server is illegal, abort action')
                        continue
                    # now attempt traversal using helper server
                    tcp_socket = tcp_traversal(response["exchangeToken"], role='host')
                    if tcp_socket is None:
                        eprint('traversal failed, abort action')
                        continue
                    eprint('traversal success, continue')
                    # set socket keep alive interval, in case NAT cut the connection
                    # see http://www.tldp.org/HOWTO/html_single/TCP-Keepalive-HOWTO/#setsockopt
                    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    tcp_socket.setblocking(False)
                    # client reads socket and forwards to stdout
                    while True:
                        data = tcp_socket.recv(2048)
                        if len(data) == 0:  # no data will be available
                            break
                        try:
                            sys.stdout.write(data)
                        except OSError:
                            debug("stdout write fail")
                            break
                    tcp_socket.close()
                    eprint("(tcp socket is closed)")
                    eprint("exiting...")
                    exit(0)
                elif response["type"] == 'error':
                    eprint('receive error from server, error: ' + str(response["message"]))
                    exit(1)
                else:
                    eprint('receive unknown request, request type: ' + str(response["type"]))
                    exit(1)
        else:
            eprint('role not recognized')
    else:
        eprint('working mode not recognized')
except ValueError as e:
    eprint("decode server response error")
    exit(1)
