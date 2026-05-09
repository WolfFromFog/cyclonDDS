from dataclasses import dataclass
from cyclonedds.idl import IdlStruct

@dataclass
class TurtlePose(IdlStruct):
    """Сообщение с позицией черепахи."""
    id: int
    x: float
    y: float
    theta: float