#!/usr/bin/env python3
"""
Launch-файл для запуска системы черепах с DDS.
Запускает телеоп для управляемой черепахи, агентов и визуализатор.
"""
import subprocess
import sys
import signal
import time

# ---------- Конфигурация ----------
RUN_VIEWER = True
AGENT_SCRIPT = "turtle_agent.py"
VIEWER_SCRIPT = "turtle_viewer.py"
TELEOP_SCRIPT = "turtle_teleop.py"

TURTLES_CONFIG = []

TURTLES_CONFIG.append({"id": 0, "controlled": True, "spawn_x": 400, "spawn_y": 300, "speed": 160, })

for i in range(1, 30):
    TURTLES_CONFIG.append({
        "id": i,
        "target": i-1,
        "spawn_x": 400 - i*1,
        "spawn_y": 300 + i*1,
        "speed": 80,
    })

# ---------- Функции ----------
def build_agent_cmd(cfg):
    cmd = [sys.executable, AGENT_SCRIPT, "--id", str(cfg["id"])]
    if cfg.get("controlled"):
        cmd.append("--controlled")
    else:
        cmd += ["--target", str(cfg["target"])]
    for p in ["spawn_x", "spawn_y", "spawn_theta", "speed",
              "angular_speed", "follow_dist", "kp_angular"]:
        if p in cfg:
            cmd += [f"--{p.replace('_', '-')}", str(cfg[p])]
    return cmd
master_speed = TURTLES_CONFIG[0].get("speed", 180.0)
def launch_processes():
    procs = []
    # 1. Телеоп для первой черепахи (id=0)
    teleop_cmd = [sys.executable, TELEOP_SCRIPT, "--id", "0", "--speed", str(master_speed)]
    print("Запуск teleop:", " ".join(teleop_cmd))
    # Телеоп должен иметь доступ к реальному stdin/stdout
    proc_teleop = subprocess.Popen(teleop_cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
    procs.append(proc_teleop)

    # 2. Агенты черепах
    for cfg in TURTLES_CONFIG:
        cmd = build_agent_cmd(cfg)
        print("Запуск агента:", " ".join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, bufsize=1)
        procs.append(proc)

    # 3. Визуализатор
    if RUN_VIEWER:
        cmd_view = [sys.executable, VIEWER_SCRIPT]
        print("Запуск viewer:", " ".join(cmd_view))
        proc_view = subprocess.Popen(cmd_view, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     universal_newlines=True, bufsize=1)
        procs.append(proc_view)
    return procs

def terminate_all(procs):
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()

def main():
    procs = launch_processes()
    def handle_sigint(sig, frame):
        print("\nОстановка...")
        terminate_all(procs)
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        # Вывод stdout/stdin только для агентов (teleop сам печатает)
        # Просто ждём завершения любого процесса
        while True:
            for p in procs:
                if p.poll() is not None:
                    # если это агент – выведем его stdout, если есть
                    if p.stdout:
                        output = p.stdout.read()
                        if output:
                            print(f"[{p.pid}] {output}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        terminate_all(procs)
        print("Все процессы остановлены.")

if __name__ == "__main__":
    main()