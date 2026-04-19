/** app.js — Root module: bootstraps all components and wires WebSocket events. */
import { ws }              from './ws.js';
import { TerminalUI }      from './terminal.js';
import { updateMetrics }   from './metrics.js';
import { CommandPalette }  from './commandPalette.js';
import { IntentCard }      from './intentCard.js';
import { GoalChecklist }   from './goalChecklist.js';
import { ContextSidebar }  from './contextSidebar.js';
import { $ }               from './utils.js';

// ── Instantiate components ───────────────────────────────────────────────────
const terminal  = new TerminalUI('terminal-container');
const intentCard = new IntentCard();
const checklist  = new GoalChecklist();

const sidebar = new ContextSidebar(
  cmd  => terminal.pasteCommand(cmd),   // history click → paste
  name => ws.sendInput(`replay ${name}`) // session click → replay
);

window.sidebar = sidebar;  // allow inline onclick in HTML

const palette = new CommandPalette(text => {
  terminal.pasteCommand(text);
  terminal.focus();
});

// ── WebSocket event handlers ─────────────────────────────────────────────────
ws.on('output_chunk', msg => {
  terminal.writeOutput(msg.text, msg.stream);
  // Show prompt after the terminal system message that signals command end
  if (msg.stream === 'system' && msg.text === '') {
    terminal.showPrompt();
  }
});

ws.on('thought', msg => {
  sidebar.addThought(msg.text);
});

ws.on('intent_card', msg => {
  intentCard.show(msg);
});

ws.on('goal_plan', msg => {
  checklist.show(msg);
});

ws.on('step_update', msg => {
  checklist.updateStep(msg.step_id, msg.status, msg.output);
  // When all steps done hide checklist
  if (msg.status === 'done' || msg.status === 'failed') {
    setTimeout(() => {
      // Check if plan is complete/failed; checklist manages itself
    }, 300);
  }
});

ws.on('metrics', msg => {
  updateMetrics(msg);
});

ws.on('cwd_change', msg => {
  terminal.setCwd(msg.cwd);
  sidebar.setCwd(msg.cwd);
});

ws.on('history', msg => {
  sidebar.setHistory(msg.items || []);
  palette.setHistory(msg.items || []);
});

ws.on('sessions', msg => {
  sidebar.setSessions(msg.sessions || []);
  palette.setSessions(msg.sessions || []);
});

ws.on('recording_status', msg => {
  sidebar.setRecordingStatus(msg.recording, msg.name);
});

ws.on('__connected__', () => {
  sidebar.clearThoughts();
});

ws.on('__disconnected__', () => {
  terminal.writeOutput('\r\n\x1b[33m⚡ Connection lost, reconnecting…\x1b[0m\r\n', 'system');
});

// ── Global keyboard shortcuts ────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  // Ctrl+K — command palette
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    palette.toggle();
    return;
  }
  // / at root to open palette (when not in an input)
  if (e.key === '/' && document.activeElement === document.body) {
    e.preventDefault();
    palette.open();
  }
  // Escape — close palette or intent card
  if (e.key === 'Escape') {
    palette.close();
  }
});

// ── Button handlers ──────────────────────────────────────────────────────────
$('palette-trigger')?.addEventListener('click', () => palette.toggle());
$('clear-btn')?.addEventListener('click', () => terminal.clear());
$('interrupt-btn')?.addEventListener('click', () => {
  ws.sendCtrlC();
  terminal.writeOutput('^C\r\n', 'system');
});

// ── Start ────────────────────────────────────────────────────────────────────
ws.connect();
terminal.focus();

// Expose for debugging
window._ct = { ws, terminal, sidebar, palette, intentCard, checklist };
