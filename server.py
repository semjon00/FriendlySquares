# TODO: Thread safety, locks? What's that?
# TODO: No exception handling, speedrun coding mode let's goo

import asyncio
import json
import random
import time
import traceback
import uuid
import websockets

import scoring
from constants import DEFAULT_PORT, PROTOCOL_VERSION


class Client:
    def __init__(self, ws, path):
        self.websocket = ws
        self.path = path
        self.client_id = str(uuid.uuid4())
        self.is_op = False
        self.game = None

    async def send_stuff(self, msg):
        await self.websocket.send(json.dumps(msg))


class Game:
    def __init__(self):
        self.p_descriptions, self.p_rotations, self.p_positions = self.generate_pieces()

        self.h, self.w = 5, 7
        self.field: list[list[int | str]] = [['empty' for _ in range(self.w)] for _ in range(self.h)]
        self.players: list[str] = []
        self.cur_player = None
        self.red_attack(5)

    def generate_pieces(self):
        colors = 'BGY'
        pieces = []
        for leading in range(3):
            for prototype, times in [("0012", 2), ("0221", 1), ("0002", 2), ("0011", 2), ("0110", 2), ("0000", 1)]:
                for _ in range(times):
                    desc = "".join([colors[(int(prototype[i]) + leading) % 3] for i in range(4)])
                    desc = self.rotate_piece(desc, random.randint(0, 3))
                    pieces.append(desc)
        random.shuffle(pieces)
        rotations = [0 for _ in range(len(pieces))]
        field_pos = [None for _ in range(len(pieces))]
        return pieces, rotations, field_pos

    def red_attack(self, n):
        for i in random.sample(range(self.h * self.w), n):
            self.field[i // self.w][i % self.w] = 'red'

    def put_piece(self, idx, pos, rot, player_id):
        assert 0 <= idx < len(self.p_descriptions)
        assert 0 <= pos[0] <= self.h
        assert 0 <= pos[1] <= self.w
        assert self.p_positions[idx] is None
        assert self.field[pos[0]][pos[1]] == 'empty'
        assert self.cur_player == player_id
        self.next_cur_player()
        self.p_positions[idx] = (pos[0], pos[1])
        self.field[pos[0]][pos[1]] = idx
        self.p_rotations[idx] = rot

    def is_game_over(self):
        pieces_left = sum([1 if x is not None else 0 for x in self.p_positions])
        empty_spots_left = sum([sum([1 if col == 'empty' else 0 for col in row]) for row in self.field])
        return pieces_left == 0 or empty_spots_left == 0

    def rotate_piece(self, d, times=1):
        # Counter-clockwise
        for _ in range(times % 4):
            d = d[1] + d[3] + d[0] + d[2]
        return d

    def get_available_pieces(self):
        idx = [i for i in range(len(self.p_positions)) if self.p_positions[i] is None]
        descr = {i: self.p_descriptions[i] for i in idx}
        return descr

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
                    f[i * 2 + i2 // 2] += ch
        return f

    def score(self, f):
        from scoring import score
        return score(f, accurate=False)

    def add_player(self, player_id: str):
        # You know what? I think we can drop the requirement to have 3 people max!
        self.players.append(player_id)
        if self.cur_player is None:
            self.cur_player = self.players[0]

    def remove_player(self, player_id: str):
        if self.cur_player == player_id:
            self.next_cur_player()
        self.players.remove(player_id)
        if len(self.players) == 0:
            self.cur_player = None  # Idk just in case

    def next_cur_player(self):
        """Give turn to the next player."""
        idx = self.players.index(self.cur_player)
        idx = (idx + 1) % len(self.players)
        self.cur_player = self.players[idx]


class GameServerMode(Game):
    def __init__(self):
        super().__init__()
        self.clients: dict[str, Client] = {}

    def add_player(self, sid, client):
        super().add_player(sid)
        self.clients[sid] = client

    def remove_player(self, sid):
        super().remove_player(sid)
        del self.clients[sid]


class Server:
    def __init__(self):
        self.op_token = str(random.randint(int(1e10), int(9e10)))
        print(f'Op token is: {self.op_token}')
        self.clients: dict[str, Client] = {}
        self.games: dict[str, GameServerMode] = {}
        self.games_last_id = 0

    async def player_to_room(self, sid, game_id):
        assert self.clients[sid].game is None
        if game_id not in self.games:
            self.games[game_id] = GameServerMode()
            print(f'Hosted game {game_id}')
        self.games[game_id].add_player(sid, self.clients[sid])
        self.clients[sid].game = game_id
        await self.clients[sid].send_stuff({'cmd': 'msg', 'msg': f'You are now in game {game_id}'})
        await self.cmd_board(sid)
        await self.cmd_pieces(sid)

    async def cmd_board(self, sid):
        c = self.clients[sid]
        g = self.games[c.game]
        s = g.get_colored_state()
        m = {'cmd': 'board', 'board': s}
        await c.send_stuff(m)

    async def cmd_pieces(self, sid):
        c = self.clients[sid]
        g = self.games[c.game]
        p = g.get_available_pieces()
        await c.send_stuff({'cmd': 'pieces', 'pieces': p})

    async def cmd_put(self, sid, idx, pos, rot):
        c = self.clients[sid]
        g = self.games[c.game]
        g.put_piece(idx, pos, rot, sid)
        await c.send_stuff({'cmd': 'msg', 'msg': 'Placement successful'})

        # Push this info
        for c in g.clients.values():
            sid = c.client_id
            await self.cmd_board(sid)
            await self.cmd_pieces(sid)

        if g.is_game_over():
            await asyncio.sleep(0)
            t_start = time.monotonic()
            score = g.score(g.get_colored_state())
            print(f'Game {c.game} Scoring took {(time.monotonic() - t_start) * 1000:.3f}ms')
            for c in g.clients.values():
                await c.send_stuff({'cmd': 'game_over', 'score': score})
            game_id = c.game
            for c in g.clients.keys():
                self.clients[c].game = None
            del self.games[game_id]
            print(f'Ended game {game_id} with score {score}')

    async def process_message(self, client_id, msg):
        match msg['cmd']:
            case 'msg':
                print(f" {client_id} Tells us: '{msg['msg']}'")
            case 'room':
                await self.player_to_room(client_id, msg['game_id'])
                print(f" {client_id} Joined game {msg['game_id']}")
            case 'board':
                await self.cmd_board(client_id)
                print(f" {client_id} Got board")
            case 'pieces':
                await self.cmd_pieces(client_id)
            case 'put':
                await self.cmd_put(client_id, msg['idx'], msg['pos'], msg['rot'])
                print(f" {client_id} Put piece")
            case 'op':
                if msg['token'] == self.op_token:
                    self.clients[client_id].is_op = True
                    print(f' {client_id} OPPED')
                else:
                    print(f' {client_id} Not opped')
                await self.clients[client_id].send_stuff({'cmd': 'op', 'status': self.clients[client_id].is_op})
            case 'version':
                assert msg['version'] == PROTOCOL_VERSION
            case _:
                raise NotImplemented('Weird command')

    async def listen_socket(self, websocket, path):
        c = Client(websocket, path)
        c = self.clients[c.client_id] = c
        print(f' {c.client_id} Connected')
        await c.send_stuff({'cmd': 'version', 'version': PROTOCOL_VERSION})
        async for message_raw in c.websocket:
            message = json.loads(message_raw)
            try:
                await self.process_message(c.client_id, message)
            except:
                print(f' {c.client_id} ERR {traceback.format_exc()}')
                await c.send_stuff({'cmd': 'msg', 'msg': f'Erroneous command', 'yours': message})
        if c.game is not None:
            self.games[c.game].remove_player(c.client_id)
            c.game = None
        del self.clients[c.client_id]
        print(f' {c.client_id} Disconnected')


if __name__ == "__main__":
    s = Server()
    start_server = websockets.serve(s.listen_socket, ['0.0.0.0'], DEFAULT_PORT)
    scoring.score(['rr', 'rr'])  # Compile Numba code
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

    # TODO: cursor and grabbed piece broadcasting
    # TODO: serversize babylon
