/** Intent confirmation card — approve / edit / retry modal. */
import { $, riskColor } from './utils.js';
import { ws } from './ws.js';

export class IntentCard {
  constructor() {
    this._overlay = $('intent-card-overlay');
    this._card    = $('intent-card');
    this._onApprove = null;
    this._overlay.addEventListener('click', e => {
      if (e.target === this._overlay) this.dismiss('retry');
    });
  }

  show(data) {
    /**
     * data: { intent, commands[], rationale, risk, explanation }
     */
    const { intent, commands, rationale, risk, explanation } = data;
    const isGoal = intent === 'multi_step_goal';
    const riskColor_ = riskColor(risk);

    this._card.innerHTML = `
      <div class="card-header">
        <span class="card-intent-badge badge-${intent}">${isGoal ? '📋 Multi-step Goal' : '🤖 AI Suggestion'}</span>
        <span class="card-title">${htmlEsc(rationale)}</span>
        <span class="card-risk-badge risk-${risk}" style="color:${riskColor_}; background: ${riskColor_}18; border: 1px solid ${riskColor_}44">
          ${risk.toUpperCase()}
        </span>
      </div>

      ${isGoal
        ? `<div class="card-rationale">This will execute <b>${commands.length}</b> terminal commands in sequence.</div>`
        : `<div class="card-rationale">${htmlEsc(rationale)}</div>`
      }

      <div class="card-commands">
        ${commands.slice(0, 6).map((cmd, i) => `
          <div class="card-cmd">
            ${isGoal ? `<span class="card-cmd-arrow">${i + 1}.</span>` : ''}
            <code style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${htmlEsc(cmd)}</code>
          </div>
        `).join('')}
        ${commands.length > 6 ? `<div style="font-size:11px;color:var(--text-dim);padding:4px 8px">…and ${commands.length - 6} more steps</div>` : ''}
      </div>

      ${explanation ? `<div class="card-explanation">ℹ ${htmlEsc(explanation)}</div>` : ''}

      ${risk === 'low' && !isGoal ? '' : `
        <div style="margin-bottom: 14px;">
          <label style="font-size:11px;color:var(--text-dim)">Or edit the command:</label>
          <input id="card-edit-input" style="
            width:100%; margin-top:6px;
            background: var(--bg-panel); border: 1px solid var(--border);
            color: var(--text); padding: 7px 10px; border-radius: var(--radius);
            font-family: 'JetBrains Mono', monospace; font-size: 12px; outline: none;
          " value="${htmlEsc(commands[0] || '')}">
        </div>
      `}

      <div class="card-actions">
        <button class="card-action-btn btn-approve" id="card-approve">
          ✓ ${isGoal ? 'Execute Plan' : 'Run Command'}
        </button>
        <button class="card-action-btn btn-retry" id="card-retry">↩ Retry</button>
        <button class="card-action-btn btn-reject" id="card-reject">✕ Cancel</button>
      </div>
    `;

    $('card-approve').onclick = () => {
      const editEl = $('card-edit-input');
      const edited = editEl ? editEl.value.trim() : null;
      this.dismiss('approve', edited !== commands[0] ? edited : null);
    };
    $('card-retry').onclick  = () => this.dismiss('retry');
    $('card-reject').onclick = () => this.dismiss('cancel');

    const editEl = $('card-edit-input');
    if (editEl) {
      editEl.addEventListener('keydown', e => {
        if (e.key === 'Enter') $('card-approve').click();
        if (e.key === 'Escape') this.dismiss('cancel');
      });
    }

    this._overlay.classList.remove('hidden');
    $('card-approve').focus();
  }

  dismiss(action, payload = null) {
    this._overlay.classList.add('hidden');
    this._card.innerHTML = '';
    if (action === 'approve') {
      ws.sendConfirm('approve', payload);
    } else if (action === 'retry') {
      ws.sendConfirm('retry');
    }
    // 'cancel' sends nothing
  }
}

function htmlEsc(str = '') {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
