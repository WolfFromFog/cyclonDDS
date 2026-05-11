#!/usr/bin/env python3
"""
Launch-файл для запуска системы черепах на DDS.

Все параметры черепах (id, цель, координаты, скорость…) задаются в списке TURTLES_CONFIG.
Запускает также визуализатор turtle_viewer.py (опционально).
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path

# ---------- Конфигурация черепах ----------
# Каждый словарь описывает одну черепаху.
# Для управляемой (первой) ставим "controlled": True, цель не нужна.
# Для ведомых указываем "target" (id цели) и опционально скорости.

TURTLES_CONFIG = []
# управляемая
#TURTLES_CONFIG.append({"id": 0, "controlled": True, "spawn_x": 400, "spawn_y": 300})
# ведомые по цепочке
for i in range(1, 6):
    TURTLES_CONFIG.append({
        "id": i,
        "target": i-1,
        "spawn_x": 400 - i*40,
        "spawn_y": 300 + i*30,
        "speed": 80 - i*10,
    })

# Параметры запуска
RUN_VIEWER = False                # запускать ли визуализатор
AGENT_SCRIPT = "turtle_agent.py" # путь к скрипту агента
VIEWER_SCRIPT = "turtle_viewer.py" # путь к визуализатору

# ---------- Функции запуска и остановки ----------
def build_cmd(config: dict) -> list:
    """Собирает команду для запуска агента."""
    cmd = [sys.executable, AGENT_SCRIPT, "--id", str(config["id"])]
    if config.get("controlled"):
        cmd.append("--controlled")
    else:
        if "target" not in config:
            raise ValueError(f"Черепаха {config['id']} должна иметь цель или быть управляемой")
        cmd += ["--target", str(config["target"])]

    # Опциональные параметры
    for param in ["spawn_x", "spawn_y", "spawn_theta", "speed",
                   "angular_speed", "follow_dist", "kp_angular"]:
        if param in config:
            kebab = param.replace("_", "-")  # аргументы через дефис
            cmd += [f"--{kebab}", str(config[param])]
    return cmd

def launch_processes():
    """Запускает все агенты и опционально viewer. Возвращает список Popen-объектов."""
    procs = []
    # Агенты черепах
    for cfg in TURTLES_CONFIG:
        cmd = build_cmd(cfg)
        print(f"Запуск: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, bufsize=1)
        procs.append(proc)

    # Визуализатор
    if RUN_VIEWER:
        cmd_view = [sys.executable, VIEWER_SCRIPT]
        print(f"Запуск viewer: {' '.join(cmd_view)}")
        proc_view = subprocess.Popen(cmd_view, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     universal_newlines=True, bufsize=1)
        procs.append(proc_view)

    return procs

def terminate_all(procs):
    """Посылает SIGTERM всем процессам, затем ждёт завершения."""
    for p in procs:
        if p.poll() is None:
            p.terminate()
    # Ждём до 3 секунд
    for p in procs:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()

# ---------- Главный поток ----------
def main():
    procs = launch_processes()
    # Перехватываем Ctrl+C для корректного завершения
    def sigint_handler(sig, frame):
        print("\nЗавершение по Ctrl+C...")
        terminate_all(procs)
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)

    # Ожидаем завершения всех процессов (можно следить за stdout)
    try:
        for p in procs:
            # Выводим stdout процесса в реальном времени
            while True:
                line = p.stdout.readline()
                if not line and p.poll() is not None:
                    break
                if line:
                    print(f"[{p.pid}] {line.rstrip()}")
            if p.returncode != 0:
                print(f"Процесс {p.pid} завершился с кодом {p.returncode}")
    except KeyboardInterrupt:
        pass
    finally:
        terminate_all(procs)
        print("Все процессы остановлены.")

if __name__ == "__main__":
    main()