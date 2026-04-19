"""NL → structured command JSON. Returns InterpretResult with commands, rationale, risk."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.ai.client import get_client, get_model
from backend.ai.context_builder import format_context_for_prompt
from backend.config import settings

_SYSTEM = """You are an expert terminal assistant. Convert a natural language request into terminal commands.

Return ONLY valid JSON in this exact schema:
{
  "commands": ["<cmd1>", "<cmd2>"],
  "rationale": "<what the user wants, one sentence>",
  "risk_level": "low|medium|high",
  "explanation": "<side effects or risks, one sentence>"
}

Risk levels:
- low: read-only (ls, cat, grep, git status, git log, find)
- medium: creates/modifies files, installs packages, writes to disk
- high: deletes data, modifies system settings, sudo, network exfil

Return ONLY the JSON. No markdown. No extra text."""


@dataclass
class InterpretResult:
    commands: List[str]
    rationale: str
    risk_level: str
    explanation: str
    raw_json: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


async def interpret(user_input: str, context: Dict[str, Any], use_local: bool = False) -> InterpretResult:
    if not settings.ai_available:
        return InterpretResult([], "", "low", "", error="AI not available")

    ctx_str = format_context_for_prompt(context)
    user_msg = f"Context:\n{ctx_str}\n\nUser request: {user_input}"

    try:
        resp = await get_client(use_local=use_local).chat.completions.create(
            model=get_model(use_local=use_local),
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=400,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return InterpretResult([], "", "low", "", error=f"No JSON in response: {raw[:200]}")

        data = json.loads(m.group())
        cmds = data.get("commands", [])
        if isinstance(cmds, str):
            cmds = [cmds]

        return InterpretResult(
            commands=[c.strip() for c in cmds if c.strip()],
            rationale=data.get("rationale", ""),
            risk_level=data.get("risk_level", "low"),
            explanation=data.get("explanation", ""),
            raw_json=data,
        )
    except json.JSONDecodeError as e:
        return InterpretResult([], "", "low", "", error=f"JSON parse error: {e}")
    except Exception as e:
        return InterpretResult([], "", "low", "", error=str(e))
