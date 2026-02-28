from .base import BaseStrategy, StrategySignal, SignalType
from .ta_strategy import TAStrategy
from .macro_strategy import MacroStrategy
from .grid_strategy import GridStrategy
from .defi_pair_strategy import DefiPairStrategy
from .downtrend_follow_strategy import DowntrendFollowStrategy

__all__ = [
    "BaseStrategy",
    "StrategySignal",
    "SignalType",
    "TAStrategy",
    "MacroStrategy",
    "GridStrategy",
    "DefiPairStrategy",
    "DowntrendFollowStrategy",
]

# 策略类型映射
STRATEGY_CLASSES = {
    "ta": TAStrategy,
    "macro": MacroStrategy,
    "grid": GridStrategy,
    "pair": DefiPairStrategy,
    "downtrend_follow": DowntrendFollowStrategy,
}


def get_strategy_class(strategy_type: str):
    """根据类型获取策略类"""
    return STRATEGY_CLASSES.get(strategy_type)
