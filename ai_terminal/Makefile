.PHONY: install dev run lint clean

# ── Installation ──────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	@echo ""
	@echo "✅ Dependencies installed."
	@echo "   Copy .env.example to .env and add your OPENROUTER_API_KEY"

# ── Development ───────────────────────────────────────────────────────────────
dev:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# ── Production ────────────────────────────────────────────────────────────────
run:
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1

# ── Utilities ─────────────────────────────────────────────────────────────────
clean:
	rm -rf data/terminal.db data/chroma __pycache__ backend/**/__pycache__
	@echo "🧹 Cleaned database and cache files."

setup:
	cp -n .env.example .env || true
	pip install -r requirements.txt
	@echo ""
	@echo "✅ Setup complete. Edit .env with your API key then run: make dev"
