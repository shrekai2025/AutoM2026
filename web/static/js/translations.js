// web/static/js/translations.js

const TRANSLATIONS = {
  // ==================== 通用 / General ====================
  "app.name": {
    zh: "AutoM2026",
    en: "AutoM2026"
  },
  "app.subtitle": {
    zh: "策略交易系统",
    en: "Algo Trading System"
  },
  
  // ==================== 导航 / Navigation ====================
  "nav.dashboard": {
    zh: "仪表盘",
    en: "Dashboard"
  },
  "nav.strategies": {
    zh: "策略库",
    en: "Strategies"
  },
  "nav.positions": {
    zh: "持仓",
    en: "Holdings"
  },
  "nav.trades": {
    zh: "历史交易",
    en: "History"
  },
  "nav.settings": {
    zh: "设置",
    en: "Settings"
  },
  "nav.market": {
    zh: "指标与行情",
    en: "Indicators"
  },
  "nav.crawler": {
    zh: "数据爬虫",
    en: "Crawler"
  },
  "nav.system": {
    zh: "系统状态",
    en: "System"
  },
  
  // ==================== 系统状态 / System Status ====================
  "system.title": {
    zh: "系统状态",
    en: "System Status"
  },
  "system.subtitle": {
    zh: "外部 API 连接与健康监控",
    en: "External API Connection & Health Monitoring"
  },
  "system.service": {
    zh: "服务名称",
    en: "Service Name"
  },
  "system.type": {
    zh: "类型",
    en: "Type"
  },
  "system.status": {
    zh: "状态",
    en: "Status"
  },
  "system.latency": {
    zh: "延迟",
    en: "Latency"
  },
  "system.last_check": {
    zh: "最近检查",
    en: "Last Check"
  },
  "system.message": {
    zh: "消息",
    en: "Message"
  },
  
  // ==================== 按钮 / Actions ====================
  "action.add": {
    zh: "添加",
    en: "Add"
  },
  "action.create": {
    zh: "新建策略",
    en: "Create New"
  },
  "action.edit": {
    zh: "编辑",
    en: "Edit"
  },
  "action.delete": {
    zh: "删除",
    en: "Delete"
  },
  "action.start": {
    zh: "启动",
    en: "Start"
  },
  "action.stop": {
    zh: "停止",
    en: "Stop"
  },
  "action.pause": {
    zh: "暂停",
    en: "Pause"
  },
  "action.run_once": {
    zh: "立即执行",
    en: "Run Once"
  },
  "action.confirm": {
    zh: "确认",
    en: "Confirm"
  },
  "action.cancel": {
    zh: "取消",
    en: "Cancel"
  },
  "action.save": {
    zh: "保存配置",
    en: "Save Config"
  },
  "action.refresh": {
    zh: "刷新",
    en: "Refresh"
  },
  
  // ==================== 策略 / Strategy ====================
  "strategy.list.title": {
    zh: "策略管理",
    en: "Strategy Management"
  },
  "strategy.new.title": {
    zh: "创建新策略",
    en: "Create New Strategy"
  },
  "strategy.id": {
    zh: "ID",
    en: "ID"
  },
  "strategy.name": {
    zh: "策略名称",
    en: "Name"
  },
  "strategy.type": {
    zh: "类型",
    en: "Type"
  },
  "strategy.symbol": {
    zh: "交易对",
    en: "Symbol"
  },
  "strategy.status": {
    zh: "状态",
    en: "Status"
  },
  "strategy.schedule": {
    zh: "调度周期",
    en: "Schedule"
  },
  "strategy.actions": {
    zh: "操作",
    en: "Actions"
  },
  
  // Strategy Types
  "strategy.type.TAStrategy": {
    zh: "技术指标策略",
    en: "Thinking TA"
  },
  "strategy.type.MacroStrategy": {
    zh: "宏观趋势策略",
    en: "Macro Trend"
  },
  "strategy.type.GridStrategy": {
    zh: "网格交易策略",
    en: "Grid Trading"
  },
  "strategy.type.macro": {
    zh: "宏观趋势策略",
    en: "Macro Trend"
  },
  "strategy.lastSignal": {
    en: "Last Signal"
  },
  "strategy.detail.logs": {
    zh: "执行日志",
    en: "Execution Logs"
  },
  "strategy.detail.process": {
    zh: "执行详情",
    en: "Process Details"
  },
  "strategy.totalTrades": {
      zh: "总交易次数",
      en: "Total Trades"
  },
  "strategy.runNow": {
      zh: "立即运行",
      en: "Run Now"
  },
  "strategy.viewDetails": {
      zh: "查看详情",
      en: "View Details"
  },
  "strategy.process.step": {
      zh: "步骤",
      en: "Step"
  },
  "strategy.process.output": {
      zh: "输出",
      en: "Output"
  },
  "strategy.process.details": {
      zh: "详细信息",
      en: "Details"
  },
  "strategy.noLogs": {
      zh: "暂无执行记录",
      en: "No execution logs found"
  },
  "strategy.noDetails": {
      zh: "该次执行无详细日志",
      en: "No details available for this execution"
  },
  "strategy.score": {
      zh: "评分",
      en: "Score"
  },
  "action.close": {
      zh: "关闭",
      en: "Close"
  },
  
  // Grid Strategy Specific
  "strategy.grid.status": {
      zh: "网格状态",
      en: "Grid Status"
  },
  "strategy.grid.level": {
      zh: "当前层级",
      en: "Grid Level"
  },
  "strategy.grid.arbitrage": {
      zh: "套利统计",
      en: "Arbitrage Stats"
  },
  "market.price": {
      zh: "当前价格",
      en: "Current Price"
  },
  
  // Status
  "status.active": {
    zh: "运行中",
    en: "Active"
  },
  "status.paused": {
    zh: "已暂停",
    en: "Paused"
  },
  "status.stopped": {
    zh: "已停止",
    en: "Stopped"
  },
  "status.error": {
    zh: "异常",
    en: "Error"
  },
  
  // ==================== 持仓 / Positions ====================
  "position.title": {
    zh: "当前持仓",
    en: "Current Holdings"
  },
  "position.symbol": {
    zh: "币种",
    en: "Symbol"
  },
  "position.amount": {
    zh: "持仓数量",
    en: "Amount"
  },
  "position.avg_cost": {
    zh: "平均成本",
    en: "Avg Price"
  },
  "position.current_price": {
    zh: "当前价格",
    en: "Mark Price"
  },
  "position.market_value": {
    zh: "持仓价值",
    en: "Value"
  },
  "position.unrealized_pnl": {
    zh: "未实现盈亏",
    en: "Unrealized P&L"
  },
  
  "position.unrealized_pnl": {
    zh: "未实现盈亏",
    en: "Unrealized P&L"
  },
  
  // ==================== 行情 / Market ====================
  "market.title": {
    zh: "行情监控",
    en: "Market Watch"
  },
  "market.symbol": {
    zh: "标的",
    en: "Symbol"
  },
  "market.price": {
    zh: "当前价格",
    en: "Price"
  },
  "market.change_24h": {
    zh: "24h 涨跌幅",
    en: "24h Change"
  },
  "market.high_24h": {
    zh: "24h 最高",
    en: "24h High"
  },
  "market.low_24h": {
    zh: "24h 最低",
    en: "24h Low"
  },
  "market.volume_24h": {
    zh: "24h 成交量",
    en: "24h Volume"
  },
  "status.unavailable": {
    zh: "暂无数据",
    en: "No Data"
  },
  "market.tab.indicators": {
    zh: "核心指标",
    en: "Indicators"
  },
  "market.tab.price": {
    zh: "价格清单",
    en: "Price List"
  },
  
  // ==================== 交易记录 / Trades ====================
  "trade.title": {
    zh: "交易历史",
    en: "Trade History"
  },
  "trade.time": {
    zh: "时间",
    en: "Time"
  },
  "trade.side": {
    zh: "方向",
    en: "Side"
  },
  "trade.price": {
    zh: "成交价",
    en: "Price"
  },
  "trade.amount": {
    zh: "数量",
    en: "Amount"
  },
  "trade.value": {
    zh: "金额",
    en: "Total"
  },
  "trade.reason": {
    zh: "理由",
    en: "Reason"
  },
  
  "side.buy": {
    zh: "买入",
    en: "BUY"
  },
  "side.sell": {
    zh: "卖出",
    en: "SELL"
  },
  "side.hold": {
    zh: "持有",
    en: "HOLD"
  },
  
  // ==================== 仪表盘 / Dashboard ====================
  "dashboard.welcome": {
    zh: "欢迎回来",
    en: "Welcome Back"
  },
  "dashboard.total_assets": {
    zh: "总资产估值",
    en: "Total Assets"
  },
  "dashboard.total_pnl": {
    zh: "累计盈亏",
    en: "Total P&L"
  },
  "dashboard.active_strategies": {
    zh: "活跃策略",
    en: "Active Strategies"
  },
  "dashboard.recent_activity": {
    zh: "最近活动",
    en: "Recent Activity"
  },
  
  // ==================== 通用提示 ====================
  "msg.confirm_delete": {
    zh: "确定要删除这个策略吗？",
    en: "Are you sure you want to delete this strategy?"
  },
  "msg.loading": {
    zh: "加载中...",
    en: "Loading..."
  },
  
  // ==================== 日志详情 / Log Details ====================
  "log.timestamp": {
    zh: "时间",
    en: "Time"
  },
  "log.type.api_call": {
    zh: "API调用",
    en: "API Call"
  },
  "log.type.llm_call": {
    zh: "LLM分析",
    en: "LLM Analysis"
  },
  "log.type.calculation": {
    zh: "计算",
    en: "Calculation"
  },
  "log.llm.prompt": {
    zh: "输入提示",
    en: "Prompt"
  },
  "log.llm.response": {
    zh: "返回内容",
    en: "Response"
  },
  "log.llm.tokens": {
    zh: "Token用量",
    en: "Token Usage"
  },
  "log.llm.raw": {
    zh: "原始JSON",
    en: "Raw JSON"
  },
  "log.expandAll": {
    zh: "展开全部",
    en: "Expand All"
  },
  "log.collapseAll": {
    zh: "收起全部",
    en: "Collapse All"
  },
  "log.showMore": {
    zh: "查看完整内容",
    en: "Show Full Content"
  },
  "log.keyFactors": {
    zh: "关键因素",
    en: "Key Factors"
  },
  "log.riskAssessment": {
    zh: "风险评估",
    en: "Risk Assessment"
  },
  
  "time.minutes": {
    zh: "分钟",
    en: "min"
  },
  "time.hours": {
    zh: "小时",
    en: "hrs"
  }
};

// State
let currentLang = localStorage.getItem('autom2026_lang') || 'zh';
const observer = new MutationObserver(handleMutations);

/**
 * Get translation
 */
window.t = function(key, params = {}) {
  const item = TRANSLATIONS[key];
  if (!item) return key;
  
  let text = item[currentLang] || item['en'] || key;
  
  Object.keys(params).forEach(k => {
    text = text.replace(`{${k}}`, params[k]);
  });
  
  return text;
};

/**
 * Set Language
 */
function setLang(lang) {
  if (currentLang === lang) return;
  currentLang = lang;
  localStorage.setItem('autom2026_lang', lang);
  updatePage();
  
  // Update buttons state
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
}

/**
 * Update all elements with data-i18n
 */
function updatePage() {
  // Disconnect observer to prevent infinite loop (updating text triggers mutation)
  observer.disconnect();

  // 1. Text content
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (key) el.textContent = t(key);
  });
  
  // 2. Placeholders
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) el.placeholder = t(key);
  });
  
  // 3. Titles
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    if (key) el.title = t(key);
  });

  // 4. Update HTML lang attribute
  document.documentElement.lang = currentLang;

  // Reconnect observer
  observer.observe(document.body, { childList: true, subtree: true });
}

/**
 * Handle DOM changes to automatically translate new elements
 */
function handleMutations(mutations) {
  let shouldUpdate = false;
  mutations.forEach(mutation => {
    if (mutation.addedNodes.length > 0) {
      shouldUpdate = true;
    }
  });
  if (shouldUpdate) updatePage();
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  // Initial update
  updatePage();
  
  // Set initial button state
  document.querySelectorAll('.lang-btn').forEach(btn => {
    if (btn.dataset.lang === currentLang) {
      btn.classList.add('active');
    }
    btn.addEventListener('click', (e) => {
      // Use currentTarget to ensure we get the data attribute from button, even if clicking child
      const target = e.currentTarget;
      if (target && target.dataset.lang) {
        setLang(target.dataset.lang);
      }
    });
  });

  // Start observing
  observer.observe(document.body, { childList: true, subtree: true });
});

// Export basics for console usage
window.i18n = { setLang, t };
