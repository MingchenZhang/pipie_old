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
CONTROL_SERVER = 'ws://104.236.245.187:8080/'
TRAVERSAL_SERVER = '104.236.245.187:3735'
RELAY_SERVER = '104.236.245.187:4396'


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def debug(*args, **kwargs):
    if DEBUG:
        eprint(*args, **kwargs)


def tcp_traversal(exchange_token):
    peerInfo = socket.getnameinfo(TRAVERSAL_SERVER, 0)
    serverSocket = socket.create_connection(peerInfo)
    localInfo = serverSocket.getsockname()
    # send local port info to server
    serverSocket.send(json.dumps({'sourcePort': localInfo[1], 'exchangeToken': str(exchange_token)}).encode())
    msg = json.loads(serverSocket.recv(1024).decode())
    debug('from traversal helper server:' + msg)

    serverSocket.close()

    if int(msg.myPortPreserve) == 0:  # remote is port preservation nat (good)
        debug('Instructed to directly connect. Connecting to: ')
        peerInfo = (msg.peerPublicIP, int(msg.peerPublicPort))
        debug(peerInfo)
        retry_time = 1
        if int(msg.peerPortPreserve) == 0:  # local nat is a port preservation nat, we could try multiple times
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
                debug('port ' + msg.peerPublicPort + ' failed to connect')
                # traceback.print_exc()
                time.sleep(random.random() / 5.0)
                continue
            finally:
                if not success:
                    sock.close()
    else:  # remote nat has some algorithm involved, need some guessing
        initialPort = int(msg.peerPublicPort)
        scanning_range = 100
        debug('Instructed to scan ports. Scanning ports [' + str(initialPort) + ', ' +
              str(initialPort + scanning_range) + ']')
        for i in range(0, 100):
            remotePort = initialPort + i
            debug('trying port: ' + str(remotePort))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(localInfo)
            success = False
            try:
                sock.settimeout(1)
                sock.connect((msg.peerPublicIP, remotePort))
                sock.settimeout(60)
                debug("connect")
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
            pass
        elif arguments.role == 'host':
            ws = websocket.create_connection(CONTROL_SERVER)
            request = {'type': 'register', 'accessPassword': arguments.password}
            if arguments.name is not None:
                request['name'] = arguments.name
            ws.send(json.dumps(request))
            eprint('trying to register')
            response = json.loads(ws.recv())
            if response.type != 'registered':
                eprint('unable to register, error: ' + str(response.message))
                exit(1)
            # save name and password
            registerName = response.name
            registerPassword = response.password
            eprint("successfully registered as " + str(registerName))
            eprint("Now waiting for requests...")
            response = json.loads(ws.recv())
            eprint("received request")
            debug(response)
            while True:
                if response.type == 'start_pipe':
                    eprint("start_pipe request received")
                    if response.connectTo != registerName or response.accessPassword != registerPassword:
                        eprint('name or password received from server is illegal, abort action')
                        continue
                    # now attempt traversal using helper server
                    tcp_socket = tcp_traversal(response.exchangeToken)
                    if tcp_socket is None:
                        eprint('traversal failed, abort action')
                        continue
                    # set socket keep alive interval, in case NAT cut the connection
                    # see http://www.tldp.org/HOWTO/html_single/TCP-Keepalive-HOWTO/#setsockopt
                    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    tcp_socket.setblocking(False)
                    # define receive behavior
                    def recv_action(file_obj):
                        received = None
                        try:
                            received = file_obj.recv(4096)  # TODO: performance improvement can be made
                        except socket.error as e:
                            err = e.args[0]
                            if err != errno.EAGAIN and err != errno.EWOULDBLOCK:
                                debug("error occurred on the tcp socket")
                                return False
                        sys.stdout.write(received)
                        return True
                    pipe_selector = selectors.DefaultSelector()
                    pipe_selector.register(tcp_socket, selectors.EVENT_READ, recv_action)
                    selector_loop = True
                    while selector_loop:
                        events = pipe_selector.select()
                        for key, mask in events:
                            callback = key.data
                            if not callback(key.fileobj, mask):
                                selector_loop = False
                    eprint("tcp socket is closed")
                    eprint("exiting...")
                    exit(0)
                elif response.type == 'error':
                    eprint('receive error from server, error: ' + str(response.message))
                    exit(1)
                else:
                    eprint('receive unknown request, request type: ' + str(response.type))
                    exit(1)
        else:
            eprint('role not recognized')
    else:
        eprint('working mode not recognized')
except json.decoder.JSONDecodeError as e:
    eprint("decode server response error")
    exit(1)
