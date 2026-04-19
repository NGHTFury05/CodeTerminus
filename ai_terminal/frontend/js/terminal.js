/** xterm.js terminal — real ANSI emulator, keyboard input, Ctrl+C relay. */
import { ws } from './ws.js';

const PROMPT_BASE = '\r\n\x1b[1;32mcodeterminus\x1b[0m:\x1b[1;34m{cwd}\x1b[0m\x1b[1;37m$\x1b[0m ';

export class TerminalUI {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.term = null;
    this.fitAddon = null;
    this._inputBuf = '';
    this._historyBuf = [];     // local echo history
    this._histIdx = -1;
    this._cwd = '~';
    this._waitingForOutput = false;
    this._initTerm();
  }

  _initTerm() {
    this.term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'bar',
      fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace",
      fontSize: 13,
      lineHeight: 1.45,
      letterSpacing: 0,
      theme: {
        background:   '#050912',
        foreground:   '#c9d1d9',
        cursor:       '#00d4ff',
        cursorAccent: '#050912',
        black:        '#0d1224',  brightBlack:   '#3d526b',
        red:          '#ff4d6d',  brightRed:     '#ff6b82',
        green:        '#00ff88',  brightGreen:   '#46ffaa',
        yellow:       '#ffb347',  brightYellow:  '#ffd070',
        blue:         '#58a6ff',  brightBlue:    '#79c0ff',
        magenta:      '#7c5cbf',  brightMagenta: '#a78bfa',
        cyan:         '#00d4ff',  brightCyan:    '#39d8f2',
        white:        '#c9d1d9',  brightWhite:   '#f0f6fc',
      },
      scrollback: 5000,
      allowProposedApi: true,
    });

    this.fitAddon = new FitAddon.FitAddon();
    const linksAddon = new WebLinksAddon.WebLinksAddon();
    this.term.loadAddon(this.fitAddon);
    this.term.loadAddon(linksAddon);
    this.term.open(this.container);
    this.fitAddon.fit();

    // Resize observer
    const ro = new ResizeObserver(() => {
      try { this.fitAddon.fit(); } catch { /* ignore */ }
    });
    ro.observe(this.container);

    // Keyboard input handling
    this.term.onData(data => this._onData(data));
  }

  _onData(data) {
    const code = data.charCodeAt(0);

    if (data === '\r') {                          // Enter
      const input = this._inputBuf.trim();
      this._inputBuf = '';
      this.term.write('\r\n');
      if (input) {
        this._historyBuf.unshift(input);
        this._histIdx = -1;
        this._waitingForOutput = true;
        ws.sendInput(input);
      } else {
        this._writePrompt();
      }

    } else if (code === 127) {                   // Backspace
      if (this._inputBuf.length > 0) {
        this._inputBuf = this._inputBuf.slice(0, -1);
        this.term.write('\b \b');
      }

    } else if (code === 3) {                     // Ctrl+C
      this._inputBuf = '';
      this.term.write('^C\r\n');
      ws.sendCtrlC();
      this._writePrompt();

    } else if (data === '\x1b[A') {              // Arrow up — history
      if (this._histIdx < this._historyBuf.length - 1) {
        this._histIdx++;
        this._setInput(this._historyBuf[this._histIdx]);
      }

    } else if (data === '\x1b[B') {              // Arrow down — history
      if (this._histIdx > 0) {
        this._histIdx--;
        this._setInput(this._historyBuf[this._histIdx]);
      } else {
        this._histIdx = -1;
        this._setInput('');
      }

    } else if (data === '\x1b[D') {              // Arrow left (ignore for now)
    } else if (data === '\x1b[C') {              // Arrow right (ignore for now)
    } else if (data === '\x1b') {                // Bare ESC — ignore
    } else if (code >= 32 || code === 9) {       // Printable / Tab
      this._inputBuf += data;
      this.term.write(data);
    }
  }

  _setInput(text) {
    // Clear current input and write new text
    this.term.write('\r\x1b[K');
    this._writePromptInline();
    this._inputBuf = text;
    this.term.write(text);
  }

  _writePrompt() {
    const short = this._cwd.replace('/Users/' + (navigator.userAgent && ''), '~');
    this.term.write(PROMPT_BASE.replace('{cwd}', this._cwd));
  }

  _writePromptInline() {
    this.term.write(PROMPT_BASE.replace('{cwd}', this._cwd));
  }

  // ── Public API ────────────────────────────────────────────────────────────

  writeOutput(text, stream) {
    // Convert LF to CRLF if needed (server sends \r\n but just in case)
    const out = text.replace(/(?<!\r)\n/g, '\r\n');
    if (stream === 'stderr') {
      this.term.write(`\x1b[31m${out}\x1b[0m`);
    } else {
      this.term.write(out);
    }
  }

  showPrompt() {
    this._waitingForOutput = false;
    this._writePrompt();
  }

  setCwd(cwd) {
    this._cwd = cwd;
    // Update header cwd
    const el = document.getElementById('header-cwd');
    if (el) el.textContent = cwd;
    if (el) el.title = cwd;
  }

  clear() {
    this.term.clear();
    this._writePrompt();
  }

  pasteCommand(cmd) {
    this._setInput(cmd);
  }

  focus() {
    this.term.focus();
  }
}
