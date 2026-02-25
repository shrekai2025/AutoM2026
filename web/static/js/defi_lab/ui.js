/**
 * UI Module
 * UI interation layer. Handles DOM updates.
 */

import { CONFIG } from './config.js';
import { sv, st, setStatus, fmtD } from './utils.js';

export function updateUIForPool(poolCfg, currentPoolKey, currentStrategy, customMeta) {
  // Toggle Strategy Sections
  const defaultSec = document.getElementById('defaultStrategySection');
  const customSec = document.getElementById('customStrategySection');
  const compareSec = document.querySelector('.compare-section');
  const weethStrategyRow = document.querySelector('.cp-row');

  if (currentPoolKey === 'custom') {
    if (defaultSec) defaultSec.classList.add('hidden');
    if (customSec) customSec.classList.remove('hidden');
    if (compareSec) compareSec.classList.add('hidden');

    const oracleInfo = document.getElementById('weethOracleInfo');
    const walletHint = document.getElementById('heroWalletHint');
    const oracleChip = document.querySelectorAll('.pair-chip')[2];

    if (oracleInfo) oracleInfo.classList.add('hidden');
    if (walletHint) walletHint.classList.add('hidden');
    if (oracleChip) oracleChip.classList.add('hidden');

    const chip = document.querySelector('.pair-val');
    if (chip) chip.textContent = customMeta ? `${customMeta.symbolA} / ${customMeta.symbolB}` : `Custom / Pair`;

    const chips = document.querySelectorAll('.pair-val');
    if (chips[1]) chips[1].textContent = `Cross-Chain Rotation`;

    const feeEl = document.getElementById('lpFeeDisplay');
    if (feeEl) feeEl.textContent = '—';

    const stakeSub = document.getElementById('kpi-staking-sub');
    if (stakeSub) stakeSub.textContent = 'Rotation Strategy';

    // Update Custom Strategy Text
    if (customMeta) {
      const title = document.getElementById('customStratTitle');
      const desc = document.getElementById('customStratDesc');

      if (title) title.textContent = `${customMeta.symbolA} ⇄ ${customMeta.symbolB} 轮动策略`;

      const formulaEl = document.getElementById('customStratFormula');

      if (customMeta.mode === 'FIXED') {
        if (desc) desc.innerHTML = `在 <strong>${customMeta.symbolA}</strong> 和 <strong>${customMeta.symbolB}</strong> 之间进行固定区间轮动。<br>
              当比率低于 <strong>${customMeta.params.minRatio}</strong> 时买入 ${customMeta.symbolA}，高于 <strong>${customMeta.params.maxRatio}</strong> 时卖出。`;

        if (formulaEl) formulaEl.textContent = `Type: Fixed Range | Buy < ${customMeta.params.minRatio} | Sell > ${customMeta.params.maxRatio}`;
      } else {
        if (desc) desc.innerHTML = `在 <strong>${customMeta.symbolA}</strong> 和 <strong>${customMeta.symbolB}</strong> 之间进行价值发现轮动。<br>
              当比率 (${customMeta.symbolA}/${customMeta.symbolB}) 低于均值时买入 ${customMeta.symbolA}，高于均值时卖出 ${customMeta.symbolA}。`;

        const meanType = customMeta.params?.useEMA ? 'EMA' : 'SMA';
        if (formulaEl) formulaEl.textContent = `Type: Dynamic ${meanType} | Buy < ${meanType} - ${customMeta.params?.stdDevMult || 2}σ | Sell > ${meanType} + ${customMeta.params?.stdDevMult || 2}σ`;
      }

      // Update Chart Headers & Legends
      st('ratioChartTitle', `${customMeta.symbolA} / ${customMeta.symbolB} 历史比率`);
      setLegend('legendDexPrice', 'blue', '比率 (Ratio)');
      setLegend('legendOracleFV', 'yellow', '均值 (Mean)');
      setLegend('legendBuyThreshold', 'red', '买入线 (Buy Zone)');
      setLegend('legendSellThreshold', 'purple', '卖出线 (Sell Zone)');

      const lSell = document.getElementById('legendSellThreshold');
      if (lSell) lSell.classList.remove('hidden');

      st('discountChartTitle', '偏离度分布');
      setLegend('legendDiscount', 'green', '偏离幅度 %');

      st('arbChartTitle', '单次轮动收益');
      setLegend('legendArbAPR', 'orange', '收益率 %');

      st('cumulChartTitle', `累计轮动收益 (${customMeta.symbolA} 本位)`);
      setLegend('legendCumulReturn', 'teal', `累计收益 (${customMeta.symbolA})`);

      // Table Headers for Custom
      const thDiff = document.querySelectorAll('th')[3]; // Discount bps
      const thAmt = document.querySelectorAll('th')[4]; // Amount
      const thDur = document.getElementById('th-duration');
      const thArb = document.getElementById('th-arb');

      if (thDiff) thDiff.textContent = 'Deviation (bps)';
      if (thAmt) thAmt.textContent = 'Amount';
      if (thDur) thDur.textContent = 'Action';
      if (thArb) thArb.textContent = 'Gain %';

      // Show Pos Chart & Price Charts
      const posChartCanvas = document.getElementById('posChart');
      if (posChartCanvas) {
        const card = posChartCanvas.closest('.chart-card');
        if (card) card.classList.remove('hidden');
      }
      const priceRow = document.getElementById('priceChartsRow');
      if (priceRow) priceRow.style.display = 'flex';

      // Update Price Chart Titles with Symbols
      st('priceChartATitle', `${customMeta.symbolA} Price (USD)`);
      st('priceChartBTitle', `${customMeta.symbolB} Price (USD)`);

      // Show Position Table Header (Custom Only)
      const thPos = document.getElementById('th-pos');
      if (thPos) thPos.classList.remove('hidden');
    }
    return;
  }

  // Default Restore
  if (defaultSec) defaultSec.classList.remove('hidden');
  if (customSec) customSec.classList.add('hidden');
  if (compareSec) compareSec.classList.remove('hidden');

  // Hide Custom Charts
  const posChartCanvas = document.getElementById('posChart');
  if (posChartCanvas) {
    const card = posChartCanvas.closest('.chart-card');
    if (card) card.classList.add('hidden');
  }
  const priceRow = document.getElementById('priceChartsRow');
  if (priceRow) priceRow.style.display = 'none';

  // Hide Position Table Header (Default)
  const thPos = document.getElementById('th-pos');
  if (thPos) thPos.classList.add('hidden');

  st('ratioChartTitle', 'weETH / ETH 历史价格比率');
  setLegend('legendDexPrice', 'blue', 'DEX 价格');
  setLegend('legendOracleFV', 'yellow', 'Oracle Fair Value');
  setLegend('legendBuyThreshold', 'red', '买入阈值 (-20bps)');

  const lSell = document.getElementById('legendSellThreshold');
  if (lSell) lSell.classList.add('hidden');

  st('discountChartTitle', '套利折价分布');
  setLegend('legendDiscount', 'green', '折价幅度 (bps)');

  st('arbChartTitle', '各次套利事件年化收益');
  setLegend('legendArbAPR', 'orange', '单次年化 APR%');

  st('cumulChartTitle', '累计套利收益曲线（假设每次 1 ETH 本金）');
  setLegend('legendCumulReturn', 'teal', '累计收益 (ETH)');

  const thDiff = document.querySelectorAll('th')[3];
  const thAmt = document.querySelectorAll('th')[4];
  const thDur = document.getElementById('th-duration');
  const thArb = document.getElementById('th-arb');
  if (thDiff) thDiff.textContent = '折价 (bps)';
  if (thAmt) thAmt.textContent = 'Amount (Unit)';
  if (thDur) thDur.textContent = '持有天数';
  if (thArb) thArb.textContent = '套利收益';

  const oracleInfo = document.getElementById('weethOracleInfo');
  const walletHint = document.getElementById('heroWalletHint');
  const oracleChip = document.querySelectorAll('.pair-chip')[2];

  if (oracleInfo) oracleInfo.classList.remove('hidden');
  if (walletHint) walletHint.classList.remove('hidden');
  if (oracleChip) oracleChip.classList.remove('hidden');

  const stakeSub = document.getElementById('kpi-staking-sub');
  if (stakeSub) {
    stakeSub.textContent = currentStrategy === 'A'
      ? 'ether.fi staking (策略A不适用)'
      : `${poolCfg.name} 预估 LP 收益`;
  }
}

// Custom Dashboard Renderer (Legacy Wrapper)
export function renderRotationDashboard(res, meta) {
  renderRotationDashboard2(res, meta);
}

// Actual New Renderer
export function renderRotationDashboard2(res, meta) {
  // Hide Standard Dashboard elements
  document.querySelector('.kpi-grid').classList.add('hidden');
  document.querySelector('.compare-section')?.classList.add('hidden');
  document.querySelector('.risk-section')?.classList.add('hidden');

  // Custom Dashboard Logic ...
  let customDash = document.getElementById('custom-rotation-dash');
  if (!customDash) {
    customDash = document.createElement('div');
    customDash.id = 'custom-rotation-dash';
    customDash.className = 'kpi-grid'; // Reuse grid style
    // document.querySelector('.hero').after(customDash); // Already in HTML? No.
    // Let's insert it if not exists
    const hero = document.querySelector('.hero');
    if (hero) hero.after(customDash);
  }
  customDash.classList.remove('hidden');

  const totalRet = (res.finalReturn * 100).toFixed(2);
  const curHold = res.currentHolding === 'A' ? meta.symbolA : meta.symbolB;
  const lastAct = res.events.at(-1);
  const lastDate = lastAct ? fmtD(lastAct.date) : 'None';

  customDash.innerHTML = `
    <div class="kpi-card">
        <div class="kpi-title">当前持仓</div>
        <div class="kpi-value highlight">${curHold}</div>
        <div class="kpi-sub">Last Rotation: ${lastDate}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-title">累计收益 (vs Hold A)</div>
        <div class="kpi-value ${res.finalReturn >= 0 ? 'green' : 'red'}">${totalRet}%</div>
        <div class="kpi-sub">Annualized: ${(res.avgTotal * 100).toFixed(2)}%</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-title">当前比率 (${meta.symbolA}/${meta.symbolB})</div>
        <div class="kpi-value">${res.currentRatio?.toFixed(6) || '—'}</div>
        <div class="kpi-sub">Target: ${res.events.length} Trades</div>
    </div>
    </div>
  `;
}

export function renderKPIs(res, currentStrategy, currentPoolKey) {
  // Ensure Standard Dashboard is visible and Custom is hidden
  document.querySelector('.kpi-grid').classList.remove('hidden');
  const customDash = document.getElementById('custom-rotation-dash');
  if (customDash) customDash.classList.add('hidden');

  const { avgArb, bestArb, avgTotal, closed, currentRatio, currentFV, currentDiscount } = res;
  const isB = currentStrategy === 'B';
  const pool = CONFIG.pools[currentPoolKey] || { name: 'Custom Pair', lpFeeAPY: 0 };

  sv('kpi-ratio-val', currentRatio ? currentRatio.toFixed(5) : '—');
  const dBps = currentDiscount ? (currentDiscount * 10000).toFixed(1) : '—';
  const sign = currentDiscount > 0 ? '⚠️ 折价' : '✅ 溢价';
  st('kpi-ratio-sub', `Oracle = ${currentFV?.toFixed(5) || '—'} | ${sign} ${Math.abs(dBps)} bps`);

  st('kpi-arb-label', `📊 历史平均年化 (10 ETH 分批建仓)`);
  sv('kpi-arb-val', (avgTotal * 100).toFixed(1) + '%');
  st('kpi-arb-sub', `${closed.length} 次事件 | ${pool.name} | 策略${currentStrategy}`);

  sv('kpi-events-val', closed.length);

  const bestTotal = closed.length > 0 ? Math.max(...closed.map(e => e.totalAPR)) : 0;
  sv('kpi-best-val', (bestTotal * 100).toFixed(1) + '%');

  if (isB) {
    st('kpi-staking-label', '💧 LP 手续费 APY');
    sv('kpi-staking-val', `~${(pool.lpFeeAPY * 100).toFixed(1)}%`);
  } else {
    st('kpi-staking-label', '📉 策略A 不享质押收益');
    sv('kpi-staking-val', '0%');
    st('kpi-staking-sub', '资金锁定/跨链中');
  }

  sv('kpi-total-val', (avgTotal * 100).toFixed(1) + '%');
  st('kpi-total-sub', isB ? `套利 + LP手续费` : `纯套利收益 (无Staking)`);
}

export function renderTable(events, currentStrategy) {
  const tbody = document.getElementById('eventsBody');
  const isB = currentStrategy === 'B';
  const validEvents = events || [];
  const closed = validEvents.filter(e => !e.ongoing).sort((a, b) => b.date - a.date);

  if (closed.length === 0) { tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:20px">无匹配事件或数据加载失败，请检查网络连接</td></tr>'; return; }


  const thDuration = document.getElementById('th-duration');
  if (thDuration) thDuration.textContent = isB ? '实际天数' : (currentStrategy === 'Custom' ? 'Type' : `固定${CONFIG.fixedExitDays}天`);

  // Custom headers check (Already handled in updateUI? No, do it here or make it safer)
  // Let's rely on updateUIForPool for headers, but here we format row data.

  tbody.innerHTML = closed.map(e => {
    let total, arb, duration;

    if (currentStrategy === 'Custom') {
      total = (e.totalAPR * 100).toFixed(2); // Using totalAPR/arbAPR field for simple gain

      const sub = (e.rating.includes('Buy') && e.totalAPR < 0 && e.lastSellRatio)
        ? `<div style="font-size:0.75em;color:var(--red)">vs Sell ${e.lastSellRatio.toFixed(5)}</div>`
        : '';

      return `<tr>
          <td>${fmtD(e.date)}</td>
          <td>${e.dexRatio?.toFixed(5)}${sub}</td>
          <td>${e.fairValue?.toFixed(5)}</td>
          <td class="${Math.abs(e.discountBps) > 200 ? 'val-green' : ''}">${e.discountBps}</td>
          <td>${e.amount?.toFixed(4) || '-'}</td>
          <td style="font-size:0.85em">${e.unitsA?.toFixed(2)} A / ${e.unitsB?.toFixed(2)} B</td>
          <td><span class="badge badge-${e.rating?.includes('Buy') ? 'a' : 'b'}">${e.type || 'Action'}</span></td>
          <td class="${e.totalAPR > 0 ? 'val-green' : 'val-red'}">${e.totalAPR !== 0 ? total + '%' : '-'}</td>
          ${isB ? `<td>-</td>` : ''}
          <td class="val-green" style="font-weight:700">${e.totalAPR !== 0 ? total + '%' : '-'}</td>
          <td><span class="badge badge-${e.rating?.includes('Buy') ? 'a' : 'b'}">${e.rating}</span></td>
        </tr>`;
    }

    total = (e.totalAPR * 100).toFixed(1);
    arb = (e.arbAPR * 100).toFixed(1);

    return `<tr>
      <td>${fmtD(e.date)}</td>
      <td>${e.dexRatio?.toFixed(5)}</td>
      <td>${e.fairValue?.toFixed(5)}</td>
      <td class="${e.discountBps > 50 ? 'val-green' : ''}">${e.discountBps}</td>
      <td>${e.amount || 10} ETH</td>
      <td>${e.durationDays}</td>
      <td class="val-blue">${arb}%</td>
      ${isB ? `<td>${(e.feeReturn * 100).toFixed(2)}%</td>` : ''}
      <td class="val-green" style="font-weight:700">${total}%</td>
      <td><span class="badge badge-${e.rating?.toLowerCase() || 'c'}">${e.rating || 'C'}</span></td>
    </tr>`;
  }).join('');
}

export function updateWalletBtn(address) {
  const btn = document.getElementById('walletBtn');
  const txt = document.getElementById('walletBtnText');
  const hint = document.getElementById('heroWalletHint');

  if (!btn || !txt) return; // Prevent errors if elements don't exist

  if (address) {
    btn.classList.add('connected');
    txt.textContent = address.slice(0, 6) + '...' + address.slice(-4);
    if (hint) hint.style.display = 'none';
  } else {
    btn.classList.remove('connected');
    txt.textContent = '连接钱包';
  }
}

// Visual State Toggles
export function switchPoolVisually(poolKey) {
  Object.keys(CONFIG.pools).forEach(key => {
    const btn = document.getElementById(`pool-${key}`);
    if (btn) btn.classList.toggle('active', key === poolKey);
  });

  const customPanel = document.getElementById('customConfigPanel');
  const standardPanel = document.getElementById('standardConfigPanel');

  if (poolKey === 'custom') {
    if (customPanel) customPanel.classList.remove('hidden');
    if (standardPanel) standardPanel.classList.add('hidden');
  } else {
    if (customPanel) customPanel.classList.add('hidden');
    if (standardPanel) standardPanel.classList.remove('hidden');
  }
}

export function switchStrategyVisually(mode) {
  const btnA = document.getElementById('btnStratA');
  const btnB = document.getElementById('btnStratB');
  if (btnA) btnA.classList.toggle('active', mode === 'A');
  if (btnB) btnB.classList.toggle('active', mode === 'B');

  const infoA = document.getElementById('stratInfoA');
  const infoB = document.getElementById('stratInfoB');
  if (infoA) infoA.classList.toggle('hidden', mode !== 'A');
  if (infoB) infoB.classList.toggle('hidden', mode !== 'B');

  document.querySelectorAll('.strat-b-only').forEach(el => el.classList.toggle('hidden', mode !== 'B'));
  const thFee = document.getElementById('th-fee');
  if (thFee) thFee.classList.toggle('hidden', mode !== 'B');

  const highlightCard = document.getElementById('kpi-arb');
  if (highlightCard) highlightCard.style.borderColor = mode === 'A' ? 'rgba(52,211,153,0.25)' : 'rgba(167,139,250,0.3)';

  const kpiVal = document.getElementById('kpi-arb-val');
  if (kpiVal) kpiVal.className = 'kpi-value ' + (mode === 'A' ? 'green' : 'purple');
}

export function switchDirectionVisually(dir) {
  const btnD = document.getElementById('dir-discount');
  const btnP = document.getElementById('dir-premium');
  if (btnD) btnD.classList.toggle('active', dir === 'discount');
  if (btnP) btnP.classList.toggle('active', dir === 'premium');

  const stratEl = document.querySelector('.strategy-toggle-wrap');
  if (stratEl) {
    stratEl.style.opacity = dir === 'premium' ? '0.3' : '1';
    stratEl.style.pointerEvents = dir === 'premium' ? 'none' : 'auto';
  }
}

function setLegend(id, color, text) {
  const el = document.getElementById(id);
  // Reconstruct innerHTML to keep the dot
  if (el) {
    el.innerHTML = `<span class="legend-dot ${color}"></span>${text}`;
  }
}
