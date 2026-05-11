import sys
import threading
import math
import time
import argparse
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_dds import TurtlePose, TurtleCmd
from ros_math import def_angl, def_distance

# Конфигурация движения
LINEAR_SPEED = 80.0          # пикселей/сек
ANGULAR_SPEED = 2.0          # рад/сек (макс.)
FOLLOW_DISTANCE_THRESH = 10  # пикселей
Kp_ANGULAR = 3.0             # коэффициент П-регулятора
WINDOW_WIDTH = 800           # границы мира (для ограничения)
WINDOW_HEIGHT = 600

class TurtleNode:
    def __init__(self, tid, x, y, theta, is_controlled, target_id,
                 participant, topic_pose, topic_cmd, qos):
        self.id = tid
        self.x = x
        self.y = y
        self.theta = theta
        self.is_controlled = is_controlled
        self.target_id = target_id
        self.target_pose = None          # (x, y, theta) цели
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        self.cmd_linear = 0.0
        self.cmd_angular = 0.0
        self.cmd_lock = threading.Lock()

        # Публикатор позиции
        self.pose_writer = DataWriter(participant, topic_pose, qos=qos)

        # Подписка на позицию цели (для ведомых черепах)
        self.target_reader = None
        if not is_controlled and target_id is not None:
            self.target_reader = DataReader(participant, topic_pose, qos=qos)
            self.target_thread = threading.Thread(target=self._target_loop, daemon=True)
            self.target_thread.start()

        # Подписка на команды (для управляемой черепахи)
        self.cmd_reader = None
        if is_controlled:
            self.cmd_reader = DataReader(participant, topic_cmd, qos=qos)
            self.cmd_thread = threading.Thread(target=self._cmd_loop, daemon=True)
            self.cmd_thread.start()

    def _target_loop(self):
        """Читает позицию цели из DDS."""
        while not self.stop_event.is_set():
            samples = self.target_reader.take()
            if self.stop_event.is_set():
                break
            for item in samples:
                pose = item.data if hasattr(item, 'data') else item
                if pose.id == self.target_id:
                    with self.lock:
                        self.target_pose = (pose.x, pose.y, pose.theta)
            time.sleep(0.001)

    def _cmd_loop(self):
        """Читает команды управления из DDS."""
        while not self.stop_event.is_set():
            samples = self.cmd_reader.take()
            if self.stop_event.is_set():
                break
            for item in samples:
                cmd = item.data if hasattr(item, 'data') else item
                if cmd.id == self.id:
                    with self.cmd_lock:
                        self.cmd_linear = cmd.linear
                        self.cmd_angular = cmd.angular
            time.sleep(0.001)

    def update(self, dt):
        """Обновляет положение черепахи за время dt."""
        if self.is_controlled:
            # Управляемая черепаха – использует команды от GUI
            with self.cmd_lock:
                linear = self.cmd_linear
                angular = self.cmd_angular
            self.x += linear * math.cos(self.theta) * dt
            self.y += linear * math.sin(self.theta) * dt
            self.theta += angular * dt
        else:
            # Ведомая черепаха – следует за целью
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

        # Нормализация угла и ограничение по краям экрана
        self.theta = (self.theta + math.pi) % (2.0 * math.pi) - math.pi
        self.x = max(0, min(WINDOW_WIDTH, self.x))
        self.y = max(0, min(WINDOW_HEIGHT, self.y))

    def publish(self):
        """Отправляет текущую позицию в DDS."""
        msg = TurtlePose(id=self.id, x=self.x, y=self.y, theta=self.theta)
        self.pose_writer.write(msg)

    def run(self, rate=60):
        """Основной цикл с фиксированной частотой."""
        dt = 1.0 / rate
        while not self.stop_event.is_set():
            start = time.time()
            self.update(dt)
            self.publish()
            elapsed = time.time() - start
            time.sleep(max(0, dt - elapsed))

    def stop(self):
        self.stop_event.set()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=int, required=True)
    parser.add_argument('--x', type=float, default=0.0)
    parser.add_argument('--y', type=float, default=0.0)
    parser.add_argument('--theta', type=float, default=0.0)
    parser.add_argument('--controlled', action='store_true')
    parser.add_argument('--target-id', type=int, default=None)
    args = parser.parse_args()

    participant = DomainParticipant(0)
    qos = Qos(
        Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
        Policy.Durability.TransientLocal
    )
    topic_pose = Topic(participant, "TurtlePose", TurtlePose, qos=qos)
    topic_cmd = Topic(participant, "TurtleCmd", TurtleCmd, qos=qos)

    node = TurtleNode(
        args.id, args.x, args.y, args.theta,
        args.controlled, args.target_id,
        participant, topic_pose, topic_cmd, qos
    )
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        participant.close()

if __name__ == "__main__":
    main()