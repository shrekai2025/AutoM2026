"""
AutoM2026 主入口

启动 Web 服务器
"""
import sys
import os
import logging
import uvicorn

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WEB_HOST, WEB_PORT, LOG_LEVEL

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

# Suppress watchfiles verbose output
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

def main():
    """启动服务"""
    print("""
    ╔═══════════════════════════════════════╗
    ║         AutoM2026 v1.0.0              ║
    ║   简化版加密货币策略交易系统          ║
    ╚═══════════════════════════════════════╝
    """)
    
    print(f"Starting server at http://{WEB_HOST}:{WEB_PORT}")
    print("Press Ctrl+C to stop\n")
    
    uvicorn.run(
        "web.app:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=True,  # 开发模式
        reload_excludes=["*.log", "*.db", "*.sqlite", "data/*", "logs/*", "*.sqlite-wal", "*.sqlite-shm"],
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
