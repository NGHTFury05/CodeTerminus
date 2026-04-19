"""SQLAlchemy async SQLite — three tables: commands, sessions, audit_log."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.config import settings


class Base(DeclarativeBase):
    pass


class CommandLog(Base):
    __tablename__ = "commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="local")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cwd: Mapped[str] = mapped_column(Text, default="")
    raw_input: Mapped[str] = mapped_column(Text)
    executed_cmd: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intent: Mapped[str] = mapped_column(String(32), default="unknown")
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stdout_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stderr_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    success: Mapped[bool] = mapped_column(Boolean, default=True)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    user_id: Mapped[str] = mapped_column(String(64), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cwd: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_type: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


# ── Engine & session factory ──────────────────────────────────────────────────
_engine = create_async_engine(settings.DB_URL, echo=False)
AsyncSessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables on startup."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def log_command(
    session_id: str,
    cwd: str,
    raw_input: str,
    executed_cmd: Optional[str] = None,
    intent: str = "unknown",
    exit_code: Optional[int] = None,
    duration_ms: Optional[float] = None,
    stdout_summary: Optional[str] = None,
    stderr_summary: Optional[str] = None,
    risk_level: str = "low",
    success: bool = True,
) -> int:
    async with AsyncSessionFactory() as db:
        entry = CommandLog(
            session_id=session_id,
            cwd=cwd,
            raw_input=raw_input,
            executed_cmd=executed_cmd,
            intent=intent,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout_summary=(stdout_summary or "")[:500],
            stderr_summary=(stderr_summary or "")[:500],
            risk_level=risk_level,
            success=success,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry.id


async def get_recent_commands(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(CommandLog)
            .where(CommandLog.session_id == session_id)
            .order_by(desc(CommandLog.timestamp))
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {
                "raw_input": r.raw_input,
                "executed_cmd": r.executed_cmd,
                "exit_code": r.exit_code,
                "cwd": r.cwd,
                "timestamp": r.timestamp.isoformat(),
                "success": r.success,
                "stdout_summary": r.stdout_summary,
                "stderr_summary": r.stderr_summary,
                "duration_ms": r.duration_ms,
            }
            for r in reversed(rows)
        ]


async def audit(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    async with AsyncSessionFactory() as db:
        entry = AuditLog(
            session_id=session_id,
            event_type=event_type,
            payload_json=json.dumps(payload),
        )
        db.add(entry)
        await db.commit()
