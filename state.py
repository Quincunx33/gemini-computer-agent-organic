from dataclasses import dataclass, field
@dataclass
class AgentState:
    task: str=""
    step: int=0
    cancelled: bool=False
    history: list=field(default_factory=list)
    def add(self, role, content):
        self.history.append({"role": role, "content": content})
