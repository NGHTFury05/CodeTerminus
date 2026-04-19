"""Plugin base class — ABC interface for CodeTerminus plugins."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CustomCommand:
    name: str
    description: str
    aliases: List[str] = field(default_factory=list)


class Plugin(ABC):
    """Base class for all CodeTerminus plugins.

    Drop a .py file implementing this class into the plugins/ directory.
    It will be loaded automatically at startup.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Semver version string."""
        ...

    @property
    def description(self) -> str:
        return ""

    def on_load(self) -> None:
        """Called once at startup after the plugin is registered."""
        pass

    def on_command(self, command: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Called before every command executes.
        Return a modified command string, or None to pass through unchanged.
        """
        return None

    def on_output(self, output: str, stream: str) -> str:
        """
        Transform command output before it is sent to the client.
        Return the (possibly modified) output string.
        """
        return output

    def on_ai_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called after AI generates an interpretation result.
        May modify or augment the result dict (commands, risk_level, explanation).
        """
        return result

    def get_custom_commands(self) -> List[CustomCommand]:
        """Declare custom commands this plugin provides to the intent classifier."""
        return []

    def get_security_allowlist(self) -> List[str]:
        """Return regex patterns this plugin explicitly allows (bypasses safe profile blocks)."""
        return []
