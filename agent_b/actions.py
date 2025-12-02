from pydantic import BaseModel
from typing import List, Optional
from navigator import Navigator
from state_capture import StateCapture

class Action(BaseModel):
    kind: str
    target_keywords: Optional[List[str]] = None
    text: Optional[str] = None

class ActionPlan(BaseModel):
    steps: List[Action]
    hints: List[str] = []
    raw_task: str

class ActionExecutor:
    def __init__(self, nav: Navigator, capture: StateCapture):
        self.nav = nav; self.capture = capture; self.step_idx = 0
    async def execute_plan(self, plan: ActionPlan, max_steps: int = 12):
        for act in plan.steps:
            if self.step_idx >= max_steps: break
            await self._execute_action(act); self.step_idx += 1
    async def _execute_action(self, act: Action):
        if act.kind == "locate_and_click":
            ok = await self.nav.click_semantic(act.target_keywords or [])
            await self.capture.capture_state(event=f"{self._step()}_click", info={"action": act.model_dump(), "clicked": ok})
        elif act.kind == "scan_and_click_cta":
            ok = await self.nav.scan_and_click_cta()
            await self.capture.capture_state(event=f"{self._step()}_scan_click", info={"action": act.model_dump(), "clicked": ok})
        elif act.kind == "maybe_type":
            ok = await self.nav.type_into_likely_field(act.text or "")
            await self.capture.capture_state(event=f"{self._step()}_type", info={"action": act.model_dump(), "typed": ok})
        elif act.kind == "wait_for_state_change":
            await self.nav.wait_possible_state_change()
            await self.capture.capture_state(event=f"{self._step()}_wait", info={"action": act.model_dump()})
        else:
            await self.capture.capture_state(event=f"{self._step()}_noop", info={"action": act.model_dump()})
    def _step(self) -> str: return f"{self.step_idx:02d}"
