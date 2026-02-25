/**
 * Main Entry Point
 * Initializes the application and coordinates modules.
 */

import { CONFIG, WEETH_ORACLE } from './config.js';
import { fetchPoolHistory, fetchCurrentOracleRate, fetchSeriesData, fetchPoolMetadata } from './data.js';
import { analyzeDataPure, analyzePairRotation } from './calculator.js';
import { renderCharts } from './charts.js';
import { 
    updateUIForPool, renderKPIs, renderTable, updateWalletBtn, 
    switchPoolVisually, switchStrategyVisually, switchDirectionVisually, renderRotationDashboard2
} from './ui.js';
import { setStatus, setCurrentTime } from './utils.js';
import { savePair, getSavedPairs } from './storage.js';

// State
const STATE = {
    currentPool: 'base',
    currentStrategy: 'A',
    currentDirection: 'discount',
    cachedDexData: null,
    walletAddress: null,
    useWalletRpc: false,
    latestOracleRate: null
};

// Global Exposure for HTML onclicks
window.switchPool = function(poolKey) {
    if (poolKey === STATE.currentPool) return;
    STATE.currentPool = poolKey;
    STATE.cachedDexData = null; // Clear cache
    
    switchPoolVisually(poolKey);
    init(true);
};

window.switchContext = function(context) {
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${context}`).classList.add('active');
    
    if (context === 'standard') {
        const lastPool = STATE.lastStandardPool || 'base';
        switchPool(lastPool);
    } else {
        if (STATE.currentPool !== 'custom') {
            STATE.lastStandardPool = STATE.currentPool;
        }
        switchPool('custom');
    }
};


window.switchStrategy = function(mode) {
    if (mode === STATE.currentStrategy) return;
    STATE.currentStrategy = mode;
    
    switchStrategyVisually(mode);
    if (STATE.cachedDexData) recalcAndRender();
};

window.switchDirection = function(dir) {
    if (dir === STATE.currentDirection) return;
    STATE.currentDirection = dir;
    
    switchDirectionVisually(dir);
    if (STATE.cachedDexData) recalcAndRender();
};

window.connectWallet = async function() {
    if (typeof window.ethereum === 'undefined') { alert('请安装 MetaMask'); return; }
    try {
        const acc = await window.ethereum.request({ method: 'eth_requestAccounts' });
        STATE.walletAddress = acc[0];
        
        // Switch Chain logic
        try {
            const cid = await window.ethereum.request({ method: 'eth_chainId' });
            if(cid !== '0x1') {
                await window.ethereum.request({method:'wallet_switchEthereumChain', params:[{chainId:'0x1'}]});
            }
            STATE.useWalletRpc = true;
        } catch { 
            STATE.useWalletRpc = false; 
        }

        if(!STATE.useWalletRpc) alert('需切换至主网读取 Oracle');
        
        updateWalletBtn(STATE.walletAddress);
        init(true);
    } catch(e) { console.error(e); }
};

// Start
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const p = urlParams.get('pool');
    
    if (p === 'eth') STATE.currentPool = 'eth_uni';
    else if (p && CONFIG.pools[p]) STATE.currentPool = p;
    
    // Initial UI Sync
    switchPoolVisually(STATE.currentPool);
    switchStrategyVisually(STATE.currentStrategy);
    switchDirectionVisually(STATE.currentDirection);

    init(false);
});

// Custom Backtest Handler
window.runCustomBacktest = async function() {
    const chainA = document.getElementById('custom-chain-a').value;
    const addrA  = document.getElementById('custom-addr-a').value;
    const chainB = document.getElementById('custom-chain-b').value;
    const addrB  = document.getElementById('custom-addr-b').value;
    
    if (!addrA || !addrB) { alert('Please enter both pool addresses'); return; }

    setStatus('Fetching custom data...', 'pulsing');
    
    // Date Range Logic
    const startVal = document.getElementById('custom-start-date').value;
    const endVal   = document.getElementById('custom-end-date').value;
    
    let startDate = startVal ? new Date(startVal) : null;
    let endDate   = endVal   ? new Date(endVal) : null;
    
    if (endDate) {
        // Set to end of day
        endDate.setHours(23, 59, 59, 999);
    }
    
    // If no date range provided, default to last 365 days? Or just let API decide (1000 days)?
    // Let's stick to API default (1000 days in data.js) if inputs empty.

    try {
        const [seriesA, seriesB, metaA, metaB] = await Promise.all([
            fetchSeriesData(chainA, addrA, startDate, endDate), 
            fetchSeriesData(chainB, addrB, startDate, endDate),
            fetchPoolMetadata(chainA, addrA),
            fetchPoolMetadata(chainB, addrB)
        ]);
        
        // Params
        const mode = window.CURRENT_CUSTOM_MODE || 'SMA';
        const params = {
            mode,
            windowSize: parseInt(document.getElementById('custom-window').value) || 30,
            stdDevMult: parseFloat(document.getElementById('custom-stddev').value) || 2.0,
            minRatio: parseFloat(document.getElementById('custom-min-ratio').value) || 0,
            maxRatio: parseFloat(document.getElementById('custom-max-ratio').value) || 1,
            useEMA: document.getElementById('use-ema').checked,
            stepSize: parseFloat(document.getElementById('custom-step-size').value) || 100,
            noLossSell: document.getElementById('no-loss-sell').checked
        };

        const result = analyzePairRotation(seriesA, seriesB, params); 
        
        // Update UI with Metadata
        const customMeta = {
            symbolA: metaA.symbol,
            symbolB: metaB.symbol,
            nameA: metaA.name,
            nameB: metaB.name,
            mode: params.mode,
            params: params
        };
        updateUIForPool(null, 'custom', 'custom', customMeta);

        renderCharts(result, false, customMeta, seriesA, seriesB); 
        renderRotationDashboard2(result, customMeta); 
        renderTable(result.events, 'Custom');

        setStatus('✅ Custom Analysis Done', 'done');

    } catch (e) {
        console.error(e);
        setStatus(`Error: ${e.message}`, 'error');
    }
};

window.setLast365 = function() {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 365);
    
    document.getElementById('custom-end-date').value = end.toISOString().split('T')[0];
    document.getElementById('custom-start-date').value = start.toISOString().split('T')[0];
};

window.setYTD = function() {
    const end = new Date();
    // Start of this year: Jan 1st
    const start = new Date(end.getFullYear(), 0, 1);
    
    document.getElementById('custom-end-date').value = end.toISOString().split('T')[0];
    document.getElementById('custom-start-date').value = start.toISOString().split('T')[0];
};



window.setCustomMode = function(mode) {
    window.CURRENT_CUSTOM_MODE = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`mode-${mode.toLowerCase()}`).classList.add('active');
    
    if (mode === 'SMA') {
        document.getElementById('params-sma').classList.remove('hidden');
        document.getElementById('params-fixed').classList.add('hidden');
    } else {
        document.getElementById('params-sma').classList.add('hidden');
        document.getElementById('params-fixed').classList.remove('hidden');
    }
};

window.autoFillFixedParams = async function() {
    const chainA = document.getElementById('custom-chain-a').value;
    const addrA  = document.getElementById('custom-addr-a').value;
    const chainB = document.getElementById('custom-chain-b').value;
    const addrB  = document.getElementById('custom-addr-b').value;
    
    if (!addrA || !addrB) return alert('请先输入资产地址');

    const btn = document.querySelector('.helper-btn');
    if(btn) btn.textContent = '⏳ 计算中...';

    // Read Date Range
    const startVal = document.getElementById('custom-start-date').value;
    const endVal   = document.getElementById('custom-end-date').value;
    
    let startDate = startVal ? new Date(startVal) : null;
    let endDate   = endVal   ? new Date(endVal) : null;
    if (endDate) endDate.setHours(23, 59, 59, 999);

    try {
        const [seriesA, seriesB] = await Promise.all([
            fetchSeriesData(chainA, addrA, startDate, endDate), 
            fetchSeriesData(chainB, addrB, startDate, endDate)
        ]);

        let validA = seriesA;
        
        // If NO custom date range, default to last 90 days
        if (!startDate && !endDate) {
            const cutoff = Date.now() - 90 * 24 * 3600 * 1000;
            validA = seriesA.filter(d => d.ts > cutoff);
        }
        
        // Build map for B
        const mapB = new Map(seriesB.map(d => [d.ts, d.price]));
        
        const ratios = [];
        validA.forEach(a => {
            const pb = mapB.get(a.ts);
            if (pb) ratios.push(a.price / pb);
        });

        if (ratios.length === 0) throw new Error('No overlapping data found');

        const min = Math.min(...ratios);
        const max = Math.max(...ratios);
        
        document.getElementById('custom-min-ratio').value = min.toFixed(6);
        document.getElementById('custom-max-ratio').value = max.toFixed(6);
        
        if(btn) btn.textContent = '✅ 已填入';
        setTimeout(() => { if(btn) btn.textContent = '✨ 建议值'; }, 2000);

    } catch (e) {
        alert('无法获取数据: ' + e.message);
        if(btn) btn.textContent = '❌ 失败';
    }
};

window.saveCurrentPair = function() {
    const chainA = document.getElementById('custom-chain-a').value;
    const addrA  = document.getElementById('custom-addr-a').value;
    const chainB = document.getElementById('custom-chain-b').value;
    const addrB  = document.getElementById('custom-addr-b').value;
    
    if (!addrA || !addrB) return alert('请输入完整地址');
    
    const id = `${chainA}:${addrA}-${chainB}:${addrB}`;
    const pair = {
        id, chainA, addrA, chainB, addrB, 
        mode: window.CURRENT_CUSTOM_MODE || 'SMA',
        params: {
            window: document.getElementById('custom-window').value,
            std: document.getElementById('custom-stddev').value,
            min: document.getElementById('custom-min-ratio').value,
            max: document.getElementById('custom-max-ratio').value,
            useEMA: document.getElementById('use-ema').checked,
            stepSize: document.getElementById('custom-step-size').value
        },
        timestamp: Date.now()
    };
    
    savePair(pair);
    refreshSavedList();
    alert('配置已保存');
};

window.loadSavedPair = function(jsonStr) {
    if(!jsonStr) return;
    const p = JSON.parse(jsonStr);
    
    document.getElementById('custom-chain-a').value = p.chainA;
    document.getElementById('custom-addr-a').value = p.addrA;
    document.getElementById('custom-chain-b').value = p.chainB;
    document.getElementById('custom-addr-b').value = p.addrB;
    
    setCustomMode(p.mode);
    if(p.params) {
        if(p.params.window) document.getElementById('custom-window').value = p.params.window;
        if(p.params.std) document.getElementById('custom-stddev').value = p.params.std;
        if(p.params.min) document.getElementById('custom-min-ratio').value = p.params.min;
        if(p.params.max) document.getElementById('custom-max-ratio').value = p.params.max;
        if(p.params.useEMA !== undefined) document.getElementById('use-ema').checked = p.params.useEMA;
        if(p.params.stepSize) document.getElementById('custom-step-size').value = p.params.stepSize;
    }
};

function refreshSavedList() {
    const list = getSavedPairs();
    const sel = document.getElementById('saved-pairs-select');
    if(!sel) return;
    sel.innerHTML = '<option value="">-- 加载已保存配置 --</option>';
    
    list.forEach(p => {
        const opt = document.createElement('option');
        opt.textContent = `${p.chainA}:${p.addrA.slice(0,6)}... / ${p.chainB}:${p.addrB.slice(0,6)}... (${p.mode})`;
        opt.value = JSON.stringify(p);
        sel.appendChild(opt);
    });
}
document.addEventListener('DOMContentLoaded', refreshSavedList);


let currentInitId = 0;

async function init(forceRefresh = false) {
    const myId = ++currentInitId;

    if (STATE.currentPool === 'custom') {
        setStatus('Ready for Custom Analysis', 'done');
        updateUIForPool(null, 'custom', STATE.currentStrategy);
        return;
    }

    const pool = CONFIG.pools[STATE.currentPool];
    setStatus(`正在获取 ${pool.name} (${pool.chain}) 数据...`, 'pulsing');
    setCurrentTime();
    
    // Update basic UI labels
    updateUIForPool(pool, STATE.currentPool, STATE.currentStrategy);

    try {
        // 1. Fetch DEX Data
        let dexData = STATE.cachedDexData;
        if (!dexData || forceRefresh) {
            dexData = await fetchPoolHistory(pool);
        }

        // Guard: Check if a newer request has started
        if (myId !== currentInitId) {
            console.log(`[Init] Request ${myId} aborted (stale)`);
            return;
        }

        STATE.cachedDexData = dexData;

        // 2. Fetch Oracle
        const oracleRate = await fetchCurrentOracleRate(STATE.useWalletRpc);
        
        // Guard Agains
        if (myId !== currentInitId) return;

        STATE.latestOracleRate = oracleRate;
        CONFIG.latestOracleRate = STATE.latestOracleRate; // Sync back to CONFIG if modules use it (legacy support)

        recalcAndRender();

    } catch (err) {
        if (myId !== currentInitId) return;
        setStatus(`❌ 数据获取失败: ${err.message}`, 'error');
        console.error(err);
    }
}

function recalcAndRender() {
    if (!STATE.cachedDexData) return;
    
    const pool = CONFIG.pools[STATE.currentPool];
    
    const result = analyzeDataPure(STATE.cachedDexData, {
        direction: STATE.currentDirection,
        strategy: STATE.currentStrategy,
        poolConfig: pool,
        latestOracleRate: STATE.latestOracleRate
    });

    // Update Status Bar
    const rateDisplay = STATE.latestOracleRate ? (1 / STATE.latestOracleRate).toFixed(4) : '—';
    let srcInfo = STATE.useWalletRpc && STATE.latestOracleRate
        ? `✅ 钱包已连接 | 实时链上汇率: 1 ETH = ${rateDisplay} weETH`
        : STATE.latestOracleRate
        ? `✅ 公共RPC | 实时链上汇率: 1 ETH = ${rateDisplay} weETH`
        : `⚠️ 无法连接链上数据 | 使用备用锚点`;

    if (STATE.currentPool === 'custom') {
        const modeName = STATE.currentStrategy === 'SMA' ? 'Dynamic SMA' : 'Fixed Range'; // Using simplified names for status
        srcInfo += ` | Custom: ${pool.name} | Strategy: ${window.CURRENT_CUSTOM_MODE || 'SMA'}`;
    } else {
        srcInfo += ` | ${pool.name} (${pool.chain}) | 策略 ${STATE.currentStrategy === 'A' ? 'A' : 'B'}`;
    }
    setStatus(srcInfo, 'done');

    renderKPIs(result, STATE.currentStrategy, STATE.currentPool);
    renderCharts(result, STATE.currentStrategy === 'B');
    renderTable(result.events, STATE.currentStrategy);
}
