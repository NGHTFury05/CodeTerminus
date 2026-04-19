/** Command Palette — Ctrl+K fuzzy-search over history, sessions, quick commands. */
import { $, el } from './utils.js';

const QUICK_COMMANDS = [
  { icon: '📁', text: 'list files', sub: 'ls -la', type: 'quick' },
  { icon: '🔍', text: 'find python files', sub: 'find . -name "*.py"', type: 'quick' },
  { icon: '🌿', text: 'git status', sub: 'git status', type: 'quick' },
  { icon: '🔄', text: 'git log', sub: 'git log --oneline -10', type: 'quick' },
  { icon: '📦', text: 'list installed packages', sub: 'pip list', type: 'quick' },
  { icon: '💻', text: 'show processes', sub: 'ps aux', type: 'quick' },
  { icon: '💾', text: 'disk usage', sub: 'df -h', type: 'quick' },
  { icon: '🌐', text: 'network stats', sub: 'ifconfig', type: 'quick' },
];

export class CommandPalette {
  constructor(onSelect) {
    this.onSelect = onSelect;   // callback(text)
    this._overlay = $('command-palette');
    this._input   = $('palette-input');
    this._results = $('palette-results');
    this._items   = [];
    this._idx     = 0;
    this._fuse    = null;
    this._initEvents();
  }

  // ── Data ──────────────────────────────────────────────────────────────────
  setHistory(items) {
    const histItems = items.map(h => ({
      icon: h.success !== false ? '✓' : '✗',
      text: h.raw_input,
      sub: `${timeAgo(h.timestamp)} · exit ${h.exit_code}`,
      type: 'history',
      success: h.success,
    }));
    this._items = [...QUICK_COMMANDS, ...histItems];
    this._fuse = new Fuse(this._items, { keys: ['text', 'sub'], threshold: 0.4 });
  }

  setSessions(sessions) {
    const sessionItems = sessions.map(s => ({
      icon: '📼',
      text: `replay ${s.name}`,
      sub: `${s.command_count} commands`,
      type: 'session',
    }));
    // Merge with existing (keep quick + history)
    const nonSession = this._items.filter(i => i.type !== 'session');
    this._items = [...nonSession, ...sessionItems];
    this._fuse = new Fuse(this._items, { keys: ['text', 'sub'], threshold: 0.4 });
  }

  // ── Open / close ──────────────────────────────────────────────────────────
  open() {
    this._overlay.classList.remove('hidden');
    this._input.value = '';
    this._idx = 0;
    this._render(this._items.slice(0, 20));
    this._input.focus();
  }

  close() {
    this._overlay.classList.add('hidden');
  }

  toggle() {
    if (this._overlay.classList.contains('hidden')) this.open();
    else this.close();
  }

  // ── Events ────────────────────────────────────────────────────────────────
  _initEvents() {
    this._input.addEventListener('input', () => this._search());
    this._input.addEventListener('keydown', e => {
      if (e.key === 'Escape') { this.close(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); this._move(1); }
      if (e.key === 'ArrowUp')   { e.preventDefault(); this._move(-1); }
      if (e.key === 'Enter') { e.preventDefault(); this._select(); }
    });
    this._overlay.addEventListener('click', e => {
      if (e.target === this._overlay) this.close();
    });
  }

  _search() {
    const q = this._input.value.trim();
    const results = q ? this._fuse.search(q).map(r => r.item) : this._items.slice(0, 20);
    this._idx = 0;
    this._render(results);
  }

  _move(delta) {
    const items = this._results.querySelectorAll('.palette-result');
    if (!items.length) return;
    items[this._idx]?.classList.remove('selected');
    this._idx = Math.max(0, Math.min(this._idx + delta, items.length - 1));
    items[this._idx]?.classList.add('selected');
    items[this._idx]?.scrollIntoView({ block: 'nearest' });
  }

  _select() {
    const items = this._results.querySelectorAll('.palette-result');
    const selected = items[this._idx];
    if (selected) {
      const text = selected.dataset.text;
      this.close();
      this.onSelect(text);
    }
  }

  _render(items) {
    this._results.innerHTML = '';
    items.forEach((item, i) => {
      const row = el('div', `palette-result${i === this._idx ? ' selected' : ''}`);
      row.dataset.text = item.text;
      row.innerHTML = `
        <span class="pr-icon">${item.icon}</span>
        <div class="pr-text">
          <div class="pr-main">${item.text}</div>
          ${item.sub ? `<div class="pr-sub">${item.sub}</div>` : ''}
        </div>
        <span class="pr-badge">${item.type}</span>
      `;
      row.addEventListener('click', () => { this.close(); this.onSelect(item.text); });
      this._results.appendChild(row);
    });
  }
}

function timeAgo(isoStr) {
  if (!isoStr) return '';
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}
