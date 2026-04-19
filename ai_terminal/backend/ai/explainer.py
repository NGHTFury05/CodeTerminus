"""Post-execution explanation engine: error analysis and Q&A."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.ai.client import get_client, get_model
from backend.config import settings


async def explain_error(
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    context: Dict[str, Any],
) -> str:
    """Explain a failed command in plain English with actionable next steps."""
    if not settings.ai_available:
        return "AI explanation not available."

    prompt = f"""A terminal command failed. Explain the error in plain language and suggest a fix.

OS: {context.get('os', '')}
CWD: {context.get('cwd', '')}
Command: {command}
Exit code: {exit_code}
Stdout: {(stdout or '(empty)')[:400]}
Stderr: {(stderr or '(empty)')[:400]}

Reply in 2-4 sentences: what went wrong and exactly what to try next."""

    try:
        resp = await get_client().chat.completions.create(
            model=get_model(fast=True),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=220,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not generate explanation: {e}"


async def answer_question(
    question: str,
    context: Dict[str, Any],
    recent_output: Optional[str] = None,
) -> str:
    """Answer a user question about their terminal, last command, or system."""
    if not settings.ai_available:
        return "AI service not available."

    ctx_lines = [
        f"OS: {context.get('os', '')}",
        f"CWD: {context.get('cwd', '')}",
    ]
    for c in context.get("recent_commands", [])[-3:]:
        ctx_lines.append(f"  $ {c['raw_input']}  → exit {c['exit_code']}")
    if recent_output:
        ctx_lines.append(f"Last output:\n{recent_output[:400]}")

    prompt = f"""You are a helpful terminal assistant. Answer the user's question.

Context:
{chr(10).join(ctx_lines)}

Question: {question}

Answer concisely (2-5 sentences), with terminal-specific precision."""

    try:
        resp = await get_client().chat.completions.create(
            model=get_model(fast=True),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not answer: {e}"
