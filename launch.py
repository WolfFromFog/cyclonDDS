#!/usr/bin/env python3
import subprocess
import sys
import time

def main():
    # Запуск GUI
    gui_proc = subprocess.Popen([sys.executable, 'gui_node.py'])
    time.sleep(1)   # даём время на инициализацию DDS

    # Управляемая черепаха (id=0)
    subprocess.Popen([
        sys.executable, 'turtle_node.py',
        '--id', '0', '--x', '400', '--y', '300', '--theta', '0',
        '--controlled'
    ])

    # Ведомые черепахи (id=1..5)
    num_followers = 5
    start_x = 400 - 60
    start_y = 300
    for i in range(1, num_followers + 1):
        subprocess.Popen([
            sys.executable, 'turtle_node.py',
            '--id', str(i),
            '--x', str(start_x - i * 40),
            '--y', str(start_y + i * 30),
            '--theta', '0',
            '--target-id', str(i - 1)
        ])

    # Ожидание завершения GUI (если GUI закрыт, можно завершить и все остальные)
    try:
        gui_proc.wait()
    except KeyboardInterrupt:
        gui_proc.terminate()
        # В реальном коде можно добавить поиск и убийство дочерних процессов,
        # но они завершатся при завершении родителя (не всегда). Для простоты оставим так.
    finally:
        print("Shutting down...")

if __name__ == "__main__":
    main()