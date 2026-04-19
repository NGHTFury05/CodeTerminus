"""Central configuration — all settings loaded from .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_BASE = Path(__file__).parent.parent  # ai_terminal/


class Settings:
    # ── OpenRouter ────────────────────────────────────────────────────────────
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL_FAST: str = os.getenv("OPENROUTER_MODEL_FAST", "meta-llama/llama-3.1-8b-instruct:free")
    MODEL_SMART: str = os.getenv("OPENROUTER_MODEL_SMART", "meta-llama/llama-3.3-70b-instruct:free")

    # ── LM Studio (local, optional) ────────────────────────────────────────────
    LM_STUDIO_URL: str = os.getenv("LM_STUDIO_URL", "")
    LM_STUDIO_MODEL: str = os.getenv("LM_STUDIO_MODEL", "local-model")

    @property
    def LM_STUDIO_AVAILABLE(self) -> bool:
        return bool(self.LM_STUDIO_URL)

    # ── Vector store ───────────────────────────────────────────────────────────
    USE_VECTOR_STORE: bool = os.getenv("USE_VECTOR_STORE", "true").lower() == "true"
    CHROMA_PATH: Path = _BASE / "data" / "chroma"

    # ── Security ───────────────────────────────────────────────────────────────
    SECURITY_PROFILE: str = os.getenv("SECURITY_PROFILE", "developer")
    # developer: low=auto, medium=confirm, high=local+confirm
    # safe:      all NL commands require confirmation
    # custom:    controlled by plugins

    # ── Timeouts ───────────────────────────────────────────────────────────────
    MAX_CMD_TIMEOUT: int = int(os.getenv("MAX_COMMAND_TIMEOUT_SECONDS", "30"))
    SESSION_TIMEOUT: int = int(os.getenv("SESSION_TIMEOUT_SECONDS", "3600"))

    # ── Paths ──────────────────────────────────────────────────────────────────
    SESSIONS_DIR: Path = _BASE / "sessions"
    PLUGINS_DIR: Path = _BASE / "plugins"
    DATA_DIR: Path = _BASE / "data"

    # ── Database ───────────────────────────────────────────────────────────────
    DB_PATH: Path = _BASE / "data" / "terminal.db"
    DB_URL: str = f"sqlite+aiosqlite:///{_BASE / 'data' / 'terminal.db'}"

    def ensure_dirs(self) -> None:
        for d in (self.SESSIONS_DIR, self.PLUGINS_DIR, self.DATA_DIR, self.CHROMA_PATH):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def ai_available(self) -> bool:
        return bool(self.OPENROUTER_API_KEY) or self.LM_STUDIO_AVAILABLE


settings = Settings()
