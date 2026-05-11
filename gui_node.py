import sys
import math
import threading
import time
import pygame
from cyclonedds.domain import DomainParticipant
from cyclonedds.sub import DataReader
from cyclonedds.pub import DataWriter
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_dds import TurtlePose, TurtleCmd

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
BACKGROUND_COLOR = (255, 255, 255)
TURTLE_RADIUS = 15
TURTLE_COLORS = [
    (0, 0, 255),    # синий – управляемая
    (0, 255, 0),    # зелёный
    (255, 0, 0),    # красный
    (255, 255, 0),  # жёлтый
    (255, 0, 255),  # пурпурный
]

class GUI:
    def __init__(self, participant, topic_pose, topic_cmd, qos):
        self.participant = participant
        self.poses = {}          # id -> (x, y, theta)
        self.lock = threading.Lock()
        self.reader = DataReader(participant, topic_pose, qos=qos)
        self.cmd_writer = DataWriter(participant, topic_cmd, qos=qos)
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

    def _reader_loop(self):
        """Фоновый поток для чтения позиций всех черепах."""
        while True:
            samples = self.reader.take()
            for item in samples:
                pose = item.data if hasattr(item, 'data') else item
                with self.lock:
                    self.poses[pose.id] = (pose.x, pose.y, pose.theta)
            time.sleep(0.001)

    def send_cmd(self, linear, angular):
        """Отправляет команду управляемой черепахе (id=0)."""
        cmd = TurtleCmd(id=0, linear=linear, angular=angular)
        self.cmd_writer.write(cmd)

    def draw(self, screen, font):
        """Отрисовывает всех черепах на экране."""
        with self.lock:
            poses_copy = self.poses.copy()
        for tid, (x, y, theta) in poses_copy.items():
            color = TURTLE_COLORS[tid % len(TURTLE_COLORS)]
            center = (int(x), int(y))
            pygame.draw.circle(screen, color, center, TURTLE_RADIUS)
            pygame.draw.circle(screen, (0, 0, 0), center, TURTLE_RADIUS, 2)
            head_x = x + TURTLE_RADIUS * math.cos(theta)
            head_y = y + TURTLE_RADIUS * math.sin(theta)
            pygame.draw.line(screen, (0, 0, 0), center, (int(head_x), int(head_y)), 3)
            text = font.render(f"T{tid}", True, (0, 0, 0))
            screen.blit(text, (x - 10, y - 20))

def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Turtle DDS GUI")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    participant = DomainParticipant(0)
    qos = Qos(
        Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
        Policy.Durability.TransientLocal
    )
    topic_pose = Topic(participant, "TurtlePose", TurtlePose, qos=qos)
    topic_cmd = Topic(participant, "TurtleCmd", TurtleCmd, qos=qos)

    gui = GUI(participant, topic_pose, topic_cmd, qos)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0   # не используется для движения, но нужно для частоты

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        keys = pygame.key.get_pressed()
        linear = 0.0
        angular = 0.0
        if keys[pygame.K_w]:
            linear = 80.0
        if keys[pygame.K_s]:
            linear = -80.0
        if keys[pygame.K_a]:
            angular = 2.0
        if keys[pygame.K_d]:
            angular = -2.0
        gui.send_cmd(linear, angular)

        screen.fill(BACKGROUND_COLOR)
        gui.draw(screen, font)
        pygame.display.flip()

    pygame.quit()
    participant.close()
    sys.exit()

if __name__ == "__main__":
    main()