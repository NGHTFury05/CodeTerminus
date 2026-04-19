/** Shared utility helpers */

export function $(id) { return document.getElementById(id); }
export function qs(sel, root = document) { return root.querySelector(sel); }
export function qsa(sel, root = document) { return [...root.querySelectorAll(sel)]; }

export function el(tag, cls = '', content = '') {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (content) e.textContent = content;
  return e;
}

export function debounce(fn, ms = 200) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export function throttle(fn, ms = 100) {
  let last = 0;
  return (...args) => {
    const now = Date.now();
    if (now - last >= ms) { last = now; fn(...args); }
  };
}

export function formatBytes(mb) {
  if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB/s`;
  if (mb >= 1) return `${mb.toFixed(1)} MB/s`;
  return `${(mb * 1000).toFixed(0)} KB/s`;
}

export function formatPct(n) {
  return n != null ? `${n.toFixed(1)}%` : '—';
}

export function timeAgo(isoStr) {
  if (!isoStr) return '';
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function riskColor(risk) {
  return { low: 'var(--accent)', medium: 'var(--warn)', high: 'var(--danger)' }[risk] || 'var(--text-muted)';
}

export function setConnStatus(state) {
  // state: 'connected' | 'connecting' | 'disconnected'
  const el = document.getElementById('connection-status');
  const txt = document.getElementById('conn-text');
  if (!el) return;
  el.className = `conn-status ${state}`;
  txt.textContent = { connected: 'Connected', connecting: 'Connecting…', disconnected: 'Disconnected' }[state];
}
