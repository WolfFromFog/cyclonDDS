#!/usr/bin/env python3
"""
Агент одной черепахи.
Управляемая черепаха (--controlled) слушает команды из DDS топика TurtleCmd.
Ведомая черепаха (--target ID) преследует цель.
"""
import sys
import argparse
import threading
import math
import time
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_dds import TurtlePose
from turtle_cmd import TurtleCmd
from ros_math import def_angl, def_distance

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
DDS_TOPIC_POSE = "TurtlePose"
DDS_TOPIC_CMD = "TurtleCmd"
DDS_DOMAIN_ID = 0

class Turtle:
    def __init__(self, tid, x, y, theta, is_controlled=False, target_id=None,
                 participant=None, pose_topic=None, cmd_topic=None, qos=None,
                 linear_speed=80.0, angular_speed=2.0,
                 follow_dist=10.0, kp_angular=3.0):
        self.id = tid
        self.x = x
        self.y = y
        self.theta = theta
        self.is_controlled = is_controlled
        self.target_id = target_id
        self.target_pose = None
        self.cmd = None            # последняя команда (TurtleCmd)
        self.lock = threading.Lock()
        self._stop_event = threading.Event()

        # параметры
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.follow_distance_thresh = follow_dist
        self.kp_angular = kp_angular

        # Публикация позы
        self.pose_writer = DataWriter(participant, pose_topic, qos=qos)

        # Подписки
        if is_controlled:
            # Читаем команды
            self.cmd_reader = DataReader(participant, cmd_topic, qos=qos)
            self.cmd_thread = threading.Thread(target=self._cmd_loop, daemon=True)
            self.cmd_thread.start()
        if target_id is not None:
            # Читаем позу цели
            self.pose_reader = DataReader(participant, pose_topic, qos=qos)
            self.pose_thread = threading.Thread(target=self._pose_loop, daemon=True)
            self.pose_thread.start()

    def stop(self):
        self._stop_event.set()

    def _cmd_loop(self):
        while not self._stop_event.is_set():
            try:
                samples = self.cmd_reader.take()
            except Exception as e:
                print(f"Cmd reader error: {e}")
                break
            if self._stop_event.is_set():
                break
            if samples:
                for item in samples:
                    data = item.data if hasattr(item, 'data') else item
                    if isinstance(data, TurtleCmd):
                        self.cmd = data
            time.sleep(0.001)

    def _pose_loop(self):
        while not self._stop_event.is_set():
            try:
                samples = self.pose_reader.take()
            except Exception as e:
                print(f"Pose reader error: {e}")
                break
            if self._stop_event.is_set():
                break
            if samples:
                for item in samples:
                    data = item.data if hasattr(item, 'data') else item
                    if hasattr(data, 'id') and data.id == self.target_id:
                        with self.lock:
                            self.target_pose = (data.x, data.y, data.theta)
            time.sleep(0.001)

    def publish_pose(self):
        msg = TurtlePose(id=self.id, x=self.x, y=self.y, theta=self.theta)
        self.pose_writer.write(msg)

    def update_controlled(self, dt):
        """Применяет последнюю полученную команду."""
        if self.cmd is None:
            linear = 0.0
            angular = 0.0
        else:
            # Масштабируем собственными максимальными скоростями
            linear = max(-self.linear_speed, min(self.linear_speed, self.cmd.linear))
            angular = max(-self.angular_speed, min(self.angular_speed, self.cmd.angular))

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

def main():
    parser = argparse.ArgumentParser(description='Turtle DDS Agent')
    parser.add_argument('--id', type=int, required=True)
    parser.add_argument('--controlled', action='store_true')
    parser.add_argument('--target', type=int, default=None)
    parser.add_argument('--spawn-x', type=float, default=400.0)
    parser.add_argument('--spawn-y', type=float, default=300.0)
    parser.add_argument('--spawn-theta', type=float, default=0.0)
    parser.add_argument('--speed', type=float, default=80.0)
    parser.add_argument('--angular-speed', type=float, default=2.0)
    parser.add_argument('--follow-dist', type=float, default=10.0)
    parser.add_argument('--kp-angular', type=float, default=3.0)
    args = parser.parse_args()

    is_controlled = args.controlled
    target_id = None if is_controlled else args.target

    participant = DomainParticipant(DDS_DOMAIN_ID)
    qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
              Policy.Durability.TransientLocal)
    pose_topic = Topic(participant, DDS_TOPIC_POSE, TurtlePose, qos=qos)
    cmd_topic = Topic(participant, DDS_TOPIC_CMD, TurtleCmd, qos=qos) if is_controlled else None

    turtle = Turtle(
        tid=args.id,
        x=args.spawn_x, y=args.spawn_y, theta=args.spawn_theta,
        is_controlled=is_controlled, target_id=target_id,
        participant=participant,
        pose_topic=pose_topic, cmd_topic=cmd_topic, qos=qos,
        linear_speed=args.speed, angular_speed=args.angular_speed,
        follow_dist=args.follow_dist, kp_angular=args.kp_angular
    )

    print(f"Agent Turtle{args.id} started. "
          f"{'Controlled via DDS cmd' if is_controlled else f'Following Turtle{target_id}'}")

    try:
        while True:
            dt = 0.016
            if is_controlled:
                turtle.update_controlled(dt)
            else:
                turtle.update_follower(dt)
            turtle.publish_pose()
            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        turtle.stop()
        participant.close()
        print(f"Agent Turtle{args.id} stopped.")

if __name__ == '__main__':
    main()