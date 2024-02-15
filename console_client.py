# https://mortoray.com/high-throughput-game-message-server-with-python-websockets/

import asyncio
import json
import websockets

from constants import DEFAULT_PORT


class Client:
    def __init__(self, websocket):
        self.websocket = websocket

    async def send_stuff(self, msg):
        await self.websocket.send(json.dumps(msg))

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
        async def async_input():
            return await asyncio.to_thread(input, '> ')
        while True:
            cmd = await async_input()
            await self.cmd(cmd.split(' '))

    async def reader(self, websocket):
        async for message_raw in websocket:
            msg = json.loads(message_raw)
            print(msg)
        await websocket.send(json.dumps({321: 121}))

async def hello():
    where = input('Enter ip: ')
    if ':' not in where:
        where = f'{where}:{DEFAULT_PORT}'
    async with websockets.connect(f"ws://{where}") as websocket:
        c = Client(websocket)
        await c.send_stuff({'cmd': 'msg', 'msg': 'I am a silly boy RAWR :3'})
        reader_task = asyncio.ensure_future(c.reader(websocket))
        commands_task = asyncio.ensure_future(c.command_loop())
        done = await asyncio.wait(
            [reader_task, commands_task],
            return_when=asyncio.FIRST_COMPLETED,
        )


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(hello())
