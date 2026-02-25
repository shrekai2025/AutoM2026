# 如何获取 API Keys

AutoM2026 需要以下 API Keys 才能正常运行。

## 必需的 API Keys

### 1. FRED API Key（宏观经济数据）

**用途**: 获取美国联邦储备经济数据（如 DXY 美元指数、黄金价格等）

**获取步骤**:
1. 访问 https://fred.stlouisfed.org/
2. 点击右上角 "Sign In" 注册账号
3. 登录后访问 https://fredaccount.stlouisfed.org/apikeys
4. 点击 "Request API Key"
5. 填写申请表单（说明用途：个人学习/研究）
6. 立即获得 API Key

**费用**: 完全免费 ✅

---

## 可选的 API Keys

### 2. OpenRouter API Key（LLM 分析）

**用途**: 使用 AI 模型进行市场分析和策略建议

**获取步骤**:
1. 访问 https://openrouter.ai/
2. 点击 "Sign In" 使用 Google/GitHub 登录
3. 进入 https://openrouter.ai/keys
4. 点击 "Create Key" 创建 API Key
5. 充值至少 $5（支持信用卡）

**费用**: 按使用量付费，GPT-4o-mini 约 $0.15/1M tokens

**注意**: 如果不需要 LLM 功能，可以在 `.env` 中设置 `LLM_ENABLED=false`

---

## 配置示例

创建 `.env` 文件：

```bash
# 必需
FRED_API_KEY=你的32位FRED_API_KEY

# 可选（如果启用 LLM）
OPENROUTER_API_KEY=sk-or-v1-你的OpenRouter密钥
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# LLM 配置
LLM_MODEL=openai/gpt-4o-mini
LLM_ENABLED=true  # 设置为 false 可禁用 LLM

# 系统配置
LOG_LEVEL=INFO
```

---

## 其他数据源（无需 API Key）

以下数据源无需 API Key，开箱即用：

- **Binance**: 加密货币价格数据（公开 API）
- **Alternative.me**: Fear & Greed 指数（公开 API）
- **Yahoo Finance**: 股票和 ETF 数据（通过 yfinance 库）

---

## 常见问题

### Q: 必须要 OpenRouter API Key 吗？
A: 不是必须的。如果不需要 LLM 分析功能，设置 `LLM_ENABLED=false` 即可。

### Q: FRED API Key 有使用限制吗？
A: 有，每天 120,000 次请求限制，对个人使用完全足够。

### Q: 可以使用其他 LLM 提供商吗？
A: 可以，代码支持任何兼容 OpenAI API 格式的提供商（如 OpenAI、Azure OpenAI 等）。

### Q: API Key 安全吗？
A: `.env` 文件已在 `.gitignore` 中，不会被上传到 GitHub。但请不要在代码中硬编码 API Key。

---

## 测试 API Keys

### 测试 FRED API

```bash
cd ~/AutoMoney/AutoM2026
source venv/bin/activate
python verify_fred.py
```

### 测试 OpenRouter API

```bash
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"
```

---

## 获取帮助

如果在获取 API Keys 过程中遇到问题：

1. FRED API: https://fred.stlouisfed.org/docs/api/
2. OpenRouter: https://openrouter.ai/docs

---

**提示**: 建议先使用 FRED API Key 部署，确认系统运行正常后，再考虑是否需要添加 LLM 功能。
