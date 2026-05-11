#! /usr/bin/env python3
import sys
import threading
import math
import time
import select
import termios
import tty
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
LINEAR_SPEED = 180.0
ANGULAR_SPEED = 5.0
FOLLOW_DISTANCE_THRESH = 30
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
                        with self.lock:
                            self.target_pose = (pose.x, pose.y, pose.theta)
            time.sleep(0.001)

    def publish_pose(self):
        msg = TurtlePose(id=self.id, x=self.x, y=self.y, theta=self.theta)
        self.writer.write(msg)
        time.sleep(0.001)

    def update_controlled(self, keys_pressed, dt):
        """
        Обновление позиции управляемой черепахи.
        keys_pressed - множество нажатых в данный момент клавиш
        """
        linear = 0.0
        angular = 0.0
        
        if 'w' in keys_pressed:
            linear = LINEAR_SPEED
        if 's' in keys_pressed:
            linear = -LINEAR_SPEED
        if 'a' in keys_pressed:
            angular = ANGULAR_SPEED
        if 'd' in keys_pressed:
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

# ----------------------------- Управление клавиатурой -----------------------------
class KeyboardHandler:
    """Обработчик клавиатуры, отслеживающий состояние клавиш."""
    def __init__(self):
        self.pressed_keys = set()
        self.old_settings = None
    
    def setup_terminal(self):
        """Настройка терминала для неблокирующего чтения."""
        self.old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
    
    def restore_terminal(self):
        """Восстановление настроек терминала."""
        if self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
    
    def update(self):
        """Обновление состояния клавиш."""
        # Сбрасываем состояние клавиш (клавиши отпущены)
        self.pressed_keys.clear()
        
        # Читаем все доступные символы
        while select.select([sys.stdin], [], [], 0)[0]:
            char = sys.stdin.read(1)
            if char:
                self.pressed_keys.add(char.lower())
    
    def is_pressed(self, key):
        """Проверка, нажата ли клавиша."""
        return key.lower() in self.pressed_keys
    
    def get_active_keys(self):
        """Получение множества активных клавиш."""
        return self.pressed_keys.copy()

# ----------------------------- Основная функция -----------------------------
def main():
    participant = DomainParticipant(DDS_DOMAIN_ID)
    qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
              Policy.Durability.TransientLocal)
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
    
    for i in range(1, num_followers + 1):
        follower = Turtle(i,
                          start_x - i*40, start_y + i*30,
                          0.0,
                          is_controlled=False,
                          target_id=i-1,
                          participant=participant, topic=topic, qos=qos)
        turtles.append(follower)

    print("Turtle simulator started!")
    print("Controls: 'w' - forward, 's' - backward, 'a' - turn left, 'd' - turn right")
    print("Press 'q' to quit")
    print("Run turtle_viewer.py in another terminal to see the visualization.")
    
    # Инициализация обработчика клавиатуры
    keyboard = KeyboardHandler()
    keyboard.setup_terminal()
    
    running = True
    last_status = ""
    
    try:
        while running:
            dt = 0.016  # ~60 FPS
            
            # Обновление состояния клавиш
            keyboard.update()
            
            # Проверка на выход
            if keyboard.is_pressed('q'):
                running = False
                break
            
            # Отображение статуса
            active_keys = keyboard.get_active_keys()
            if active_keys:
                key_descriptions = []
                if 'w' in active_keys: key_descriptions.append("forward")
                if 's' in active_keys: key_descriptions.append("backward")
                if 'a' in active_keys: key_descriptions.append("left")
                if 'd' in active_keys: key_descriptions.append("right")
                status = f"\rMoving: {', '.join(key_descriptions)}   "
            else:
                status = "\rStopped                    "
            
            if status != last_status:
                print(status, end='', flush=True)
                last_status = status
            
            # Обновление всех черепах
            for t in turtles:
                if t.is_controlled:
                    t.update_controlled(active_keys, dt)  # Передаем множество активных клавиш
                else:
                    t.update_follower(dt)
           
            # Публикация позиций
            for t in turtles:
                t.publish_pose()

            time.sleep(dt)
            
    except KeyboardInterrupt:
        print("\nSimulation stopped by user")
    finally:
        # Восстановление настроек терминала
        keyboard.restore_terminal()
        print("\nShutting down...")
        for t in turtles:
            t.stop()
        participant.close()
        sys.exit(0)

if __name__ == "__main__":
    main()