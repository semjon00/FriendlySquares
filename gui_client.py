import asyncio
import json

import pygame
import websockets

from constants import DEFAULT_PORT, PROTOCOL_VERSION


class Connector:
    def __init__(self):
        self.websocket = None

    async def send(self, msg):
        assert self.websocket is not None
        await self.websocket.send(json.dumps(msg))

    async def activate(self, where):
        self.deactivate()
        if where == 'l':
            where = 'localhost'
        if ':' not in where:
            where = f'{where}:{DEFAULT_PORT}'
        self.websocket = await websockets.connect(f"ws://{where}", open_timeout=1.0)
        await self.send({'cmd': 'version', 'version': PROTOCOL_VERSION})

    def deactivate(self):
        if self.websocket is not None:
            self.websocket.close()
            self.websocket = None

    async def messages(self):
        # My eyes need bleach. Now yours probably need it too :)
        while True:
            try:
                packet = await asyncio.wait_for(self.websocket.recv(), timeout=0.0025)
                yield json.loads(packet)
            except asyncio.TimeoutError:
                return


class Phase:
    def __init__(self):
        self.finished = False
        self.result = None

    async def prep(self): pass
    async def process_event(self, screen): pass
    def draw(self, screen): pass


class TextInputPhase(Phase):
    def __init__(self, my_text):
        super().__init__()
        self.my_text = my_text
        self.finished = False
        self.result = ''
        self.font = pygame.font.SysFont("monospace", 32, bold=True)

    async def process_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.finished = True
                return
            elif event.key == pygame.K_BACKSPACE:
                self.result = self.result[:-1]
            elif event.key == pygame.K_ESCAPE:
                self.result = ''
            else:
                key = event.unicode
                is_allowed = len(key) == 1 and (key[0].isalnum() or key[0] in '[].:')
                if is_allowed:
                    self.result += event.unicode

    def draw(self, screen):
        background = pygame.Surface(screen.get_size())
        background = background.convert()
        background.fill((250, 250, 250))
        text_surf = self.font.render(self.my_text, True, (31, 31, 31))
        background.blit(text_surf, (100, 100))
        draw_text = self.result if len(self.result) < 17 else '\u2026' + self.result[-15:]
        text_surf = self.font.render(draw_text, True, (245, 125, 31))
        background.blit(text_surf, (100, 150))
        screen.blit(background, (0, 0))


class GameState:
    def __init__(self):
        self.board = None
        self.pieces = None
        self.pieces_pos = {}
        self.rotations = {}
        self.piece_size = 64
        self.selected_piece = None
        self.score = None  # Set if game over

    def set_pieces(self, pieces):
        is_new = self.pieces is None

        self.pieces = {int(k): v for (k, v) in pieces.items()}
        # TODO: should be server-size
        if is_new:
            for i, desc in self.pieces.items():
                pos_i, pos_u = i // 8, i % 8
                self.pieces_pos[i] = (88 + pos_u * 80, 430 + 32 + pos_i * 80)
                self.rotations[i] = 0

    def locate_piece_pos(self, click_pos):
        for i, pos in self.pieces_pos.items():
            hit = pos[0] + 3 <= click_pos[0] < pos[0] + self.piece_size - 3 and \
                  pos[1] + 3 <= click_pos[1] < pos[1] + self.piece_size - 3
            if hit:
                return i
        return None

    def board_pos(self, i, u):
        return 152 + u * 72, 32 + i * 72

    def locate_board_pos(self, click_pos):
        for i in range(len(self.board) // 2):
            for u in range(len(self.board[0]) // 2):
                pos = self.board_pos(i, u)
                hit = pos[0] + 3 <= click_pos[0] < pos[0] + self.piece_size - 3 and \
                      pos[1] + 3 <= click_pos[1] < pos[1] + self.piece_size - 3
                if hit:
                    return i, u
        return None

class GamingPhase(Phase):
    def __init__(self, connector):
        super().__init__()
        self.finished = False
        self.connector = connector
        self.gs = GameState()
        self.font = pygame.font.SysFont("monospace", 32, bold=True)

    async def process_message(self, msg):
        match msg['cmd']:  # Do you feel the déjà vu?
            case 'board':
                self.gs.board = msg['board']
            case 'pieces':
                self.gs.set_pieces(msg['pieces'])
            case 'game_over':
                self.gs.score = msg['score']
            case 'msg':
                pass  # Not implemented
            case 'version':
                assert msg['version'] == PROTOCOL_VERSION
            case 'op':
                pass  # Not implemented

    async def prep(self):
        async for msg in self.connector.messages():
            await self.process_message(msg)

    async def process_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.gs.selected_piece is not None:
                    hit = self.gs.locate_board_pos(pygame.mouse.get_pos())
                    if hit is not None:
                        # Setting piece
                        await self.connector.send(
                            {'cmd': 'put', 'idx': self.gs.selected_piece, 'pos': (hit[0], hit[1]),
                             'rot': self.gs.rotations[self.gs.selected_piece]}
                        )
                        self.gs.selected_piece = None
                        return

                hit = self.gs.locate_piece_pos(pygame.mouse.get_pos())
                if hit is None or hit == self.gs.selected_piece:
                    self.gs.selected_piece = None
                else:
                    self.gs.selected_piece = hit
            if event.button == 3:
                if self.gs.selected_piece is not None:
                    self.gs.rotations[self.gs.selected_piece] += 1
        if event.type == pygame.KEYDOWN:
            self.finished = True

    def render_piece(self, description, size, rotation=0):
        for _ in range(rotation % 4):
            description = description[1] + description[3] + description[0] + description[2]
        if 'w' in description:
            border = 0
        else:
            border = size // 16
        surf = pygame.Surface((size, size))
        surf.fill((128, 128, 128))
        half_size = (size + 1) // 2
        points = [(border, border), (half_size, border), (border, half_size), (half_size, half_size)]
        colors = {'B': (53, 85, 122), 'G': (81, 157, 60), 'Y': (187, 187, 72), 'r': (139, 65, 62), 'w': (240, 240, 240)}
        for i in range(4):
            color = colors[description[i]]
            pos = list(points[i]) + [half_size - border, half_size - border]
            pygame.draw.rect(surf, color, tuple(pos))
        return surf

    def render_score_box(self, score):
        box = pygame.Surface((400, 400), pygame.SRCALPHA)
        box.fill((32, 32, 32, 128))
        for vals in [('B', (53, 85, 122), (60, 100)),
                     ('G', (81, 157, 60), (60, 150)),
                     ('Y', (187, 187, 72), (60, 200)),
                     ('total', (32, 32, 32), (60, 300))]:
            t = {'B': 'Blue', 'G': 'Green', 'Y': 'Yellow', 'total': 'Total'}[vals[0]]
            text = f'{t} score: {score[vals[0]]}'
            text_surf = self.font.render(text, True, vals[1])
            box.blit(text_surf, (vals[2][0], vals[2][1]))
        return box

    def draw(self, screen):
        # TODO: fancy cursors

        background = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        background = background.convert()
        background.fill((250, 250, 250))

        # Drawing board
        b = self.gs.board
        if b is not None:
            for i in range(len(b) // 2):
                for u in range(len(b[0]) // 2):
                    desc = b[i * 2][u * 2: 2 + u * 2] + b[1 + i * 2][u * 2: 2 + u * 2]
                    render = self.render_piece(desc, 64)
                    background.blit(render, self.gs.board_pos(i, u))

        # Drawing free pieces
        p = self.gs.pieces
        if p is not None:
            for i, desc in p.items():
                if i == self.gs.selected_piece:
                    posdraw = self.gs.pieces_pos[i]
                    posdraw = tuple([posdraw[0] - 8, posdraw[1] - 8, 64 + 16, 64 + 16])
                    pygame.draw.rect(background, (48, 48, 48), posdraw)

                render = self.render_piece(desc, 64, self.gs.rotations[i])
                background.blit(render, self.gs.pieces_pos[i])

        # Draw game over score
        if self.gs.score is not None:
            score_box = self.render_score_box(self.gs.score)
            background.blit(score_box, (200, 200))

        screen.blit(background, (0, 0))


class Gui:
    def __init__(self):
        pygame.init()
        self.connector = Connector()
        self.phase_i = None
        self.phase: Phase | None = None
        self.screen = None

    async def reset_phase(self):
        self.screen = pygame.display.set_mode([500, 300])
        self.phase_i = 0
        self.phase = TextInputPhase('Enter server IP:')

    async def switch_phase(self):
        result: str = self.phase.result
        match self.phase_i:
            case 0:
                try:
                    await self.connector.activate(result)
                    self.phase_i = 1
                    self.phase = TextInputPhase('Enter room:')
                except:
                    await self.reset_phase()
            case 1:
                self.screen = pygame.display.set_mode([800, 800])
                await self.connector.send({'cmd': 'room', 'game_id': result})
                self.phase_i = 2
                self.phase = GamingPhase(self.connector)
            case 2:
                self.screen = pygame.display.set_mode([500, 300])
                self.phase_i = 1
                self.phase = TextInputPhase('Enter room:')

    async def run(self):
        clock = pygame.time.Clock()

        running = True
        await self.reset_phase()
        while running:
            await self.phase.prep()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                await self.phase.process_event(event)
            self.phase.draw(self.screen)
            if self.phase.finished:
                await self.switch_phase()
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()


if __name__ == '__main__':
    asyncio.run(Gui().run())
