#!/bin/bash
# AutoM2026 停止脚本

echo "Stopping AutoM2026..."

# 1. 通过端口查找 (更准确)
pids_port=$(lsof -t -i:8080 2>/dev/null)

# 2. 通过命令行查找 (包含 AutoM2026 的 python 进程)
# 注意: 排除 grep 自身，排除编辑器插件进程 (run-jedi-language-server)
pids_cmd=$(ps -ef | grep "python" | grep "AutoM2026" | grep -v "grep" | grep -v "jedi" | awk '{print $2}')

# 合并 PID (去除换行)
pids=$(echo "$pids_port $pids_cmd" | xargs)

if [ -z "$pids" ]; then
    echo "No running process found (Port 8080 or process 'AutoM2026')."
else
    echo "Found processes: $pids"
    kill -9 $pids 2>/dev/null
    echo "✅ Stopped successfully."
fi
