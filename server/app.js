const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 8080 });

var nameMap = {};
var peerInfoExchangeToken = {}; // TODO: might leak token if it is not used

wss.on('connection', function connection(ws) {
    ws.on('message', function (message) {
        try{
            message = JSON.parse(message);
        }catch(e){
            ws.send(JSON.stringify({type: 'error', message: 'message parsing failed'}));
            ws.close();
            return;
        }
        if(message.type == 'register'){
            // {type: 'register', name: 'my_new_machine', accessPassword: '123'}
            if(typeof message.name == 'string'){ // with a given name
                if(nameMap[message.name] != undefined){ // name taken
                    ws.send(JSON.stringify({type: 'error', message: 'name taken'}));
                    ws.close();
                    return;
                }
                if(typeof message.accessPassword != 'string'){ // kick user off if no password is given
                    ws.send(JSON.stringify({type: 'error', message: 'access password is not given'}));
                    ws.close();
                    return;
                }
                nameMap[message.name] = ws;
                ws.name = message.name;
                ws.accessPassword = message.accessPassword;
                ws.send(JSON.stringify({type: 'registered', name: ws.name}));
            }else{ // no given name, will allocate one for it
                if(typeof message.accessPassword != 'string'){ // kick user off if no password is given
                    ws.send(JSON.stringify({type: 'error', message: 'access password is not given'}));
                    ws.close();
                    return;
                }
                do{
                    let name = Math.floor(Math.random()*9999999).toString();
                }while(nameMap[name] != undefined);
                nameMap[name] = ws;
                ws.name = name;
                ws.accessPassword = message.accessPassword;
                ws.send(JSON.stringify({type: 'registered', name: ws.name}));
            }
        }else if(message.type == 'start_pipe'){
            // {type: 'start_pipe', connectTo: 'my_new_machine', accessPassword: '123'}
            if(nameMap[message.name] == undefined){ // name not exist
                ws.send(JSON.stringify({type: 'error', message: 'name taken'}));
                ws.close();
                return;
            }
            let exchangeToken = Math.floor(Math.random()*9999999).toString();
            peerInfoExchangeToken[exchangeToken] = true;
        }
    });

    ws.on('close', function () {
        if(ws.name) delete nameMap[ws.name];
        ws.close();
    });
});

const Net = require('net');

var server = Net.createServer(function(socket) {
    socket.on('data', function (data) {
        // TODO: handle packet fragmentation problem
        // server expects {exchangeToken:"1233421", sourcePort:"32323"}
        let info = JSON.parse(data.toString('utf8'));
        let token = info.exchangeToken;
        let sourcePort = parseInt(info.sourcePort);
        if(!token || !sourcePort){
            socket.send(JSON.stringify({type:'error', message: 'format error'}));
            socket.close();
            return;
        }
        if(peerInfoExchangeToken[token] === true){
            // this is the first client
            peerInfoExchangeToken[token] = {
                publicIP: socket.remoteAddress,
                publicPort: socket.remotePort,
                sourcePort,
                socket
            };
        }else if(typeof peerInfoExchangeToken[token] == 'object'){
            // this is the second client
            // send the following to both peers
            // "peerPublicIP|peerPublicPort|peerSourcePort|myPortPreserve|peerPortPreserve"
            let client1Info = peerInfoExchangeToken[token];
            socket.send(JSON.stringify({
                type:'success',
                peerPublicIP: client1Info.publicIP,
                peerPublicPort: client1Info.publicPort,
                peerSourcePort: client1Info.sourcePort,
                myPortPreserve: (sourcePort == socket.remotePort),
                peerPortPreserve: (client1Info.sourcePort == client1Info.publicPort),
            }));
            client1Info.socket.send(JSON.stringify({
                type:'success',
                peerPublicIP: socket.remoteAddress,
                peerPublicPort: socket.remotePort,
                peerSourcePort: sourcePort,
                myPortPreserve: (client1Info.sourcePort == client1Info.publicPort),
                peerPortPreserve: (socket.remotePort == sourcePort),
            }));
            socket.close();
            client1Info.close();
        }else{
            socket.send(JSON.stringify({type:'error', message: 'exchange token not found'}));
            socket.close();
            return;
        }
    });
    socket.on('end', function () {

    });
});

server.listen(1337, '127.0.0.1');