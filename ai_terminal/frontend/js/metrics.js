/** Live metrics bar — updates CPU/RAM/GPU/Disk/Net/Proc every 2s from WebSocket. */
import { $, formatBytes, formatPct } from './utils.js';

function bar(id, pct) {
  const el = $(id);
  if (!el) return;
  const clamped = Math.min(Math.max(pct || 0, 0), 100);
  el.style.width = `${clamped}%`;
  // Color warning thresholds
  if (clamped > 90) el.style.background = 'var(--danger)';
  else if (clamped > 70) el.style.background = '';  // reset to CSS class default
}

export function updateMetrics(m) {
  // CPU
  const cpu = m.cpu ?? 0;
  const cpuEl = $('cpu-val');
  if (cpuEl) cpuEl.textContent = `${cpu}%`;
  bar('cpu-bar', cpu);

  // RAM
  const ram = m.ram ?? 0;
  const ramEl = $('ram-val');
  if (ramEl) ramEl.textContent = `${ram}%`;
  bar('ram-bar', ram);

  // GPU
  const gpuEl = $('gpu-val');
  const gpuBar = $('gpu-bar');
  if (m.gpu != null) {
    if (gpuEl) gpuEl.textContent = `${m.gpu}%`;
    bar('gpu-bar', m.gpu);
  } else {
    if (gpuEl) gpuEl.textContent = 'N/A';
    if (gpuBar) gpuBar.style.width = '0%';
  }

  // Disk %
  const diskEl = $('disk-val');
  if (diskEl) diskEl.textContent = `${m.disk_percent ?? 0}%`;
  bar('disk-bar', m.disk_percent);

  // Network
  const upEl = $('net-up');
  const downEl = $('net-down');
  if (upEl) upEl.textContent = formatBytes(m.net_sent_mb_s ?? 0);
  if (downEl) downEl.textContent = formatBytes(m.net_recv_mb_s ?? 0);

  // Process count
  const procEl = $('proc-val');
  if (procEl) procEl.textContent = m.process_count ?? '—';
}
