# python -m nuitka --include-package=pygame --include-package=websockets --standalone --onefile --disable-console gui_client.py

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
            where = '127.0.0.1'  # 'localhost' does not work for Windows
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
        self.p_descriptions = []
        self.p_positions: list[dict] = []

        self.piece_size = 64
        self.selected_piece = None
        self.score = None  # Set only if game over

    def set_positions(self, positions):
        self.p_positions = positions

    def set_descriptions(self, descriptions):
        self.p_descriptions = descriptions

    def locate_piece_by_px_pos(self, click_pos):
        for i, pos in enumerate(self.p_positions):
            pos_px = None
            if pos['type'] == 'board':
                pos_px = self.board_pos_px(pos['ii'], pos['uu'])
            elif pos['type'] == 'free':
                pos_px = self.laying_pos_px(pos['ii'], pos['uu'])
            if pos_px is None:
                continue
            hit = (pos_px[0] + 3 <= click_pos[0] < pos_px[0] + self.piece_size - 3 and
                   pos_px[1] + 3 <= click_pos[1] < pos_px[1] + self.piece_size - 3)
            if hit:
                return i
        return None

    def board_cell_by_px_pos(self, click_pos):
        for i in range(5):
            for u in range(7):
                pos_px = self.board_pos_px(i, u)
                hit = (pos_px[0] + 3 <= click_pos[0] < pos_px[0] + self.piece_size - 3 and
                       pos_px[1] + 3 <= click_pos[1] < pos_px[1] + self.piece_size - 3)
                if hit:
                    return i, u
        return None

    def board_pos_px(self, i, u):
        return 152 + u * 72, 32 + i * 72

    def laying_pos_px(self, i, u):
        return 88 + u * 80, 430 + 32 + i * 80


class GamingPhase(Phase):
    def __init__(self, connector):
        super().__init__()
        self.finished = False
        self.connector = connector
        self.gs = GameState()
        self.font = pygame.font.SysFont("monospace", 32, bold=True)

    async def process_message(self, msg):
        match msg['cmd']:  # Do you feel the déjà vu?
            case 'positions':
                self.gs.set_positions(msg['positions'])
            case 'descriptions':
                self.gs.set_descriptions(msg['descriptions'])
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
                click_pos = pygame.mouse.get_pos()
                if self.gs.selected_piece is not None:
                    hit = self.gs.board_cell_by_px_pos(click_pos)
                    if hit is not None and self.gs.locate_piece_by_px_pos(click_pos) is None:
                        # Setting piece
                        await self.connector.send(
                            {'cmd': 'put', 'idx': self.gs.selected_piece, 'pos': (hit[0], hit[1]),
                             'rot': self.gs.p_positions[self.gs.selected_piece]['r']}
                        )
                        self.gs.selected_piece = None
                        return

                hit = self.gs.locate_piece_by_px_pos(pygame.mouse.get_pos())
                if hit is None or hit == self.gs.selected_piece:
                    self.gs.selected_piece = None
                else:
                    self.gs.selected_piece = hit
            if event.button == 3:
                if self.gs.selected_piece is not None:
                    self.gs.p_positions[self.gs.selected_piece]['r'] += 1
        if event.type == pygame.KEYDOWN:
            if self.gs.score is not None:
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
        box.fill((64, 64, 64, 196))
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

        # Drawing selected piece box
        if self.gs.selected_piece is not None:
            posdraw = self.gs.p_positions[self.gs.selected_piece]
            posdraw = self.gs.laying_pos_px(posdraw['ii'], posdraw['uu'])
            posdraw = tuple([posdraw[0] - 8, posdraw[1] - 8, 64 + 16, 64 + 16])
            pygame.draw.rect(background, (48, 48, 48), posdraw)

        # Draw board
        for i in range(5):
            for u in range(7):
                pos_px = self.gs.board_pos_px(i, u)
                render = self.render_piece('wwww', 64)
                background.blit(render, pos_px)

        # Draw pieces
        for piece_i in range(len(self.gs.p_positions)):
            desc = self.gs.p_descriptions[piece_i]
            pos = self.gs.p_positions[piece_i]
            render = self.render_piece(desc, 64, rotation=pos['r'])
            pos_px = None
            if pos['type'] == 'board':
                pos_px = self.gs.board_pos_px(pos['ii'], pos['uu'])
            elif pos['type'] == 'free':
                pos_px = self.gs.laying_pos_px(pos['ii'], pos['uu'])
            background.blit(render, pos_px)

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
        splash_text = random.choice([
            'Does not contain GMO!',
            'All the candies will be mine!',
            'Best soundtrack award!',
            'Real treasure was the friends we made along the way',
            'A family-friendly three-way game',
            'Esoteric and weird',
            'Coding is a pain _and_ a bliss, I am hooked',
            'Somebody coded all this, you know...',
            'Sleep > late-night gaming',
            'Take pauses',
            'We both losers, baby',
            'Even more squary than _that_ game!',
            'Do you like the graphics?',
            'My head hurts',
            'pygame.display.set_caption'
        ])
        pygame.display.set_caption(f'FriendlySquares - {splash_text}')
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
