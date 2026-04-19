# CodeTerminus — AI Terminal Agent 🖥️🤖

> An intelligent, context-aware terminal agent that understands natural language, plans multi-step goals, explains errors, and remembers your session — all inside a browser-based terminal powered by a FastAPI + WebSocket backend.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage Guide](#usage-guide)
- [Intent Classification](#intent-classification)
- [Security System](#security-system)
- [Storage & Memory](#storage--memory)
- [Plugin System](#plugin-system)
- [AI Intelligence Layer](#ai-intelligence-layer)
- [System Monitoring](#system-monitoring)
- [Session Recording & Replay](#session-recording--replay)
- [Known Limitations & Bugs Fixed](#known-limitations--bugs-fixed)
- [Requirements](#requirements)

---

## Overview

CodeTerminus is a full-stack, agentic terminal application. Unlike a traditional terminal, it can:

- **Understand natural language** — type `"show me all Python files modified today"` and it translates that into the right shell command automatically.
- **Plan multi-step goals** — type `"set up a Django project with Postgres"` and it generates, previews, and executes a step-by-step plan.
- **Explain errors** — when a command fails, the AI explains what went wrong and suggests a fix.
- **Remember context** — previous commands, outputs, and goals are stored in a SQLite database and a ChromaDB vector store for intelligent context recall.
- **Route high-risk commands** — dangerous commands are confirmed before execution, and optionally re-verified through a local LM Studio model.

---

## Features

### 🧠 AI Intelligence Layer
- **Intent Classification** — every input is classified into one of 5 intents: direct shell command, natural language command, multi-step goal, question, or terminal meta-action. A fast rule-based pre-filter handles obvious cases; ambiguous inputs go to the AI.
- **Natural Language Interpreter** — converts plain-English requests into shell commands with risk assessment and rationale.
- **Multi-step Goal Planner** — breaks complex goals into ordered steps, executes them sequentially, and adapts the plan if a step fails.
- **Error Explainer** — when a command exits non-zero, the AI explains the error in plain English using stdout/stderr context.
- **Q&A Mode** — ask questions about the last output or any topic (`"what does exit code 127 mean?"`) and get a direct answer.
- **Context Builder** — assembles relevant context (recent commands, current directory, vector-store recalls) before each AI call.

### 🛡️ Multi-Layer Security
- Pre-execution input validation with regex patterns for injection, path traversal, and dangerous operations.
- Post-execution AI-command validation with risk scoring (`low` / `medium` / `high`).
- Security profiles: `developer` (low-risk auto-executes), `safe` (all NL commands need confirmation), `custom` (plugin-driven).
- High-risk commands optionally re-routed to a local LM Studio model for offline verification.

### 💾 Persistent Storage & Memory
- **SQLite** (via SQLAlchemy async) — stores all executed commands, exit codes, durations, and summaries.
- **ChromaDB vector store** — indexes command history as embeddings for semantic recall (`"commands like what I ran yesterday"`).
- **Session files** (`.aits` format) — recorded command sequences that can be replayed in one click.

### 📊 Real-time System Monitoring
- CPU, RAM, GPU (if available), Disk I/O, Network I/O, and process count — updated every 2 seconds via the live WebSocket connection.

### 🎬 Session Recording & Replay
- Start recording with a session name, run commands normally, stop to save. Replay any saved session in one click from the sidebar.

### 🌐 xterm.js Terminal Frontend
- Full ANSI colour and escape-code rendering.
- WebSocket-based real-time streaming — output appears as it's generated, not after the command finishes.
- Auto-reconnects with exponential backoff if the server is temporarily unavailable.
- Command Palette (Ctrl+K or `/`) for quick access to history, sessions, and suggestions.
- AI Thoughts sidebar shows the agent's internal reasoning steps.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Frontend)                    │
│  xterm.js terminal  ·  Metrics bar  ·  Context sidebar  │
│  Command Palette    ·  Intent Card  ·  Goal Checklist   │
└────────────────────────┬────────────────────────────────┘
                         │  WebSocket /ws/{session_id}
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI Backend                          │
│                                                          │
│  ┌─────────────┐    ┌──────────────────────────────┐   │
│  │ REST API    │    │      WebSocket Handler        │   │
│  │ /api/*      │    │  CommandRouter ─► Sandbox     │   │
│  └─────────────┘    └──────────┬───────────────────┘   │
│                                │                         │
│  ┌─────────────────────────────▼──────────────────────┐ │
│  │              AI Intelligence Layer                  │ │
│  │  IntentClassifier → Interpreter / Planner /        │ │
│  │  Explainer / ContextBuilder                        │ │
│  └─────────────────────────────┬──────────────────────┘ │
│                                │                         │
│  ┌─────────────────────────────▼──────────────────────┐ │
│  │                    Storage                          │ │
│  │    SQLite (aiosqlite)  ·  ChromaDB  ·  .aits files │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                         │
              OpenRouter API / LM Studio (local)
```

---

## Directory Structure

```
CodeTerminus/
└── ai_terminal/
    ├── backend/
    │   ├── main.py               # FastAPI app, WebSocket gateway, static server
    │   ├── config.py             # Central settings loaded from .env
    │   ├── ai/
    │   │   ├── client.py         # OpenRouter / LM Studio client factory
    │   │   ├── intent_classifier.py  # 5-category intent classification
    │   │   ├── interpreter.py    # NL → shell command translation
    │   │   ├── planner.py        # Multi-step goal planning & adaptation
    │   │   ├── explainer.py      # Error explanation & Q&A answering
    │   │   └── context_builder.py    # Assembles context for AI calls
    │   ├── exec/
    │   │   ├── sandbox.py        # Async subprocess executor with cwd tracking
    │   │   └── os_adapter.py     # Cross-platform command translation & metrics
    │   ├── router/
    │   │   ├── command_router.py # Main dispatch: intent → handler
    │   │   └── security_engine.py    # Pre/post-execution security validation
    │   ├── storage/
    │   │   ├── db.py             # SQLAlchemy async schema + query helpers
    │   │   ├── vector_store.py   # ChromaDB add/query wrapper
    │   │   └── sessions.py       # .aits session file load/save/list
    │   └── plugins/
    │       ├── base.py           # Plugin base class interface
    │       └── registry.py       # Plugin loader from plugins/ directory
    ├── frontend/
    │   ├── index.html            # Single-page app shell
    │   ├── css/                  # Styles
    │   └── js/
    │       ├── app.js            # Root: bootstraps all components, wires WS events
    │       ├── ws.js             # WebSocket manager with reconnect + ping
    │       ├── terminal.js       # xterm.js wrapper
    │       ├── metrics.js        # System metrics display
    │       ├── commandPalette.js # Ctrl+K command palette
    │       ├── intentCard.js     # AI confirmation card UI
    │       ├── goalChecklist.js  # Multi-step plan checklist UI
    │       ├── contextSidebar.js # History, sessions, AI thoughts sidebar
    │       └── utils.js          # Shared DOM helpers
    ├── data/                     # Auto-created: terminal.db + chroma vector store
    ├── sessions/                 # Auto-created: .aits recorded session files
    ├── plugins/                  # Drop-in plugin directory
    ├── .env                      # Your local config (never commit this)
    ├── .env.example              # Template for .env
    ├── requirements.txt
    └── Makefile
```

---

## Installation

### Prerequisites
- Python 3.10+ (Anaconda or system Python)
- Internet connection (for OpenRouter AI calls)
- A free [OpenRouter API key](https://openrouter.ai/keys)

### Steps

**1. Clone the repository**
```bash
git clone https://github.com/NGHTFury05/CodeTerminus.git
cd CodeTerminus/ai_terminal
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set up environment**
```bash
cp .env.example .env
# Open .env and add your OPENROUTER_API_KEY
```

---

## Configuration

All settings live in `ai_terminal/.env`. Copy `.env.example` and fill in your values:

```env
# ── Required ─────────────────────────────────────
OPENROUTER_API_KEY=sk-or-v1-...        # Get from https://openrouter.ai/keys

# ── Model selection (free tier models shown) ─────
OPENROUTER_MODEL_FAST=google/gemma-4-31b-it:free      # Used for intent classification
OPENROUTER_MODEL_SMART=nvidia/nemotron-super-120b:free # Used for planning & interpretation

# ── Local model (optional) ────────────────────────
LM_STUDIO_URL=                         # Set to http://localhost:1234 if using LM Studio
LM_STUDIO_MODEL=local-model            # Model name in LM Studio

# ── Features ──────────────────────────────────────
USE_VECTOR_STORE=true                  # Enable ChromaDB semantic memory

# ── Security profile ──────────────────────────────
# developer: low-risk auto-executes, medium/high needs confirmation
# safe:      all NL commands require confirmation
# custom:    controlled by plugins
SECURITY_PROFILE=developer

# ── Timeouts ──────────────────────────────────────
MAX_COMMAND_TIMEOUT_SECONDS=30
SESSION_TIMEOUT_SECONDS=3600
```

---

## Running the Application

From inside `ai_terminal/`:

```bash
# Development (auto-reloads on file changes)
make dev

# Production
make run
```

Then open your browser at **http://localhost:8000**.

> The backend serves the frontend — no separate build step needed.

### Other Makefile commands

| Command | Description |
|---|---|
| `make install` | Install dependencies |
| `make dev` | Start with hot-reload |
| `make run` | Start production server |
| `make clean` | Delete database and cache files |
| `make setup` | First-time setup (copies .env, installs deps) |

---

## Usage Guide

### Direct shell commands
Type any standard shell command and it executes immediately:
```
$ ls -la
$ git status
$ python app.py
$ cd ~/Documents
```

### Natural language commands
Describe what you want in plain English:
```
show me all python files modified today
find all folders larger than 1 GB
list processes using port 8000
compress the logs folder into an archive
```
The agent translates your request into the correct command, shows you what it intends to run (with risk level and rationale), then executes it according to your security profile.

### Multi-step goals
Describe a larger objective:
```
set up a new Django project with postgres
create a React app with TypeScript and Tailwind
initialize a git repo and push it to GitHub
```
The agent generates a step-by-step plan, shows it in the Goal Checklist panel, waits for your approval, then executes each step in sequence. If a step fails, it adapts the remaining plan.

### Asking questions
Ask anything about the terminal or last output:
```
why did that command fail?
what does exit code 127 mean?
what is the difference between chmod 755 and 644?
```

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Open Command Palette |
| `/` | Open Command Palette (when focused on page) |
| `Escape` | Close palette / cancel |
| `Ctrl+C` | Interrupt running command |

---

## Intent Classification

Every input goes through a two-stage classification pipeline:

**Stage 1 — Fast rule-based filter:**
- If the first word is a known shell command (e.g. `git`, `ls`, `python`) *and* the rest doesn't look like natural-language prose → `DIRECT_EXEC`
- If the input starts with question words or ends with `?` → `QUESTION`
- If it contains goal-oriented phrases (`set up`, `deploy`, `scaffold`) → `MULTI_STEP_GOAL`
- If it matches session meta-commands (`record`, `replay`, `stop`) → `META_ACTION`

**Stage 2 — AI classification (for ambiguous inputs):**
- The input is sent to the fast model with a structured prompt
- Returns one of: `direct_exec`, `nl_command`, `multi_step_goal`, `question`, `meta_action`

> **Note:** The prose-detection heuristic prevents sentences like `"find all the personal projects in my device"` from being passed verbatim to the shell `find` command.

---

## Security System

### Security profiles

| Profile | Low risk | Medium risk | High risk |
|---|---|---|---|
| `developer` | Auto-execute | Confirm | Local model + Confirm |
| `safe` | Confirm | Confirm | Blocked |
| `custom` | Plugin-defined | Plugin-defined | Plugin-defined |

### What gets blocked (pre-execution)
- Command injection: `;`, `&&`, `\|\|`, `\`...\``, `$(...)`, `{...}`
- Destructive operations: `rm -rf /`, `dd if=/dev/zero`, `mkfs`
- Privilege escalation: `sudo su`, `passwd root`
- Network execution: `curl ... | sh`, `wget ... | bash`
- Excessive path traversal: `../../..`

### Risk levels on AI-generated commands
- `low` — read-only operations, safe file operations
- `medium` — writes, installs, config changes
- `high` — system-level changes, network operations, deletions

---

## Storage & Memory

### SQLite database (`data/terminal.db`)
Stores every executed command with:
- Session ID, working directory, raw user input
- Translated shell command, intent type, risk level
- Exit code, duration (ms), stdout/stderr summaries
- Timestamp

Used for: command history sidebar, session recall, error context.

### ChromaDB vector store (`data/chroma/`)
Indexes `"user input → command"` pairs as sentence embeddings.
Used for: semantic similarity recall when building AI context (`"find commands like what I ran to set up postgres last week"`).

Disable with `USE_VECTOR_STORE=false` in `.env` for lighter setups.

### Session files (`sessions/*.aits`)
JSON files storing recorded command sequences. Load and replay from the sidebar.

---

## Plugin System

Drop a Python file into `ai_terminal/plugins/` that subclasses `PluginBase` and it's auto-loaded at startup. Plugins can:
- Add custom intent handlers
- Override security decisions
- Inject additional context into AI calls

See `backend/plugins/base.py` for the interface.

---

## AI Intelligence Layer

| Module | Responsibility |
|---|---|
| `client.py` | Factory for OpenRouter and LM Studio clients; selects fast vs. smart model |
| `intent_classifier.py` | Two-stage classification; prose detection to prevent shell misrouting |
| `interpreter.py` | NL → shell command; returns commands + risk + rationale + explanation |
| `planner.py` | Goal → ordered steps; `adapt_plan()` regenerates remaining steps after failure |
| `explainer.py` | `explain_error()` on stderr; `answer_question()` for Q&A mode |
| `context_builder.py` | Assembles recent DB history + vector-store recalls for every AI call |

---

## System Monitoring

A background task pushes system metrics over the WebSocket every 2 seconds:

| Metric | Source |
|---|---|
| CPU % | `psutil.cpu_percent()` |
| RAM % | `psutil.virtual_memory()` |
| GPU % | `GPUtil.getGPUs()` (N/A if no GPU) |
| Disk read/write MB/s | `psutil.disk_io_counters()` |
| Disk % | `psutil.disk_usage()` |
| Network sent/recv MB/s | `psutil.net_io_counters()` |
| Process count | `psutil.pids()` |

---

## Session Recording & Replay

1. Enter a name in the "Sessions" sidebar input and click **Record** (or type `record <name>` in the terminal).
2. Execute commands normally — every command is appended to the recording.
3. Click **Stop** (or type `stop`) to save the session as a `.aits` file.
4. Click any saved session in the sidebar (or type `replay <name>`) to re-execute the full sequence.

---

## Known Limitations & Bugs Fixed

| Bug | Status |
|---|---|
| `Sandbox.__init__` called with `cwd=` instead of `initial_cwd=` — caused every WebSocket connection to crash immediately, producing an infinite "Connection lost" loop | ✅ Fixed |
| Intent classifier treated any sentence starting with a known shell command word (e.g. `find`, `grep`, `echo`) as `DIRECT_EXEC` with 97% confidence, passing natural-language prose verbatim to the shell | ✅ Fixed — prose detection heuristic added |

---

## Requirements

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-dotenv>=1.0.0
openai>=1.30.0          # OpenRouter-compatible client
psutil>=5.9.0
GPUtil>=1.4.0
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.19.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
aiofiles>=23.0.0
```

---

*Built with FastAPI · xterm.js · ChromaDB · OpenRouter*
