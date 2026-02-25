/**
 * Data Module
 * Data fetching layer. Handles API calls to GeckoTerminal and RPC calls to Ethereum nodes.
 */

import { CONFIG, WEETH_ORACLE, MAINNET_RPCS } from './config.js';
// Wait, ui.js imports data.js to call fetch? Or main.js calls fetch?
// Better: main.js calls fetch. ui.js handles updateWalletBtn.
// data.js needs to know if wallet is connected?
// `useWalletRpc` state is needed.
// check fetchCurrentOracleRate in app.js. It uses `window.ethereum`.
// I'll export state setters/getters if needed or pass args.

// Generic Series Fetcher
export async function fetchSeriesData(networkId, poolAddress, startDate, endDate) {
  if (networkId === 'binance') {
    return fetchBinanceSeries(poolAddress, startDate, endDate);
  }

  // GeckoTerminal Logic: limit=1000 to cover enough history
  // ohlcv/day?limit=1000
  // Note: GeckoTerminal's 'limit' is the number of candles returned latest first.
  // We fetch last 1000 days (approx 3 years) which covers most needs.
  // Then we filter.
  const limit = 1000;
  let url = `/api/defi/pool-history/${networkId}/${poolAddress}?limit=${limit}`;
  if (startDate) url += `&start=${startDate.toISOString()}`;
  if (endDate) url += `&end=${endDate.toISOString()}`;

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), 10000);
  const r = await fetch(url, { headers: { Accept: 'application/json' }, signal: controller.signal });
  clearTimeout(id);

  if (!r.ok) {
    if (r.status === 429) throw new Error('GeckoTerminal API Limit (429)');
    throw new Error(`API Error ${r.status}`);
  }

  const j = await r.json();
  const ohlcv = j.data;
  if (!ohlcv || !Array.isArray(ohlcv)) throw new Error('Invalid Data');

  let data = ohlcv.map(d => ({
    ts: d.ts,
    date: new Date(d.ts),
    price: d.price
  }));

  // Filter by Date
  if (startDate) {
    data = data.filter(d => d.ts >= startDate.getTime());
  }
  if (endDate) {
    // End date usually means inclusive of that day?
    // Date input value is YYYY-MM-DD.
    // If end is 2025-04-08, we want data up to end of that day?
    // Or just <= that timestamp.
    // Let's assume endDate is set to 23:59:59 of that day.
    data = data.filter(d => d.ts <= endDate.getTime());
  }

  return data;
}

// Binance API Fetcher
export async function fetchBinanceSeries(symbol, startDate, endDate) {
  // Binance public API: /api/v3/klines
  // symbol: BTCUSDT, ETHUSDT etc.
  // interval=1d
  // startTime, endTime in ms
  let url = `https://api.binance.com/api/v3/klines?symbol=${symbol.toUpperCase()}&interval=1d&limit=1000`;

  if (startDate && typeof startDate.getTime === 'function') {
    const t = startDate.getTime();
    if (!isNaN(t)) url += `&startTime=${Math.floor(t)}`;
  }
  if (endDate && typeof endDate.getTime === 'function') {
    const t = endDate.getTime();
    if (!isNaN(t)) url += `&endTime=${Math.floor(t)}`;
  }

  const r = await fetch(url);
  if (!r.ok) throw new Error(`Binance API Error ${r.status}: ${r.statusText}`);

  const data = await r.json();
  if (!Array.isArray(data)) throw new Error('Invalid Binance Data');

  // [Open Time, Open, High, Low, Close, Volume, Close Time, ...]
  return data.map(d => ({
    ts: d[0],
    date: new Date(d[0]),
    price: parseFloat(d[4]) // Close price
  })).sort((a, b) => a.ts - b.ts);
}

export async function fetchPoolMetadata(networkId, poolAddress) {
  if (networkId === 'binance') {
    return {
      name: `Binance ${poolAddress.toUpperCase()}`,
      symbol: poolAddress.toUpperCase()
    };
  }
  const url = `/api/defi/pool-metadata/${networkId}/${poolAddress}`;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), 10000);
  const r = await fetch(url, { headers: { Accept: 'application/json' }, signal: controller.signal });
  clearTimeout(id);
  if (!r.ok) return { name: 'Unknown Pool', symbol: 'UNK' }; // Fallback

  const j = await r.json();
  return {
    name: j.name || 'Unknown',
    symbol: j.symbol || 'TOKEN'
  };
}

// GeckoTerminal API (Legacy Wrapper)
export async function fetchPoolHistory(pool) {
  const [data, meta] = await Promise.all([
    fetchSeriesData(pool.networkId, pool.address),
    fetchPoolMetadata(pool.networkId, pool.address)
  ]);

  const name = meta.name.toUpperCase();
  // Logic: we want dexRatio = ETH value per 1 weETH (should be > 1.0)
  // GeckoTerminal Price = Quote per Base.
  // If Pool is "weETH / WETH", Base=weETH, Price = WETH per weETH (> 1). OK.
  // If Pool is "WETH / weETH", Base=WETH, Price = weETH per WETH (< 1). Invert.

  const isEthBase = name.startsWith('WETH /') || name.startsWith('ETH /') || name.startsWith('WETH/') || name.startsWith('ETH/');
  const isWeEthBase = name.startsWith('WEETH /') || name.startsWith('WEETH/');

  return data.map(d => {
    let px = d.price;

    if (isEthBase) {
      px = 1 / px;
    } else if (isWeEthBase) {
      // Do nothing, already correct
    } else {
      // Fallback Heuristic
      if (px < 0.5) px = 1 / px;
    }

    return { ts: d.ts, date: d.date, dexRatio: px };
  });
}

// Oracle Rate (MetaMask优先)
export async function fetchCurrentOracleRate(useWalletRpc) {
  let rate = null;

  if (useWalletRpc && window.ethereum) {
    try {
      rate = await callConvertToAssets(window.ethereum, 'latest', true);
    } catch (e) {
      console.warn('Wallet RPC fetch failed:', e);
    }
  }

  if (!rate) {
    const rpc = await findWorkingRpc();
    if (rpc) {
      try { rate = await callConvertToAssets(new URL(rpc).href, 'latest', false); } catch (e) { }
    }
  }

  // Fallback
  return rate || (1 / CONFIG.fallbackEthPerWeEth);
}

export async function callConvertToAssets(provider, blockTag, isWallet) {
  const txObj = { to: WEETH_ORACLE.ADDRESS, data: WEETH_ORACLE.CALLDATA };
  if (isWallet) {
    const res = await provider.request({ method: 'eth_call', params: [txObj, blockTag] });
    return Number(BigInt(res)) / 1e18;
  } else {
    const r = await rpcCall(provider, 'eth_call', [txObj, blockTag]);
    if (!r.result || r.result === '0x') throw new Error('Bad RPC result');
    return Number(BigInt(r.result)) / 1e18;
  }
}

async function findWorkingRpc() {
  for (const r of MAINNET_RPCS) {
    try {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(r, {
        method: 'POST',
        body: JSON.stringify({ jsonrpc: '2.0', method: 'eth_blockNumber', params: [], id: 1 }),
        signal: controller.signal
      });
      clearTimeout(id);
      if (res.ok) return r;
    } catch { }
  }
  return null;
}

async function rpcCall(url, method, params) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), 5000);
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 }),
    signal: controller.signal
  });
  clearTimeout(id);
  return r.json();
}
