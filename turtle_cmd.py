#! /usr/bin/env python3
"""
Агент одной черепахи. Запускается как отдельный процесс.
Примеры:
  Управляемая (id=0):        python3 turtle_agent.py --id 0 --controlled
  Ведомая за turtle0:        python3 turtle_agent.py --id 1 --target 0
  Ведомая со своими параметрами:
    python3 turtle_agent.py --id 2 --target 1 --spawn-x 200 --spawn-y 300 --speed 50
"""
import sys
import argparse
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

# ----------------------------- Конфигурация по умолчанию -----------------------------
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
DDS_TOPIC_NAME = "TurtlePose"
DDS_DOMAIN_ID = 0

# ----------------------------- Класс черепахи (без изменений в логике) -----------------------------
class Turtle:
    def __init__(self, tid, x, y, theta, is_controlled=False, target_id=None,
                 participant=None, topic=None, qos=None,
                 linear_speed=80.0, angular_speed=2.0,
                 follow_dist=10.0, kp_angular=3.0):
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

        # Параметры управления
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.follow_distance_thresh = follow_dist
        self.kp_angular = kp_angular

        self.topic = topic
        self.writer = DataWriter(participant, self.topic, qos=qos)

        self.reader = None
        if target_id is not None:
            self.reader = DataReader(participant, self.topic, qos=qos)
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

    def stop(self):
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
                    pose = item.data if hasattr(item, 'data') else item
                    if pose.id == self.target_id:
                        with self.lock:
                            self.target_pose = (pose.x, pose.y, pose.theta)
            time.sleep(0.001)

    def publish_pose(self):
        msg = TurtlePose(id=self.id, x=self.x, y=self.y, theta=self.theta)
        self.writer.write(msg)
        time.sleep(0.001)

    def update_controlled(self, keys_pressed, dt):
        linear = 0.0
        angular = 0.0
        if keys_pressed:
            if 'w' in keys_pressed:
                linear = self.linear_speed
            if 's' in keys_pressed:
                linear = -self.linear_speed
            if 'a' in keys_pressed:
                angular = self.angular_speed
            if 'd' in keys_pressed:
                angular = -self.angular_speed

        self.x += linear * math.cos(self.theta) * dt
        self.y += linear * math.sin(self.theta) * dt
        self.theta += angular * dt
        self.theta = (self.theta + math.pi) % (2.0 * math.pi) - math.pi

        self.x = max(0, min(WINDOW_WIDTH, self.x))
        self.y = max(0, min(WINDOW_HEIGHT, self.y))

    def update_follower(self, dt):
        with self.lock:
            if self.target_pose is None:
                return
            tx, ty, _ = self.target_pose

        dist = def_distance(tx, ty, self.x, self.y)
        if dist < self.follow_distance_thresh:
            linear = 0.0
            angular = 0.0
        else:
            delta_angle = def_angl(tx, ty, self.x, self.y, self.theta)
            angular = max(-self.angular_speed,
                          min(self.angular_speed, self.kp_angular * delta_angle))
            linear = self.linear_speed

        self.x += linear * math.cos(self.theta) * dt
        self.y += linear * math.sin(self.theta) * dt
        self.theta += angular * dt
        self.theta = (self.theta + math.pi) % (2.0 * math.pi) - math.pi

        self.x = max(0, min(WINDOW_WIDTH, self.x))
        self.y = max(0, min(WINDOW_HEIGHT, self.y))

# ----------------------------- Класс для чтения клавиш -----------------------------
class KeyboardHandler:
    def __init__(self):
        self.pressed_keys = set()
        self.old_settings = None
        self.is_terminal = sys.stdin.isatty()

    def setup(self):
        if self.is_terminal:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

    def restore(self):
        if self.is_terminal and self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def update(self):
        if not self.is_terminal:
            return
        self.pressed_keys.clear()
        while select.select([sys.stdin], [], [], 0)[0]:
            char = sys.stdin.read(1)
            if char:
                self.pressed_keys.add(char.lower())

    def is_pressed(self, key):
        return key.lower() in self.pressed_keys

    def get_active_keys(self):
        return self.pressed_keys.copy()

# ----------------------------- Основная функция -----------------------------
def main():
    parser = argparse.ArgumentParser(description='Turtle DDS Agent')
    parser.add_argument('--id', type=int, required=True, help='ID черепахи')
    parser.add_argument('--controlled', action='store_true', help='Управляемая черепаха')
    parser.add_argument('--target', type=int, default=None, help='ID цели для ведомой')
    parser.add_argument('--spawn-x', type=float, default=400.0)
    parser.add_argument('--spawn-y', type=float, default=300.0)
    parser.add_argument('--spawn-theta', type=float, default=0.0)
    parser.add_argument('--speed', type=float, default=80.0, help='Линейная скорость')
    parser.add_argument('--angular-speed', type=float, default=2.0, help='Макс. угловая скорость')
    parser.add_argument('--follow-dist', type=float, default=10.0, help='Дистанция остановки')
    parser.add_argument('--kp-angular', type=float, default=3.0, help='Коэф. П-регулятора')
    args = parser.parse_args()

    # Определяем роль
    is_controlled = args.controlled
    target_id = None if is_controlled else args.target

    # Инициализация DDS
    participant = DomainParticipant(DDS_DOMAIN_ID)
    qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
              Policy.Durability.TransientLocal)
    topic = Topic(participant, DDS_TOPIC_NAME, TurtlePose, qos=qos)

    # Создаём одну черепаху
    turtle = Turtle(
        tid=args.id,
        x=args.spawn_x,
        y=args.spawn_y,
        theta=args.spawn_theta,
        is_controlled=is_controlled,
        target_id=target_id,
        participant=participant,
        topic=topic,
        qos=qos,
        linear_speed=args.speed,
        angular_speed=args.angular_speed,
        follow_dist=args.follow_dist,
        kp_angular=args.kp_angular
    )

    keyboard = KeyboardHandler()
    keyboard.setup()

    print(f"Agent Turtle{args.id} started. "
          f"{'Controlled via keyboard' if is_controlled else f'Following Turtle{target_id}'}. "
          f"Press Ctrl+C to stop.")

    running = True
    try:
        while running:
            dt = 0.016  # ~60 FPS

            keyboard.update()

            # Выход по 'q' только если есть терминал и черепаха управляемая
            if keyboard.is_terminal and keyboard.is_pressed('q'):
                running = False
                break

            active_keys = keyboard.get_active_keys() if is_controlled else None

            if is_controlled:
                turtle.update_controlled(active_keys, dt)
            else:
                turtle.update_follower(dt)

            turtle.publish_pose()
            time.sleep(dt)

    except KeyboardInterrupt:
        pass
    finally:
        keyboard.restore()
        turtle.stop()
        participant.close()
        print(f"Agent Turtle{args.id} stopped.")

if __name__ == "__main__":
    main()