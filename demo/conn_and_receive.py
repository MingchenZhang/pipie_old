#import selectors
import socket
import random
from time import sleep
#import fcntl, os

import time
import traceback

import select

peerInfo = ('104.236.245.187', 9000)
localPort = random.randint(10000, 65000)
serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
serverSocket.bind(("", localPort))
serverSocket.connect(peerInfo)

serverSocket.send((str(localPort) + '\n').encode())
msg = serverSocket.recv(1024).decode()

print('from proxy:' + msg)
peer_addr = msg.split('|')
print('peer addr: ' + peer_addr[0] + ':' + peer_addr[1] + ' real port: ' + peer_addr[2])

serverSocket.close()

if int(peer_addr[3]) == 0:
    # remote is port preservation nat (good)
    print('Instructed to directly connect. Connecting to: ')
    peerInfo = (peer_addr[0], int(peer_addr[1]))
    print(peerInfo)
    retry_time = 1
    if int(peer_addr[4]) == 0:
        # local nat is a port preservation nat, we could try multiple times
        retry_time = 1000
        # if local is not port preservation nat, only one try is needed (more connection would use other port)
        # and if remote computer reject the connection right away, there is no way to establish tcp connection.
    for i in range(0, retry_time):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        #fcntl.fcntl(sock, fcntl.F_SETFL, os.O_NONBLOCK)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", localPort))
            sock.connect(peerInfo)
            print("connect")
            sock.settimeout(None)
            sock.send(str(random.randint(1000, 9999)).encode())
            print('received: ' + sock.recv(1024).decode())
            break
        except socket.error as e:
            print('port ' + peer_addr[1] + ' failed to connect')
            # traceback.print_exc()
            sleep(random.random()/5.0)
            continue
        finally:
            sock.close()
else:
    # remote nat has some algorithm involved, need some guessing
    initialPort = int(peer_addr[1])
    scanning_range = 100
    print('Instructed to scan ports. Scanning ports [' + str(initialPort) + ', ' +
          str(initialPort + scanning_range) + ']')
    socksPool = []
    for i in range(0, 100):
        remotePort = initialPort + i
        print('trying port: '+str(remotePort))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", localPort))
        try:
            sock.settimeout(1)
            sock.connect((peer_addr[0], remotePort))
            sock.settimeout(60)
            print("connect")
            sock.send(str(random.randint(1000, 9999)).encode())
            print('received: ' + sock.recv(1024).decode())
            break
        except socket.error as e:
            print('port ' + str(remotePort) + ' failed to connect')
            # traceback.print_exc()
        finally:
            sock.close()
