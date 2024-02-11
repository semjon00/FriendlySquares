import asyncio
import socketio

from constants import DEFAULT_PORT

sio = socketio.AsyncClient()

@sio.event
async def connect():
    print('connection established')

@sio.event
async def message(data):
    print('asda', data)

async def send_message(data):
    await sio.emit('message', data)

@sio.event
async def disconnect():
    print('disconnected from server')


async def main():
    await sio.connect(f'http://localhost:{DEFAULT_PORT}')
    await send_message('test')
    await send_message('test')
    await sio.wait()


if __name__ == '__main__':
    asyncio.run(main())
