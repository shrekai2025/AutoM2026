# AutoMoney UI 风格指南与规范

(Archive for AutoM2026)

---

## 1. 核心设计原则 (Design Principles)

| 原则               | 描述                                                 |
| :----------------- | :--------------------------------------------------- |
| **科技与金融融合** | 界面需传达专业、精准和现代感，避免花哨装饰。         |
| **极简主义**       | 减少视觉干扰，聚焦数据和决策操作，信息层级清晰。     |
| **深色模式优先**   | 默认采用深色主题，适应长时间盯盘和金融工具的惯例。   |
| **流畅交互**       | 使用微动画和过渡效果提升用户体验，但不应喧宾夺主。   |
| **数据驱动**       | 核心信息（价格、盈亏、状态）应当在视觉上优先级最高。 |

---

## 2. 技术栈 (Tech Stack)

| 类别         | 技术选型                                                    | 用途                                                  |
| :----------- | :---------------------------------------------------------- | :---------------------------------------------------- |
| **UI 原语**  | [Radix UI](https://www.radix-ui.com/)                       | 无样式、可访问的组件原语 (Dialog, Popover, Select 等) |
| **样式管理** | [class-variance-authority (CVA)](https://cva.style/)        | 管理组件变体和样式                                    |
| **样式合并** | [tailwind-merge](https://github.com/dcastil/tailwind-merge) | 合并 Tailwind 类，避免冲突                            |
| **工具库**   | [clsx](https://github.com/lukeed/clsx)                      | 条件类名拼接                                          |
| **图标库**   | [Lucide React](https://lucide.dev/)                         | 线条风格图标，轻量美观                                |
| **图表库**   | [Recharts](https://recharts.org/)                           | 声明式 React 图表                                     |
| **表单**     | [react-hook-form](https://react-hook-form.com/)             | 高性能表单处理                                        |
| **通知**     | [Sonner](https://sonner.emilkowal.ski/)                     | 轻量级 Toast 通知                                     |

---

## 3. 视觉规范 (Visual Identity)

### 3.1 色彩系统 (Color System)

使用 CSS 变量管理，支持主题切换。所有颜色均使用 `oklch` 色彩空间以获得更好的感知一致性。

#### 核心色板

| 语义名称 | CSS 变量        | 深色模式              | 浅色模式           | 用途                  |
| :------- | :-------------- | :-------------------- | :----------------- | :-------------------- |
| 背景     | `--background`  | `oklch(0.145 0 0)`    | `#ffffff`          | 页面整体背景          |
| 前景色   | `--foreground`  | `oklch(0.985 0 0)`    | `oklch(0.145 0 0)` | 主要文字颜色          |
| 卡片背景 | `--card`        | `oklch(0.145 0 0)`    | `#ffffff`          | 模块、面板背景        |
| 主色     | `--primary`     | `oklch(0.985 0 0)`    | `#030213`          | 强调按钮、重要状态    |
| 次要色   | `--secondary`   | `oklch(0.269 0 0)`    | `oklch(0.95 ...)`  | 次要操作、标签背景    |
| 边框     | `--border`      | `oklch(0.269 0 0)`    | `rgba(0,0,0,0.1)`  | 分割线、边框          |
| 链接     | `--link`        | `oklch(0.7 0.15 220)` | `#3b82f6`          | 可点击文本 (Sky Blue) |
| 破坏性   | `--destructive` | `oklch(0.396 ...)`    | `#d4183d`          | 删除、停止等危险操作  |

#### 金融语义色

| 语义      | 颜色                  | 用途                   |
| :-------- | :-------------------- | :--------------------- |
| 涨 (Bull) | `#34d399` / `#10b981` | 盈利、买入、上涨       |
| 跌 (Bear) | `#f87171` / `#ef4444` | 亏损、卖出、下跌       |
| 中性      | `#64748b` / `#94a3b8` | 未激活、持仓、可用余额 |

#### 图表/策略色

| 名称      | 颜色      | 建议用途         |
| :-------- | :-------- | :--------------- |
| 蓝色系    | `#3B82F6` | 总量、主策略线   |
| 紫色系    | `#8B5CF6` | 辅助策略、套利类 |
| 绿色系    | `#10B981` | HODL、长期策略   |
| 黄/橙色系 | `#F59E0B` | 动量、趋势策略   |

### 3.2 字体排印 (Typography)

- **字体栈**: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`
- **基础字号**: `16px` (`--font-size`)
- **字重**: Normal `400`, Medium `500`, Bold `700`

| 层级    | 样式                         | 用途               |
| :------ | :--------------------------- | :----------------- |
| `h1`    | `text-xl` (Medium)           | 页面标题           |
| `h2`    | `text-lg / text-sm` (Medium) | 卡片/模块标题      |
| `body`  | `text-base` (Normal)         | 正文、表格内容     |
| `label` | `text-xs` (Medium)           | 辅助信息、统计标签 |

### 3.3 间距系统 (Spacing)

基于 Tailwind 的 4px 单位系统：

| Token               | 值      | 常用场景           |
| :------------------ | :------ | :----------------- |
| `gap-0.5`           | 2px     | 图标与文字间距     |
| `gap-1` / `gap-1.5` | 4-6px   | 紧凑元素间距       |
| `gap-2`             | 8px     | 按钮组、标签间距   |
| `gap-3`             | 12px    | 卡片内元素间距     |
| `p-2` / `p-3`       | 8-12px  | 内边距（紧凑卡片） |
| `px-6 py-4`         | 24x16px | 大卡片头部/内容区  |

### 3.4 圆角 (Border Radius)

- **基础**: `--radius: 0.625rem` (10px)
- **变体**:
  - `rounded-md` (6px): 按钮、输入框
  - `rounded-lg` (8px): 卡片内元素
  - `rounded-xl` (12px): 外层卡片、模态框

### 3.5 阴影与特效 (Effects)

#### 玻璃拟态 (Glassmorphism)

```css
.glass-effect {
  background: rgba(255, 255, 255, 0.7); /* 浅色模式 */
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.dark .glass-effect {
  background: rgba(0, 0, 0, 0.3); /* 深色模式 */
  border: 1px solid rgba(255, 255, 255, 0.1);
}
```

#### 渐变光晕 (Gradient Glow)

用于卡片装饰，提升层次感：

```css
/* 卡片背景渐变 */
.card-gradient {
  background: linear-gradient(to bottom right, #0f172a, #1e293b);
}

/* 装饰性光晕 (绝对定位) */
.glow-blue {
  position: absolute;
  top: 0;
  right: 0;
  width: 5rem;
  height: 5rem;
  background: rgba(59, 130, 246, 0.2);
  border-radius: 9999px;
  filter: blur(1.5rem);
}
```

#### 动画库

| 名称         | 效果          | 用途       |
| :----------- | :------------ | :--------- |
| `shimmer`    | 骨架屏闪光    | 加载状态   |
| `float`      | 轻微浮动      | 强调元素   |
| `glow`       | 呼吸发光      | 警报/高亮  |
| `breath`     | 尺寸+阴影呼吸 | 重要状态   |
| `pulse-ring` | 扩散脉冲环    | 通知、提示 |

---

## 4. 组件规范 (Component Guidelines)

### 4.1 按钮 (Button)

使用 CVA 管理变体，基于 Radix `Slot` 支持 `asChild`。

| 变体          | 样式                      | 用途       |
| :------------ | :------------------------ | :--------- |
| `default`     | 实色背景 (`bg-primary`)   | 主操作     |
| `destructive` | 红色系 (`bg-destructive`) | 删除、停止 |
| `outline`     | 透明背景 + 边框           | 次要操作   |
| `secondary`   | 次要色背景                | 辅助操作   |
| `ghost`       | 无背景，Hover 高亮        | 轻量操作   |
| `link`        | 下划线文本                | 链接       |

| 尺寸      | 高度               | 用途         |
| :-------- | :----------------- | :----------- |
| `sm`      | `h-8` (32px)       | 表格行内按钮 |
| `default` | `h-9` (36px)       | 标准按钮     |
| `lg`      | `h-10` (40px)      | 强调按钮     |
| `icon`    | `size-9` (36x36px) | 纯图标按钮   |

**必须状态**: `:hover`, `:active`, `:disabled` (透明度 50%, 禁用点击)。

### 4.2 卡片 (Card)

结构化组件：`Card` → `CardHeader` → `CardTitle` + `CardDescription` → `CardContent` → `CardFooter`。

| 子组件        | 默认样式                    | 说明     |
| :------------ | :-------------------------- | :------- |
| `Card`        | `bg-card border rounded-xl` | 外层容器 |
| `CardHeader`  | `px-6 pt-6 gap-1.5`         | 标题区   |
| `CardTitle`   | `leading-none` (继承 h4)    | 卡片标题 |
| `CardContent` | `px-6 [&:last-child]:pb-6`  | 内容区   |
| `CardFooter`  | `px-6 pb-6`                 | 操作区   |

**装饰技巧** (参考 Dashboard):

- 使用 `relative overflow-hidden` + 绝对定位的 `div` 添加渐变/光晕。
- Hover 时 `scale-[1.02] transition-transform` 微放大。

### 4.3 徽章 (Badge)

| 变体          | 样式                                 | 用途      |
| :------------ | :----------------------------------- | :-------- |
| `default`     | `bg-primary text-primary-foreground` | 默认      |
| `secondary`   | `bg-secondary`                       | 次要信息  |
| `destructive` | `bg-destructive text-white`          | 错误/警告 |
| `outline`     | 透明 + 边框                          | 轻量标签  |

**金融场景扩展**:

```jsx
<Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/50">🔥 Accelerating</Badge>
<Badge className="bg-red-500/20 text-red-400 border-red-500/50">🛡️ Defensive</Badge>
<Badge className="bg-blue-500/20 text-blue-400 border-blue-500/50">⚖️ Holding</Badge>
```

### 4.4 表格 (Table)

| 元素   | 样式                                                       |
| :----- | :--------------------------------------------------------- |
| 表头   | `bg-slate-800/30`, `text-slate-400`, `text-xs`, `border-b` |
| 行     | `border-b border-slate-700`, `hover:bg-slate-800/50`       |
| 单元格 | `px-4 py-3`, 数值右对齐                                    |

### 4.5 图表 (Chart with Recharts)

**Tooltip 样式**:

```jsx
<Tooltip
  contentStyle={{
    backgroundColor: "#1e293b",
    border: "1px solid #334155",
    borderRadius: "6px",
    color: "#fff",
    fontSize: "11px",
  }}
/>
```

**网格与坐标轴**:

```jsx
<CartesianGrid strokeDasharray="3 3" stroke="#334155" />
<XAxis dataKey="date" stroke="#64748b" style={{ fontSize: '11px' }} />
```

---

## 5. 交互规范 (Interaction Patterns)

| 场景           | 规范                                                                    |
| :------------- | :---------------------------------------------------------------------- |
| **即时反馈**   | 所有按钮点击/表单提交需有 Loading 状态 (Spinner 或禁用)。               |
| **危险确认**   | 涉及资金或停止策略的操作，必须弹窗 (`AlertDialog`) 二次确认。           |
| **状态可见**   | 策略运行状态 (Active/Paused/Error) 必须在列表和详情页醒目展示 (Badge)。 |
| **空状态**     | 列表为空时，展示引导性文案和操作按钮。                                  |
| **Hover 效果** | 卡片/表格行 Hover 时应有轻微背景变化或阴影变化。                        |
| **过渡动画**   | 所有状态变化使用 `transition-all` 或 `transition-colors`。              |

### 5.1 数据实时状态反馈 (Live Data Indicator)

当页面存在实时数据（通过 WebSocket 长连接或 API 轮询获取）时，**必须**在 UI 上提供连接状态的视觉反馈。

#### 设计规则

1.  **呼吸灯指示器**: 在实时数据旁放置一个小圆点或脉冲动画，表示数据正在刷新。
2.  **状态颜色**:

| 状态                    | 颜色             | 含义                          |
| :---------------------- | :--------------- | :---------------------------- |
| **正常 (Connected)**    | `#10b981` (绿色) | 连接正常，数据实时更新        |
| **延迟 (Delayed)**      | `#f59e0b` (黄色) | 响应超时或数据陈旧 (>30s)     |
| **断开 (Disconnected)** | `#ef4444` (红色) | 连接失败或长时间无响应 (>60s) |

3.  **适用场景**:
    - 价格显示 (BTC/ETH 实时价格)
    - 策略运行状态
    - 持仓盈亏

#### CSS 实现

```css
/* 呼吸灯基础样式 */
.live-indicator {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 6px;
  vertical-align: middle;
}

/* 正常状态 - 绿色呼吸灯 */
.live-indicator.connected {
  background-color: #10b981;
  animation: pulse-green 2s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
}

@keyframes pulse-green {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
  }
}

/* 延迟状态 - 黄色呼吸灯 */
.live-indicator.delayed {
  background-color: #f59e0b;
  animation: pulse-yellow 1.5s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7);
}

@keyframes pulse-yellow {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(245, 158, 11, 0);
  }
}

/* 断开状态 - 红色呼吸灯 */
.live-indicator.disconnected {
  background-color: #ef4444;
  animation: pulse-red 1s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
}

@keyframes pulse-red {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(239, 68, 68, 0);
  }
}
```

#### HTML 示例

```html
<!-- 价格显示带呼吸灯 -->
<div class="stat-value">
  $43,250.00
  <span class="live-indicator connected" title="实时更新中"></span>
</div>

<!-- 连接异常时 -->
<div class="stat-value text-muted">
  $43,250.00
  <span class="live-indicator disconnected" title="连接已断开"></span>
</div>
```

#### JavaScript 状态管理逻辑

```javascript
// 轮询状态管理
let lastUpdateTime = Date.now();
const DELAY_THRESHOLD = 30000; // 30秒视为延迟
const DISCONNECT_THRESHOLD = 60000; // 60秒视为断开

function updateIndicatorStatus() {
  const indicator = document.querySelector(".live-indicator");
  const elapsed = Date.now() - lastUpdateTime;

  indicator.classList.remove("connected", "delayed", "disconnected");

  if (elapsed < DELAY_THRESHOLD) {
    indicator.classList.add("connected");
  } else if (elapsed < DISCONNECT_THRESHOLD) {
    indicator.classList.add("delayed");
  } else {
    indicator.classList.add("disconnected");
  }
}

// 每次收到数据时更新
function onDataReceived(data) {
  lastUpdateTime = Date.now();
  updateIndicatorStatus();
  // ... 更新 UI
}

// 定时检查连接状态
setInterval(updateIndicatorStatus, 5000);
```

---

## 6. 响应式设计 (Responsive Design)

| 断点 | 值     | 布局调整                              |
| :--- | :----- | :------------------------------------ |
| `sm` | 640px  | 移动端基础                            |
| `md` | 768px  | 平板/小屏笔记本，网格从 1 列变 2-3 列 |
| `lg` | 1024px | 标准桌面                              |
| `xl` | 1280px | 大屏桌面                              |

**常用模式**:

```css
grid-cols-1 md:grid-cols-2 lg:grid-cols-3
```

---

## 7. AutoM2026 应用建议

由于 AutoM2026 使用原生 CSS + Jinja2 模板（无 Tailwind），建议：

1.  **CSS 变量文件**: 创建 `variables.css`，定义上述所有 `--color-*` 变量。
2.  **组件类**: 创建 `components.css`，定义 `.card`, `.btn`, `.btn-primary`, `.badge` 等类。
3.  **工具类**: 创建 `utilities.css`，定义 `.glass-effect`, `.animate-shimmer` 等。
4.  **保持一致性**: 虽然技术栈不同，但视觉语言（色彩、圆角、间距、动画）应与原项目保持一致。

---

_Last Updated: 2026-01-18_
