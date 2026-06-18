# 项目上下文

## 技术栈

- **核心**: Vite 7, TypeScript, Express, React 19
- **路由**: react-router-dom v7（BrowserRouter，由 Express SPA fallback 兜底）
- **UI**: Tailwind CSS（自定义深色调色板：`night/deep/elevated/turf/gold/miss`）

## 目录结构

```
├── scripts/                # 构建与启动脚本
│   ├── build.sh            # 构建脚本
│   ├── dev.sh              # 开发环境启动脚本
│   ├── prepare.sh          # 预处理脚本
│   └── start.sh            # 生产环境启动脚本
├── server/                 # 服务端逻辑
│   ├── routes/             # API 路由（保留示例，未在前端使用）
│   ├── server.ts           # Express 服务入口
│   └── vite.ts             # Vite 中间件集成 + 生产 SPA fallback
├── src/                    # 前端源码（React SPA）
│   ├── components/
│   │   └── Layout.tsx      # 全局导航 + 页脚
│   ├── data/data.json      # 28 场比赛 × 7 个 AI 的预测数据
│   ├── lib/data.ts         # 数据类型定义、命中率聚合、查询工具
│   ├── pages/
│   │   ├── LeaderboardPage.tsx   # 首页 - AI 排行榜
│   │   ├── MatchListPage.tsx     # 比赛列表（按时间倒序）
│   │   ├── MatchDetailPage.tsx   # 比赛详情 - 7 AI 命中矩阵
│   │   ├── AiListPage.tsx        # AI 选手列表
│   │   ├── AiDetailPage.tsx      # AI 个人页 - 各维度命中率 + 命中条带
│   │   └── NotFoundPage.tsx
│   ├── App.tsx             # 路由配置
│   ├── index.css           # 全局样式 + Tailwind 入口
│   └── index.tsx           # React 客户端入口
├── DESIGN.md               # 设计风格规范
├── index.html              # 入口 HTML
├── package.json            # 项目依赖管理
├── tsconfig.json           # TypeScript 配置（jsx: react-jsx, moduleResolution: bundler）
└── vite.config.ts          # Vite 配置（含 @vitejs/plugin-react v4）
```

## 包管理规范

**仅允许使用 pnpm** 作为包管理器，**严禁使用 npm 或 yarn**。
**常用命令**：
- 安装依赖：`pnpm add <package>`
- 安装开发依赖：`pnpm add -D <package>`
- 安装所有依赖：`pnpm install`
- 移除依赖：`pnpm remove <package>`

## 开发规范

- 使用 Tailwind CSS 进行样式开发
- React 组件函数省略显式返回类型注解；若需要类型，使用 `React.JSX.Element`（React 19 不再暴露全局 `JSX` 命名空间）
- 数据来源仅 `src/data/data.json`，所有聚合（命中率、排名）通过 `src/lib/data.ts` 计算，前端组件直接消费导出的 `aiSummaries / matches` 等
- AI 命中维度只有 4 项：让球胜平负 / 全场比分 / 总进球 / 半全场（"胜平负 spf" 列在表格中作为信息展示但不计入命中率）
- 路由使用 `BrowserRouter`，路径中的 AI 名称含括号/中文，必须用 `encodeURIComponent` / `decodeURIComponent` 处理

### 编码规范

- 默认按 TypeScript `strict` 心智写代码；优先复用当前作用域已声明的变量、函数、类型和导入，禁止引用未声明标识符或拼错变量名。
- 禁止隐式 `any` 和 `as any`；函数参数、返回值、解构项、事件对象、Express `req`/`res`、`catch` 错误在使用前应有明确类型或先完成类型收窄，并清理未使用的变量和导入。
