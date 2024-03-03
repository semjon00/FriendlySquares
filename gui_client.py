# python -m nuitka --show-modules --include-package=pygame,websockets,pyperclip --include-data-dir=./res/=res --windows-icon-from-ico=res/green_tile.png --standalone --onefile --disable-console gui_client.py

import asyncio
import json
import random
import time
from enum import Enum

import pygame
import websockets

from constants import DEFAULT_PORT, GAME_VERSION

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
        ts = time.time()
        ok = False
        while time.time() - ts < 1.0:
            if ok:
                break
            async for msg in self.messages():
                if msg['cmd'] == 'version':
                    if msg['version'] != GAME_VERSION:  # Strict, can relax in the future
                        await self.websocket.close()
                        raise Exception('Server and client versions do not match.')
                    else:
                        ok = True
                        break
        if not ok:
            raise Exception('Server and client versions do not match.')


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
            elif (event.key == pygame.K_v) and (event.mod & pygame.KMOD_CTRL):
                import pyperclip
                self.result += pyperclip.paste()
            elif (event.key == pygame.K_x) and (event.mod & pygame.KMOD_CTRL):
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


class RenderEngine(Enum):
    SIMPLE = 1
    GEMS = 2


class TextureProvider:
    def __init__(self):
        self.loaded: dict[str, pygame.Surface] = {}

    def __getitem__(self, key):
        if not self.present(key):
            self.loaded[key] = pygame.image.load(f'res/{key}.png')
        return self.loaded[key]

    def __setitem__(self, key, value):
        self.loaded[key] = value.copy()

    def present(self, key):
        return key in self.loaded

    def clear_cache(self):
        self.loaded.clear()

class GameState:
    def __init__(self):
        self.p_descriptions = []
        self.p_positions: list[dict] = []
        self.player_data: dict[str, dict] = {}
        self.me = None

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
    def __init__(self, connector, tp):
        super().__init__()
        self.finished = False
        self.connector = connector
        self.gs = GameState()
        self.font = pygame.font.SysFont("monospace", 32, bold=True)

        self.re = RenderEngine.GEMS
        self.tp: TextureProvider = tp

    async def process_message(self, msg):
        match msg['cmd']:  # Do you feel the déjà vu?
            case 'positions':
                self.gs.set_positions(msg['positions'])
            case 'descriptions':
                self.gs.set_descriptions(msg['descriptions'])
            case 'player_data':
                self.gs.player_data = msg['player_data']
            case 'you':
                self.gs.me = msg['you']
            case 'game_over':
                self.gs.score = msg['score']
            case 'msg':
                pass  # Not implemented
            case 'op':
                pass  # Not implemented

    async def prep(self):
        async for msg in self.connector.messages():
            await self.process_message(msg)

    async def process_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            if self.gs.score is None:
                mouse_position = pygame.mouse.get_pos()
                await self.connector.send({'cmd': 'curpos', 'curpos': mouse_position})
            else:
                pass  # Not implemented ;(
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
                if hit is None or hit == self.gs.selected_piece or self.gs.p_positions[hit]['type'] != 'free':
                    self.gs.selected_piece = None
                else:
                    self.gs.selected_piece = hit
            if event.button == 3:
                if self.gs.selected_piece is not None:
                    self.gs.p_positions[self.gs.selected_piece]['r'] += 1
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_v:
                self.re = RenderEngine.SIMPLE if self.re == RenderEngine.GEMS else RenderEngine.GEMS
            if self.gs.score is not None and event.key == pygame.K_ESCAPE:
                self.finished = True

    def render_piece(self, description, piece_i, size, rotation=0):
        if self.re == RenderEngine.GEMS:
            name_id = f'cached_piece_{str(description)}-{piece_i}'
            if not self.tp.present(name_id):
                r = random.Random((piece_i, description))
                surf = pygame.Surface((128, 128), pygame.SRCALPHA)
                poss = (0, 0), (64, 0), (0, 64), (64, 64)
                for i in range(4):
                    fn = {'Y': 'yellow', 'G': 'green', 'B': 'blue', 'w': 'white', 'r': 'brick'}[description[i]] + '_tile'
                    if description[i] in ['Y', 'G', 'B']:
                        fn += str(r.randint(1, 5))
                    texture: pygame.Surface = self.tp[fn]
                    texture_part = texture.subsurface((poss[i][0], poss[i][1], 64, 64))
                    surf.blit(texture_part, poss[i])
                surf = surf.subsurface((5, 5, 128 - 10, 128 - 10))
                surf = pygame.transform.smoothscale(surf, (57, 57))  # Blur, basically
                surf = pygame.transform.smoothscale(surf, (64, 64))
                self.tp[name_id] = surf
            surf = pygame.transform.rotate(self.tp[name_id], (rotation * 90) % 360)
            return surf
        elif self.re == RenderEngine.SIMPLE:
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

    def render_cursor(self, color):
        if self.re == RenderEngine.GEMS:
            name_id = f'cached_cursor_{str(color)}'
            if not self.tp.present(name_id):
                cursor = self.tp['cursor'].copy()
                color += [255]
                color[1] = 255
                for x in range(cursor.get_width()):
                    for y in range(cursor.get_height()):
                        c = cursor.get_at((x, y))  # Preserve the alpha value.
                        c = [int(c[i] * color[i] / 256) for i in range(4)]
                        cursor.set_at((x, y), c)  # Set the color of the pixel.
                cursor = pygame.transform.smoothscale(cursor, (24, 24))
                self.tp[name_id] = cursor
            return self.tp[name_id]
        elif self.re == RenderEngine.SIMPLE:
            surf = pygame.Surface((64, 64), pygame.SRCALPHA)
            brigth_color = tuple([int(c * 0.85) for c in color])
            dim_color = tuple([int(c * 0.70) for c in color])
            pygame.draw.rect(surf, brigth_color, (0, 0, 16, 16))
            pygame.draw.rect(surf, dim_color, (0, 0, 8, 24))
            pygame.draw.rect(surf, dim_color, (0, 0, 24, 8))
            pygame.draw.rect(surf, brigth_color, (0, 0, 4, 4))
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
            if self.re == RenderEngine.GEMS:
                posdraw = self.gs.p_positions[self.gs.selected_piece]
                posdraw = self.gs.laying_pos_px(posdraw['ii'], posdraw['uu'])
                posdraw = tuple([posdraw[0] - 6, posdraw[1] - 6, 64 + 12, 64 + 12])
                pygame.draw.rect(background, (128, 128, 128, 128), posdraw)
            elif self.re == RenderEngine.SIMPLE:
                posdraw = self.gs.p_positions[self.gs.selected_piece]
                posdraw = self.gs.laying_pos_px(posdraw['ii'], posdraw['uu'])
                posdraw = tuple([posdraw[0] - 6, posdraw[1] - 6, 64 + 12, 64 + 12])
                pygame.draw.rect(background, (64, 64, 64), posdraw)

        # Draw pieces
        filled = set()
        for piece_i in range(len(self.gs.p_positions)):
            desc = self.gs.p_descriptions[piece_i]
            pos = self.gs.p_positions[piece_i]
            render = self.render_piece(desc, piece_i,64, rotation=pos['r'])
            pos_px = None
            filled.add((pos['ii'], pos['uu']))
            if pos['type'] == 'board':
                pos_px = self.gs.board_pos_px(pos['ii'], pos['uu'])
            elif pos['type'] == 'free':
                pos_px = self.gs.laying_pos_px(pos['ii'], pos['uu'])
            background.blit(render, pos_px)

        # Draw board
        for i in range(5):
            for u in range(7):
                if (i, u) in filled:
                    continue
                pos_px = self.gs.board_pos_px(i, u)
                render = self.render_piece('wwww', 0, 64)
                background.blit(render, pos_px)

        # Draw cursors
        for player in self.gs.player_data.keys():
            data = self.gs.player_data[player]
            render = self.render_cursor(data['color'])
            if self.gs.me == player:
                pygame.mouse.set_cursor(pygame.cursors.Cursor((0, 0), render))
            else:
                # pos = data['curpos'] if self.gs.me != player else pygame.mouse.get_pos()
                if self.gs.score is None and 'curpos' in data and data['curpos'] is not None:
                    background.blit(render, data['curpos'])

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
        self.tp = TextureProvider()

    async def reset_phase(self):
        self.screen = pygame.display.set_mode([500, 300])
        self.phase_i = 0
        self.phase = TextInputPhase('Enter server IP:')

    async def switch_phase(self):
        result: str = self.phase.result
        self.tp.clear_cache()
        # pygame.mouse.set_visible(True)
        match self.phase_i:
            case 0:
                try:
                    await self.connector.activate(result)
                    self.phase_i = 1
                    self.phase = TextInputPhase('Enter room:')
                except Exception as e:
                    if e.__class__ is asyncio.exceptions.TimeoutError:
                        print('Connection timed out')
                    if 'do not match' in str(e):  # Production-grade code right here /s
                        print(e)
                    await self.reset_phase()
            case 1:
                self.screen = pygame.display.set_mode([800, 800])
                if result.startswith('op'):
                    token = result.split(':')[0][2:]
                    await self.connector.send({'cmd': 'op', 'token': token})
                    result = result.split(':')[1]
                await self.connector.send({'cmd': 'room', 'game_id': result})
                self.phase_i = 2
                self.phase = GamingPhase(self.connector, self.tp)
                # pygame.mouse.set_visible(False)
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
        # Why doesn't it work?!
        # pygame.display.set_icon(pygame.image.load('res/green_tile.png'))
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
            clock.tick(91)
        pygame.quit()


if __name__ == '__main__':
    asyncio.run(Gui().run())
    # TODO: Copy-paste
    # TODO: In case of crash
