from cyclonedds.idl import IdlStruct
from cyclonedds.idl.annotations import key

class TurtlePose(IdlStruct):
    """Сообщение с позицией черепахи."""
    id: int
    x: float
    y: float
    theta: float