# 🚀 AutoM2026 - 加密货币策略交易系统

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

AutoM2026 是一个面向个人的、轻量级加密货币策略交易系统。它集成了技术指标分析、宏观数据采集、网格交易以及 AI 辅助决策，旨在通过简单的 Web 界面提供专业的量化交易体验。

---

## ✨ 核心特性

- **多策略支持**:
  - 📈 **TA Strategy**: 基于 EMA/RSI/MACD/BBands 的技术分析策略。
  - 🌍 **Macro Strategy**: 整合 Fear & Greed 指数和 FRED 宏观数据的趋势策略。
  - 🕸️ **Grid Strategy**: 自动低买高卖的经典网格交易策略。
- **交易与模拟**:
  - 🧪 **Paper Trading**: 内置模拟交易引擎，零风险测试策略。
  - 💰 **Dry Run / Live**: 支持对接 Binance 公开数据，支持模拟盘和实盘扩展。
- **风控与通知**:
  - 🛡️ **Risk Control**: 包含最大回撤保护、单笔仓位限制、熔断机制。
  - 📢 **Telegram Bot**: 实时推送交易执行记录和风控告警。
- **Web UI 管理**: 响应式管理后台，支持策略一键开关、持仓查询与历史账单。
- **AI 智能辅助**: 支持接入 OpenRouter 进行市场宏观环境分析。

---

## 🛠️ 技术栈

- **后端**: FastAPI, SQLAlchemy (Async), Pydantic
- **调度**: APScheduler (分布式任务管理)
- **数据**: SQLite, aiosqlite
- **UI**: Jinja2 Templates, Vanilla CSS/JS
- **容器**: Docker, Docker Compose

---

## 🚀 快速开始

### 1. 环境准备

- **本地**: Python 3.9+
- **服务器 (推荐)**: Ubuntu 20.04+, Docker & Docker Compose
- **API Keys (可选)**:
  - [FRED API Key](https://fred.stlouisfed.org/docs/api/api_key.html) (宏观数据)
  - [OpenRouter API Key](https://openrouter.ai/) (LLM 智能分析)

### 2. 克隆项目

```bash
git clone https://github.com/shrekai2025/AutoMoney.git
cd AutoMoney/AutoM2026
```

### 3. 初始化配置

运行交互式配置脚本：
```bash
chmod +x setup_env.sh
./setup_env.sh
```
此脚本会协助您创建 `.env` 文件并填入必要的 API Keys。

### 4. 运行系统

#### A. 本地运行
```bash
chmod +x start.sh
./start.sh
```
访问: `http://localhost:8080`

#### B. Docker 部署 (推荐服务器使用)
```bash
docker-compose up -d
```
访问: `http://服务器IP:8080`

---

## 📜 部署与运维指南

### 端口开放 (重要)
如果您在腾讯云、阿里云等云服务器部署，请在 **安全组/防火墙** 中开放 `8080` 端口。

### Systemd 服务 (如果不使用 Docker)
您可以参考以下配置将应用注册为系统服务：
1. 创建 `/etc/systemd/system/autom2026.service`
2. 填入项目路径、Python 虚拟环境路径及执行命令。
3. 执行 `systemctl enable --now autom2026`

### 反向代理 (Nginx)
建议使用 Nginx 对外提供服务并配置 SSL：
```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 🧠 与 AI Agent / Skill 配合使用

AutoM2026 提供了一个完整的 **Trading Hub Skill** (`trading-hub-skill` 目录)，让 AI Agent (如 Openclaw/Claude/Cursor) 能够无缝接入您的交易系统基础设施。

它将系统功能分为了三个渐进式层级：
1. **L1 市场数据 (Market Data)**: 获取大盘全局快照（含链上估值、FRED 宏观、ETF 资金流向及实时报价）与 K 线数据。
2. **L2 技术分析 (Technical Analysis)**: 自动化多时间框架 (15m/1h/4h/1d) 技术指标计算与信号提取，Agent 可藉此构建高级交易策略并回传决策。
3. **L3 策略回测 (Strategy Backtest)**: 双币套利与轮动回测引擎，支持 CEX (Binance) 与 DEX (GeckoTerminal) 深度数据分析。

**接入方式**:
- 将 `trading-hub-skill/SKILL.md` 等相关规则与工作流文件喂给您的 AI 助手，它将自动理解整个 API 协议，并成为您的全能投资分析顾问。

---

## 📂 目录结构

```text
AutoM2026/
├── config/          # API/数据库/全局配置
├── core/            # 系统内核 (Database, Scheduler, Monitor)
├── data_collectors/ # 各类数据爬虫与采集器
├── execution/       # 交易执行引擎 (Paper/Live)
├── indicators/      # 技术指标计算库
├── models/          # SQLAlchemy 数据模型定义
├── strategies/      # 交易策略逻辑实现
├── web/             # FastAPI App, 静态资源与模板
├── main.py          # 程序启动入口
└── setup_env.sh     # 环境初始化向导
```

---

## 🤝 贡献说明

1. **Fork** 本仓库。
2. **创建 Feature 分支**: `git checkout -b feature/AmazingFeature`
3. **提交更改**: `git commit -m 'Add some AmazingFeature'`
4. **Push 分支**: `git push origin feature/AmazingFeature`
5. **发起 Pull Request**。

---

## 🛡️ 安全提示

- **只读权限**: 建议在 Binance 等平台创建 API Key 时，**仅开启读取权限**，实盘交易需谨慎。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

**祝交易顺利，早日财富自由！🚀**
