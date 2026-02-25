# AutoM2026 - 简化版加密货币策略交易系统

本地个人使用的加密货币策略交易系统，支持多种策略类型。

## 功能特性

- ✅ 技术指标策略 (TA Strategy): 基于 EMA/RSI/MACD/BBands 分析
- ✅ 宏观趋势策略 (Macro Strategy): 基于 Fear & Greed 和价格趋势
- ✅ 网格交易策略 (Grid Strategy): 自动低买高卖
- ✅ 模拟交易引擎
- ✅ 简单 Web UI

## 快速开始

```bash
# 进入项目目录
cd AutoM2026

# 运行启动脚本 (首次会自动创建虚拟环境和安装依赖)
chmod +x start.sh
./start.sh
```

启动后访问: http://localhost:8080

## 目录结构

```
AutoM2026/
├── config/          # 配置
├── core/            # 核心模块 (数据库、调度器)
├── data_collectors/ # 数据采集 (Binance, Fear&Greed)
├── indicators/      # 技术指标计算
├── strategies/      # 策略实现
├── execution/       # 交易执行
├── models/          # 数据模型
├── web/             # Web UI
├── main.py          # 入口
└── start.sh         # 启动脚本
```

## 配置

环境变量 (可选):

- `FRED_API_KEY`: FRED 宏观经济数据 API Key
- `OPENROUTER_API_KEY`: LLM API Key (用于辅助分析)
- `LLM_ENABLED`: 是否启用 LLM (true/false)

## 使用方法

1. **创建策略**: 在 Web UI 点击 "新建策略"
2. **启动策略**: 点击策略行的 "启动" 按钮
3. **手动执行**: 点击 "执行" 立即运行策略
4. **查看持仓**: 在 "持仓" 页查看当前持仓
5. **查看交易**: 在 "交易" 页查看历史交易
