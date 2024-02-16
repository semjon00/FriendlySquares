import asyncio
import json
import pygame
import websockets
import select

from constants import DEFAULT_PORT, PROTOCOL_VERSION

class Phase:
    def __init__(self):
        self.finished = False
        self.result = None

    async def prep(self): pass
    async def process_event(self, screen): pass
    def draw(self, screen): pass


class ServerSelectPhase(Phase):
    def __init__(self):
        super().__init__()
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
        text_surf = self.font.render('Enter server IP:', True, (31, 31, 31))
        background.blit(text_surf, (100, 100))
        draw_text = self.result if len(self.result) < 17 else '\u2026' + self.result[-15:]
        text_surf = self.font.render(draw_text, True, (245, 125, 31))
        background.blit(text_surf, (100, 150))
        screen.blit(background, (0, 0))


class GamingPhase(Phase):
    def __init__(self):
        super().__init__()
        self.finished = False
        self.websocket = None
        self.dev_patience = -1  # Testing code

    async def activate_connection(self, where):
        if ':' not in where:
            where = f'{where}:{DEFAULT_PORT}'
        self.websocket = await websockets.connect(f"ws://{where}", open_timeout=1.0)
        await self.send_stuff({'cmd': 'version', 'version': PROTOCOL_VERSION})

    async def send_stuff(self, msg):
        assert self.websocket is not None
        await self.websocket.send(json.dumps(msg))

    async def process_msg(self, msg):
        self.dev_patience = 100  # Testing code

    async def prep(self):
        # My eyes need bleach. Now yours probably need it too :)
        while True:
            try:
                packet = await asyncio.wait_for(self.websocket.recv(), timeout=0.0025)
                await self.process_msg(json.loads(packet))
            except asyncio.TimeoutError:
                break

    async def process_event(self, event):
        # Testing code
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_t:
                await self.websocket.send(json.dumps({'cmd': 'op', 'token': 'test'}))

    def render_piece(self, description, size):
        border = size // 16
        surf = pygame.Surface((size, size))
        surf.fill((128, 128, 128))
        half_size = (size + 1) // 2
        points = [(border, border), (half_size, border), (border, half_size), (half_size, half_size)]
        colors = {'B': (53, 85, 122), 'G': (81, 157, 60), 'Y': (187, 187, 72), 'R': (179, 69, 82)}
        for i in range(4):
            color = colors[description[i]]
            pos = list(points[i]) + [half_size - border, half_size - border]
            pygame.draw.rect(surf, color, tuple(pos))
        return surf

    def draw(self, screen):
        background = pygame.Surface(screen.get_size())
        background = background.convert()
        background.fill((250, 250, 250))

        # Testing code
        self.dev_patience -= 1
        if self.dev_patience >= 0:
            background.blit(self.render_piece('YGBY', 64), (30, 30))
        pygame.draw.rect(background, (255, 0, 0), (300, 300, 100, 100))
        screen.blit(background, (0, 0))


class Gui:
    def __init__(self):
        pygame.init()
        self.phase_i = None
        self.phase: Phase | None = None
        self.screen = None

    async def switch_phase(self, num):
        if self.phase_i == num:
            return
        self.phase_i = num
        if num == 1:
            result = self.phase.result
            self.screen = pygame.display.set_mode([800, 800])
            self.phase = GamingPhase()
            try:
                await self.phase.activate_connection(result)
            except Exception as e:
                await self.switch_phase(0)
        else:
            self.screen = pygame.display.set_mode([500, 300])
            self.phase = ServerSelectPhase()


    async def run(self):
        clock = pygame.time.Clock()

        running = True
        await self.switch_phase(0)
        while running:
            await self.phase.prep()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                await self.phase.process_event(event)
            self.phase.draw(self.screen)
            if self.phase.finished:
                await self.switch_phase((self.phase_i + 1) % 2)
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()


if __name__ == '__main__':
    asyncio.run(Gui().run())
