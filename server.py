# TODO: Thread safety, locks? What's that?
# TODO: No exception handling, speedrun coding mode let's goo

import asyncio
import json
import random
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
        self.players: list[Client] = []

        self.h, self.w = 5, 7
        self.field: list[list[int | str]] = [['empty' for _ in range(self.w)] for _ in range(self.h)]
        self.red_attack(5)

    def broadcast_to_players(self, msg):
        for c in self.players:
            c.send_stuff(msg)

    def generate_pieces(self):
        colors = 'BGY'
        pieces = []
        for leading in range(3):
            for prototype, times in [("0012", 2), ("0221", 1), ("0002", 2), ("0011", 2), ("0110", 2), ("0000", 1)]:
                for _ in range(times):
                    pieces.append("".join([colors[(int(prototype[i]) + leading) % 3] for i in range(4)]))
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
        # TODO: turn-based
        self.p_positions[idx] = (pos[0], pos[1])
        self.field[pos[0]][pos[1]] = idx
        self.p_rotations[idx] = rot

        if self.is_game_over():
            score = self.score()
            self.broadcast_to_players(score)

    def is_game_over(self):
        pieces_left = sum([1 if x is not None else 0 for x in self.p_positions])
        empty_spots_left = sum([sum([1 if col == 'empty' else 0 for col in row]) for row in self.field])
        return pieces_left == 0 or empty_spots_left == 0

    def rotate_piece(self, d, times=1):
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

    def score(self):
        # Easy and laggy implementation, but easy
        bs = self.get_colored_state()
        w = len(bs[0])
        h = len(bs)

        colors = 'BGY'
        scores = {x: 0 for x in bs}
        for c in colors:
            for start in range(w * h):
                start_i = start // w
                start_u = start % w
                if bs[start_i][start_u] != c:
                    continue

                dist: list[list[int | None]] = [[1_000_000 for _ in range(w)] for _ in range(h)]
                dist[start_i][start_u] = 0
                for iter in range(w + h + 1):
                    for i in range(h):
                        for u in range(w):
                            if dist[i][u] == 1_000_000 or bs[i][u] != c:
                                continue
                            scores[c] = max(scores[c], dist[i][u])
                            next = dist[i][u] + 1
                            if i > 0:
                                dist[i-1][u] = min(dist[i-1][u], next)
                            if u > 0:
                                dist[i][u - 1] = min(dist[i][u - 1], next)
                            if i < h - 1:
                                dist[i+1][u] = min(dist[i+1][u], next)
                            if u < w - 1:
                                dist[i][u + 1] = min(dist[i][u+1], next)
        # Wow, that's a drop! 6 levels down!
        scores['total'] = sum(scores.values())
        return scores

    # TODO: scoring, disbanding and game over


class Server:
    def __init__(self):
        self.op_token = random.randint(int(1e10), int(9e10))
        print(f'Op token is: {self.op_token}')
        self.clients: dict[str, Client] = {}
        self.games: dict[str, Game] = {}
        self.games_last_id = 0

    async def player_add(self, sid, game_id):
        assert len(self.games[game_id].players) < 1
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

    async def process_message(self, client_id, msg):
        msg = json.loads(msg)
        match msg['cmd']:
            case 'msg':
                print(f" {client_id} Tells us: '{msg['msg']}'")
            case 'host':
                await self.cmd_host(client_id)  # Logs, too
            case 'join':
                await self.player_add(client_id, msg['game_id'])
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
                # TODO: Maybe tell them?
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
            try:
                await self.process_message(c.client_id, message_raw)
            except:
                print(f' {c.client_id} ERR {traceback.print_exc()}')
        print(f' {c.client_id} Disconnected')


if __name__ == "__main__":
    s = Server()
    start_server = websockets.serve(s.listen_socket, "localhost", DEFAULT_PORT, ping_interval=5, ping_timeout=5)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
