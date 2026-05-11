from dataclasses import dataclass
from cyclonedds.idl import IdlStruct

@dataclass
class TurtlePose(IdlStruct):
    """Позиция черепахи."""
    id: int
    x: float
    y: float
    theta: float

@dataclass
class TurtleCmd(IdlStruct):
    """Команда управления (линейная и угловая скорость)."""
    id: int          # идентификатор черепахи, которой предназначена команда
    linear: float
    angular: float