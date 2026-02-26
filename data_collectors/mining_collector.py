"""
Mining Collector — 基于 WhatToMine 公开 API

数据源:
  - https://whattomine.com/coins/1.json  (BTC 网络实时数据)
    提供: block_reward, difficulty, nethash, exchange_rate

计算逻辑:
  - 每 TH/s 日收益 (BTC) = 86400 * block_reward / (difficulty * 2^32 / nethash)
  - 关机价 (USD) = 日电费 / 日收益BTC
  - 将主流矿机的关机价汇总展示

主流矿机参数（定期维护，来源: 矿机厂商官网）
"""
import logging
import time
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# 主流矿机参数: (name, hashrate_TH, power_W)
# 定期更新（来源: Antminer/Whatsminer/Avalon 官网）
KNOWN_MINERS = [
    ("Antminer S21 XP Hyd",   473.0, 5676),
    ("Antminer S21 Pro",       234.0, 3510),
    ("Antminer S21",           200.0, 3500),
    ("Antminer S19 XP Hyd",   255.0, 5304),
    ("Antminer S19 Pro",       110.0, 3250),
    ("Whatsminer M60S",        186.0, 3441),
    ("Whatsminer M50S",        126.0, 3276),
    ("Avalon A1566",           185.0, 5180),
    ("Antminer S19k Pro",      120.0, 2760),
    ("Antminer S19j Pro",       96.0, 3068),
]

ELECTRIC_FEE_USD_PER_KWH = 0.06   # 基准电费


class MiningCollector:
    """矿业数据采集器（基于 WhatToMine API）"""

    def __init__(self):
        self.wtm_btc_url = "https://whattomine.com/coins/1.json"

    async def get_miners_data(self) -> dict:
        """获取矿业数据：关机价范围、盈利矿机数、最优矿机"""
        from core.http_client import SharedHTTPClient
        from core.monitor import monitor

        start = time.monotonic()
        session = await SharedHTTPClient.get_session()
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AutoM2026/1.0)",
            "Accept": "application/json",
        }
        import aiohttp
        try:
            async with session.get(
                self.wtm_btc_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"WhatToMine API error {resp.status}")
                    await monitor.record_status("Mining (WTM)", "Scraper", False, 0, f"HTTP {resp.status}")
                    return {}

                data = await resp.json()

            result = self._calculate(data)
            latency = int((time.monotonic() - start) * 1000)
            await monitor.record_status(
                "Mining (WTM)", "Scraper", True, latency,
                f"{result.get('profitable_miners', 0)}/{result.get('total_miners', 0)} profitable, "
                f"BTC≈${data.get('exchange_rate', 0):,.0f}"
            )
            return result

        except Exception as e:
            logger.error(f"Mining data fetch error: {e}")
            await monitor.record_status("Mining (WTM)", "Scraper", False, 0, str(e)[:80])
            return {}

    def _calculate(self, network: dict) -> dict:
        """
        根据网络数据计算各矿机关机价

        公式来源: Bitcoin mining economics
          - 每 TH/s 日产出 (BTC) = 86400 * block_reward / (difficulty * 2^32 / nethash)
          - 等价简化: daily_btc_per_th = 86400 * block_reward * 1e12 / (difficulty * 2**32)
          - 关机价 = (power_W * 24 / 1000 * electric_fee) / daily_btc
        """
        try:
            block_reward = float(network.get("block_reward", 3.125))
            difficulty   = float(network.get("difficulty", 1e14))
            nethash      = float(network.get("nethash", 1e21))  # H/s
            btc_price    = float(network.get("exchange_rate", 0))

            # 网络整体算力 (EH/s) 供展示
            nethash_ehs = nethash / 1e18

            # 每 TH/s 每日产 BTC
            # difficulty = nethash * block_time / 2^32 (approx)
            # 精确: daily_btc_per_th = 86400 / block_time * block_reward / (nethash_in_TH)
            block_time_s = float(network.get("block_time", 600))
            nethash_ths  = nethash / 1e12
            blocks_per_day = 86400 / block_time_s
            daily_btc_per_th = blocks_per_day * block_reward / nethash_ths  # BTC per TH/s per day

            if daily_btc_per_th <= 0:
                logger.warning("Mining calc: daily_btc_per_th <= 0, cannot compute shutdown prices")
                return {}

            shutdown_prices = []
            profitable_count = 0
            best_miner_name: Optional[str] = None
            best_efficiency = 9999.0

            for name, hashrate_th, power_w in KNOWN_MINERS:
                daily_power_cost = (power_w * 24 / 1000) * ELECTRIC_FEE_USD_PER_KWH
                daily_btc = daily_btc_per_th * hashrate_th
                shutdown_price = daily_power_cost / daily_btc if daily_btc > 0 else 0

                if shutdown_price > 0:
                    shutdown_prices.append(shutdown_price)

                    if btc_price > 0 and btc_price > shutdown_price:
                        profitable_count += 1

                eff = power_w / hashrate_th
                if eff < best_efficiency:
                    best_efficiency = eff
                    best_miner_name = name

            return {
                "total_miners": len(KNOWN_MINERS),
                "profitable_miners": profitable_count,
                "best_miner": best_miner_name,
                "shutdown_range": (
                    f"${min(shutdown_prices):,.0f} ~ ${max(shutdown_prices):,.0f}"
                    if shutdown_prices else "N/A"
                ),
                "nethash_ehs": round(nethash_ehs, 1),
                "btc_price_wtm": btc_price,
            }

        except Exception as e:
            logger.error(f"Mining calculate error: {e}")
            return {}


mining_collector = MiningCollector()
