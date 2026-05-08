#! /usr/bin/env python3
#Сюда писать всю роса-независимую матешу
import math

#Вычисляет угол, на котороый надо повернуться
#черепахе, чтоб смотрела на другую
def def_angl(x_1, y_1, x_2, y_2, theta)->float:
    """
    Входные:
    x_1,y_1 - координаты черепахи-цели
    x_2, y_2, theta - коориданты и угол текущей черепахи, которая будет смотреть 
    (поворачиваться)
    Выход: угол на который надо повернуться
    """
    dx = x_1 - x_2
    dy = y_1 - y_2
    if dx == 0.0 and dy == 0.0:
        return 0.0
    
    angle_to_target = math.atan2(dy, dx)
    delta = angle_to_target - theta
    delta = (delta + math.pi) % (2.0 * math.pi) - math.pi
    return delta

def def_distance(x_1, y_1, x_2, y_2)->float:
    """
    Вычисляет растояние до цели
    Входные:
    x_1,y_1 - координаты черепахи-цели
    x_2, y_2 - коориданты текущей черепахи
    Выход: растояние до цели
    """
    dx = x_1 - x_2
    dy = y_1 - y_2

    d = math.hypot(dx, dy)

    return d
