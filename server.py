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
from constants import DEFAULT_PORT, GAME_VERSION


class CustomDict:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        else:
            raise AttributeError(f"'CustomDict' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __dict__(self):
        return self._data


class PiecePos(CustomDict):
    def __init__(self, type, ii, uu, r):
        super().__init__({'type': type, 'ii': ii, 'uu': uu, 'r': r})


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
        self.p_descriptions, self.p_positions = self.generate_pieces()

        self.h, self.w = 5, 7
        self.occupied: list[list[bool]] = [[False for _ in range(self.w)] for _ in range(self.h)]
        self.players: list[str] = []
        self.player_data: dict[str, dict] = {}
        self.cur_player = None
        self.red_attack(5)

    def generate_pieces(self):
        colors = 'BGY'
        descriptions = []
        for leading in range(3):
            for prototype, times in [("0012", 2), ("0221", 1), ("0002", 2), ("0011", 2), ("0110", 2), ("0000", 1)]:
                for _ in range(times):
                    desc = "".join([colors[(int(prototype[i]) + leading) % 3] for i in range(4)])
                    desc = self.rotate_piece(desc, random.randint(0, 3))
                    descriptions.append(desc)
        random.shuffle(descriptions)

        positions = []
        for i in range(len(descriptions)):
            pos_i, pos_u = float(i // 8), float(i % 8)
            pos_i += random.uniform(-0.1, +0.1)
            pos_u += random.uniform(-0.1, +0.1)
            positions.append(PiecePos('free', float(pos_i), float(pos_u), random.randint(0, 3)))
        return descriptions, positions

    def red_attack(self, n):
        for pp in range(n):
            for attempt in range(1000):  # Deadlock protection
                i = random.sample(range(self.h * self.w), 1)[0]
                if not self.occupied[i // self.w][i % self.w]:
                    self.occupied[i // self.w][i % self.w] = True
                    self.p_positions.append(PiecePos('board', i // self.w, i % self.w, 0))
                    break
            assert len(self.p_descriptions) + 1 == len(self.p_positions)
            self.p_descriptions.append('rrrr')

    def put_piece(self, idx, pos, rot, player_id):
        assert 0 <= idx < len(self.p_descriptions)
        assert 0 <= pos[0] <= self.h
        assert 0 <= pos[1] <= self.w
        assert self.p_positions[idx].type != 'board'
        assert not self.occupied[pos[0]][pos[1]]
        assert self.cur_player == player_id
        self.next_cur_player()
        self.p_positions[idx] = PiecePos('board', pos[0], pos[1], rot)
        self.occupied[pos[0]][pos[1]] = True

    def is_game_over(self):
        are_all_placed = all([x.type == 'board' for x in self.p_positions])
        is_all_occupied = all([all(row) for row in self.occupied])
        return are_all_placed or is_all_occupied

    def rotate_piece(self, d, times=1):
        # Counter-clockwise
        for _ in range(times % 4):
            d = d[1] + d[3] + d[0] + d[2]
        return d

    def get_colored_state(self):
        f = ['w' * (2 * self.w) for _ in range(2 * self.h)]
        for i in range(len(self.p_positions)):
            if not self.p_positions[i].type == 'board':
                continue
            pos = self.p_positions[i]
            desc = self.rotate_piece(self.p_descriptions[i], times=pos.r)
            fi, fu = pos.ii * 2, pos.uu * 2
            f[fi] = f[fi][:fu] + desc[:2] + f[fi][fu + 2:]
            f[fi + 1] = f[fi + 1][:fu] + desc[2:] + f[fi + 1][fu + 2:]
        return f

    def add_player(self, player_id: str):
        # You know what? I think we can drop the requirement to have 3 people max!
        self.players.append(player_id)

        def dist(c1, c2):
            if c1 is None or c2 is None:
                return 1000
            return sum([abs(c1[i] - c2[i]) for i in range(3)])
        color_rand = random.Random(player_id)
        def rand_color():
            color_base = color_rand.uniform(-128, 128)
            color_base = [255, 0, 255 - color_base] if color_base >= 0 else [255 + color_base, 0, 255]
            vibrancy = color_rand.uniform(0.4, 0.8)
            darken = color_rand.uniform(0.6, 1.0)
            return tuple([int((256 * (1 - vibrancy) + x * vibrancy) * darken) for x in color_base])
        def nice_color():
            best_c = None
            best_dist = -1
            patinence = 30
            while best_dist < 50.0 and patinence >= 0:
                patinence -= 1
                c = rand_color()
                this_dist = min([dist(p['color'], c) for p in self.player_data.values()] + [100.0])
                if this_dist > best_dist:
                    best_c = c
                    best_dist = this_dist
            return best_c
        data = {'curpos': None, 'color': nice_color()}
        self.player_data[player_id] = data
        if self.cur_player is None:
            self.cur_player = self.players[0]

    def remove_player(self, player_id: str):
        if self.cur_player == player_id:
            self.next_cur_player()
        self.players.remove(player_id)
        del self.player_data[player_id]
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
        await self.clients[sid].send_stuff({'cmd': 'you', 'you': sid})
        await self.cmd_positions(sid)
        await self.cmd_descriptions(sid)

    async def cmd_positions(self, sid):
        c = self.clients[sid]
        g = self.games[c.game]
        await c.send_stuff({'cmd': 'positions', 'positions': [x.__dict__() for x in g.p_positions]})

    async def cmd_descriptions(self, sid):
        c = self.clients[sid]
        g = self.games[c.game]
        await c.send_stuff({'cmd': 'descriptions', 'descriptions': g.p_descriptions})

    async def cmd_put(self, sid, idx, pos, rot):
        c = self.clients[sid]
        g = self.games[c.game]
        g.put_piece(idx, pos, rot, sid)
        await c.send_stuff({'cmd': 'msg', 'msg': 'Placement successful'})

        # Push this info
        for c in g.clients.values():
            sid = c.client_id
            await self.cmd_positions(sid)

        if g.is_game_over():
            await asyncio.sleep(0)
            t_start = time.monotonic()
            score = scoring.score(g.get_colored_state(), accurate=False)
            print(f'Game {c.game} Scoring took {(time.monotonic() - t_start) * 1000:.3f}ms')
            for c in g.clients.values():
                await c.send_stuff({'cmd': 'game_over', 'score': score})
            game_id = c.game
            for c in g.clients.keys():
                self.clients[c].game = None
            del self.games[game_id]
            print(f'Ended game {game_id} with score {score}')

    async def cmd_curpos(self, sid, pos):
        c = self.clients[sid]
        if c.game is None:
            # Cursor positions are not implemented for the gameover screen
            return
        g = self.games[c.game]
        g.player_data[sid]['curpos'] = pos
        # Yikes, this will spawn some spam. Whatever.
        for c in g.clients.values():
            await c.send_stuff({'cmd': 'player_data', 'player_data': g.player_data})

    async def process_message(self, client_id, msg):
        match msg['cmd']:
            case 'msg':
                print(f" {client_id} Tells us: '{msg['msg']}'")
            case 'room':
                await self.player_to_room(client_id, msg['game_id'])
                print(f" {client_id} Joined game {msg['game_id']}")
            case 'positions':
                await self.cmd_positions(client_id)
                print(f" {client_id} Requested positions")
            case 'descriptions':
                await self.cmd_descriptions(client_id)
                print(f" {client_id} Requested positions")
            case 'put':
                await self.cmd_put(client_id, msg['idx'], msg['pos'], msg['rot'])
                print(f" {client_id} Put piece")
            case 'curpos':
                await self.cmd_curpos(client_id, msg['curpos'])
            case 'op':
                if msg['token'] == self.op_token:
                    self.clients[client_id].is_op = True
                    print(f' {client_id} OPPED')
                else:
                    print(f' {client_id} Not opped')
                await self.clients[client_id].send_stuff({'cmd': 'op', 'status': self.clients[client_id].is_op})
            case _:
                raise NotImplemented('Weird command')

    async def listen_socket(self, websocket, path):
        c = Client(websocket, path)
        await c.send_stuff({'cmd': 'version', 'version': GAME_VERSION})
        c = self.clients[c.client_id] = c
        print(f' {c.client_id} Connected')
        try:
            async for message_raw in c.websocket:
                message = json.loads(message_raw)
                try:
                    await self.process_message(c.client_id, message)
                except:
                    print(f' {c.client_id} ERR {traceback.format_exc()}')
                    await c.send_stuff({'cmd': 'msg', 'msg': f'Erroneous command', 'yours': message})
        except websockets.exceptions.ConnectionClosedError:
            pass
        if c.game is not None:
            self.games[c.game].remove_player(c.client_id)
            c.game = None
            # The game itself might persist, even if there are zero players - this is not a bug, this is a feature!
        del self.clients[c.client_id]
        print(f' {c.client_id} Disconnected')


if __name__ == "__main__":
    print(f'FriendlySquares server {GAME_VERSION} has started')
    s = Server()
    start_server = websockets.serve(s.listen_socket, ['0.0.0.0'], DEFAULT_PORT)
    scoring.score(['rr', 'rr'])  # Compile Numba code
    print(f'Ready to accept connections')
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

    # TODO: grabbed piece broadcasting
    # TODO: serversize babylon
    # TODO: current_player identifier
    # TODO: timeout - random placement - 30sek
