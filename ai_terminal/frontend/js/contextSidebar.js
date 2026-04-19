/** Context sidebar — AI thought log, directory tree, history, sessions. */
import { $, el, timeAgo } from './utils.js';
import { ws } from './ws.js';

export class ContextSidebar {
  constructor(onHistoryClick, onSessionClick) {
    this._onHistory = onHistoryClick;
    this._onSession = onSessionClick;
    this._collapsed = new Set();
    this._cwd = '~';
    this._histItems = [];
    this._sessions  = [];
    this._recording = false;
    this._recName   = '';
    this._initRecordBtn();
  }

  // ── Thought log ───────────────────────────────────────────────────────────
  addThought(text) {
    const log = $('thought-log');
    if (!log) return;
    const entry = el('div', 'thought-entry new');
    entry.textContent = `› ${text}`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
    // After a short delay, de-emphasize
    setTimeout(() => entry.classList.remove('new'), 1500);
    // Keep only last 30
    while (log.children.length > 30) log.firstChild.remove();
  }

  clearThoughts() {
    const log = $('thought-log');
    if (log) log.innerHTML = '';
  }

  // ── History ───────────────────────────────────────────────────────────────
  setHistory(items) {
    this._histItems = items || [];
    const list = $('history-list');
    if (!list) return;
    list.innerHTML = '';
    items.forEach(item => {
      const d = el('div', `history-item${item.success === false ? ' failed' : ''}`);
      d.title = item.raw_input;
      d.innerHTML = `
        <span class="item-icon">${item.success === false ? '✗' : '✓'}</span>
        <span class="item-text">${htmlEsc(item.raw_input)}</span>
        <span class="item-badge">${timeAgo(item.timestamp)}</span>
      `;
      d.addEventListener('click', () => this._onHistory(item.raw_input));
      list.appendChild(d);
    });
  }

  // ── Sessions ──────────────────────────────────────────────────────────────
  setSessions(sessions) {
    this._sessions = sessions || [];
    const list = $('sessions-list');
    if (!list) return;
    list.innerHTML = '';
    sessions.forEach(s => {
      const d = el('div', 'session-item');
      d.innerHTML = `
        <span class="item-icon">📼</span>
        <span class="item-text">${htmlEsc(s.name)}</span>
        <span class="item-badge">${s.command_count} cmds</span>
      `;
      d.addEventListener('click', () => this._onSession(s.name));
      list.appendChild(d);
    });
  }

  // ── Directory tree (built from cwd) ──────────────────────────────────────
  setCwd(cwd) {
    this._cwd = cwd;
    const tree = $('dir-tree');
    if (!tree) return;
    // Fetch directory listing from server
    fetch(`/api/history/x?limit=0`)  // dummy call to wake API
      .catch(() => {});
    // Build simple inline listing by parsing cwd
    const parts = cwd.split('/').filter(Boolean);
    tree.innerHTML = '';
    parts.forEach((part, i) => {
      const d = el('div', 'dir-entry is-dir');
      d.style.paddingLeft = `${i * 10 + 6}px`;
      d.innerHTML = `<span>📂</span> ${htmlEsc(part)}`;
      tree.appendChild(d);
    });
  }

  // ── Recording ─────────────────────────────────────────────────────────────
  setRecordingStatus(recording, name = '') {
    this._recording = recording;
    this._recName   = name;
    const btn = $('sidebar-record-btn');
    const headerBtn = $('record-btn');
    if (btn) {
      btn.classList.toggle('active', recording);
      btn.title = recording ? 'Stop recording' : 'Start recording';
    }
    if (headerBtn) {
      headerBtn.classList.toggle('recording', recording);
      headerBtn.textContent = '';
      const dot = el('span', 'rec-dot');
      headerBtn.appendChild(dot);
      headerBtn.append(` ${recording ? 'Stop' : 'Record'}`);
    }
  }

  // ── Section collapse ──────────────────────────────────────────────────────
  toggleSection(contentId) {
    const content = $(contentId);
    if (!content) return;
    const isCollapsed = this._collapsed.has(contentId);
    if (isCollapsed) {
      content.style.display = '';
      this._collapsed.delete(contentId);
    } else {
      content.style.display = 'none';
      this._collapsed.add(contentId);
    }
  }

  // ── Recording button ──────────────────────────────────────────────────────
  _initRecordBtn() {
    const btn = $('sidebar-record-btn');
    const headerBtn = $('record-btn');

    const toggle = () => {
      const name = $('session-name-input')?.value.trim();
      if (!this._recording) {
        if (!name) { alert('Enter a session name first.'); return; }
        ws.sendMeta('record_start', name);
      } else {
        ws.sendMeta('record_stop', this._recName);
      }
    };

    btn?.addEventListener('click', toggle);
    headerBtn?.addEventListener('click', toggle);
  }
}

function htmlEsc(s = '') {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
