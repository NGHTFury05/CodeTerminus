/** WebSocket manager — connect, reconnect with backoff, typed message dispatch. */
import { setConnStatus } from './utils.js';

const SESSION_ID_KEY = 'ct_session_id';

function getSessionId() {
  let id = sessionStorage.getItem(SESSION_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_ID_KEY, id);
  }
  return id;
}

class WSManager {
  constructor() {
    this.sessionId = getSessionId();
    this.ws = null;
    this._handlers = {};     // type → [handler]
    this._backoff = 500;
    this._reconnectTimer = null;
    this._pingTimer = null;
    this._dead = false;      // set true to stop reconnecting
  }

  connect() {
    if (this._dead) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws/${this.sessionId}`;
    setConnStatus('connecting');

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      setConnStatus('connected');
      this._backoff = 500;
      this._startPing();
      this.emit('__connected__', {});
    };

    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        const handlers = this._handlers[msg.type] || [];
        handlers.forEach(h => h(msg));
      } catch { /* ignore malformed */ }
    };

    this.ws.onclose = () => {
      setConnStatus('disconnected');
      this._stopPing();
      this.emit('__disconnected__', {});
      if (!this._dead) this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose will follow
    };
  }

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => {
      setConnStatus('connecting');
      this.connect();
    }, this._backoff);
    this._backoff = Math.min(this._backoff * 2, 8000);
  }

  _startPing() {
    this._pingTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
      }
    }, 20000);
  }

  _stopPing() {
    clearInterval(this._pingTimer);
  }

  // ── Public API ────────────────────────────────────────────────────────────

  on(type, handler) {
    if (!this._handlers[type]) this._handlers[type] = [];
    this._handlers[type].push(handler);
    return () => { this._handlers[type] = this._handlers[type].filter(h => h !== handler); };
  }

  emit(type, data) {
    (this._handlers[type] || []).forEach(h => h(data));
  }

  send(msg) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  sendInput(text)  { this.send({ type: 'input', text }); }
  sendCtrlC()      { this.send({ type: 'ctrl_c' }); }
  sendConfirm(action, payload) { this.send({ type: 'confirm', action, payload }); }
  sendMeta(action, session)    { this.send({ type: 'meta', action, session }); }

  destroy() {
    this._dead = true;
    clearTimeout(this._reconnectTimer);
    this._stopPing();
    this.ws?.close();
  }
}

export const ws = new WSManager();
