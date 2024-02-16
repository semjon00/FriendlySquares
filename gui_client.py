import asyncio
import json
import pygame
import websockets

from constants import DEFAULT_PORT, PROTOCOL_VERSION

class Phase:
    def __init__(self):
        self.finished = False
        self.result = None

    async def process_event(self, screen):
        pass

    def draw(self, screen):
        pass


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
                key = pygame.key.name(event.key)
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
        self.dev_patience = 100  # Testing code
        self.messages_out = None

    async def process_incoming_message(self, msg):
        # Testing code
        self.dev_patience = 100

    async def process_event(self, event):
        # Testing code
        import random
        if random.randint(0, 599) == 0:
            await self.messages_out({'cmd': 'board'})

    def draw(self, screen):
        background = pygame.Surface(screen.get_size())
        background = background.convert()
        background.fill((250, 250, 250))

        # Testing code
        self.dev_patience -= 1
        if self.dev_patience >= 0:
            pygame.draw.circle(background, (255, 0, 0), (100, 100), 50)
        pygame.draw.rect(background, (255, 0, 0), (300, 300, 100, 100))
        screen.blit(background, (0, 0))


class Connector:
    def __init__(self, where):
        self.where = where
        if ':' not in where:
            self.where = f'{where}:{DEFAULT_PORT}'
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.messages_out = None

    async def process_incoming_message(self, msg):
        await self.send_stuff(msg)

    async def send_stuff(self, msg):
        assert self.websocket is not None
        await self.websocket.send(json.dumps(msg))

    async def reader(self, websocket):
        async for message_raw in websocket:
            msg = json.loads(message_raw)
            await self.messages_out(msg)

    async def hello(self):
        async with websockets.connect(f"ws://{self.where}") as websocket:
            self.websocket = websocket
            await self.send_stuff({'cmd': 'version', 'version': PROTOCOL_VERSION})

            reader_task = asyncio.ensure_future(self.reader(websocket))
            done = await asyncio.wait(
                [reader_task],
                return_when=asyncio.FIRST_COMPLETED,
            )


class Gui:
    def __init__(self):
        pygame.init()
        self.phase_i = None
        self.phase: Phase | None = None
        self.connector: Connector | None = None
        self.screen = None

    async def switch_phase(self, num, result):
        if self.phase_i == num:
            return
        if num == 1:
            self.screen = pygame.display.set_mode([800, 800])
            self.phase = GamingPhase()
            self.connector = Connector(result)
            self.connector.messages_out = self.phase.process_incoming_message
            self.phase.messages_out = self.connector.process_incoming_message
            self.connector.hello_task = asyncio.create_task(self.connector.hello())
            await self.connector.hello()
        else:
            self.screen = pygame.display.set_mode([500, 300])
            self.phase = ServerSelectPhase()
        self.phase_i = num

    async def run(self):
        clock = pygame.time.Clock()

        running = True
        await self.switch_phase(0, None)
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                await self.phase.process_event(event)
            if self.phase.finished:
                await self.switch_phase((self.phase_i + 1) % 2, self.phase.result)
            self.phase.draw(self.screen)
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()


if __name__ == '__main__':
    asyncio.run(Gui().run())
