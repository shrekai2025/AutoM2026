"""
ETF 链上监控采集器 (全免费方案)

数据源:
1. yfinance + Yahoo Finance v8 API  - ETF AUM，免费无需 Key
2. mempool.space API                - BTC 地址余额（已验证可用）
3. blockscout.com API               - ETH 地址余额（免费，无需 Key）

不依赖 Alchemy / Arkham / Nansen / Etherscan 付费 API。

使用方法:
    from data_collectors.etf_onchain_collector import etf_onchain_collector
    data = await etf_onchain_collector.get_all()

托管地址维护:
    在 ETF_BTC_ADDRESSES / ETF_ETH_ADDRESSES 中手动维护，
    地址来源: Arkham Intelligence 网站免费搜索（无需 API Key）
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  已知 ETF 托管地址（公开可查，来源: Arkham / SEC 文件）
#  地址格式: {"etf": "IBIT", "label": "贝莱德 BTC ETF"}
#
#  ⚠️  维护说明: 定期到 https://platform.arkhamintelligence.com
#     免费搜索 "BlackRock Bitcoin ETF" / "Fidelity Bitcoin ETF" 更新地址
# ─────────────────────────────────────────────────────────

# BTC 托管地址（Coinbase Custody）
ETF_BTC_ADDRESSES: List[Dict] = [
    # 贝莱德 IBIT — Coinbase Custody
    # 地址来源: Arkham 公开标签 / SEC 13F 文件
    {
        "etf": "IBIT",
        "name": "贝莱德BTC ETF",
        "address": "bc1qd8ejkl3xelunpgjz2a9svkfevuzqsadmdyap4x",
        "custodian": "Coinbase Custody",
    },
    # 灰度 GBTC — Coinbase Custody
    {
        "etf": "GBTC",
        "name": "灰度BTC信托",
        "address": "bc1qazcm763858nkj2dj986etajv6wquslv8uxjyjeq",
        "custodian": "Coinbase Custody",
    },
    # 富达 FBTC — 自托管（多地址，以下为主要地址之一）
    {
        "etf": "FBTC",
        "name": "富达BTC ETF",
        "address": "3LYJfcfHBoBB2G7Zc3rHkEWFNZfDS45fYd",
        "custodian": "Fidelity Self-Custody",
    },
]

# ETH 托管地址
ETF_ETH_ADDRESSES: List[Dict] = [
    # 贝莱德 ETHA — Coinbase Custody（ETH）
    {
        "etf": "ETHA",
        "name": "贝莱德ETH ETF",
        "address": "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503",
        "custodian": "Coinbase Custody",
    },
    # 富达 FETH
    {
        "etf": "FETH",
        "name": "富达ETH ETF",
        "address": "0xb61f2bf39b7fa5d3f5c84c23c0c9b01f62bdce06",  # Fidelity 自托管主要地址
        "custodian": "Fidelity Self-Custody",
    },
]

# ETF ticker 列表（用于 yfinance 抓取 AUM）
ETF_TICKERS = {
    "IBIT": {"name": "贝莱德BTC ETF", "type": "BTC"},
    "FBTC": {"name": "富达BTC ETF",   "type": "BTC"},
    "GBTC": {"name": "灰度BTC信托",    "type": "BTC"},
    "ARKB": {"name": "方舟BTC ETF",   "type": "BTC"},
    "BITB": {"name": "Bitwise BTC",   "type": "BTC"},
    "ETHA": {"name": "贝莱德ETH ETF", "type": "ETH"},
    "FETH": {"name": "富达ETH ETF",   "type": "ETH"},
    "ETHW": {"name": "灰度ETH信托",    "type": "ETH"},
}


class ETFOnchainCollector:
    """ETF 链上监控采集器 (全免费方案)"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        # mempool.space: 免费BTC地址余额API（无需Key），速率限制宽松
        self.mempool_api = "https://mempool.space/api"
        # blockscout: 免费ETH地址余额API（无需Key）
        self.blockscout_api = "https://eth.blockscout.com/api/v2"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    # ──────────────────────────────────────────
    #  1. yfinance: ETF AUM (总资产) 查询
    # ──────────────────────────────────────────

    async def get_etf_aum(self, ticker: str) -> Optional[float]:
        """
        获取 ETF 总净资产 (AUM)
        
        优先用 yfinance (totalAssets)；
        后备: Yahoo Finance v8 chart API（更稳定)，估算 price*shares
        
        返回: AUM 金额（美元），None 表示失败
        """
        # 方法1: yfinance
        try:
            import yfinance as yf

            def _fetch():
                t = yf.Ticker(ticker)
                info = t.info
                aum = info.get("totalAssets") or info.get("totalNetAssets")
                if not aum:
                    price = info.get("previousClose") or info.get("regularMarketPreviousClose")
                    shares = info.get("sharesOutstanding")
                    if price and shares:
                        aum = price * shares
                return aum

            aum = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=8)
            if aum:
                return float(aum)
        except Exception as e:
            logger.debug(f"yfinance AUM failed for {ticker}: {e}")

        # 方法2: Yahoo Finance v8 chart API (后备) — 只提供价格而非AUM，跳过
        # 注意: v8 API 不提供 totalAssets，返回的 regularMarketPrice 是单份价格而非AUM
        # （例: IBIT 价格 ~55美元 vs. 实际AUM ~500亿），不能用于AUM展示，直接返回 None
        return None

    async def get_all_etf_aum(self) -> Dict[str, Dict]:
        """
        批量获取所有 ETF AUM（并发）
        
        返回格式:
        {
            "IBIT": {"name": "...", "type": "BTC", "aum_usd": 50e9, "ok": True},
            ...
        }
        """
        # 真正并发执行所有 ticker
        tickers = list(ETF_TICKERS.keys())
        aum_values = await asyncio.gather(
            *[self.get_etf_aum(t) for t in tickers],
            return_exceptions=True,
        )

        results = {}
        for ticker, aum in zip(tickers, aum_values):
            if isinstance(aum, Exception):
                aum = None
            meta = ETF_TICKERS[ticker]
            results[ticker] = {
                "name": meta["name"],
                "type": meta["type"],
                "aum_usd": float(aum) if aum else None,
                "ok": aum is not None,
            }

        return results

    # ──────────────────────────────────────────
    #  2. Blockchain.info: BTC 地址余额
    # ──────────────────────────────────────────

    async def get_btc_address_balance(self, address: str) -> Optional[float]:
        """
        通过 mempool.space API 查询 BTC 地址余额 (单位: BTC)
        
        API: https://mempool.space/api/address/{address}
        完全免费，无需 API Key，支持 legacy/bech32 格式
        返回 chain_stats.funded_txo_sum - chain_stats.spent_txo_sum (satoshi)
        """
        session = await self._get_session()
        url = f"{self.mempool_api}/address/{address}"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        
        try:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    chain_stats = data.get("chain_stats", {})
                    funded = chain_stats.get("funded_txo_sum", 0)
                    spent = chain_stats.get("spent_txo_sum", 0)
                    return (funded - spent) / 1e8  # satoshi -> BTC
                elif resp.status == 429:
                    logger.warning(f"mempool.space rate limited for {address[:12]}...")
                    return None
                else:
                    logger.debug(f"mempool.space {resp.status} for {address[:12]}...")
                    return None
        except Exception as e:
            logger.debug(f"BTC balance fetch failed for {address[:12]}...: {e}")
            return None

    async def get_all_btc_holdings(self) -> List[Dict]:
        """
        查询所有已知 BTC ETF 托管地址余额
        
        返回: [{etf, name, address_short, btc_balance, custodian}, ...]
        """
        results = []
        for entry in ETF_BTC_ADDRESSES:
            # 速率控制：每次请求间隔
            await asyncio.sleep(0.5)
            
            balance = await self.get_btc_address_balance(entry["address"])
            results.append({
                "etf": entry["etf"],
                "name": entry["name"],
                "address_short": entry["address"][:12] + "...",
                "btc_balance": balance,
                "custodian": entry["custodian"],
                "ok": balance is not None,
            })
        
        return results

    # ──────────────────────────────────────────
    #  3. Blockscout: ETH 地址余额
    # ──────────────────────────────────────────

    async def get_eth_address_balance(self, address: str) -> Optional[float]:
        """
        通过 Blockscout 免费 API 查询 ETH 地址余额 (单位: ETH)
        
        API: https://eth.blockscout.com/api/v2/addresses/{address}
        完全免费，无需注册，无需 API Key
        备选: Etherscan（需要注册免费 key）
        """
        session = await self._get_session()
        url = f"{self.blockscout_api}/addresses/{address}"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        
        try:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # coin_balance 以 Wei 返回（字符串）
                    wei_str = data.get("coin_balance", "0") or "0"
                    return int(wei_str) / 1e18  # Wei -> ETH
                elif resp.status == 429:
                    logger.warning(f"Blockscout rate limited for {address[:10]}...")
                    return None
                else:
                    logger.debug(f"Blockscout {resp.status} for {address[:10]}...")
                    return None
        except Exception as e:
            logger.debug(f"ETH balance fetch failed for {address[:10]}...: {e}")
            return None

    async def get_all_eth_holdings(self) -> List[Dict]:
        """
        查询所有已知 ETH ETF 托管地址余额（通过 Blockscout）
        """
        results = []
        for entry in ETF_ETH_ADDRESSES:
            await asyncio.sleep(0.5)  # Blockscout 免费，适当间隔即可
            
            balance = await self.get_eth_address_balance(entry["address"])
            results.append({
                "etf": entry["etf"],
                "name": entry["name"],
                "address_short": entry["address"][:10] + "...",
                "eth_balance": balance,
                "custodian": entry["custodian"],
                "ok": balance is not None,
            })
        
        return results

    # ──────────────────────────────────────────
    #  4. 聚合: 获取所有数据
    # ──────────────────────────────────────────

    async def get_all(self) -> Dict:
        """
        获取所有 ETF 链上监控数据
        
        返回:
        {
            "etf_aum": {ticker: {...}},      # yfinance AUM
            "btc_holdings": [{...}],          # Blockchain.info 余额
            "eth_holdings": [{...}],          # Etherscan 余额
            "btc_total": float,               # 已知地址 BTC 汇总
            "eth_total": float,               # 已知地址 ETH 汇总
            "timestamp": str,
        }
        """
        logger.info("ETF Onchain Collector: fetching all data...")
        
        # 并发执行 AUM 查询（yfinance），串行执行链上查询（速率限制）
        aum_task = asyncio.create_task(self.get_all_etf_aum())
        
        # 链上数据串行（避免触发速率限制）
        btc_holdings = await self.get_all_btc_holdings()
        eth_holdings = await self.get_all_eth_holdings()
        
        etf_aum = await aum_task
        
        # 汇总链上总持仓
        btc_total = sum(
            h["btc_balance"] for h in btc_holdings
            if h["ok"] and h["btc_balance"]
        )
        eth_total = sum(
            h["eth_balance"] for h in eth_holdings
            if h["ok"] and h["eth_balance"]
        )
        
        return {
            "etf_aum": etf_aum,
            "btc_holdings": btc_holdings,
            "eth_holdings": eth_holdings,
            "btc_total": btc_total,
            "eth_total": eth_total,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ──────────────────────────────────────────
    #  5. 格式化为 macro_indicators 卡片
    # ──────────────────────────────────────────

    async def get_macro_indicators(self, btc_price: float = 0, eth_price: float = 0) -> List[Dict]:
        """
        获取格式化后的 macro_indicators 卡片列表，
        可直接追加到 web/app.py 的 macro_indicators 列表中
        
        Args:
            btc_price: 当前 BTC/USD 价格（用于计算链上持仓市值）
            eth_price: 当前 ETH/USD 价格
        """
        try:
            data = await self.get_all()
        except Exception as e:
            logger.error(f"ETF onchain get_all failed: {e}")
            return []

        cards = []
        etf_aum = data.get("etf_aum", {})

        # ── BTC ETF AUM 卡片（前5大）──
        # 用 yfinance totalAssets 作为 AUM 数据（最准确的可免费获取数据）
        btc_etfs = [
            (ticker, info)
            for ticker, info in etf_aum.items()
            if info["type"] == "BTC" and info["ok"] and info["aum_usd"]
        ]
        # 按 AUM 降序排列
        btc_etfs.sort(key=lambda x: x[1]["aum_usd"] or 0, reverse=True)

        if btc_etfs:
            # 合计 BTC ETF 总 AUM
            total_btc_aum = sum(info["aum_usd"] for _, info in btc_etfs if info["aum_usd"])
            cards.append({
                "name_zh": "BTC ETF 总规模",
                "name_en": "Total BTC ETF AUM",
                "abbr": "BTC-ETF-AUM",
                "value": f"${total_btc_aum / 1e9:.1f}B",
                "tags": ["资金", "BTC", "ETF"],
                "class": "text-primary",
                "desc": f"含 {len(btc_etfs)} 支 BTC ETF 合计总净资产",
            })

            # 前3大 ETF 单独展示
            for ticker, info in btc_etfs[:3]:
                aum_b = info["aum_usd"] / 1e9
                cards.append({
                    "name_zh": info["name"],
                    "name_en": f"{ticker} AUM",
                    "abbr": ticker,
                    "value": f"${aum_b:.2f}B",
                    "tags": ["资金", "BTC", "ETF"],
                    "class": "text-warning" if aum_b > 10 else "",
                    "desc": f"{ticker} ETF 总净资产 (via yfinance)",
                })

        # ── ETH ETF AUM 卡片 ──
        eth_etfs = [
            (ticker, info)
            for ticker, info in etf_aum.items()
            if info["type"] == "ETH" and info["ok"] and info["aum_usd"]
        ]
        eth_etfs.sort(key=lambda x: x[1]["aum_usd"] or 0, reverse=True)

        if eth_etfs:
            total_eth_aum = sum(info["aum_usd"] for _, info in eth_etfs if info["aum_usd"])
            cards.append({
                "name_zh": "ETH ETF 总规模",
                "name_en": "Total ETH ETF AUM",
                "abbr": "ETH-ETF-AUM",
                "value": f"${total_eth_aum / 1e9:.2f}B",
                "tags": ["资金", "ETH", "ETF"],
                "class": "text-primary",
                "desc": f"含 {len(eth_etfs)} 支 ETH ETF 合计总净资产",
            })

        # ── 链上 BTC 余额卡片（按地址） ──
        btc_holdings = data.get("btc_holdings", [])
        for h in btc_holdings:
            if not h["ok"] or not h.get("btc_balance"):
                continue
            btc_bal = h["btc_balance"]
            usd_val = btc_bal * btc_price if btc_price else 0
            cards.append({
                "name_zh": f"{h['etf']} 链上持仓",
                "name_en": f"{h['etf']} On-chain Balance",
                "abbr": f"CHAIN-{h['etf']}",
                "value": f"{btc_bal:,.0f} BTC",
                "sub_value": f"≈${usd_val / 1e9:.1f}B" if usd_val else h["custodian"],
                "tags": ["链上", "BTC", "ETF"],
                "class": "text-success",
                "desc": f"托管: {h['custodian']} | {h['address_short']}",
            })

        # ── 链上 ETH 余额卡片 ──
        eth_holdings = data.get("eth_holdings", [])
        for h in eth_holdings:
            if not h["ok"] or not h.get("eth_balance"):
                continue
            eth_bal = h["eth_balance"]
            usd_val = eth_bal * eth_price if eth_price else 0
            cards.append({
                "name_zh": f"{h['etf']} 链上持仓",
                "name_en": f"{h['etf']} On-chain Balance",
                "abbr": f"CHAIN-{h['etf']}",
                "value": f"{eth_bal:,.0f} ETH",
                "sub_value": f"≈${usd_val / 1e9:.2f}B" if usd_val else h["custodian"],
                "tags": ["链上", "ETH", "ETF"],
                "class": "text-success",
                "desc": f"托管: {h['custodian']} | {h['address_short']}",
            })

        return cards

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# 全局实例
etf_onchain_collector = ETFOnchainCollector()
