import random
import socket

serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
serverSocket.bind(('', 9000))
serverSocket.listen(5)

while True:
    print('swapping ready')
    (clientsocket1, address1) = serverSocket.accept()
    print('1 connected')
    received, addr = clientsocket1.recvfrom(256)
    realPort1 = int(received)
    print('1 receive: ' + str(address1))
    client1_need_scan = 0
    if address1[1] != realPort1:
        client1_need_scan = 1
    (clientsocket2, address2) = serverSocket.accept()
    print('2 connected')
    received, addr = clientsocket2.recvfrom(256)
    realPort2 = int(received)
    print('2 receive: ' + str(address2))
    client2_need_scan = 0
    if address2[1] != realPort2:
        client2_need_scan = 1
    client1_nat_type = client1_need_scan
    client2_nat_type = client2_need_scan
    if client1_need_scan == 1 and client2_need_scan == 1:
        client1_need_scan = 1
        client2_need_scan = 0
    clientsocket1.send(str(address2[0] + "|" + str(address2[1]) + '|' + str(realPort2) + '|' +
                           str(client2_need_scan) + '|' + str(client1_nat_type)).encode())
    clientsocket2.send(str(address1[0] + "|" + str(address1[1]) + '|' + str(realPort1) + '|' +
                           str(client1_need_scan) + '|' + str(client2_nat_type)).encode())
    clientsocket1.close()
    clientsocket2.close()
    print('swapping complete')
