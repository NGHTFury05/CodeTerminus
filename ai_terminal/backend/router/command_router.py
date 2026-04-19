"""Central command router — intent dispatch → security → AI → sandbox → storage."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from backend.ai import context_builder, explainer, interpreter, planner
from backend.ai.intent_classifier import IntentType, classify
from backend.exec.sandbox import Sandbox
from backend.router.security_engine import SecurityEngine
from backend.storage import db as dbmod
from backend.storage import sessions as sessions_mod
from backend.storage import vector_store
from backend.config import settings


# ── Session state ─────────────────────────────────────────────────────────────
@dataclass
class SessionState:
    session_id: str
    cwd: str = field(default_factory=lambda: __import__("os").getcwd())
    sandbox: Optional[Sandbox] = None
    # Recording
    recording: bool = False
    recording_name: str = ""
    recording_commands: List[str] = field(default_factory=list)
    # Plan execution
    current_plan: Optional[planner.Plan] = None
    # Pending confirmation
    pending_commands: List[str] = field(default_factory=list)
    pending_risk: str = "low"
    pending_rationale: str = ""
    pending_explanation: str = ""
    # Last output (for Q&A context)
    last_stdout: str = ""
    last_stderr: str = ""
    last_exit_code: Optional[int] = None


# ── Message helpers ───────────────────────────────────────────────────────────
def _chunk(text: str, stream: str = "stdout") -> Dict:
    return {"type": "output_chunk", "text": text, "stream": stream}

def _thought(text: str) -> Dict:
    return {"type": "thought", "text": text}

def _err(text: str) -> Dict:
    return {"type": "output_chunk", "text": f"\x1b[31m{text}\x1b[0m\r\n", "stream": "stderr"}

def _cwd(path: str) -> Dict:
    return {"type": "cwd_change", "cwd": path}


# ── Router ────────────────────────────────────────────────────────────────────
class CommandRouter:
    def __init__(self, session: SessionState):
        self.session = session
        self.security = SecurityEngine()
        if self.session.sandbox is None:
            self.session.sandbox = Sandbox(session.session_id, initial_cwd=session.cwd)

    @property
    def _sb(self) -> Sandbox:
        return self.session.sandbox

    # ── Entry point ───────────────────────────────────────────────────────────
    async def handle(self, user_input: str) -> AsyncIterator[Dict]:
        # Stage 1 security check
        v = self.security.pre_validate(user_input)
        if not v.allowed:
            await dbmod.audit(self.session.session_id, "blocked_input", {"input": user_input, "reason": v.reason})
            yield _err(f"🚫 Blocked: {v.reason}")
            return

        # Classify intent
        yield _thought("Classifying intent…")
        intent_result = await classify(user_input)
        intent = intent_result.intent
        yield _thought(f"Intent: {intent.value}  confidence {intent_result.confidence:.0%}")

        if intent == IntentType.DIRECT_EXEC:
            async for m in self._direct(user_input):
                yield m
        elif intent == IntentType.NL_COMMAND:
            async for m in self._nl_command(user_input):
                yield m
        elif intent == IntentType.MULTI_STEP_GOAL:
            async for m in self._goal(user_input):
                yield m
        elif intent == IntentType.QUESTION:
            async for m in self._question(user_input):
                yield m
        elif intent == IntentType.META_ACTION:
            async for m in self._meta(user_input):
                yield m
        else:
            async for m in self._nl_command(user_input):
                yield m

    # ── Confirmation response ─────────────────────────────────────────────────
    async def handle_confirm(self, action: str, edited_cmd: Optional[str] = None) -> AsyncIterator[Dict]:
        if action == "approve":
            cmds = [edited_cmd] if edited_cmd else self.session.pending_commands
            async for m in self._exec_commands(cmds, "nl_command", " && ".join(cmds), self.session.pending_risk):
                yield m
            self.session.pending_commands = []
        elif action == "retry":
            self.session.pending_commands = []
            yield _chunk("↩ Please rephrase your request.\r\n", "system")
        else:  # edit
            self.session.pending_commands = []

    # ── Intent handlers ───────────────────────────────────────────────────────
    async def _direct(self, command: str) -> AsyncIterator[Dict]:
        async for m in self._exec_commands([command], "direct_exec", command, "low"):
            yield m

    async def _nl_command(self, user_input: str) -> AsyncIterator[Dict]:
        ctx = await context_builder.build(self.session.session_id, user_input, self.session.cwd)
        yield _thought("Interpreting natural language…")

        use_local = False
        result = await interpreter.interpret(user_input, ctx, use_local=use_local)

        if result.error or not result.commands:
            yield _err(f"Interpretation failed: {result.error or 'No command generated'}")
            return

        # Post-validate each command
        for cmd in result.commands:
            pv = self.security.post_validate(cmd, result.risk_level)
            if not pv.allowed:
                await dbmod.audit(self.session.session_id, "blocked_ai_cmd", {"cmd": cmd, "reason": pv.reason})
                yield _err(f"🚫 {pv.reason}")
                return

        # Re-route high-risk to LM Studio
        if result.risk_level == "high" and settings.LM_STUDIO_AVAILABLE:
            yield _thought("High-risk detected → routing to local model…")
            local = await interpreter.interpret(user_input, ctx, use_local=True)
            if local.commands and not local.error:
                result = local

        yield _thought(f"Rationale: {result.rationale}")

        if self.security.needs_confirmation(result.risk_level):
            self.session.pending_commands = result.commands
            self.session.pending_risk = result.risk_level
            self.session.pending_rationale = result.rationale
            self.session.pending_explanation = result.explanation
            yield {
                "type": "intent_card",
                "intent": "nl_command",
                "commands": result.commands,
                "rationale": result.rationale,
                "risk": result.risk_level,
                "explanation": result.explanation,
            }
            return

        # Auto-execute (low risk, developer profile)
        async for m in self._exec_commands(result.commands, "nl_command", user_input, result.risk_level):
            yield m

    async def _goal(self, goal: str) -> AsyncIterator[Dict]:
        ctx = await context_builder.build(self.session.session_id, goal, self.session.cwd)
        yield _thought("Planning multi-step goal…")
        p = await planner.plan(goal, ctx)
        if p.error or not p.steps:
            yield _err(f"Planning failed: {p.error or 'No steps generated'}")
            return
        self.session.current_plan = p
        yield {"type": "goal_plan", **p.to_dict()}
        yield {
            "type": "intent_card",
            "intent": "multi_step_goal",
            "commands": [s.command for s in p.steps],
            "rationale": f"Execute {len(p.steps)} steps to accomplish: {p.goal}",
            "risk": p.highest_risk(),
            "explanation": f"{len(p.steps)} steps planned. Review and approve to begin execution.",
        }

    async def execute_plan(self) -> AsyncIterator[Dict]:
        p = self.session.current_plan
        if not p:
            return
        total = len(p.steps)
        for step in p.steps:
            step.status = "running"
            yield {"type": "step_update", "step_id": step.id, "status": "running"}
            yield _chunk(f"\r\n\x1b[1;36m━━ Step {step.id}/{total}: {step.description} ━━\x1b[0m\r\n", "system")
            yield _chunk(f"\x1b[2m$ {step.command}\x1b[0m\r\n", "system")

            stdout_buf, stderr_buf, exit_code = [], [], 0
            async for chunk in self._sb.run(step.command):
                if chunk.stream == "stdout":
                    stdout_buf.append(chunk.text); yield _chunk(chunk.text, "stdout")
                elif chunk.stream == "stderr":
                    stderr_buf.append(chunk.text); yield _chunk(chunk.text, "stderr")
                elif chunk.stream == "system":
                    if chunk.exit_code is not None:
                        exit_code = chunk.exit_code
                    if chunk.cwd:
                        self.session.cwd = self._sb.cwd = chunk.cwd
                        yield _cwd(chunk.cwd)

            step.output = ("".join(stdout_buf + stderr_buf))[:500]
            step.exit_code = exit_code

            if exit_code == 0:
                step.status = "done"
                yield {"type": "step_update", "step_id": step.id, "status": "done"}
            else:
                step.status = "failed"
                yield {"type": "step_update", "step_id": step.id, "status": "failed", "output": step.output}
                yield _chunk(f"\r\n\x1b[33m⚠ Step {step.id} failed. Adapting plan…\x1b[0m\r\n", "system")
                ctx = await context_builder.build(self.session.session_id, p.goal, self.session.cwd)
                self.session.current_plan = await planner.adapt_plan(p, step, ctx)
                yield {"type": "goal_plan", **self.session.current_plan.to_dict()}
                break

        if all(s.status == "done" for s in self.session.current_plan.steps):
            yield _chunk(f"\r\n\x1b[1;32m✓ Goal complete: {p.goal}\x1b[0m\r\n", "system")
            self.session.current_plan = None

    async def _question(self, question: str) -> AsyncIterator[Dict]:
        ctx = await context_builder.build(self.session.session_id, question, self.session.cwd)
        yield _thought("Answering your question…")
        recent_out = self.session.last_stdout or self.session.last_stderr
        answer = await explainer.answer_question(question, ctx, recent_out)
        yield _chunk(f"\r\n\x1b[1;34m🤖 {answer}\x1b[0m\r\n\r\n", "system")

    async def _meta(self, command: str) -> AsyncIterator[Dict]:
        s = command.lower().strip()
        if s.startswith("record "):
            name = command[7:].strip()
            self.session.recording = True
            self.session.recording_name = name
            self.session.recording_commands = []
            yield _chunk(f"\r\n🔴 Recording: {name}\r\n", "system")
            yield {"type": "recording_status", "recording": True, "name": name}
        elif s in ("stop", "stop recording"):
            if self.session.recording:
                sessions_mod.save_session(self.session.recording_name, self.session.recording_commands)
                self.session.recording = False
                yield _chunk(f"\r\n⏹ Saved '{self.session.recording_name}' ({len(self.session.recording_commands)} commands)\r\n", "system")
                yield {"type": "recording_status", "recording": False}
                yield {"type": "sessions", "sessions": sessions_mod.list_sessions()}
        elif s.startswith("replay "):
            name = command[7:].strip()
            data = sessions_mod.load_session(name)
            if not data:
                yield _err(f"Session '{name}' not found")
                return
            cmds = data.get("commands", [])
            yield _chunk(f"\r\n▶ Replaying '{name}' ({len(cmds)} commands)\r\n", "system")
            for i, cmd in enumerate(cmds):
                yield _chunk(f"\r\n[{i+1}/{len(cmds)}] $ {cmd}\r\n", "system")
                async for ch in self._sb.run(cmd):
                    if ch.stream in ("stdout", "stderr"):
                        yield _chunk(ch.text, ch.stream)
                    elif ch.stream == "system" and ch.cwd:
                        self.session.cwd = self._sb.cwd = ch.cwd
                        yield _cwd(ch.cwd)
                await asyncio.sleep(0.3)
            yield _chunk("\r\n✅ Replay complete\r\n", "system")
        else:
            yield _err(f"Unknown meta command: {command}")

    # ── Shared execution helper ───────────────────────────────────────────────
    async def _exec_commands(
        self, commands: List[str], intent_str: str, raw_input: str, risk_level: str
    ) -> AsyncIterator[Dict]:
        for cmd in commands:
            pv = self.security.post_validate(cmd, risk_level)
            if not pv.allowed:
                yield _err(f"🚫 Blocked: {pv.reason}")
                continue

            yield _chunk(f"\x1b[2m$ {cmd}\x1b[0m\r\n", "system")
            stdout_buf, stderr_buf, exit_code, duration_ms = [], [], 0, 0.0
            start_cwd = self.session.cwd

            async for chunk in self._sb.run(cmd):
                if chunk.stream == "stdout":
                    stdout_buf.append(chunk.text); yield _chunk(chunk.text, "stdout")
                elif chunk.stream == "stderr":
                    stderr_buf.append(chunk.text); yield _chunk(chunk.text, "stderr")
                elif chunk.stream == "system":
                    if chunk.exit_code is not None:
                        exit_code = chunk.exit_code
                    if chunk.duration_ms is not None:
                        duration_ms = chunk.duration_ms
                    if chunk.cwd:
                        self.session.cwd = self._sb.cwd = chunk.cwd
                        yield _cwd(chunk.cwd)

            stdout_str = "".join(stdout_buf)
            stderr_str = "".join(stderr_buf)
            self.session.last_stdout = stdout_str
            self.session.last_stderr = stderr_str
            self.session.last_exit_code = exit_code

            if self.session.recording:
                self.session.recording_commands.append(cmd)

            await dbmod.log_command(
                session_id=self.session.session_id,
                cwd=start_cwd,
                raw_input=raw_input,
                executed_cmd=cmd,
                intent=intent_str,
                exit_code=exit_code,
                duration_ms=duration_ms,
                stdout_summary=stdout_str[:500],
                stderr_summary=stderr_str[:500],
                risk_level=risk_level,
                success=exit_code == 0,
            )

            vector_store.add(
                text=f"{raw_input} → {cmd}",
                metadata={
                    "session_id": self.session.session_id,
                    "cmd": cmd,
                    "exit_code": str(exit_code),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            if duration_ms > 500:
                yield _chunk(f"\x1b[2m[{duration_ms:.0f}ms · exit {exit_code}]\x1b[0m\r\n", "system")

            if exit_code != 0 and settings.ai_available and stderr_str.strip():
                yield _thought("Generating error explanation…")
                ctx = await context_builder.build(self.session.session_id, cmd, self.session.cwd)
                exp = await explainer.explain_error(cmd, stdout_str, stderr_str, exit_code, ctx)
                yield _chunk(f"\r\n\x1b[33m💡 {exp}\x1b[0m\r\n", "system")
