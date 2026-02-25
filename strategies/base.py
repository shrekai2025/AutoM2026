"""
策略抽象基类 (v3 — Phase 1A 升级)

变更记录:
- v3: StrategySignal 扩展 stop_loss/take_profit/urgency/order_type/symbol/entry_price/metadata
      BaseStrategy.analyze() 支持 MarketContext 和旧 Dict 两种输入
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from datetime import datetime


class SignalType(str, Enum):
    """交易信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class StrategySignal:
    """
    策略信号 (v3)
    
    向后兼容: 所有 v3 新增字段都有默认值，现有策略零改动。
    """
    signal: SignalType
    conviction_score: float       # 0-100
    position_size: float          # 0-1 建议仓位比例
    reason: str
    
    # -- v3 新增字段 --
    symbol: str = "BTC"           # 交易标的
    entry_price: Optional[float] = None   # 期望入场价 (None=市价)
    stop_loss: Optional[float] = None     # 止损价
    take_profit: Optional[float] = None   # 止盈价
    urgency: str = "normal"       # "immediate" / "normal" / "low"
    order_type: str = "market"    # "market" / "limit"
    metadata: Optional[Dict[str, Any]] = None  # 策略附加数据 (自由扩展)
    
    # -- 原有字段 --
    logs: Optional[List[dict]] = None     # Process details
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.logs is None:
            self.logs = []
        if self.metadata is None:
            self.metadata = {}


class BaseStrategy(ABC):
    """
    策略抽象基类 (v3)
    
    所有策略都需要实现:
    1. analyze() - 分析市场数据并生成信号
    2. get_default_config() - 返回默认配置
    
    v3 变更:
    - analyze() 同时支持 MarketContext 对象和旧 Dict 参数
    - 新增 strategy_version 属性
    """
    
    strategy_type: str = "base"
    strategy_version: str = "1.0"
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = self.get_default_config()
        if config:
            self._recursive_update(self.config, config)
        self._last_signal: Optional[StrategySignal] = None

    def _recursive_update(self, base_dict: Dict, update_dict: Dict):
        """递归更新配置"""
        for k, v in update_dict.items():
            if k in base_dict and isinstance(base_dict[k], dict) and isinstance(v, dict):
                self._recursive_update(base_dict[k], v)
            else:
                base_dict[k] = v
    
    @abstractmethod
    async def analyze(self, market_data=None) -> StrategySignal:
        """
        分析市场数据并生成交易信号
        
        Args:
            market_data: MarketContext 对象 或 旧版 Dict。
                         None 时策略应自行获取数据。
            
        Returns:
            StrategySignal 交易信号
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        返回策略默认配置
        
        Returns:
            配置字典
        """
        pass
    
    @property
    def last_signal(self) -> Optional[StrategySignal]:
        """获取最后一次信号"""
        return self._last_signal
    
    def update_config(self, new_config: Dict[str, Any]):
        """更新策略配置"""
        self._recursive_update(self.config, new_config)
