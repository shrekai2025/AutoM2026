# AutoM2026 前端开发指南

本指南为 AutoM2026 项目的前端开发规范，涵盖 **UI 样式标准** 和 **多语言支持**。所有前端代码必须遵循本指南。

---

## 目录

1.  [技术栈](#1-技术栈)
2.  [多语言支持 (i18n)](#2-多语言支持-i18n)
3.  [UI 样式规范摘要](#3-ui-样式规范摘要)
4.  [组件开发规范](#4-组件开发规范)
5.  [文件结构](#5-文件结构)

---

## 1. 技术栈

| 类别     | 技术                       | 说明             |
| :------- | :------------------------- | :--------------- |
| 后端模板 | Jinja2                     | FastAPI 集成     |
| 样式     | 原生 CSS + CSS 变量        | 不使用 Tailwind  |
| 交互     | Vanilla JavaScript         | 轻量，无框架依赖 |
| 图表     | (待定) Chart.js / Recharts | 如需图表         |

---

## 2. 多语言支持 (i18n)

### 2.1 核心规则

> ⚠️ **强制规则**: 所有用户可见的文案必须同时提供中英双语，禁止硬编码单一语言文案。

### 2.2 实现方案（硬编码）

使用简单的 JavaScript 对象存储翻译，通过 `lang` 属性切换。

#### 翻译文件：`translations.js`

```javascript
// web/static/js/translations.js

const TRANSLATIONS = {
  // ==================== 通用 ====================
  "app.name": {
    zh: "AutoM2026",
    en: "AutoM2026",
  },
  "app.subtitle": {
    zh: "策略交易系统",
    en: "Strategy Trading System",
  },

  // ==================== 导航 ====================
  "nav.dashboard": {
    zh: "仪表盘",
    en: "Dashboard",
  },
  "nav.strategies": {
    zh: "策略",
    en: "Strategies",
  },
  "nav.positions": {
    zh: "持仓",
    en: "Positions",
  },
  "nav.trades": {
    zh: "交易",
    en: "Trades",
  },

  // ==================== 按钮/操作 ====================
  "action.create": {
    zh: "新建",
    en: "Create",
  },
  "action.edit": {
    zh: "编辑",
    en: "Edit",
  },
  "action.delete": {
    zh: "删除",
    en: "Delete",
  },
  "action.start": {
    zh: "启动",
    en: "Start",
  },
  "action.stop": {
    zh: "停止",
    en: "Stop",
  },
  "action.pause": {
    zh: "暂停",
    en: "Pause",
  },
  "action.execute": {
    zh: "执行",
    en: "Execute",
  },
  "action.cancel": {
    zh: "取消",
    en: "Cancel",
  },
  "action.confirm": {
    zh: "确认",
    en: "Confirm",
  },
  "action.save": {
    zh: "保存",
    en: "Save",
  },

  // ==================== 策略 ====================
  "strategy.name": {
    zh: "策略名称",
    en: "Strategy Name",
  },
  "strategy.type": {
    zh: "策略类型",
    en: "Strategy Type",
  },
  "strategy.type.ta": {
    zh: "技术指标",
    en: "Technical Analysis",
  },
  "strategy.type.macro": {
    zh: "宏观趋势",
    en: "Macro Trend",
  },
  "strategy.type.grid": {
    zh: "网格交易",
    en: "Grid Trading",
  },
  "strategy.status": {
    zh: "状态",
    en: "Status",
  },
  "strategy.status.active": {
    zh: "运行中",
    en: "Active",
  },
  "strategy.status.paused": {
    zh: "已暂停",
    en: "Paused",
  },
  "strategy.status.stopped": {
    zh: "已停止",
    en: "Stopped",
  },
  "strategy.status.error": {
    zh: "错误",
    en: "Error",
  },
  "strategy.lastSignal": {
    zh: "最后信号",
    en: "Last Signal",
  },
  "strategy.conviction": {
    zh: "信念分数",
    en: "Conviction",
  },

  // ==================== 交易/持仓 ====================
  "trade.buy": {
    zh: "买入",
    en: "Buy",
  },
  "trade.sell": {
    zh: "卖出",
    en: "Sell",
  },
  "trade.hold": {
    zh: "持有",
    en: "Hold",
  },
  "position.symbol": {
    zh: "币种",
    en: "Symbol",
  },
  "position.amount": {
    zh: "数量",
    en: "Amount",
  },
  "position.avgCost": {
    zh: "均价",
    en: "Avg Cost",
  },
  "position.currentPrice": {
    zh: "现价",
    en: "Price",
  },
  "position.value": {
    zh: "价值",
    en: "Value",
  },
  "position.pnl": {
    zh: "盈亏",
    en: "P&L",
  },

  // ==================== 状态/提示 ====================
  "status.loading": {
    zh: "加载中...",
    en: "Loading...",
  },
  "status.noData": {
    zh: "暂无数据",
    en: "No Data",
  },
  "status.connected": {
    zh: "已连接",
    en: "Connected",
  },
  "status.disconnected": {
    zh: "已断开",
    en: "Disconnected",
  },
  "status.delayed": {
    zh: "延迟",
    en: "Delayed",
  },

  // ==================== 时间 ====================
  "time.today": {
    zh: "今日",
    en: "Today",
  },
  "time.total": {
    zh: "累计",
    en: "Total",
  },

  // ==================== 单位 ====================
  "unit.usdt": {
    zh: "USDT",
    en: "USDT",
  },
};

// 当前语言 (默认中文)
let currentLang = localStorage.getItem("lang") || "zh";

/**
 * 获取翻译文本
 * @param {string} key - 翻译键
 * @param {object} params - 可选参数 (用于占位符替换)
 * @returns {string}
 */
function t(key, params = {}) {
  const translation = TRANSLATIONS[key];
  if (!translation) {
    console.warn(`Missing translation: ${key}`);
    return key;
  }
  let text = translation[currentLang] || translation["en"] || key;

  // 替换占位符 {name}
  Object.keys(params).forEach((param) => {
    text = text.replace(`{${param}}`, params[param]);
  });

  return text;
}

/**
 * 切换语言
 * @param {string} lang - 'zh' 或 'en'
 */
function setLang(lang) {
  currentLang = lang;
  localStorage.setItem("lang", lang);
  updatePageTexts();
}

/**
 * 更新页面所有带 data-i18n 属性的元素
 */
function updatePageTexts() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });

  // 更新 placeholder
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    el.placeholder = t(key);
  });

  // 更新 title
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    el.title = t(key);
  });
}

// 页面加载时初始化
document.addEventListener("DOMContentLoaded", updatePageTexts);
```

### 2.3 HTML 使用方式

```html
<!-- 基础用法：data-i18n 属性 -->
<a href="/" data-i18n="nav.dashboard">仪表盘</a>
<button data-i18n="action.create">新建</button>

<!-- 占位符 -->
<input type="text" data-i18n-placeholder="strategy.name" />

<!-- Tooltip -->
<span
  class="live-indicator connected"
  data-i18n-title="status.connected"
></span>

<!-- 语言切换按钮 -->
<div class="lang-switcher">
  <button onclick="setLang('zh')" class="btn btn-sm">中文</button>
  <button onclick="setLang('en')" class="btn btn-sm">EN</button>
</div>
```

### 2.4 Jinja2 模板集成

在 `base.html` 中引入翻译脚本：

```html
<head>
  <!-- ... -->
  <script src="/static/js/translations.js"></script>
</head>
```

对于服务端渲染的内容，使用 Jinja2 宏：

```jinja2
{# 定义语言切换宏 #}
{% macro i18n(key) %}
<span data-i18n="{{ key }}">{{ translations.get(key, {}).get(g.lang, key) }}</span>
{% endmacro %}

{# 使用 #}
{{ i18n('nav.dashboard') }}
```

---

## 3. UI 样式规范摘要

完整规范请参阅：[UI_STYLE_GUIDE.md](./UI_STYLE_GUIDE.md)

### 3.1 核心色彩

| 语义      | 颜色值    | 用途               |
| :-------- | :-------- | :----------------- |
| 背景      | `#0f172a` | 页面/卡片背景      |
| 前景      | `#f8fafc` | 主要文字           |
| 主色      | `#3b82f6` | 强调、链接、主按钮 |
| 涨 (Bull) | `#10b981` | 盈利、买入、上涨   |
| 跌 (Bear) | `#ef4444` | 亏损、卖出、下跌   |
| 边框      | `#334155` | 分割线、边框       |
| 次要文字  | `#94a3b8` | 标签、辅助信息     |

### 3.2 按钮样式

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
}

.btn-danger {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: white;
}

.btn-outline {
  background: transparent;
  border: 1px solid #475569;
  color: #cbd5e1;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### 3.3 实时状态指示器

```css
.live-indicator {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 6px;
}

.live-indicator.connected {
  background-color: #10b981;
  animation: pulse-green 2s ease-in-out infinite;
}

.live-indicator.delayed {
  background-color: #f59e0b;
  animation: pulse-yellow 1.5s ease-in-out infinite;
}

.live-indicator.disconnected {
  background-color: #ef4444;
  animation: pulse-red 1s ease-in-out infinite;
}
```

---

## 4. 组件开发规范

### 4.1 开发清单

每个新组件/页面必须完成：

- [ ] 所有文案使用 `data-i18n` 属性
- [ ] 在 `translations.js` 中添加对应翻译
- [ ] 遵循 UI 样式规范（颜色、间距、圆角）
- [ ] 实时数据添加 `.live-indicator`
- [ ] 响应式布局检查 (sm/md/lg)

### 4.2 命名规范

| 类型    | 规范                                      | 示例                           |
| :------ | :---------------------------------------- | :----------------------------- |
| CSS 类  | kebab-case                                | `.stat-card`, `.btn-primary`   |
| JS 函数 | camelCase                                 | `updatePrice()`, `setLang()`   |
| 翻译键  | 模块.功能 (dot notation)                  | `strategy.type.ta`             |
| 文件名  | snake_case (Python) / kebab-case (CSS/JS) | `base.html`, `translations.js` |

---

## 5. 文件结构

```
AutoM2026/
├── web/
│   ├── app.py              # FastAPI 应用
│   ├── templates/          # Jinja2 模板
│   │   ├── base.html       # 基础布局 (含语言切换)
│   │   ├── index.html      # 仪表盘
│   │   ├── strategies.html # 策略列表
│   │   └── ...
│   └── static/             # 静态资源
│       ├── css/
│       │   ├── variables.css   # CSS 变量
│       │   ├── components.css  # 组件样式
│       │   └── utilities.css   # 工具类
│       └── js/
│           └── translations.js # 多语言翻译
├── UI_STYLE_GUIDE.md       # UI 样式详细规范
└── FRONTEND_DEV_GUIDE.md   # 本文档
```

---

## 附录：快速参考

### 常用翻译键

```javascript
t("nav.dashboard"); // 仪表盘 / Dashboard
t("action.create"); // 新建 / Create
t("strategy.status.active"); // 运行中 / Active
t("trade.buy"); // 买入 / Buy
t("position.pnl"); // 盈亏 / P&L
t("status.loading"); // 加载中... / Loading...
```

### 语言切换

```javascript
setLang("en"); // 切换到英文
setLang("zh"); // 切换到中文
```

---

_Last Updated: 2026-01-18_
