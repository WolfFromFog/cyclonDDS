from dataclasses import dataclass
from cyclonedds.idl import IdlStruct

@dataclass
class TurtleCmd(IdlStruct):
    """Команда движения: линейная скорость и угловая скорость."""
    linear: float
    angular: float