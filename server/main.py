from aiohttp import web
import socketio

from constants import DEFAULT_PORT

sio = socketio.AsyncServer()
app = web.Application()
sio.attach(app)

class Client:
    def __init__(self, sid):
        self.my_uuid = sid
        sio.enter_room(sid, f'room{self.my_uuid}')
        self.game = None

    async def send_stuff(self, data):
        await sio.emit('message', data, room=f'room{self.my_uuid}')


clients = {}

@sio.event
def connect(sid, environ):
    client = Client(sid)
    clients[sid] = client
    print(f'Connected {sid} with {client.my_uuid}')

@sio.event
async def message(sid, data):
    print("message recieved ", data)
    await clients[sid].send_stuff('marshmellow')
    await clients[sid].send_stuff('egg')
    await clients[sid].send_stuff('chicken')

@sio.event
def disconnect(sid):
    print(f'Disconnected {sid} with {clients[sid].my_uuid}')
    print('disconnect ', sid)
    del clients[sid]


if __name__ == '__main__':
    web.run_app(app, port=DEFAULT_PORT)
