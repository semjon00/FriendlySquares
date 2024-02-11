from __future__ import annotations

import json
import random
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


class Game:
    def __init__(self):
        self.p_descriptions, self.p_rotations, self.p_positions = self.generate_pieces()
        self.players = []

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
                        ch = self.rotate_piece(self.p_descriptions[p], times=self.p_rotations[p])[i2:i2+2]
                    f[i * 2 + i2] += ch
        return f


clients = {}
games = {}

@sio.event
def connect(sid, environ):
    client = Client(sid)
    clients[sid] = client
    print(f'Connected {sid} with {client.my_uuid}')

@sio.event
async def message(sid, msg):
    msg = json.loads(msg)
    match msg['cmd']:
        case 'op':
            pass

    print("message recieved ", msg)


@sio.event
def disconnect(sid):
    print(f'Disconnected {sid} with {clients[sid].my_uuid}')
    print('disconnect ', sid)
    del clients[sid]


if __name__ == '__main__':
    web.run_app(app, port=DEFAULT_PORT)
