# 预测字段映射表 (FIELD_MAPPING.md)

> **重要提示**：
> 1. ⚠️ 标记的字段是前端和后端命名不一致的，需要特别注意
> 2. 每次修改代码前必须查此表确认字段名
> 3. 新增字段时必须更新此表

---

## 1. predictions 表 - 足球预测

### 1.1 预测字段

| 维度 | 前端字段名 | prediction JSON字段 | 数据库列名 | API返回字段 | 备注 |
|:-----|:-----------|:-------------------|:-----------|:------------|:-----|
| 胜平负 | `spf` | `spf` | `spf_pred` | `spf` | ✅ 一致 |
| 让球 | `handicap_spf` | `handicap_spf` | `handicap_spf_pred` | `handicap_spf` | ✅ 一致 |
| 比分 | `score` | `score` | `score_pred` | `score` | ✅ 一致 |
| 进球数 | `goals` | `goals` | `goals_pred` | `goals` | ✅ 一致 |
| 半全场 | `half_full` | `half_full` | `half_full_pred` | `half_full` | ✅ 一致 |

### 1.2 命中字段

| 维度 | 数据库列名 | 说明 |
|:-----|:-----------|:-----|
| 胜平负 | `spf_hit` | boolean |
| 让球 | `handicap_spf_hit` | boolean |
| 比分 | `score_hit` | boolean |
| 进球数 | `goals_hit` | boolean |
| 半全场 | `half_full_hit` | boolean |

### 1.3 前端配置（index.js 第410-414行）

```javascript
const fieldConfig = {
    col1: { key: 'win_loss', fallbackKey: 'spf', hitKey: 'spf', label: '胜平负' },
    col2: { key: 'handicap_win_loss', fallbackKey: 'handicap_spf', hitKey: 'handicap_spf', label: '让球' },
    col3: { key: 'score', hitKey: 'score', label: '比分' },
    col4: { key: 'goals', hitKey: 'goals', label: '进球数' },
    col5: { key: 'half_full', hitKey: 'half_full', label: '半全场' }
};
```

---

## 2. predictions 表 - 篮球预测

### 2.1 预测字段

| 维度 | 前端字段名 | prediction JSON字段 | 数据库列名 | API返回字段 | 备注 |
|:-----|:-----------|:-------------------|:-----------|:------------|:-----|
| 胜负 | `win_loss` | `win_loss` | `win_loss_pred` | `win_loss` | ✅ 一致 |
| 让分 | `handicap_win_loss` | ⚠️ `handicap_result` | `handicap_win_loss_pred` | `handicap_win_loss` | **不匹配** |
| 胜分差 | `score_diff_range` | `score_diff_range` | `score_diff_range_pred` | `score_diff_range` | ✅ 一致 |
| 总分 | `total_points` | `total_points` | `total_points_pred` | `total_points` | ✅ 一致 |
| 半场胜负 | `half_win_loss` | `half_win_loss` | `half_win_loss_pred` | `half_win_loss` | ✅ 一致 |

### 2.2 命中字段

| 维度 | 数据库列名 | 说明 |
|:-----|:-----------|:-----|
| 胜负 | `win_loss_hit` | boolean（如果存在） |
| 让分 | `handicap_win_loss_hit` | boolean（如果存在） |
| 胜分差 | `score_diff_range_hit` | boolean（如果存在） |
| 总分 | `total_points_hit` | boolean（如果存在） |

### 2.3 前端配置（index.js 第398-407行）

```javascript
const fieldConfig = {
    col1: { key: 'win_loss', hitKey: 'win_loss', label: '胜负' },
    col2: { key: 'handicap_win_loss', hitKey: 'handicap_win_loss', label: '让分' },
    col3: { key: 'score_diff_range', hitKey: 'score_diff_range', label: '胜分差',
            format: (p) => `${p.score_diff_range || '-'}分` },
    col4: { key: 'total_points', hitKey: 'total_points', label: '总分' }
};
```

### 2.4 ⚠️ 已知不匹配问题

**让分字段**：
- 后端写入（multi_ai_predict.py 第1425行）：`prediction.handicap_result`
- 前端读取（index.js 第399行）：`pred.handicap_win_loss`
- 数据库列名：`handicap_win_loss_pred`

**解决方案**：index.js 第417-424行的 `getPredValue` 函数已添加 `_pred` 后缀 fallback：
```javascript
function getPredValue(pred, key, fallbackKey) {
    const prediction = pred.prediction || {};
    return prediction[key] 
        || prediction[key + '_pred']  // _pred 后缀 fallback
        || (fallbackKey && prediction[fallbackKey]) 
        || '-';
}
```

---

## 3. traditional_predictions 表 - 传统彩预测

### 3.1 表结构

| 字段名 | 类型 | 说明 |
|:-------|:-----|:-----|
| `id` | integer | 主键 |
| `game_type` | varchar | 玩法类型：胜负彩/任9/半全场/进球彩 |
| `ai_name` | varchar | AI名称 |
| `predictions` | jsonb | 预测数据数组 |
| `ren9` | jsonb | 任9推荐场次号列表 |
| `confidence` | varchar | 置信度 |
| `created_at` | timestamp | 创建时间 |
| `matches_info` | jsonb | 比赛信息快照 |
| `issue` | varchar | 期号 |

### 3.2 predictions JSON 结构

```json
[
  {
    "match": "01",
    "home_team": "主队",
    "away_team": "客队",
    "prediction": "3/1/0",
    "confidence": "高",
    "analysis": "分析文本"
  }
]
```

### 3.3 ren9 JSON 结构

```json
["01", "02", "03", "04", "05", "06", "07", "08", "09"]
```

### 3.4 前端字段（CT/ct.html）

| 维度 | 字段名 | 说明 |
|:-----|:-------|:-----|
| 场次 | `match` | 场次号（01-14） |
| 主队 | `home_team` | 主队名称 |
| 客队 | `away_team` | 客队名称 |
| 预测 | `prediction` | 预测结果 |
| 置信度 | `confidence` | 高/中/低 |
| 分析 | `analysis` | 分析文本 |

---

## 4. match_intelligence 表 - 情报库

### 4.1 表结构

| 字段名 | 类型 | 说明 |
|:-------|:-----|:-----|
| `match_id` | varchar | 比赛ID（主键），格式：CT26105_01 |
| `home_team` | varchar | 主队 |
| `away_team` | varchar | 客队 |
| `match_time` | timestamp | 比赛时间 |
| `league` | varchar | 联赛 |
| `basic_data` | jsonb | 基础数据（阵容、伤停、交锋） |
| `expert_opinions` | jsonb | 专家观点 |
| `media_analysis` | jsonb | 媒体分析 |
| `market_sentiment` | jsonb | 市场情绪 |
| `summary` | text | 情报总结 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

### 4.2 JSON 字段结构

```json
{
  "basic_data": {
    "injuries": "伤停信息",
    "lineup": "预计阵容",
    "head_to_head": "交锋记录"
  },
  "expert_opinions": {
    "opinions": "专家观点汇总"
  },
  "media_analysis": {
    "analysis": "媒体分析"
  },
  "market_sentiment": {
    "odds": "赔率变化",
    "sentiment": "市场情绪"
  },
  "summary": "情报总结，100字以内"
}
```

---

## 5. 数据流总结

### 5.1 竞彩预测数据流

```
AI 响应
    ↓
multi_ai_predict.py (parse_*_prediction)
    ↓
┌─────────────────────────────────────┐
│ prediction JSON: { spf: "3", ... }  │
│ 数据库列: spf_pred = "3"            │
└─────────────────────────────────────┘
    ↓
server.js API 规范化
    ↓
┌─────────────────────────────────────┐
│ 返回: { spf: "3", spf_pred: "3" }   │
└─────────────────────────────────────┘
    ↓
index.js 前端渲染
    ↓
getPredValue(pred, 'spf')
    ↓
显示: "3"
```

### 5.2 传统彩预测数据流

```
AI 响应
    ↓
traditional_lottery_predict.py
    ↓
┌─────────────────────────────────────┐
│ predictions JSON: [{ match: "01", prediction: "3" }] │
│ ren9 JSON: ["01", "02", ...]        │
└─────────────────────────────────────┘
    ↓
CT/server_traditional.js API
    ↓
┌─────────────────────────────────────┐
│ 返回: { predictions: [...], ren9: [...] } │
└─────────────────────────────────────┘
    ↓
CT/ct.html 前端渲染
```

---

## 6. 修改记录

| 日期 | 修改内容 | 相关文件 |
|:-----|:---------|:---------|
| 2026-08-16 | 添加 `_pred` 后缀 fallback | index.js |
| 2026-08-16 | 创建此字段映射表 | FIELD_MAPPING.md |

---

## 7. 待修复问题

| 问题 | 优先级 | 说明 |
|:-----|:-------|:-----|
| 篮球让分字段命名不一致 | 中 | 后端用 `handicap_result`，前端期望 `handicap_win_loss` |
| 建议统一为 `handicap_win_loss` | 低 | 需要同时修改 multi_ai_predict.py 和 index.js |
