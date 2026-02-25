/**
 * Utils Module
 * Utility functions for formatting, DOM manipulation, and math helpers.
 */

// Math Helpers
export function mean(arr) { return arr.reduce((a, b) => a + b, 0) / arr.length; }

// Review/Rating Logic
export function getRating(r) { return r > 0.5 ? 'S' : r > 0.2 ? 'A' : r > 0.1 ? 'B' : 'C'; }

// DOM Helpers
export function sv(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
export function st(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }

export function setStatus(msg, state) {
  const d = document.querySelector('.status-dot');
  const t = document.getElementById('statusText');
  if (d) d.className = `status-dot ${state}`;
  if (t) t.textContent = msg;
}

export function setCurrentTime() {
  const el = document.getElementById('currentTime');
  if (el) el.textContent = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
}

export function fmtD(d) {
  return d?.toISOString?.()?.slice(0, 10) ?? '—';
}

// Canvas Helpers
export function gc(id) {
  return document.getElementById(id).getContext('2d');
}

export function mkGrad(ctx, a, b) {
  const g = ctx.createLinearGradient(0, 0, 0, 280);
  g.addColorStop(0, a);
  g.addColorStop(1, b);
  return g;
}
