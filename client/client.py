import argparse
import sys
import websocket
import json


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


CONTROL_SERVER = 'ws://104.236.245.187:8080/'
TRAVERSAL_SERVER = '104.236.245.187:3735'
RELAY_SERVER = '104.236.245.187:4396'

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
                eprint('unable to register, error: '+str(response.message))
                exit(1)
            registerName = response.name
            eprint("successfully registered as "+str(registerName))

        else:
            eprint('role not recognized')
    else:
        eprint('working mode not recognized')
except json.decoder.JSONDecodeError as e:
    eprint("decode server response error")
    exit(1)
