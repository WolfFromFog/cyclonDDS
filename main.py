# main.py
import sys
import time
import threading
import math
import pygame
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from turtle_dds import TurtlePose
from cyclonedds.util import duration
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

LINEAR_SPEED = 80.0          # пикселей в секунду
ANGULAR_SPEED = 2.0          # радиан в секунду (макс. скорость поворота)
FOLLOW_DISTANCE_THRESH = 10  # пикселей – при меньшем расстоянии остановка

DDS_TOPIC_NAME = "TurtlePose"
DDS_DOMAIN_ID = 0

# ----------------------------- Класс черепахи -----------------------------
class Turtle:
    def __init__(self, tid, x, y, theta, is_controlled=False, target_id=None,
                 participant=None, qos=None):
        self.id = tid
        self.x = x
        self.y = y
        self.theta = theta
        self.is_controlled = is_controlled      # управляется клавиатурой
        self.target_id = target_id              # ID цели, за которой следуем (None для управляемой)
        self.target_pose = None                 # последняя известная позиция цели
        self.lock = threading.Lock()            # для потокобезопасного доступа к target_pose

        # DDS: публикатор (все черепахи публикуют своё положение)
        self.topic = Topic(participant, DDS_TOPIC_NAME, TurtlePose, qos=qos)
        self.writer = DataWriter(participant, self.topic, qos=qos)

        # DDS: подписчик на целевую черепаху (если задана)
        self.reader = None
        if target_id is not None:
            self.reader = DataReader(participant, self.topic, qos=qos)
            # в отдельном потоке принимаем сообщения
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

    def _reader_loop(self):
        """Цикл чтения входящих DDS-сообщений для получения позиции цели."""
        while True:
            samples = self.reader.take()
            for sample in samples:
                pose = sample.data
                if pose.id == self.target_id:
                    with self.lock:
                        self.target_pose = (pose.x, pose.y, pose.theta)
            time.sleep(0.01)   # небольшая пауза, чтобы не нагружать процессор

    def publish_pose(self):
        """Отправить текущую позицию через DDS."""
        msg = TurtlePose(id=self.id, x=self.x, y=self.y, theta=self.theta)
        self.writer.write(msg)

    def update_controlled(self, keys, dt):
        """Обновление управляемой черепахи по клавишам."""
        # Управление: W/S – вперёд/назад, A/D – поворот
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

        # Динамика
        self.x += linear * math.cos(self.theta) * dt
        self.y += linear * math.sin(self.theta) * dt
        self.theta += angular * dt
        # Нормализация угла
        self.theta %= 2 * math.pi

    def update_follower(self, dt):
        """Обновление ведомой черепахи: стремится к целевой позиции."""
        with self.lock:
            if self.target_pose is None:
                return
            tx, ty, _ = self.target_pose

        dist = def_distance(tx, ty, self.x, self.y)
        if dist < FOLLOW_DISTANCE_THRESH:
            # достаточно близко – стоим
            linear = 0.0
            angular = 0.0
        else:
            # вычисляем нужный угол поворота
            delta_angle = def_angl(tx, ty, self.x, self.y, self.theta)
            # ограничим максимальную угловую скорость
            angular = max(-ANGULAR_SPEED, min(ANGULAR_SPEED, delta_angle))
            linear = LINEAR_SPEED

        # Применяем движение
        self.x += linear * math.cos(self.theta) * dt
        self.y += linear * math.sin(self.theta) * dt
        self.theta += angular * dt
        self.theta %= 2 * math.pi

    def draw(self, screen):
        """Отрисовка черепахи в виде круга с "головой"."""
        color = TURTLE_COLORS[self.id % len(TURTLE_COLORS)]
        center = (int(self.x), int(self.y))
        pygame.draw.circle(screen, color, center, TURTLE_RADIUS)
        pygame.draw.circle(screen, (0,0,0), center, TURTLE_RADIUS, 2)

        # рисуем направление (голову)
        head_len = TURTLE_RADIUS
        head_x = self.x + head_len * math.cos(self.theta)
        head_y = self.y + head_len * math.sin(self.theta)
        pygame.draw.line(screen, (0,0,0), center, (int(head_x), int(head_y)), 3)

# ----------------------------- Основная функция -----------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Turtle DDS Demo")
    clock = pygame.time.Clock()

    # DDS участник
    participant = DomainParticipant(DDS_DOMAIN_ID)
    # QoS: надёжная доставка для всех
    qos = Qos(
    Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)), Policy.Durability.TransientLocal)   

    # Создаём черепах
    turtles = []

    # Управляемая черепаха (id=0)
    turtle0 = Turtle(0, WINDOW_WIDTH//2, WINDOW_HEIGHT//2, 0.0,
                     is_controlled=True, target_id=None,
                     participant=participant, qos=qos)
    turtles.append(turtle0)

    # Ведомые черепахи: id = 1,2,3... каждая следит за предыдущей
    num_followers = 3
    start_x = WINDOW_WIDTH//2 - 60
    start_y = WINDOW_HEIGHT//2
    for i in range(1, num_followers+1):
        follower = Turtle(i,
                          start_x - i*40, start_y + i*30,
                          0.0,
                          is_controlled=False,
                          target_id=i-1,      # следит за предыдущей
                          participant=participant, qos=qos)
        turtles.append(follower)

    # Основной игровой цикл
    running = True
    while running:
        dt = clock.tick(60) / 1000.0   # секунды с предыдущего кадра
        if dt > 0.05:                  # защита от слишком больших dt
            dt = 0.05

        # Обработка событий
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # Получаем состояние клавиш (только для управляемой)
        keys = pygame.key.get_pressed()

        # Обновление состояния каждой черепахи
        for t in turtles:
            if t.is_controlled:
                t.update_controlled(keys, dt)
            else:
                t.update_follower(dt)

        # Публикация всех состояний через DDS
        for t in turtles:
            t.publish_pose()

        # Отрисовка
        screen.fill(BACKGROUND_COLOR)
        for t in turtles:
            t.draw(screen)

        # Отображение ID и расстояний (необязательно)
        font = pygame.font.SysFont(None, 24)
        for t in turtles:
            text = font.render(f"T{t.id}", True, (0,0,0))
            screen.blit(text, (t.x-10, t.y-20))

        pygame.display.flip()

    # Завершение
    pygame.quit()
    participant.close()
    sys.exit()

if __name__ == "__main__":
    main()