# TODO: Thread safety, locks? What's that?
# TODO: No exception handling, speedrun coding mode let's goo

import asyncio
import json
import random
import time
import traceback
import uuid
import websockets

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

    def put_piece(self, idx, pos, rot):
        assert 0 <= idx < len(self.p_descriptions)
        assert 0 <= pos[0] <= self.h
        assert 0 <= pos[1] <= self.w
        assert self.p_positions[idx] is None
        assert self.field[pos[0]][pos[1]] == 'empty'
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

    def score(self, f, heuristic=True):
        t_start = time.monotonic()
        colors = ['B', 'G', 'Y']
        scores = {x: 0 for x in colors}
        f = ['b' * len(f[0])] + f + ['r' * len(f[0])]
        f = ['b' + x + 'b' for x in f]

        # Brute force implementation that turned out to be incredibly slow
        D_Is = [ 0, -1, -1, -1,  0, +1, +1, +1]
        D_Us = [+1, +1,  0, -1, -1, -1,  0, +1]
        o = [[False] * len(x) for x in f]
        for start_i in range(1, len(f) - 1):
            for start_u in range(1, len(f[0]) - 1):
                asyncio.sleep(0)  # Temporarily allow context switching
                color = f[start_i][start_u]
                if color not in ['B', 'G', 'Y']:
                    continue
                if heuristic:
                    neighbors = sum([f[start_i + D_Is[y]][start_u + D_Us[y]] == color for y in range(8)])
                    if neighbors > 3:
                        break
                pos_i, pos_u = start_i, start_u
                st = [-1]
                while len(st):
                    scores[color] = max(scores[color], len(st))
                    bite_head = True
                    o[pos_i][pos_u] = True
                    for dir in range(st[-1] + 1, 8):
                        d_i: int = D_Is[dir]
                        d_u: int = D_Us[dir]
                        if f[pos_i + d_i][pos_u + d_u] == color and not o[pos_i + d_i][pos_u + d_u]:
                            st[-1] = dir
                            st.append(-1)
                            pos_i += d_i
                            pos_u += d_u
                            bite_head = False
                            break
                    if bite_head:
                        st.pop()
                        o[pos_i][pos_u] = False
                        if len(st) == 0:
                            break
                        pos_i -= D_Is[st[-1]]
                        pos_u -= D_Us[st[-1]]

        print(f'Scoring took {(time.monotonic() - t_start) * 1000:.3f}ms')
        scores['total'] = sum(scores.values())
        return scores


class GameServerMode(Game):
    def __init__(self):
        super().__init__()
        self.players: dict[str, Client] = {}


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
            await self.player_to_room(sid, game_id)
            print(f' {sid} Hosted game {game_id}')
        assert len(self.games[game_id].players.keys()) < 3
        self.games[game_id].players[sid] = self.clients[sid]
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
        g.put_piece(idx, pos, rot)
        await c.send_stuff({'cmd': 'msg', 'msg': 'Placement successful'})

        # Push this info
        for c in g.players.values():
            sid = c.client_id
            await self.cmd_board(sid)
            await self.cmd_pieces(sid)

        if g.is_game_over():
            await asyncio.sleep(0)
            score = g.score(g.get_colored_state())
            for c in g.players.values():
                await c.send_stuff({'cmd': 'game_over', 'score': score})
            game_id = c.game
            for c in g.players.keys():
                self.clients[c].game = None
            del self.games[game_id]
            print(f' {c} Ended game {game_id} with score {score}')

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
            del self.games[c.game].players[c.client_id]
            c.game = None
        del self.clients[c.client_id]
        print(f' {c.client_id} Disconnected')


if __name__ == "__main__":
    s = Server()
    start_server = websockets.serve(s.listen_socket, ['localhost', '0.0.0.0'], DEFAULT_PORT)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

    # TODO: cursor and grabbed piece broadcasting
    # TODO: turn-based
    # TODO: serversize babylon
