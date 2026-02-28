"""
AutoM2026 配置文件
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 加载 .env 文件
load_dotenv(BASE_DIR / ".env")

# 数据库配置
DATABASE_PATH = BASE_DIR / "data" / "autom2026.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

# API 配置
BINANCE_API_URL = "https://api.binance.com"
FRED_API_URL = "https://api.stlouisfed.org/fred"
FEAR_GREED_API_URL = "https://api.alternative.me/fng"

# API Keys (从环境变量读取)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# LLM 配置
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() == "true"

# 调度器配置
SCHEDULER_TIMEZONE = "Asia/Shanghai"
DEFAULT_TA_INTERVAL_MINUTES = 10  # 技术分析策略默认执行间隔
DEFAULT_MACRO_INTERVAL_HOURS = 4  # 宏观策略默认执行间隔
DEFAULT_GRID_CHECK_SECONDS = 30   # 网格策略价格检查间隔

# Web UI 配置
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = BASE_DIR / "logs"

# ========== Phase 1 新增配置 ==========

# Telegram 通知
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 风控配置
RISK_MAX_POSITION_PCT = float(os.getenv("RISK_MAX_POSITION_PCT", "0.30"))
RISK_MAX_DRAWDOWN_PCT = float(os.getenv("RISK_MAX_DRAWDOWN_PCT", "0.15"))
RISK_DAILY_LOSS_LIMIT_PCT = float(os.getenv("RISK_DAILY_LOSS_LIMIT_PCT", "0.05"))
RISK_COOLDOWN_HOURS = int(os.getenv("RISK_COOLDOWN_HOURS", "24"))

# 交易模式: paper / dry_run / live
TRADING_MODE = os.getenv("TRADING_MODE", "paper")

# Portfolio 快照间隔 (小时)
PORTFOLIO_SNAPSHOT_INTERVAL_HOURS = int(os.getenv("PORTFOLIO_SNAPSHOT_HOURS", "1"))

# 确保必要目录存在
(BASE_DIR / "data").mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
