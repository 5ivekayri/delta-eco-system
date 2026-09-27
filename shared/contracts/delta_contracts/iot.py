from datetime import datetime
from pydantic import Field, StrictBool
from .devices import StrictModel


class LightInput(StrictModel):
    enabled: StrictBool


class IoTState(StrictModel):
    source: str
    desk_light: bool
    temperature: float
    brightness: int = Field(ge=0, le=100)
    motion: bool
    updated_at: datetime
