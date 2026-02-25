#!/bin/bash
# AutoM2026 启动脚本

cd "$(dirname "$0")"

echo "==================================="
echo "  AutoM2026 - 策略交易系统"
echo "==================================="

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 检查依赖
echo "Checking dependencies..."
pip install -q -r requirements.txt

# 初始化数据库
echo "Initializing database..."
python -c "from core.database import init_db_sync; init_db_sync()"

# 启动服务
echo ""
echo "Starting server..."
echo "Access: http://localhost:8080"
echo ""

python main.py
