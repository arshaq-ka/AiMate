from enum import Enum


class CharacterState(Enum):
    IDLE = "Idle"
    THINKING = "Thinking"
    MONITORING = "Monitoring"
    MONITORING_PAUSED = "Monitoring paused"
    PAUSED = "Paused"
