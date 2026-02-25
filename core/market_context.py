"""
MarketContext — 策略输入的统一容器 (Phase 1B)

所有策略通过 MarketContext 获取数据，屏蔽数据来源差异。
回测引擎和实盘调度器都构建 MarketContext，策略代码完全相同。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List


@dataclass
class DataQualityReport:
    """
    数据质量报告
    
    由 DataQualityChecker 生成，附着在 MarketContext 上。
    策略可根据 completeness 分数决定是否降低 conviction。
    """
    completeness: float = 1.0         # 0-1，数据完整度
    warnings: List[str] = field(default_factory=list)
    missing_bars: int = 0             # 缺失 K 线数量
    suspicious_bars: int = 0          # 可疑 K 线数量 (涨跌幅异常)
    timestamp_aligned: bool = True    # 时间戳是否已对齐到 UTC

    @property
    def is_reliable(self) -> bool:
        """completeness >= 0.8 且无严重异常时视为可靠"""
        return self.completeness >= 0.8 and self.suspicious_bars == 0


@dataclass
class MarketContext:
    """
    策略输入的统一容器 (v3)
    
    使用方式:
        signal = await strategy.analyze(ctx)
    
    字段说明:
        symbol:          交易标的 (如 "BTC")
        current_price:   当前价格
        timestamp:       数据采集时间 (UTC)
        klines:          多时间框架 K 线 {"1h": [{"open":..., "close":...}, ...], ...}
        indicators:      各时间框架指标 {"1h": {"rsi": 45.2, "ema_9": ..., ...}, ...}
        ticker_24h:      24h ticker 数据 {"price": ..., "volume": ..., "price_change_24h": ...}
        fear_greed:      恐惧贪婪指数 (0-100)
        macro_data:      宏观数据 {"fed_funds_rate": ..., "treasury_10y": ..., ...}
        portfolio_state: 当前组合状态 {"balance": ..., "positions": {...}}
        data_quality:    数据质量报告
        metadata:        扩展数据 (链上数据、AI Advisory 结果等)
    """
    symbol: str
    current_price: float
    timestamp: datetime
    
    # 行情数据
    klines: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    indicators: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ticker_24h: Dict[str, Any] = field(default_factory=dict)
    
    # 外部数据
    fear_greed: Optional[int] = None
    macro_data: Optional[Dict[str, Any]] = None
    
    # 组合状态
    portfolio_state: Optional[Dict[str, Any]] = None
    
    # 数据质量
    data_quality: Optional[DataQualityReport] = None
    
    # 扩展
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于存储 market_snapshot）"""
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "fear_greed": self.fear_greed,
            "data_quality": {
                "completeness": self.data_quality.completeness,
                "warnings": self.data_quality.warnings,
                "missing_bars": self.data_quality.missing_bars,
                "suspicious_bars": self.data_quality.suspicious_bars,
            } if self.data_quality else None,
            "ticker_24h": {
                k: v for k, v in self.ticker_24h.items()
                if k in ("price", "volume", "price_change_24h")
            } if self.ticker_24h else None,
        }

    @classmethod
    def from_legacy_dict(cls, market_data: Dict[str, Any], symbol: str = "BTC") -> "MarketContext":
        """
        从旧版 Dict 参数构建 MarketContext (向后兼容)
        
        旧版策略的 market_data 结构各异，这里做最大努力转换。
        """
        price = (
            market_data.get("price") or
            market_data.get("current_price") or
            0.0
        )
        return cls(
            symbol=symbol,
            current_price=float(price),
            timestamp=datetime.utcnow(),
            klines=market_data.get("klines", {}),
            indicators=market_data.get("indicators", {}),
            ticker_24h=market_data.get("ticker_24h", {}),
            fear_greed=market_data.get("fear_greed"),
            macro_data=market_data.get("macro_data"),
            portfolio_state=market_data.get("portfolio_state"),
        )
