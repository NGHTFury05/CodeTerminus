/** Goal checklist — multi-step plan with live step status updates. */
import { $ } from './utils.js';

export class GoalChecklist {
  constructor() {
    this._panel = $('goal-checklist');
    this._steps = [];
    this._goal  = '';
  }

  show(data) {
    this._goal  = data.goal || '';
    this._steps = (data.steps || []).map(s => ({ ...s }));
    this._render();
    this._panel.classList.add('visible');
  }

  updateStep(stepId, status, output) {
    const step = this._steps.find(s => s.id === stepId);
    if (step) {
      step.status = status;
      if (output) step.output = output;
      this._render();
    }
  }

  hide() {
    this._panel.classList.remove('visible');
    this._steps = [];
  }

  _render() {
    const total = this._steps.length;
    const done  = this._steps.filter(s => s.status === 'done').length;

    this._panel.innerHTML = `
      <div class="goal-title">
        📋 ${htmlEsc(this._goal)}
        <span style="float:right; font-weight:400; color:var(--text-muted)">${done}/${total}</span>
      </div>
      ${this._steps.map(s => `
        <div class="step-item ${s.status}">
          <div class="step-id">${stepIcon(s.status, s.id)}</div>
          <div style="flex:1">
            <div class="step-desc">${htmlEsc(s.description)}</div>
            <div class="step-cmd">$ ${htmlEsc(s.command)}</div>
            ${s.status === 'failed' && s.output ? `<div style="font-size:10px;color:var(--danger);margin-top:2px">${htmlEsc(s.output.slice(0,120))}</div>` : ''}
          </div>
          <span class="step-risk-badge risk-${s.risk_level}">${s.risk_level}</span>
        </div>
      `).join('')}
    `;
  }
}

function stepIcon(status, id) {
  if (status === 'done')    return '✓';
  if (status === 'failed')  return '✗';
  if (status === 'running') return '◌';
  if (status === 'skipped') return '—';
  return String(id);
}

function htmlEsc(s = '') {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
