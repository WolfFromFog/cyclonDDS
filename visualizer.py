#! /usr/bin/env python3
import sys
import threading
import math
import time
import pygame
from cyclonedds.domain import DomainParticipant
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_dds import TurtlePose

# ----------------------------- Конфигурация -----------------------------
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
BACKGROUND_COLOR = (255, 255, 255)
TURTLE_RADIUS = 15
TURTLE_COLORS = [
    (0, 0, 255),    # синий – управляемая
    (0, 255, 0),    # зелёный – ведомая 1
    (255, 0, 0),    # красный – ведомая 2
    (255, 255, 0),  # жёлтый
    (255, 0, 255),  # пурпурный
]
DDS_TOPIC_NAME = "TurtlePose"
DDS_DOMAIN_ID = 0

# ----------------------------- Класс для отображения -----------------------------
class TurtleViewer:
    def __init__(self):
        self.turtles = {}  # id -> (x, y, theta)
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        
        # Инициализация DDS
        self.participant = DomainParticipant(DDS_DOMAIN_ID)
        qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
                  Policy.Durability.TransientLocal)
        self.topic = Topic(self.participant, DDS_TOPIC_NAME, TurtlePose, qos=qos)
        self.reader = DataReader(self.participant, self.topic, qos=qos)
        
        # Запуск потока чтения
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        
        # Инициализация Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Turtle DDS Viewer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)
    
    def _reader_loop(self):
        while not self._stop_event.is_set():
            try:
                samples = self.reader.take()
            except Exception as e:
                print(f"Reader error: {e}")
                break
            if self._stop_event.is_set():
                break
            if samples:
                for item in samples:
                    if hasattr(item, 'data'):
                        pose = item.data
                    else:
                        pose = item
                    with self.lock:
                        self.turtles[pose.id] = (pose.x, pose.y, pose.theta)
            time.sleep(0.000001)
    
    def draw_turtle(self, turtle_id, x, y, theta):
        color = TURTLE_COLORS[turtle_id % len(TURTLE_COLORS)]
        center = (int(x), int(y))
        pygame.draw.circle(self.screen, color, center, TURTLE_RADIUS)
        pygame.draw.circle(self.screen, (0, 0, 0), center, TURTLE_RADIUS, 2)

        head_len = TURTLE_RADIUS
        head_x = x + head_len * math.cos(theta)
        head_y = y + head_len * math.sin(theta)
        pygame.draw.line(self.screen, (0, 0, 0), center, (int(head_x), int(head_y)), 3)

        text = self.font.render(f"T{turtle_id}", True, (0, 0, 0))
        self.screen.blit(text, (x - 10, y - 20))
    
    def run(self):
        running = True
        try:
            while running:
                dt = self.clock.tick(60) / 1000.0
                
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        running = False
                
                self.screen.fill(BACKGROUND_COLOR)
                
                with self.lock:
                    for turtle_id, (x, y, theta) in self.turtles.items():
                        self.draw_turtle(turtle_id, x, y, theta)
                
                pygame.display.flip()
                
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def stop(self):
        self._stop_event.set()
        if hasattr(self, 'reader_thread') and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1.0)
        pygame.quit()
        self.participant.close()
        sys.exit(0)

# ----------------------------- Основная функция -----------------------------
def main():
    viewer = TurtleViewer()
    viewer.run()

if __name__ == "__main__":
    main()