# 项目上下文

## 技术栈

- **后端**: Node.js 原生 HTTP 服务器 (server.js) + Python 脚本
- **前端**: 多页面 HTML 应用，Tailwind CSS CDN，Hash 路由 SPA
- **数据库**: PostgreSQL（matches + predictions 两张表，metadata/prediction 为 JSONB）
- **传统彩**: 独立服务 (CT/server_traditional.js, 端口 5001)
- **主题**: 深色紫色主题（`#1a0a2e` 背景）

## 目录结构

```
├── server.js              # 主服务（端口 5000），API 路由 + 静态文件 + 定时任务
├── index.html             # 入口跳转页（→ /ix.html）
├── .coze                  # 项目配置
├── AGENTS.md              # 本文件
├── DESIGN.md              # 设计规范
├── start-all.sh           # 一键启动脚本
├── package.json           # Node.js 依赖
│
├── JC/                    # 核心业务代码
│   ├── api.js             # 公共 API 模块（数据库查询、数据规范化）
│   ├── api.v20260727a.js  # api.js 副本（兼容旧 import 路径）
│   ├── index.js           # 首页逻辑
│   ├── calculator.js      # 计算器逻辑
│   ├── briefs.js          # 简报逻辑
│   ├── styles.css         # 全局样式
│   ├── ix.html            # 主页面
│   ├── ct.html → CT/ct.html  # 传统彩页面（通过 URL 别名访问）
│   ├── auto_settle.py     # 自动结算脚本（支持 --match-id 参数）
│   ├── traditional_lottery_predict.py  # 传统彩预测脚本
│   ├── discover_matches.py  # 赛程发现脚本
│   ├── generate_brief.py    # 简报生成脚本
│   ├── auto_predict.py      # 自动预测脚本
│   ├── titan007_client.py   # titan007 数据客户端
│   ├── sporttery_client.py  # 竞彩官网客户端
│   ├── odds_source_*.py     # 赔率数据源（500/okooo/zgzcw）
│   ├── supabase_db.py       # Supabase 数据库工具
│   └── requirements.txt     # Python 依赖
│
├── CT/                    # 传统彩独立服务
│   ├── server_traditional.js  # 传统彩服务（端口 5001）
│   └── ct.html              # 传统彩前端页面
│
└── public/                # 静态资源
```

## URL 别名

server.js 中配置了 URL 别名，将根路径请求映射到 JC/ 目录：
- `/api.js` → `/JC/api.js`
- `/ix.html` → `/JC/ix.html`
- `/ct.html` → `/CT/ct.html`
- `/styles.css` → `/JC/styles.css`
- 等等

## 数据源

PostgreSQL 两张表：
- `matches`：比赛信息（id, sport_type, home_team, away_team, metadata JSONB, status）
  - 比分存储在 metadata 中：`metadata->>'home_score'`, `metadata->>'away_score'`
  - 赔率存储在 metadata 中：`metadata->>'win_odds'` 等
- `predictions`：AI 预测数据（prediction JSONB, hit_status JSONB, is_settled）

## API 端点

### 公共 API
- `GET /api/matches` - 比赛列表
- `GET /api/matches/:id` - 比赛详情
- `GET /api/predictions` - 预测列表
- `GET /api/ai_stats` - AI 统计
- `GET /api/betting_daily` - 每日投注统计
- `GET /api/betting_summary` - 投注汇总
- `GET /api/briefs` - 简报列表
- `GET /api/date-tabs` - 日期标签
- `GET /api/football-recent` - 近期足球
- `GET /api/football-history` - 足球历史
- `GET /api/parlay-latest` - 最新串关
- `GET /api/parlay-history` - 串关历史

### 管理 API
- `POST /api/admin/discover` - 触发赛程发现
- `POST /api/admin/predict` - 触发预测
- `POST /api/admin/settle` - 触发结算
- `POST /api/admin/report` - 触发报告
- `POST /api/admin/commentary` - 触发解说生成
- `POST /api/admin/briefing` - 触发简报生成

### 传统彩 API（端口 5001）
- `GET /api/traditional-lottery/predict` - 传统彩预测
- `GET /api/traditional-lottery/latest` - 最新传统彩
- `GET /api/traditional-lottery/fetch` - 抓取传统彩数据

## Python 脚本

### auto_settle.py
自动结算脚本，支持两种调用方式：
- `python3 auto_settle.py` - 结算所有未结算比赛
- `python3 auto_settle.py --match-id <id>` - 结算指定比赛

### traditional_lottery_predict.py
传统彩预测脚本，支持胜负彩、半全场、进球彩、任9。

## AI 名单

10 个 AI，其中 3 个已退赛：
- **活跃（7个）**: 混元、豆包、DeepSeek、MiniMax、扣子（皮皮）、BetAgent、Grok
- **已退赛（3个）**: Kimi、千问、天工

## 预测维度

5 个维度：
1. `spf` - 胜平负
2. `handicap` - 让球
3. `score` - 比分
4. `goals` - 进球数
5. `half_full` - 半全场

## 服务启动

```bash
# 主服务（端口 5000）
node server.js

# 传统彩服务（端口 5001）
node CT/server_traditional.js

# 一键启动
bash start-all.sh
```
