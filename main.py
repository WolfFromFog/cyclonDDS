import sys
import threading
import math
import time
import pygame
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_dds import TurtlePose
from ros_math import def_angl, def_distance

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
LINEAR_SPEED = 80.0
ANGULAR_SPEED = 2.0
FOLLOW_DISTANCE_THRESH = 10
DDS_TOPIC_NAME = "TurtlePose"
DDS_DOMAIN_ID = 0
Kp_ANGULAR = 3.0

# ----------------------------- Класс черепахи -----------------------------
class Turtle:
    def __init__(self, tid, x, y, theta, is_controlled=False, target_id=None,
                 participant=None, topic=None, qos=None):
        self.id = tid
        self.x = x
        self.y = y
        self.theta = theta
        self.is_controlled = is_controlled
        self.target_id = target_id
        self.target_pose = None
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self.reader_thread = None

        self.topic = topic
        self.writer = DataWriter(participant, self.topic, qos=qos)

        self.reader = None
        if target_id is not None:
            self.reader = DataReader(participant, self.topic, qos=qos)
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

    def stop(self):
        """Безопасное завершение потока чтения."""
        self._stop_event.set()
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1.0)

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
                    if pose.id == self.target_id:
                        #print(f"T{self.id} got target at ({pose.x:.1f}, {pose.y:.1f})")
                        with self.lock:
                            self.target_pose = (pose.x, pose.y, pose.theta)
            time.sleep(0.000001)

    def publish_pose(self):
        msg = TurtlePose(id=self.id, x=self.x, y=self.y, theta=self.theta)
        self.writer.write(msg)
        #print(f"T{self.id} published: ({self.x:.1f}, {self.y:.1f})")
        time.sleep(0.000001)

    def update_controlled(self, keys, dt):
        linear = 0.0
        angular = 0.0
        if keys[pygame.K_w]:
            linear = LINEAR_SPEED
        if keys[pygame.K_s]:
            linear = -LINEAR_SPEED
        if keys[pygame.K_a]:
            angular = ANGULAR_SPEED
        if keys[pygame.K_d]:
            angular = -ANGULAR_SPEED

        self.x += linear * math.cos(self.theta) * dt
        self.y += linear * math.sin(self.theta) * dt
        self.theta += angular * dt
        self.theta = (self.theta + math.pi) % (2.0 * math.pi) - math.pi

        # Ограничение по границам окна
        self.x = max(0, min(WINDOW_WIDTH, self.x))
        self.y = max(0, min(WINDOW_HEIGHT, self.y))

    def update_follower(self, dt):
        with self.lock:
            if self.target_pose is None:
                return
            tx, ty, _ = self.target_pose

        dist = def_distance(tx, ty, self.x, self.y)
        if dist < FOLLOW_DISTANCE_THRESH:
            linear = 0.0
            angular = 0.0
        else:
            delta_angle = def_angl(tx, ty, self.x, self.y, self.theta)
            angular = max(-ANGULAR_SPEED, min(ANGULAR_SPEED, Kp_ANGULAR * delta_angle))
            linear = LINEAR_SPEED

        self.x += linear * math.cos(self.theta) * dt
        self.y += linear * math.sin(self.theta) * dt
        self.theta += angular * dt
        self.theta = (self.theta + math.pi) % (2.0 * math.pi) - math.pi

        # Ограничение по границам окна
        self.x = max(0, min(WINDOW_WIDTH, self.x))
        self.y = max(0, min(WINDOW_HEIGHT, self.y))

    def draw(self, screen, font):
        color = TURTLE_COLORS[self.id % len(TURTLE_COLORS)]
        center = (int(self.x), int(self.y))
        pygame.draw.circle(screen, color, center, TURTLE_RADIUS)
        pygame.draw.circle(screen, (0, 0, 0), center, TURTLE_RADIUS, 2)

        head_len = TURTLE_RADIUS
        head_x = self.x + head_len * math.cos(self.theta)
        head_y = self.y + head_len * math.sin(self.theta)
        pygame.draw.line(screen, (0, 0, 0), center, (int(head_x), int(head_y)), 3)

        text = font.render(f"T{self.id}", True, (0, 0, 0))
        screen.blit(text, (self.x - 10, self.y - 20))


# ----------------------------- Основная функция -----------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Turtle DDS Demo")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    participant = DomainParticipant(DDS_DOMAIN_ID)
    # Для надёжности используем стандартный QoS (если с Reliability/TransientLocal будут проблемы)
    #qos = Qos()   # Работает гарантированно
    # Альтернативно, можно вернуть настройки с Reliable, если всё работает:
    qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),Policy.Durability.TransientLocal)
    topic = Topic(participant, DDS_TOPIC_NAME, TurtlePose, qos=qos)

    turtles = []

    # Управляемая черепаха
    turtle0 = Turtle(0, WINDOW_WIDTH//2, WINDOW_HEIGHT//2, 0.0,
                     is_controlled=True, target_id=None,
                     participant=participant, topic=topic, qos=qos)
    turtles.append(turtle0)

    # Ведомые черепахи
    num_followers = 5
    start_x = WINDOW_WIDTH//2 - 60
    start_y = WINDOW_HEIGHT//2
    #time.sleep(0.1)
    for i in range(1, num_followers + 1):
        follower = Turtle(i,
                          start_x - i*40, start_y + i*30,
                          0.0,
                          is_controlled=False,
                          target_id=i-1,
                          participant=participant, topic=topic, qos=qos)
        turtles.append(follower)
        #time.sleep(0.1)

    running = True
    try:
        frame_count = 0
        while running:
            dt = clock.tick(60) / 1000.0
            if dt > 0.05:
                dt = 0.05

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            keys = pygame.key.get_pressed()

            for t in turtles:
                if t.is_controlled:
                    t.update_controlled(keys, dt)
                else:
                    t.update_follower(dt)
           
            for t in turtles:
                t.publish_pose()

            screen.fill(BACKGROUND_COLOR)
            for t in turtles:
                t.draw(screen, font)

            pygame.display.flip()
    except KeyboardInterrupt:
        pass
    finally:
        for t in turtles:
            t.stop()
        pygame.quit()
        participant.close()
        sys.exit(0)


if __name__ == "__main__":
    main()