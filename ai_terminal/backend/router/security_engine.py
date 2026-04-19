"""3-stage security engine: pre-AI, post-AI, policy profiles."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from backend.config import settings

# ── Pattern sets ──────────────────────────────────────────────────────────────
_ALWAYS_BLOCK = [
    r"rm\s+-rf\s+/(?:\s|$)",
    r"dd\s+if=.*\s+of=/dev/",
    r"mkfs\.",
    r"format\s+[a-z]:",
    r"curl\s+.*\|\s*(?:ba)?sh",
    r"wget\s+.*\|\s*(?:ba)?sh",
    r"kill\s+-9\s+1\b",
    r">\s*/etc/passwd",
    r">\s*/etc/shadow",
    r">\s*/etc/sudoers",
    r":\s*\(\s*\)\s*\{.*\}\s*;",  # fork bomb
    r"powershell\s+.*-e[nc]+\s+",
    r"reg\s+delete.*HKLM",
    r"del\s+/[fqs].*\*",
    r"eval\s*\(\s*base64",
]

_SAFE_PROFILE_BLOCK = [
    r"\bsudo\b",
    r"\bchmod\s+[0-7]*7",
    r"\bchown\b.*root",
    r"\bsystemctl\b",
    r"\.\..*\.\..*\.\.",  # deep traversal
]

_HIGH_RISK_PATTERNS = [
    r"\brm\s+(-\w+\s+)*",
    r"\bdel\b",
    r"\bsudo\b",
    r"\btruncate\b",
    r"\bdrop\s+(table|database)\b",
    r"\bshred\b",
    r"\bwipe\b",
]


def _first_match(patterns: list, text: str) -> Optional[str]:
    t = text.lower()
    for pat in patterns:
        if re.search(pat, t):
            return pat
    return None


@dataclass
class ValidationResult:
    allowed: bool
    reason: str = ""
    block_level: str = "none"  # 'none' | 'warn' | 'block'


class SecurityEngine:
    def __init__(self, profile: Optional[str] = None):
        self.profile = profile or settings.SECURITY_PROFILE

    # Stage 1 — raw input before AI ───────────────────────────────────────────
    def pre_validate(self, user_input: str) -> ValidationResult:
        if not user_input or user_input.isspace():
            return ValidationResult(allowed=False, reason="Empty input", block_level="block")
        if m := _first_match(_ALWAYS_BLOCK, user_input):
            return ValidationResult(allowed=False, reason=f"Blocked dangerous pattern: {m}", block_level="block")
        if self.profile == "safe":
            if m := _first_match(_SAFE_PROFILE_BLOCK, user_input):
                return ValidationResult(allowed=False, reason=f"Blocked by safe profile: {m}", block_level="block")
        return ValidationResult(allowed=True)

    # Stage 2 — AI-generated command before execution ─────────────────────────
    def post_validate(self, command: str, risk_level: str = "low") -> ValidationResult:
        if m := _first_match(_ALWAYS_BLOCK, command):
            return ValidationResult(allowed=False, reason=f"AI command blocked: {m}", block_level="block")
        if self.profile == "safe":
            if m := _first_match(_SAFE_PROFILE_BLOCK, command):
                return ValidationResult(allowed=False, reason=f"Safe profile blocks: {m}", block_level="block")
        if risk_level == "high":
            return ValidationResult(allowed=True, reason="High-risk — requires explicit approval", block_level="warn")
        if risk_level == "medium":
            return ValidationResult(allowed=True, reason="Medium-risk — showing confirmation", block_level="warn")
        return ValidationResult(allowed=True)

    # Stage 3 — policy gates ──────────────────────────────────────────────────
    def needs_confirmation(self, risk_level: str) -> bool:
        if self.profile == "safe":
            return True
        if self.profile == "developer":
            return risk_level in ("medium", "high")
        return True  # custom: always confirm (plugins can override)

    def needs_local_routing(self, risk_level: str) -> bool:
        """Route high-risk commands to LM Studio when available."""
        return risk_level == "high" and settings.LM_STUDIO_AVAILABLE
