const WebSocket = require('ws');
const Net = require('net');
const MAX_GIVEN_NAME_DIGIT = 8;
const MAX_EXCHANGE_TOKEN_DIGIT = 8;



var nameMap = {};
var peerInfoExchangeToken = {}; // TODO: might leak token if it is not used, add a timer to expire

var ws = new WebSocket.Server({ port: 80 });
ws.on('connection', function connection(ws) {
    ws.on('message', function (message) {
        try{
            message = JSON.parse(message);
        }catch(e){
            ws.send(JSON.stringify({type: 'error', message: 'message parsing failed'}));
            ws.close();
            return;
        }
        if(message.type == 'register'){
            // expect: {type: 'register', name: 'my_new_machine', accessPassword: '123'}
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
                ws.send(JSON.stringify({type: 'registered', name: ws.name, password: ws.accessPassword}));
                console.log('new user registered: ' + ws.name);
            }else{ // no given name, will allocate one for it
                if(typeof message.accessPassword != 'string'){ // kick user off if no password is given
                    ws.send(JSON.stringify({type: 'error', message: 'access password is not given'}));
                    ws.close();
                    return;
                }
                do{
                    var name = Math.floor(Math.random()*Math.pow(10, MAX_GIVEN_NAME_DIGIT)).toString();
                }while(nameMap[name] != undefined);
                nameMap[name] = ws;
                ws.name = name;
                ws.accessPassword = message.accessPassword;
                ws.send(JSON.stringify({type: 'registered', name: ws.name}));
            }
        }else if(message.type == 'start_pipe_request'){
            // expect: {type: 'start_pipe', connectTo: 'my_new_machine', accessPassword: '123'}
            console.log('start_pipe_request received');
            console.log(message);
            var connectPeer = nameMap[message.connectTo];
            if(connectPeer == undefined){ // name not exist
                ws.send(JSON.stringify({type: 'error', message: 'name not found'}));
                ws.close();
                return;
            }
            if(connectPeer.accessPassword != message.accessPassword){
                ws.send(JSON.stringify({type: 'error', message: 'password mismatch'}));
                ws.close();
                return;
            }
            // generate an exchange token to pair client and host
            do{
                var exchangeToken = Math.floor(Math.random()*Math.pow(10, MAX_EXCHANGE_TOKEN_DIGIT)).toString();
            }while(peerInfoExchangeToken[exchangeToken] != undefined);
            peerInfoExchangeToken[exchangeToken] = true;
            var host = nameMap[message.connectTo];
            // instruction send to both client and host, they should now use traversal helper to establish a direct connection
            host.send(JSON.stringify({type: 'start_pipe', connectTo: host.name, accessPassword: host.accessPassword, exchangeToken}));
            ws.send(JSON.stringify({type: 'start_pipe', exchangeToken}));
            console.log('exchange token '+exchangeToken+' was created')
        }
    });

    ws.on('close', function () {
        if(ws.name){
            delete nameMap[ws.name];
            console.log('user left: ' + ws.name);
        }else{
            console.log('unknown user left');
        }
        ws.close();
    });
});

// traversal helper
var traversalServer = Net.createServer(function(socket) {
    socket.on('data', function (data) {
        // TODO: handle packet fragmentation problem
        // server expects {exchangeToken:"1233421", sourcePort:32323}
        console.log('traversal server receives:'+data.toString('utf8'));
        let info = JSON.parse(data.toString('utf8'));
        let token = info.exchangeToken;
        let sourcePort = parseInt(info.sourcePort);
        if(!token || !sourcePort){
            socket.write(JSON.stringify({type:'error', message: 'format error'}));
            socket.destroy();
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
            // "{peerPublicIP, peerPublicPort, peerSourcePort, myPortPreserve, peerPortPreserve}"
            let client1Info = peerInfoExchangeToken[token];
            socket.write(JSON.stringify({
                type:'success',
                peerPublicIP: client1Info.publicIP,
                peerPublicPort: client1Info.publicPort,
                peerSourcePort: client1Info.sourcePort,
                myPortPreserve: (sourcePort == socket.remotePort),
                peerPortPreserve: (client1Info.sourcePort == client1Info.publicPort),
            }));
            client1Info.socket.write(JSON.stringify({
                type:'success',
                peerPublicIP: socket.remoteAddress,
                peerPublicPort: socket.remotePort,
                peerSourcePort: sourcePort,
                myPortPreserve: (client1Info.sourcePort == client1Info.publicPort),
                peerPortPreserve: (socket.remotePort == sourcePort),
            }));
            socket.destroy();
            client1Info.socket.destroy();
        }else{
            socket.write(JSON.stringify({type:'error', message: 'exchange token not found'}));
            socket.destroy();
            return;
        }
    });
    socket.on('end', function () {

    });
    socket.on('error', function (e) {
        console.error(e);
    });
});
traversalServer.listen(3735, '0.0.0.0');

// relay server
var relayTokenMatch = {};
var relayServer = Net.createServer(function(socket) {
    // first read first MAX_EXCHANGE_TOKEN_DIGIT bytes to get relay target
    readSocket(socket, MAX_EXCHANGE_TOKEN_DIGIT, (byte)=>{
        var token = parseInt(byte);
        if(isNaN(token)){
            console.warn('exchangeToken:'+token+' format error');
            socket.destroy();
            return;
        }
        if(!relayTokenMatch[token]){
            // first in the relay pair
            relayTokenMatch[token] = socket;
            socket.token = token;
        }else{
            // send in the relay pair, start pipe
            socket.pipe(relayTokenMatch[token]);
            relayTokenMatch[token].pipe(socket);
            socket.on('close', () => {relayTokenMatch[token].close();});
            relayTokenMatch[token].on('close', () => {socket.close();});
            delete relayTokenMatch[token];
        }
    });
    socket.on('close', ()=>{
        if(socket.token) delete relayTokenMatch[socket.token];
    });
    socket.on('error', function (e) {
        if(socket.token) delete relayTokenMatch[socket.token];
    });
});
relayServer.listen(4396, '0.0.0.0');

// helper method
function readSocket(socket, nb, cb) {
    var r = socket.read(nb);
    if (r === null) return socket.once('readable', ()=>readSocket(socket, nb, cb));
    cb(r);
}

