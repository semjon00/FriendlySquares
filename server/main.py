# TODO: Thread safety, locks? What's that?
# TODO: No exception handling, speedrun coding mode let's goo

import asyncio
import json
import random
from aiohttp import web
import socketio

from constants import DEFAULT_PORT


class Client:
    def __init__(self, sio, sid):
        self.__sio = sio
        self.sid = sid
        self.game = None
        self.is_op = False

    async def send_stuff(self, data):
        await self.__sio.emit('my_message', json.dumps(data), room=f'room{self.sid}')


class Game:
    def __init__(self):
        self.p_descriptions, self.p_rotations, self.p_positions = self.generate_pieces()
        self.players: list[Client] = []

        self.h, self.w = 5, 7
        self.field: list[list[int | str]] = [['empty' for _ in range(self.h)] for _ in range(self.w)]
        self.red_attack(5)

    def generate_pieces(self):
        colors = 'BGY'
        pieces = []
        for leading in range(3):
            for prototype, times in [("0012", 2), ("0221", 1), ("0002", 2), ("0011", 2), ("0110", 2), ("0000", 1)]:
                for _ in range(times):
                    pieces += "".join([colors[(int(prototype[i]) + leading) % 3] for i in range(4)])
        random.shuffle(pieces)
        rotations = [0 for _ in range(len(pieces))]
        field_pos = [None for _ in range(len(pieces))]
        return pieces, rotations, field_pos

    def red_attack(self, n):
        for i in random.sample(range(self.h * self.w), n):
            self.field[i // self.h][i % self.h] = 'red'

    def put_piece(self, idx, pos, rot):
        assert 0 <= idx < len(self.p_descriptions)
        assert 0 <= pos[0] <= self.h
        assert 0 <= pos[1] <= self.h
        assert self.p_positions[idx] is None
        assert self.field[pos[0]][pos[1]] == 'empty'
        # TODO: turn-based
        self.p_positions[idx] = (pos[0], pos[1])
        self.field[pos[0]][pos[1]] = idx
        self.p_rotations[idx] = rot

    def rotate_piece(self, d, times=1):
        for _ in range(times % 4):
            d = d[1] + d[3] + d[0] + d[2]

    def get_colored_state(self):
        f = ["" for _ in range(2 * self.h)]
        for i in range(self.h):
            for i2 in range(0, 4, 2):
                for j in range(self.w):
                    p = self.field[i][j]
                    if p == 'empty':
                        ch = 'ww'
                    elif p == 'red':
                        ch = 'rr'
                    else:
                        ch = self.rotate_piece(self.p_descriptions[p], times=self.p_rotations[p])[i2:i2 + 2]
                    f[i * 2 + i2] += ch
        return f

    # TODO: scoring, disbanding and game over


class Server:
    def __init__(self):
        self.sio = socketio.AsyncServer()
        self.app = web.Application()
        self.sio.attach(self.app)
        self.sio.on('connect', self.connect)
        self.sio.on('my_message', self.my_message)
        self.sio.on('disconnect', self.disconnect)

        self.op_token = random.randint(int(1e10), int(9e10))
        print(f'Op token is: {self.op_token}')
        self.clients: dict[str, Client] = {}
        self.games: dict[str, Game] = {}
        self.games_last_id = 0

    async def player_add(self, sid, game_id):
        assert len(self.games[game_id].players) < 3
        self.games[game_id].players.append(self.clients[sid])
        self.clients[sid].game = game_id
        await self.clients[sid].send_stuff({'cmd': 'msg', 'msg': f'You are now in game {game_id}'})

    async def cmd_host(self, sid):
        assert self.clients[sid].game is None
        self.games_last_id += 1
        now_id = str(self.games_last_id)
        self.games[now_id] = Game()
        await self.player_add(sid, now_id)
        print(f' {sid} Hosted game {now_id}')

    async def cmd_board(self, sid):
        c = self.clients[sid]
        g = self.games[c.game]
        s = g.get_colored_state()
        m = {'cmd': 'board', 'board': s}
        await c.send_stuff(m)

    async def cmd_put(self, sid, idx, pos, rot):
        c = self.clients[sid]
        g = self.games[c.game]
        g.put_piece(idx, pos, rot)
        await c.send_stuff({'cmd': 'msg', 'msg': 'Placement successful'})

    async def connect(self, sid, environ):
        client = Client(self.sio, sid)
        self.clients[sid] = client
        await self.sio.enter_room(sid, f'room{sid}')
        await client.send_stuff({'msg': 'ok_from_server'})
        print(f' {sid} Connected')

    async def my_message(self, sid, msg):
        msg = json.loads(msg)
        match msg['cmd']:
            case 'msg':
                print(f" {sid} Tells us: '{msg['msg']}'")
            case 'host':
                await self.cmd_host(sid)
            case 'join':
                await self.player_add(sid, msg['game_id'])
                print(f" {sid} Joined game {msg['game_id']}")
            case 'board':
                await self.cmd_board(sid)
                print(f" {sid} Got board")
            case 'put':
                await self.cmd_put(sid, msg['idx'], msg['pos'], msg['rot'])
                print(f" {sid} Put piece")
            case 'op':
                if msg['token'] == self.op_token:
                    self.clients[sid].is_op = True
                    print(f' {sid} OPPED')
                else:
                    print(f' {sid} Not opped')
                # TODO: Maybe tell them?
            case _:
                raise NotImplemented('Weird command')

    async def disconnect(self, sid):
        print(f' {sid} Disconnected')
        del self.clients[sid]
        raise NotImplemented('Disbanding game')


if __name__ == '__main__':
    s = Server()
    web.run_app(s.app, port=DEFAULT_PORT)
