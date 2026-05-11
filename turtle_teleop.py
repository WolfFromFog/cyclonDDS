#!/usr/bin/env python3
"""
Публикует команды скорости для черепахи (по умолчанию id=0) через DDS.
Управление: w/s — вперёд/назад, a/d — поворот, q — выход.
"""
import sys
import select
import termios
import tty
import threading
import time
import argparse
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.topic import Topic
from cyclonedds.core import Qos, Policy
from cyclonedds.util import duration
from turtle_cmd import TurtleCmd

DDS_TOPIC_CMD = "TurtleCmd"
DDS_DOMAIN_ID = 0

class KeyboardHandler:
    def __init__(self):
        self.pressed_keys = set()
        self.old_settings = None
        self.running = True

    def setup(self):
        self.old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    def restore(self):
        if self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def update(self):
        self.pressed_keys.clear()
        while select.select([sys.stdin], [], [], 0)[0]:
            char = sys.stdin.read(1)
            if char:
                if char.lower() == 'q':
                    self.running = False
                else:
                    self.pressed_keys.add(char.lower())

    def get_active_keys(self):
        return self.pressed_keys.copy()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=int, default=0, help='ID управляемой черепахи')
    parser.add_argument('--speed', type=float, default=80.0, help='Линейная скорость')
    parser.add_argument('--angular-speed', type=float, default=2.0, help='Угловая скорость')
    args = parser.parse_args()

    # DDS
    participant = DomainParticipant(DDS_DOMAIN_ID)
    qos = Qos(Policy.Reliability.Reliable(max_blocking_time=duration(seconds=0.1)),
              Policy.Durability.TransientLocal)
    topic = Topic(participant, DDS_TOPIC_CMD, TurtleCmd, qos=qos)
    writer = DataWriter(participant, topic, qos=qos)

    kb = KeyboardHandler()
    kb.setup()

    print(f"Teleop for Turtle{args.id}. Keys: w/a/s/d, q to quit.")
    try:
        while kb.running:
            dt = 0.016
            kb.update()
            active = kb.get_active_keys()
            linear = 0.0
            angular = 0.0
            if 'w' in active:
                linear = args.speed
            if 's' in active:
                linear = -args.speed
            if 'a' in active:
                angular = args.angular_speed
            if 'd' in active:
                angular = -args.angular_speed

            cmd = TurtleCmd(linear=linear, angular=angular)
            writer.write(cmd)
            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        kb.restore()
        participant.close()
        print("Teleop stopped.")

if __name__ == '__main__':
    main()