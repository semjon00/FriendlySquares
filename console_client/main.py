import asyncio
import json
import socketio
from constants import DEFAULT_PORT


class Client:
    def __init__(self):
        self.sio = socketio.AsyncClient()
        self.sio.on('connect', self.connect)
        self.sio.on('my_message', self.my_message)
        self.sio.on('disconnect', self.disconnect)

    async def __send_stuff_routine(self, data):
        await self.sio.emit('my_message', json.dumps(data))

    async def send_stuff(self, data):
        await asyncio.create_task(self.__send_stuff_routine(data))

    async def connect(self):
        """What happens on connection"""
        print('Connection established')

    async def my_message(self, data):
        print(data)

    async def disconnect(self):
        print('Disconnected from server')

    async def do_connect(self, where):
        if ':' not in where:
            where = where + ':' + str(DEFAULT_PORT)
        await self.sio.connect(f'http://{where}')
        await self.send_stuff({'cmd': 'msg', 'msg': 'ok_from_client'})
        await self.sio.wait()

    async def cmd(self, cmd):
        match cmd[0]:
            case 'host':
                await self.send_stuff({'cmd': 'host'})
            case 'join':
                await self.send_stuff({'cmd': 'join', 'game_id': cmd[1]})
            case 'board':
                await self.send_stuff({'cmd': 'board'})
            case 'put':
                await self.send_stuff({'cmd': 'put',
                                       'idx': int(cmd[1]), 'pos': (int(cmd[2]), int(cmd[3])), 'rot': int(cmd[4])})

    async def command_loop(self):
        while True:
            cmd = input('> ')
            await self.cmd(cmd.split(' '))


async def main():
    #where = input('Please enter server address: ')
    where = 'localhost'
    c = Client()
    await asyncio.create_task(asyncio.create_task(c.command_loop()))
    await c.do_connect(where)


if __name__ == '__main__':
    asyncio.run(main())
