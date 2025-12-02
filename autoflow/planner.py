from pydantic import BaseModel
from typing import List
import os, yaml
from pathlib import Path
from actions import Action, ActionPlan

HINTS = {"create": ["create","new","add","start","compose","make"],
         "filter": ["filter","search","refine"],
         "settings": ["settings","preferences","configure"],
         "save": ["save","submit","done","finish"],
         "project": ["project","issue","task","ticket","doc","database"]}

class Planner:
    def __init__(self): self.api_key = os.getenv("OPENAI_API_KEY")
    def plan(self, user_task: str) -> ActionPlan:
        t = user_task.lower(); intents = [k for k, ws in HINTS.items() if any(w in t for w in ws)]
        steps: List[Action] = []
        if "filter" in intents:
            steps += [Action(kind="locate_and_click", target_keywords=["filter"]),
                      Action(kind="wait_for_state_change"),
                      Action(kind="maybe_type", target_keywords=["search","filter"], text="status:open"),
                      Action(kind="wait_for_state_change")]
        elif "settings" in intents:
            steps += [Action(kind="locate_and_click", target_keywords=["settings"]),
                      Action(kind="wait_for_state_change")]
        elif "create" in intents:
            steps += [Action(kind="locate_and_click", target_keywords=["create","new","add"]),
                      Action(kind="wait_for_state_change"),
                      Action(kind="maybe_type", target_keywords=["name","title"], text="Demo Item"),
                      Action(kind="wait_for_state_change"),
                      Action(kind="locate_and_click", target_keywords=["save","create","done","submit"]),
                      Action(kind="wait_for_state_change")]
        else:
            steps += [Action(kind="scan_and_click_cta"), Action(kind="wait_for_state_change")]
        return ActionPlan(steps=steps, hints=intents, raw_task=user_task)

class ExampleTasks:
    def __init__(self):
        p = Path(__file__).parent.parent / "tasks" / "examples.yaml"
        self.examples = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    def get_example(self, key: str): return self.examples.get(key)
