"""
下跌趋势跟随策略测试脚本

演示如何使用 DowntrendFollowStrategy 生成做空信号
"""
import asyncio
import logging
from strategies.downtrend_follow_strategy import DowntrendFollowStrategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_downtrend_strategy():
    """测试下跌趋势策略"""

    # 初始化策略
    config = {
        "symbol": "BTC",
        "timeframes": ["15m", "1h", "4h"],
        "short_threshold": 35,
        "atr_stop_mult": 1.5,
        "risk_reward_1r": 1.0,
        "risk_reward_2r": 2.0,
    }

    strategy = DowntrendFollowStrategy(config)

    logger.info("=" * 80)
    logger.info("下跌趋势跟随策略测试")
    logger.info("=" * 80)
    logger.info(f"策略类型: {strategy.strategy_type}")
    logger.info(f"策略版本: {strategy.strategy_version}")
    logger.info(f"交易标的: {config['symbol']}")
    logger.info(f"时间框架: {config['timeframes']}")
    logger.info("=" * 80)

    # 执行分析（将自动从数据库或API获取数据）
    try:
        signal = await strategy.analyze()

        logger.info("\n" + "=" * 80)
        logger.info("策略信号结果")
        logger.info("=" * 80)
        logger.info(f"信号类型: {signal.signal.value.upper()}")
        logger.info(f"信念分数: {signal.conviction_score:.1f}/100")
        logger.info(f"建议仓位: {signal.position_size * 100:.1f}%")
        logger.info(f"信号原因: {signal.reason}")
        logger.info("-" * 80)

        if signal.signal.value == "sell":
            logger.info("交易参数:")
            logger.info(f"  入场价格: ${signal.entry_price:,.2f}")
            logger.info(f"  止损价格: ${signal.stop_loss:,.2f}")
            logger.info(f"  止盈目标1 (1R): ${signal.take_profit:,.2f}")

            metadata = signal.metadata or {}
            if "take_profit_2r" in metadata:
                logger.info(f"  止盈目标2 (2R): ${metadata['take_profit_2r']:,.2f}")
            if "risk" in metadata:
                logger.info(f"  风险金额: ${metadata['risk']:,.2f}")
            if "exit_condition" in metadata:
                logger.info(f"  离场参考: {metadata['exit_condition']}")

            logger.info("-" * 80)
            logger.info("技术指标详情:")
            if "ema20" in metadata:
                logger.info(f"  EMA20: ${metadata['ema20']:,.2f}")
            if "ema200" in metadata:
                logger.info(f"  EMA200: ${metadata['ema200']:,.2f}")
            if "atr" in metadata:
                logger.info(f"  ATR: ${metadata['atr']:,.2f}")
            if "swing_high" in metadata:
                logger.info(f"  Swing High: ${metadata['swing_high']:,.2f}")

            if "score_by_tf" in metadata:
                logger.info("-" * 80)
                logger.info("各时间框架评分:")
                for tf, score in metadata["score_by_tf"].items():
                    logger.info(f"  {tf}: {score:.1f}/100")

        logger.info("=" * 80)

        # 格式化输出类似截图的消息
        if signal.signal.value == "sell":
            print("\n" + "🔔" * 40)
            print(f"📉 {signal.metadata.get('grade', 'GOOD').upper()}机会 做空信号")
            print("=" * 80)
            print(f"标的: {signal.symbol}USDT")
            print(f"入场: ${signal.entry_price:,.2f}")
            print(f"止损(SL): ${signal.stop_loss:,.2f}")
            print(f"止盈1(1R): ${signal.take_profit:,.2f}")
            if "take_profit_2r" in signal.metadata:
                print(f"止盈2(2R): ${signal.metadata['take_profit_2r']:,.2f}")
            print(f"离场参考: {signal.metadata.get('exit_condition', 'N/A')}")
            print("-" * 80)
            print(f"信号原因: {signal.reason}")
            print("🔔" * 40)

    except Exception as e:
        logger.error(f"策略执行失败: {e}", exc_info=True)


async def test_with_mock_data():
    """使用模拟数据测试（用于演示）"""

    logger.info("\n" + "=" * 80)
    logger.info("使用模拟数据测试")
    logger.info("=" * 80)

    # 模拟一个下跌趋势的市场数据
    # 这里需要构造符合格式的K线数据
    # 实际使用时会从数据库或API获取真实数据

    mock_kline = {
        "open": 95000,
        "high": 95500,
        "low": 94000,
        "close": 94200,
        "volume": 1000,
    }

    # 生成200根K线（模拟下跌趋势）
    mock_klines = []
    base_price = 100000
    for i in range(200):
        # 模拟下跌趋势
        price = base_price - i * 30 + (i % 10 - 5) * 50
        mock_klines.append({
            "open": price + 100,
            "high": price + 200,
            "low": price - 100,
            "close": price,
            "volume": 1000 + i * 10,
        })

    market_data = {
        "klines": {
            "15m": mock_klines[-100:],
            "1h": mock_klines[-150:],
            "4h": mock_klines,
        }
    }

    strategy = DowntrendFollowStrategy()

    try:
        signal = await strategy.analyze(market_data)

        logger.info(f"信号: {signal.signal.value.upper()}")
        logger.info(f"分数: {signal.conviction_score:.1f}")
        logger.info(f"原因: {signal.reason}")

        if signal.entry_price:
            logger.info(f"入场: ${signal.entry_price:,.2f}")
            logger.info(f"止损: ${signal.stop_loss:,.2f}")
            logger.info(f"止盈: ${signal.take_profit:,.2f}")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    # 运行真实数据测试
    asyncio.run(test_downtrend_strategy())

    # 运行模拟数据测试
    # asyncio.run(test_with_mock_data())
