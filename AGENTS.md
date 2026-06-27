# 项目上下文

## 技术栈

- **核心**: 纯 HTML 单文件应用（无构建步骤）
- **样式**: Tailwind CSS CDN
- **数据**: Supabase JS SDK CDN（仅查询 `matches` + `predictions` 两张表）
- **路由**: Hash 路由 SPA（`#/`, `#/matches`, `#/matches/:id`, `#/ai/:name`, `#/betting`）
- **主题**: 深色紫色主题（`#1a0a2e` 背景）

## 目录结构

```
├── index.html          # 完整单文件应用（HTML + CSS + JS 全部内联）
├── .coze               # 项目配置（native-static 模板，Node.js server.js 托管）
├── AGENTS.md           # 项目说明（本文件）
└── DESIGN.md           # 设计规范
```

## 数据源

仅查询 Supabase 两张表：
- `matches`：比赛信息（队伍、时间、让球、比分、赔率、状态）
- `predictions`：AI 预测数据（各维度预测值、命中状态、分析、串关数据）

所有统计数据（排行榜、盈亏、命中率）在 JavaScript 中从这两张表实时计算。

## AI 名单

10 个 AI，其中 3 个已退赛：
- **活跃（7个）**: 混元、豆包、DeepSeek、MiniMax、扣子（皮皮）、BetAgent、Grok
- **已退赛（3个）**: Kimi、千问、天工

## 预测维度

5 个维度：
1. `spf` - 胜平负（赔率：win_odds / draw_odds / lose_odds）
2. `handicap` - 让球（赔率：handicap_win_odds / handicap_draw_odds / handicap_lose_odds）
3. `score` - 比分
4. `goals` - 进球数
5. `half_full` - 半全场

## 盈亏计算规则

- 每维度每场投入 1 单位
- 命中收益 = odds - 1（使用对应维度的赔率）
- 未中亏损 = -1
- 对于无赔率维度（score/goals/half_full），使用 SPF 赔率作为参考

## 颜色规范

- 命中 = 绿色（`#10B981`）
- 未中 = 红色（`#EF4444`）
- 盈亏正数 = 绿色
- 盈亏负数 = 红色
- 背景 = 深紫色 `#1a0a2e`
- 卡片 = 稍浅紫色 `#2d1b4e`
