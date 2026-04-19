"""Multi-step goal planner with adaptive re-planning on failure."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.ai.client import get_client, get_model
from backend.ai.context_builder import format_context_for_prompt
from backend.config import settings

_SYSTEM = """You are an expert terminal planner. Break a high-level goal into atomic terminal commands.

Return ONLY valid JSON:
{
  "goal": "<concise restatement>",
  "steps": [
    {
      "id": 1,
      "description": "<what this step does>",
      "command": "<exact terminal command>",
      "depends_on": [],
      "risk_level": "low|medium|high"
    }
  ]
}

Rules:
- One command per step
- depends_on lists step IDs that must succeed first
- Keep steps atomic and ordered
- Use platform-appropriate commands from context
- Return ONLY the JSON object"""


@dataclass
class PlanStep:
    id: int
    description: str
    command: str
    depends_on: List[int]
    risk_level: str = "low"
    status: str = "pending"  # pending | running | done | failed | skipped
    output: Optional[str] = None
    exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "description": self.description,
            "command": self.command, "depends_on": self.depends_on,
            "risk_level": self.risk_level, "status": self.status,
        }


@dataclass
class Plan:
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"goal": self.goal, "steps": [s.to_dict() for s in self.steps]}

    def next_step(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.status != "pending":
                continue
            deps_ok = all(
                any(s.id == dep and s.status == "done" for s in self.steps)
                for dep in step.depends_on
            )
            if deps_ok or not step.depends_on:
                return step
        return None

    def highest_risk(self) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        return max((s.risk_level for s in self.steps), key=lambda r: order.get(r, 0), default="low")


async def plan(goal: str, context: Dict[str, Any]) -> Plan:
    if not settings.ai_available:
        return Plan(goal=goal, error="AI not available")

    prompt = f"Context:\n{format_context_for_prompt(context)}\n\nGoal: {goal}"
    try:
        resp = await get_client().chat.completions.create(
            model=get_model(),  # Smart model for planning
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=900,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return Plan(goal=goal, error=f"No JSON: {raw[:200]}")

        data = json.loads(m.group())
        steps = [
            PlanStep(
                id=s["id"],
                description=s.get("description", ""),
                command=s.get("command", ""),
                depends_on=s.get("depends_on", []),
                risk_level=s.get("risk_level", "low"),
            )
            for s in data.get("steps", [])
        ]
        return Plan(goal=data.get("goal", goal), steps=steps)
    except Exception as e:
        return Plan(goal=goal, error=str(e))


async def adapt_plan(original: Plan, failed_step: PlanStep, context: Dict[str, Any]) -> Plan:
    """Re-plan the remaining steps after a failure."""
    if not settings.ai_available:
        return original

    done = [s for s in original.steps if s.status == "done"]
    done_summary = "\n".join(f"  ✓ Step {s.id}: {s.command}" for s in done) or "  (none)"

    prompt = f"""A multi-step plan partially failed. Create a revised plan for the remaining work.

Goal: {original.goal}

Completed:{done_summary}

Failed step {failed_step.id}: {failed_step.description}
  Command: {failed_step.command}
  Output: {(failed_step.output or '')[:300]}

Create a new plan starting from where we left off. Use the same JSON schema."""

    try:
        resp = await get_client().chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            new_steps = [
                PlanStep(
                    id=s["id"],
                    description=s.get("description", ""),
                    command=s.get("command", ""),
                    depends_on=[],
                    risk_level=s.get("risk_level", "low"),
                )
                for s in data.get("steps", [])
            ]
            return Plan(goal=original.goal, steps=done + new_steps)
    except Exception:
        pass
    return original
