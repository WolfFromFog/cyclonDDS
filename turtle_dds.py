# turtle_dds.py
from dataclasses import dataclass
from cyclonedds.idl import IdlStruct
from cyclonedds.idl.annotations import key

@dataclass
class TurtlePose(IdlStruct):
    """Сообщение с позицией черепахи."""
    id: int          # идентификатор черепахи
    x: float
    y: float
    theta: float