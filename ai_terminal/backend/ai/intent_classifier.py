"""Fast intent classification into 5 categories."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from backend.ai.client import get_client, get_model
from backend.config import settings

DIRECT_COMMANDS = frozenset([
    "ls", "dir", "cd", "mkdir", "rm", "del", "cp", "mv", "cat", "type",
    "ps", "tasklist", "pwd", "echo", "touch", "grep", "find", "head", "tail",
    "pip", "pip3", "python", "python3", "node", "npm", "git", "docker",
    "curl", "wget", "ping", "ssh", "scp", "rsync", "tar", "zip", "unzip",
    "chmod", "chown", "sudo", "make", "cargo", "go", "java", "mvn",
    "df", "du", "top", "htop", "kill", "killall", "ifconfig", "ipconfig",
    "which", "where", "whoami", "hostname", "date", "time", "history",
    "export", "env", "source", "clear", "cls", "exit", "logout",
    "vim", "nano", "less", "more", "sort", "wc", "awk", "sed", "cut",
    "systemctl", "service", "brew", "apt", "yum", "dnf", "pacman",
    "uvicorn", "gunicorn", "flask", "django-admin", "manage.py",
    "poetry", "pipenv", "conda", "venv",
])

META_PREFIXES = ("record ", "stop recording", "replay ", "stop", "export session", "import session")


class IntentType(str, Enum):
    DIRECT_EXEC = "direct_exec"
    NL_COMMAND = "nl_command"
    MULTI_STEP_GOAL = "multi_step_goal"
    QUESTION = "question"
    META_ACTION = "meta_action"


@dataclass
class IntentResult:
    intent: IntentType
    confidence: float = 1.0
    raw_input: str = ""


def _looks_like_prose(tail: str) -> bool:
    """Return True when the text after the command word reads as natural language.

    Heuristic: 3+ space-separated tokens that are all plain lowercase words
    (no flags like -l, no paths like /foo, no extensions like .py, no digits).
    E.g. "all the personal projects in my device" → True
         "-la /tmp --color"                        → False
    """
    tokens = tail.strip().split()
    if len(tokens) < 3:
        return False
    prose_tokens = [
        t for t in tokens
        if re.match(r'^[a-z]+$', t)   # purely lowercase letters
    ]
    return len(prose_tokens) >= len(tokens) * 0.75   # ≥75 % plain words


def _fast_classify(text: str) -> Optional[IntentResult]:
    """Rule-based pre-filter — avoids AI call for obvious cases."""
    s = text.strip()
    parts = s.split()
    first = parts[0].lower() if parts else ""
    tail = " ".join(parts[1:])

    # Shell command word detected — but check it isn't followed by natural prose
    if first in DIRECT_COMMANDS:
        if _looks_like_prose(tail):
            # Looks like NL, let AI decide — return low-confidence so AI is called
            return IntentResult(IntentType.NL_COMMAND, 0.5, text)
        return IntentResult(IntentType.DIRECT_EXEC, 0.97, text)

    # Meta actions
    if any(s.lower().startswith(p) for p in META_PREFIXES):
        return IntentResult(IntentType.META_ACTION, 0.92, text)

    # Questions
    if s.endswith("?") or any(s.lower().startswith(q) for q in ("what ", "why ", "how ", "explain ", "when ", "where ")):
        return IntentResult(IntentType.QUESTION, 0.88, text)

    # Multi-step goals
    goal_phrases = ("set up", "create a ", "initialize ", "bootstrap ", "build a ", "deploy ", "configure ", "install and setup", "scaffold")
    if any(p in s.lower() for p in goal_phrases):
        return IntentResult(IntentType.MULTI_STEP_GOAL, 0.78, text)

    return None


async def classify(text: str) -> IntentResult:
    """Classify user input. Fast rules first, then AI for ambiguous cases."""
    fast = _fast_classify(text)
    if fast and fast.confidence >= 0.9:
        return fast

    if not settings.ai_available:
        return fast or IntentResult(IntentType.NL_COMMAND, 0.5, text)

    prompt = f"""Classify this terminal input into exactly one category. Respond with JSON only.

Input: "{text}"

Categories:
- direct_exec: A shell command ready to execute (ls -la, git commit -m "fix", python app.py)
- nl_command: Natural language for a single shell command ("show me all python files", "list running processes")
- multi_step_goal: A multi-step project goal ("set up a Django project with postgres", "bootstrap a React app")
- question: Asking something, not doing something ("why did that fail?", "what does exit code 127 mean?")
- meta_action: Terminal management ("record session my-work", "replay my-work", "stop recording")

Return only: {{"intent": "<category>", "confidence": <0.0-1.0>}}"""

    try:
        resp = await get_client(fast=True).chat.completions.create(
            model=get_model(fast=True),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return IntentResult(
                intent=IntentType(data.get("intent", "nl_command")),
                confidence=float(data.get("confidence", 0.7)),
                raw_input=text,
            )
    except Exception as e:
        print(f"[intent_classifier] AI failed: {e}")

    return fast or IntentResult(IntentType.NL_COMMAND, 0.5, text)
