"""
回测引擎核心 (Phase 2A)

事件驱动架构:
1. 逐条 K 线回放
2. 为每条 K 线构建 MarketContext -> 调用 strategy.analyze()
3. 信号经过 RiskManager 评估
4. 模拟撮合: 市价单即时成交 / 限价单挂单等待
5. 手续费 + 滑点模型
6. 记录全部交易和净值曲线
"""
import logging
import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Type

from strategies.base import BaseStrategy, StrategySignal, SignalType
from core.market_context import MarketContext, DataQualityReport
from risk.risk_manager import RiskManager, RiskAction

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """回测交易记录"""
    timestamp: datetime
    side: str               # "buy" / "sell"
    symbol: str
    price: float            # 成交价 (含滑点)
    amount: float           # 成交数量
    value: float            # 成交价值 (USDT)
    fee: float              # 手续费 (USDT)
    reason: str = ""
    conviction: float = 0
    bar_index: int = 0


@dataclass
class BacktestResult:
    """回测结果"""
    # 配置
    symbol: str
    interval: str
    start_date: str
    end_date: str
    initial_capital: float
    fee_rate: float
    slippage_rate: float

    # 结果
    final_capital: float = 0
    total_bars: int = 0
    total_trades: int = 0
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)  # [{"time":..., "equity":...}]
    signals_log: List[Dict[str, Any]] = field(default_factory=list)


class BacktestEngine:
    """
    事件驱动回测引擎

    用法:
        engine = BacktestEngine(initial_capital=10000)
        result = await engine.run(
            strategy_class=TAStrategy,
            strategy_config={...},
            klines=klines_list,
            symbol="BTCUSDT",
            interval="1h",
        )
    """

    def __init__(
        self,
        initial_capital: float = 10000,
        fee_rate: float = 0.001,        # 0.1% 手续费
        slippage_rate: float = 0.0005,   # 0.05% 滑点
        use_risk_manager: bool = True,
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.use_risk_manager = use_risk_manager

    async def run(
        self,
        strategy_class: Type[BaseStrategy],
        strategy_config: Optional[Dict[str, Any]] = None,
        klines: List[Dict[str, Any]] = None,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        start_date: str = "",
        end_date: str = "",
        progress_callback=None,
    ) -> BacktestResult:
        """
        运行回测

        Args:
            strategy_class: 策略类
            strategy_config: 策略配置 (None 使用默认)
            klines: K 线数据列表 (从 data_loader 获取)
            symbol: 交易对
            interval: 时间框架
            start_date/end_date: 用于报告展示
            progress_callback: 进度回调 async fn(current, total)

        Returns:
            BacktestResult
        """
        if not klines or len(klines) < 2:
            raise ValueError("Not enough klines for backtest (need >= 2)")

        # 初始化策略
        strategy = strategy_class(strategy_config)

        # 初始化风控 (独立实例，不影响全局)
        risk_mgr = RiskManager() if self.use_risk_manager else None

        # 初始化账户状态
        cash = self.initial_capital
        position = 0.0          # 持仓数量
        avg_cost = 0.0          # 平均持仓成本
        trades: List[BacktestTrade] = []
        equity_curve: List[Dict[str, Any]] = []
        signals_log: List[Dict[str, Any]] = []

        # 维护指标计算所需的历史窗口
        warmup = min(50, len(klines) // 5)  # 预热期

        total = len(klines)

        for i in range(warmup, total):
            bar = klines[i]
            bar_time = self._parse_time(bar.get("open_time"))
            close_price = bar["close"]
            high = bar["high"]
            low = bar["low"]

            # === 构建 MarketContext ===
            # 给策略提供截止到当前 bar 的历史数据 (防止未来数据泄露)
            history_window = klines[max(0, i - 200):i + 1]
            ctx = self._build_context(
                symbol=symbol.replace("USDT", ""),
                current_price=close_price,
                bar_time=bar_time,
                klines_history=history_window,
                interval=interval,
            )

            # === 策略分析 ===
            try:
                signal = await strategy.analyze(ctx)
            except Exception as e:
                logger.warning(f"Strategy analyze error at bar {i}: {e}")
                signal = StrategySignal(
                    signal=SignalType.HOLD,
                    conviction_score=50,
                    position_size=0,
                    reason=f"Error: {e}",
                )

            # 记录信号
            signals_log.append({
                "bar_index": i,
                "time": bar_time.isoformat() if bar_time else str(bar.get("open_time")),
                "price": close_price,
                "signal": signal.signal.value,
                "conviction": signal.conviction_score,
                "position_size": signal.position_size,
                "reason": signal.reason,
            })

            # === 风控评估 ===
            if risk_mgr and signal.signal != SignalType.HOLD:
                portfolio_value = cash + position * close_price
                portfolio_state = {
                    "total_value": portfolio_value,
                    "positions": {},
                    "total_pnl_pct": (
                        (portfolio_value - self.initial_capital) / self.initial_capital * 100
                        if self.initial_capital > 0 else 0
                    ),
                    "daily_pnl": 0,
                }
                decision = risk_mgr.evaluate(
                    signal=signal,
                    portfolio_state=portfolio_state,
                    current_price=close_price,
                )
                if decision.action == RiskAction.REJECT:
                    signal = StrategySignal(
                        signal=SignalType.HOLD,
                        conviction_score=50,
                        position_size=0,
                        reason=f"Risk rejected: {decision.reason}",
                    )
                elif decision.final_signal:
                    signal = decision.final_signal

            # === 撮合执行 ===
            if signal.signal == SignalType.BUY and signal.position_size > 0:
                # 计算买入金额
                buy_value = cash * min(signal.position_size, 1.0)
                if buy_value > 10:  # 最低 $10
                    # 滑点: 买入价上移
                    exec_price = close_price * (1 + self.slippage_rate)
                    # 手续费
                    fee = buy_value * self.fee_rate
                    net_value = buy_value - fee
                    buy_amount = net_value / exec_price

                    # 更新账户
                    total_cost = avg_cost * position + exec_price * buy_amount
                    position += buy_amount
                    if position > 0:
                        avg_cost = total_cost / position
                    cash -= buy_value

                    trade = BacktestTrade(
                        timestamp=bar_time or datetime.utcnow(),
                        side="buy",
                        symbol=symbol,
                        price=exec_price,
                        amount=buy_amount,
                        value=buy_value,
                        fee=fee,
                        reason=signal.reason,
                        conviction=signal.conviction_score,
                        bar_index=i,
                    )
                    trades.append(trade)

            elif signal.signal == SignalType.SELL and signal.position_size > 0:
                sell_amount = position * min(signal.position_size, 1.0)
                if sell_amount > 0 and position > 0:
                    # 滑点: 卖出价下移
                    exec_price = close_price * (1 - self.slippage_rate)
                    sell_value = sell_amount * exec_price
                    fee = sell_value * self.fee_rate
                    net_value = sell_value - fee

                    position -= sell_amount
                    cash += net_value

                    trade = BacktestTrade(
                        timestamp=bar_time or datetime.utcnow(),
                        side="sell",
                        symbol=symbol,
                        price=exec_price,
                        amount=sell_amount,
                        value=sell_value,
                        fee=fee,
                        reason=signal.reason,
                        conviction=signal.conviction_score,
                        bar_index=i,
                    )
                    trades.append(trade)

            # === 记录净值 ===
            equity = cash + position * close_price
            equity_curve.append({
                "time": bar_time.isoformat() if bar_time else str(bar.get("open_time")),
                "equity": round(equity, 2),
                "price": close_price,
                "position": round(position, 8),
                "cash": round(cash, 2),
            })

            # 进度回调
            if progress_callback and i % 100 == 0:
                await progress_callback(i - warmup, total - warmup)

        # === 构建结果 ===
        final_equity = cash + position * klines[-1]["close"]

        result = BacktestResult(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            slippage_rate=self.slippage_rate,
            final_capital=round(final_equity, 2),
            total_bars=total - warmup,
            total_trades=len(trades),
            trades=trades,
            equity_curve=equity_curve,
            signals_log=signals_log,
        )

        logger.info(
            f"Backtest complete: {symbol} {interval} {start_date}~{end_date} | "
            f"Return: {(final_equity / self.initial_capital - 1) * 100:.2f}% | "
            f"Trades: {len(trades)}"
        )

        return result

    def _build_context(
        self,
        symbol: str,
        current_price: float,
        bar_time: Optional[datetime],
        klines_history: List[Dict],
        interval: str,
    ) -> MarketContext:
        """为回测构建 MarketContext (与实盘相同的接口)"""
        # 简化指标计算 (从 K 线历史提取)
        closes = [k["close"] for k in klines_history]
        indicators = {}

        if len(closes) >= 50:
            indicators["ema_9"] = self._ema(closes, 9)
            indicators["ema_21"] = self._ema(closes, 21)
            indicators["ema_50"] = self._ema(closes, 50)
            indicators["rsi"] = self._rsi(closes, 14)
            indicators["current_price"] = current_price

            # MACD
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            macd_line = ema12 - ema26
            indicators["macd"] = {
                "macd_line": macd_line,
                "histogram": macd_line,  # 简化版
            }

            # Bollinger
            if len(closes) >= 20:
                sma20 = sum(closes[-20:]) / 20
                std20 = (sum((c - sma20) ** 2 for c in closes[-20:]) / 20) ** 0.5
                upper = sma20 + 2 * std20
                lower = sma20 - 2 * std20
                bb_width = upper - lower
                percent_b = (current_price - lower) / bb_width if bb_width > 0 else 0.5
                indicators["bollinger"] = {
                    "upper": upper,
                    "lower": lower,
                    "middle": sma20,
                    "percent_b": percent_b,
                }

        return MarketContext(
            symbol=symbol,
            current_price=current_price,
            timestamp=bar_time or datetime.utcnow(),
            klines={interval: klines_history},
            indicators={interval: indicators},
            ticker_24h={"price": current_price},
            data_quality=DataQualityReport(completeness=1.0),
        )

    @staticmethod
    def _ema(data: List[float], period: int) -> float:
        """计算 EMA"""
        if len(data) < period:
            return data[-1] if data else 0
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = (val - ema) * multiplier + ema
        return ema

    @staticmethod
    def _rsi(data: List[float], period: int = 14) -> float:
        """计算 RSI"""
        if len(data) < period + 1:
            return 50
        deltas = [data[i] - data[i - 1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _parse_time(val) -> Optional[datetime]:
        """解析时间戳"""
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, (int, float)):
            ts = val / 1000 if val > 1e12 else val
            return datetime.fromtimestamp(ts)
        return None
