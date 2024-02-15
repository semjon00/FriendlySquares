import pygame

class Phase:
    def __init__(self):
        self.finished = False

    def process_event(self, screen):
        pass

    def draw(self, screen):
        pass


class ServerSelectPhase(Phase):
    def __init__(self):
        super().__init__()
        self.text = ''
        self.finished = False
        self.font = pygame.font.SysFont("monospace", 32, bold=True)

    def process_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.finished = True
                return
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_ESCAPE:
                self.text = ''
            else:
                key = pygame.key.name(event.key)
                is_allowed = len(key) == 1 and (key[0].isalnum() or key[0] in '[].:')
                if is_allowed:
                    self.text += event.unicode

    def draw(self, screen):
        background = pygame.Surface(screen.get_size())
        background = background.convert()
        background.fill((250, 250, 250))
        text_surf = self.font.render('Enter server IP:', True, (31, 31, 31))
        background.blit(text_surf, (100, 100))
        draw_text = self.text if len(self.text) < 17 else '\u2026' + self.text[-15:]
        text_surf = self.font.render(draw_text, True, (245, 125, 31))
        background.blit(text_surf, (100, 150))
        screen.blit(background, (0, 0))


class GamingPhase(Phase):
    def __init__(self):
        super().__init__()
        self.finished = False

    def process_event(self, screen):
        pass

    def draw(self, screen):
        pass


class Gui:
    def __init__(self):
        pygame.init()
        self.phase_i = 0
        self.phase: Phase = ServerSelectPhase()

    def switch_phase(self, num):
        if self.phase_i == num:
            return
        phase = GamingPhase() if num == 1 else ServerSelectPhase()
        self.phase = phase
        self.phase_i = num

    def run(self):
        clock = pygame.time.Clock()
        screen = pygame.display.set_mode([500, 300])

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                self.phase.process_event(event)
            if self.phase.finished:
                self.switch_phase((self.phase_i + 1) % 2)
            self.phase.draw(screen)
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()


if __name__ == '__main__':
    Gui().run()
