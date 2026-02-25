"""
Telegram 通知模块 (Phase 1F)

通过 Telegram Bot API 推送:
1. 交易执行通知
2. 风控告警 (含熔断触发/解除)
3. 每日盈亏摘要

使用 httpx 直接调用 API，零额外依赖。

配置 (.env):
    TELEGRAM_BOT_TOKEN=your_bot_token
    TELEGRAM_CHAT_ID=your_chat_id
"""
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 延迟导入 httpx (可能未安装)
_httpx = None


def _get_httpx():
    global _httpx
    if _httpx is None:
        try:
            import httpx
            _httpx = httpx
        except ImportError:
            logger.warning("httpx not installed, Telegram notifications disabled")
    return _httpx


class TelegramNotifier:
    """Telegram 通知器"""
    
    TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self.bot_token and self.chat_id)
        
        if self._enabled:
            logger.info("Telegram notifier initialized")
        else:
            logger.info("Telegram notifier disabled (no token/chat_id)")
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        发送消息到 Telegram
        
        Args:
            text: 消息内容 (支持 HTML 格式)
            parse_mode: 解析模式 ("HTML" / "Markdown")
            
        Returns:
            是否发送成功
        """
        if not self._enabled:
            return False
        
        httpx = _get_httpx()
        if httpx is None:
            return False
        
        url = self.TELEGRAM_API.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                else:
                    logger.error(f"Telegram API error: {resp.status_code} - {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    
    # ========== 预定义消息模板 ==========
    
    async def notify_trade(
        self,
        side: str,
        symbol: str,
        amount: float,
        price: float,
        strategy_name: str = "",
        reason: str = "",
        conviction: float = 0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        is_paper: bool = True,
    ) -> bool:
        """交易执行通知"""
        mode = "📋 模拟" if is_paper else "💰 实盘"
        emoji = "🟢" if side == "buy" else "🔴"
        
        lines = [
            f"{emoji} <b>{mode} {side.upper()} {symbol}</b>",
            f"",
            f"策略: {strategy_name}" if strategy_name else "",
            f"数量: {amount:.6f}",
            f"价格: ${price:,.2f}",
            f"价值: ${amount * price:,.2f}",
            f"信念: {conviction:.0f}%",
        ]
        
        if stop_loss:
            lines.append(f"止损: ${stop_loss:,.2f}")
        if take_profit:
            lines.append(f"止盈: ${take_profit:,.2f}")
        if reason:
            lines.append(f"原因: {reason[:100]}")
        
        lines.append(f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        
        text = "\n".join(line for line in lines if line)
        return await self.send_message(text)
    
    async def notify_risk_alert(
        self,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """风控告警通知"""
        emoji_map = {
            "circuit_breaker_triggered": "🚨",
            "circuit_breaker_released": "✅",
            "max_drawdown_breach": "⚠️",
            "daily_loss_limit": "⚠️",
            "max_exposure_reject": "🛑",
        }
        emoji = emoji_map.get(event_type, "⚠️")
        
        lines = [
            f"{emoji} <b>风控告警: {event_type}</b>",
            f"",
            message,
        ]
        
        if details:
            for k, v in details.items():
                lines.append(f"  {k}: {v}")
        
        lines.append(f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        
        text = "\n".join(lines)
        return await self.send_message(text)
    
    async def notify_daily_summary(
        self,
        total_value: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        total_trades: int,
        active_strategies: int,
        circuit_breaker: bool = False,
    ) -> bool:
        """每日盈亏摘要"""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        pnl_sign = "+" if daily_pnl >= 0 else ""
        
        lines = [
            f"📊 <b>每日摘要</b>",
            f"",
            f"总价值: ${total_value:,.2f}",
            f"今日盈亏: {pnl_emoji} {pnl_sign}${daily_pnl:,.2f} ({pnl_sign}{daily_pnl_pct:.2f}%)",
            f"今日交易: {total_trades} 笔",
            f"活跃策略: {active_strategies}",
        ]
        
        if circuit_breaker:
            lines.append(f"🚨 熔断状态: 激活中")
        
        lines.append(f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        
        text = "\n".join(lines)
        return await self.send_message(text)


# 全局实例
telegram_notifier = TelegramNotifier()
