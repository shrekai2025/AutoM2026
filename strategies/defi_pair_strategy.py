import logging
import asyncio
from datetime import datetime
import numpy as np
from typing import Dict, Any, List, Optional

from .base import BaseStrategy, StrategySignal, SignalType
from data_collectors.gecko_terminal import gecko_terminal

logger = logging.getLogger(__name__)

class DefiPairStrategy(BaseStrategy):
    """
    DeFi 双币轮动/套利策略
    
    分析两个资产的价格比率 (Asset A / Asset B), 寻找均值回归或偏差套利机会。
    支持基于动态 SMA/EMA 或 固定阈值 的网格/波段操作。
    """
    
    strategy_type = "pair"
    strategy_version = "1.0"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.logs = []
        
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            # 资金池和资产 A (Base Asset)
            "asset_a": {
                "source": "gecko",          # 'gecko' or 'binance'
                "network": "base",
                "address": "0x91f0f34916ca4e2cce120116774b0e4fa0cdcaa8",
                "symbol": "weETH"
            },
            # 资金池和资产 B (Quote Asset)
            "asset_b": {
                "source": "gecko",          
                "network": "base",
                "address": "0x4200000000000000000000000000000000000006", 
                "symbol": "WETH"
            },
            
            # 定价模式: SMA = 动态均值回归，FIXED = 固定区间套利
            "mode": "SMA",
            
            # SMA 均值参数
            "window_size": 30,
            "std_dev_mult": 2.0,
            "use_ema": False,
            
            # 固定区间参数 (A/B 比率)
            "min_ratio": 1.0,  # 跌破此线买入 A
            "max_ratio": 1.05, # 涨破此线卖出 A (买入 B)
            
            # 交易手数 / 风险
            "step_size": 0.2,  # 每次交易占总资金的 20%
        }
        
    def _add_log(self, step: str, details: str, output: str = "", data: Dict = None):
        """添加分析过程日志"""
        log_entry = {
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "type": "calculation",
            "step": step,
            "details": details,
            "output": output,
        }
        if data:
            log_entry["data"] = data
        self.logs.append(log_entry)
        
    async def _fetch_price_series(self, cfg: Dict) -> List[Dict]:
        """抓取资产价格序列"""
        src = cfg.get("source", "gecko")
        limit = self.config["window_size"] + 5
        
        if src == "binance":
            # 动态导入防止循环依赖或启动报错
            from data_collectors.binance import binance_collector
            klines = await binance_collector.get_klines(
                symbol=cfg.get("address", cfg.get("symbol", "BTCUSDT")),
                interval="1d",
                limit=limit
            )
            # Map Binance klines to common format {ts: ms_timestamp, price: float}
            return [
                {"ts": int(k["open_time"].timestamp() * 1000), "price": k["close"]}
                for k in klines
            ]
            
        # 默认使用 GeckoTerminal
        series = await gecko_terminal.get_pool_history(
            network=cfg["network"],
            pool_address=cfg["address"],
            limit=limit
        )
        return series
        
    async def analyze(self, market_data=None) -> StrategySignal:
        self.logs = []
        cfg_a = self.config["asset_a"]
        cfg_b = self.config["asset_b"]
        
        self._add_log(
            "Data Fetching", 
            f"Fetching history for A ({cfg_a['symbol']}) and B ({cfg_b['symbol']})",
            "API Call"
        )
        
        # 为了实时交易，我们需要足够的历史数据来计算当前日的指标
        try:
            series_a = await self._fetch_price_series(cfg_a)
            series_b = await self._fetch_price_series(cfg_b)
            
            if not series_a or not series_b:
                return StrategySignal(
                    signal=SignalType.HOLD,
                    conviction_score=0,
                    position_size=0,
                    reason="Data missing from data source",
                    logs=self.logs
                )
                
            # 对齐数据
            prices_a = {item['ts']: item['price'] for item in series_a}
            prices_b = {item['ts']: item['price'] for item in series_b}
            
            common_ts = sorted(list(set(prices_a.keys()) & set(prices_b.keys())))
            if len(common_ts) < self.config["window_size"] and self.config["mode"] == "SMA":
                return StrategySignal(
                    signal=SignalType.HOLD,
                    conviction_score=0,
                    position_size=0,
                    reason="Not enough historical data for indicators calculation",
                    logs=self.logs
                )
        except Exception as e:
            return StrategySignal(
                signal=SignalType.HOLD,
                conviction_score=0,
                position_size=0,
                reason=f"Data fetching error: {e}",
                logs=self.logs
            )

        # 取最近一个窗口的数据计算当前指标
        ratios = []
        for ts in common_ts:
            ra = prices_a[ts]
            rb = prices_b[ts]
            # 为了确保除数不为0
            if rb > 0:
                ratios.append(ra / rb)
                
        current_ratio = ratios[-1]
        
        mean_val = None
        upper_band = None
        lower_band = None
        
        if self.config["mode"] == "FIXED":
            mean_val = (self.config["min_ratio"] + self.config["max_ratio"]) / 2
            lower_band = self.config["min_ratio"]
            upper_band = self.config["max_ratio"]
            
        elif self.config["mode"] == "SMA":
            # 计算最近 N 天的序列
            window = ratios[-self.config["window_size"]:]
            mean_val = float(np.mean(window))
            std_dev = float(np.std(window))
            mult = self.config["std_dev_mult"]
            lower_band = mean_val - mult * std_dev
            upper_band = mean_val + mult * std_dev
            
        self._add_log(
            "Indicator Calc",
            f"Mode: {self.config['mode']}. Mean: {mean_val:.4f}, Bands: [{lower_band:.4f}, {upper_band:.4f}]",
            f"Ratio: {current_ratio:.4f}"
        )   

        # 生成信号逻辑:
        # 当前我们是对资产 A (Base Asset) 的操作信号。买入 A = 卖出 B。
        signal = SignalType.HOLD
        position_size = 0.0
        reason = f"Current ratio {current_ratio:.4f} within bands [{lower_band:.4f}, {upper_band:.4f}]"
        score = 50.0
        
        # 如果比率跌破下轨，代表 Asset A 过度低估，Buy A
        if current_ratio < lower_band:
            signal = SignalType.BUY
            position_size = self.config["step_size"]
            reason = f"Ratio {current_ratio:.4f} drops below lower band {lower_band:.4f}. Asset A undervalued."
            score = 80 + 20 * min(abs(current_ratio - lower_band) / lower_band, 1.0)
            
        # 如果比率升破上轨，代表 Asset A 过度高估，Sell A (Buy B)
        elif current_ratio > upper_band:
            signal = SignalType.SELL
            position_size = self.config["step_size"] 
            reason = f"Ratio {current_ratio:.4f} breaks above upper band {upper_band:.4f}. Asset A overvalued."
            score = 80 + 20 * min(abs(current_ratio - upper_band) / upper_band, 1.0)
        
        self._add_log(
            "Decision logic",
            reason,
            f"Signal {signal.value}"
        )

        return StrategySignal(
            signal=signal,
            conviction_score=min(100.0, score),
            position_size=position_size,
            reason=reason,
            symbol=cfg_a['symbol'],
            logs=self.logs,
            metadata={
                "current_ratio": current_ratio,
                "mean_val": mean_val,
                "upper_band": upper_band,
                "lower_band": lower_band
            }
        )
