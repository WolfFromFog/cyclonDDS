#!/usr/bin/env python3
import sys
import math
import pygame
from cyclonedds.domain import DomainParticipant
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_dds import TurtlePose

# Константы отрисовки
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
BACKGROUND_COLOR = (255, 255, 255)
TURTLE_RADIUS = 15
TURTLE_COLORS = [
    (0, 0, 255),    # синий
    (0, 255, 0),    # зелёный
    (255, 0, 0),    # красный
    (255, 255, 0),  # жёлтый
    (255, 0, 255),  # пурпурный
    (0, 255, 255),  # голубой
    (128, 0, 128),  # фиолетовый
]

def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Turtle Visualizer")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    # DDS setup
    participant = DomainParticipant(0)
    qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
              Policy.Durability.TransientLocal)
    topic = Topic(participant, "TurtlePose", TurtlePose, qos=qos)
    reader = DataReader(participant, topic, qos=qos)

    turtles = {}  # id -> (x, y, theta)

    running = True
    while running:
        # Обработка событий Pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # Получение всех доступных сообщений из DDS
        samples = reader.take()
        for sample in samples:
            pose = sample.data if hasattr(sample, 'data') else sample
            turtles[pose.id] = (pose.x, pose.y, pose.theta)

        # Отрисовка
        screen.fill(BACKGROUND_COLOR)
        for tid, (x, y, theta) in turtles.items():
            color = TURTLE_COLORS[tid % len(TURTLE_COLORS)]
            center = (int(x), int(y))

            # Тело черепахи
            pygame.draw.circle(screen, color, center, TURTLE_RADIUS)
            pygame.draw.circle(screen, (0, 0, 0), center, TURTLE_RADIUS, 2)

            # Голова (направление)
            head_len = TURTLE_RADIUS
            head_x = x + head_len * math.cos(theta)
            head_y = y + head_len * math.sin(theta)
            pygame.draw.line(screen, (0, 0, 0), center, (int(head_x), int(head_y)), 3)

            # ID черепахи
            text = font.render(f"T{tid}", True, (0, 0, 0))
            screen.blit(text, (x - 10, y - 20))

        pygame.display.flip()
        clock.tick(60)  # 60 FPS

    pygame.quit()
    participant.close()
    sys.exit(0)

if __name__ == "__main__":
    main()