from abc import ABC,abstractmethod
from dataclasses import dataclass,field
from delta_contracts.tools import ToolCall


@dataclass
class LLMTurn:
    text:str=''
    calls:list[ToolCall]=field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    async def respond(self,messages:list[dict],tools:list[dict],context:dict)->LLMTurn:
        pass
