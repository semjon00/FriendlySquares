# https://mortoray.com/high-throughput-game-message-server-with-python-websockets/
# TODO: Thread safety, locks? What's that?
# TODO: No exception handling, speedrun coding mode let's goo

import asyncio
import json
import websockets

from constants import DEFAULT_PORT, PROTOCOL_VERSION


class Client:
    def __init__(self, websocket):
        self.websocket = websocket

    async def send_stuff(self, msg):
        await self.websocket.send(json.dumps(msg))

    async def cmd(self, cmd):
        match cmd[0]:
            case 'room':
                await self.send_stuff({'cmd': 'room', 'game_id': cmd[1]})
            case 'positions':
                await self.send_stuff({'cmd': 'positions'})
            case 'descriptions':
                await self.send_stuff({'cmd': 'descriptions'})
            case 'put':
                await self.send_stuff({'cmd': 'put',
                                       'idx': int(cmd[1]), 'pos': (int(cmd[2]), int(cmd[3])), 'rot': int(cmd[4])})
            case 'op':
                await self.send_stuff({'cmd': 'op', 'token': cmd[1]})
            case 'help':
                print('room <n>\n'
                      'positions\n'
                      'descriptions\n'
                      'put <piece_idx> <pos_h> <pos_w> <rotation>')

    async def command_loop(self):
        async def async_input():
            return await asyncio.to_thread(input, '> ')
        while True:
            cmd = await async_input()
            await self.cmd(cmd.split(' '))

    async def process_message(self, msg):
        match msg['cmd']:  # Do you feel the déjà vu?
            case 'descriptions':
                print()
                pieces = msg['descriptions']
                for chunk_offset in range(0, len(pieces), 8):
                    chunk = pieces[chunk_offset:chunk_offset + 8]
                    for i, p in enumerate(chunk):
                        print(str(chunk_offset + i).ljust(3), end='')
                    print()
                    for r in range(0, 4, 2):
                        for p in chunk:
                            print(str(p[r:r+2]).ljust(3), end='')
                        print()
                    print()
                print()
            case 'positions':
                print('Parsing of positions message is not implemented...')
            case 'game_over':
                print(f"The game is over!"
                      f"Your team got {msg['score']['total']} points.")
            case 'msg':
                print(msg['msg'])
            case 'version':
                assert msg['version'] == PROTOCOL_VERSION
            case 'op':
                print('Made you a server administrator.' if msg['status'] else
                      'The provided token is incorrect. This incident will be reported.')

    async def reader(self, websocket):
        async for message_raw in websocket:
            msg = json.loads(message_raw)
            await self.process_message(msg)


async def hello():
    where = input('Enter ip: ')
    if where == 'l':
        where = '127.0.0.1'
    if ':' not in where:
        where = f'{where}:{DEFAULT_PORT}'
    async with websockets.connect(f"ws://{where}") as websocket:
        c = Client(websocket)
        await c.send_stuff({'cmd': 'version', 'version': PROTOCOL_VERSION})
        reader_task = asyncio.ensure_future(c.reader(websocket))
        commands_task = asyncio.ensure_future(c.command_loop())
        done = await asyncio.wait(
            [reader_task, commands_task],
            return_when=asyncio.FIRST_COMPLETED,
        )


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(hello())
