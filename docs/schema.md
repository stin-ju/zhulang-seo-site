# 数据库 Schema 文档

> 生成时间：2026-06-20  
> 数据库：PostgreSQL  
> 用途：AI 竞彩预测排行榜系统

---

## 一、表结构总览

| 表名 | 说明 | 记录数 |
|------|------|--------|
| `matches` | 比赛信息表 | 43 |
| `predictions` | AI 预测记录表 | 10 |

**表关系**：`predictions.match_id` → `matches.id`（多对一）

---

## 二、matches 表（比赛信息）

### 2.1 字段定义

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `id` | TEXT | NOT NULL | - | 比赛编号（主键），如 `周五029` |
| `sport_type` | VARCHAR(20) | YES | `'football'` | 运动类型，目前仅足球 |
| `match_date` | DATE | YES | - | 比赛日期 |
| `match_time` | TEXT | YES | - | 比赛时间，格式 `HH:MM` |
| `status` | VARCHAR(20) | YES | `'待比赛'` | 比赛状态 |
| `home_team` | VARCHAR(100) | YES | - | 主队名称 |
| `away_team` | VARCHAR(100) | YES | - | 客队名称 |
| `home_score` | INTEGER | YES | - | 主队得分（赛后填入） |
| `away_score` | INTEGER | YES | - | 客队得分（赛后填入） |
| `handicap` | INTEGER | YES | `0` | 让球数（正=主队让球，负=客队让球） |
| `odds` | JSONB | YES | - | 赔率数据（JSON） |
| `metadata` | JSONB | YES | - | 扩展元数据（预留） |

### 2.2 status 枚举值

| 值 | 说明 | 数量 |
|----|------|------|
| `待比赛` | 尚未开赛 | 8 |
| `on_sale` | 在售中（体彩状态） | 9 |
| `已确认` | 比赛结束，结果已确认 | 26 |
| `未开赛` | 等待开售 | 0 |

### 2.3 odds 字段格式

```json
{
  "spf": {
    "win": 1.45,      // 主胜赔率
    "draw": 3.83,     // 平局赔率
    "lose": 5.60      // 主负赔率
  },
  "handicap_spf": {
    "win": 2.51,      // 让球主胜赔率
    "draw": 3.25,     // 让球平局赔率
    "lose": 2.36      // 让球主负赔率
  }
}
```

**说明**：
- `spf` = 胜平负（标准玩法）
- `handicap_spf` = 让球胜平负（handicap 值决定让球方向）
- 部分比赛可能缺少 `spf` 赔率（如特殊赛事），此时 `handicap_spf` 仍可用

### 2.4 示例数据

```
id:         周五029
sport_type: football
match_date: 2026-06-20
match_time: 03:00
status:     待比赛
home_team:  美国
away_team:  澳大利亚
handicap:   -1
odds:       {"spf":{"win":1.45,"draw":3.83,"lose":5.6},"handicap_spf":{"win":2.51,"draw":3.25,"lose":2.36}}
```

---

## 三、predictions 表（AI 预测记录）

### 3.1 字段定义

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `id` | BIGINT | NOT NULL | 自增 | 预测记录 ID（主键） |
| `match_id` | TEXT | YES | - | 关联的比赛编号（外键 → matches.id） |
| `ai_name` | TEXT | NOT NULL | - | AI 名称，如 `AI-豆包` |
| `prediction` | JSONB | YES | - | 预测内容（JSON） |
| `hit_status` | JSONB | YES | - | 命中状态（JSON） |
| `analysis` | TEXT | YES | - | AI 分析文本 |
| `is_settled` | BOOLEAN | YES | `false` | 是否已结算 |

### 3.2 prediction 字段格式

```json
{
  "spf": "胜",              // 胜平负预测：胜/平/负
  "handicap_spf": "让胜",   // 让球胜平负预测：让胜/让平/让负
  "score": "3-1",           // 比分预测
  "goals": 4,               // 进球数预测（整数）
  "half_full": "胜胜"       // 半全场预测：胜胜/胜平/胜负/平胜/平平/平负/负胜/负平/负负
}
```

### 3.3 hit_status 字段格式

```json
{
  "spf": true,              // 命中=true，未中=false，null=未结算
  "handicap_spf": null,
  "score": null,
  "goals": null,
  "half_full": null
}
```

**说明**：
- `true` = 命中
- `false` = 未命中
- `null` = 比赛未结束，尚未结算

### 3.4 AI 名单（当前 8 个）

| AI 名称 | 说明 |
|---------|------|
| AI-扣子（皮皮） | Coze 平台 Bot |
| AI-豆包 | 字节跳动豆包 |
| AI-文心 | 百度文心一言 |
| AI-混元 | 腾讯混元 |
| AI-DeepSeek | DeepSeek |
| AI-智谱清言 | 智谱 GLM |
| AI-MiniMax | MiniMax |
| AI-天工 | 天工 AI |

### 3.5 示例数据

```
id:          1
match_id:    周五029
ai_name:     AI-豆包
prediction:  {"spf":"胜","handicap_spf":"让胜","score":"3-1","goals":4,"half_full":"胜胜"}
hit_status:  {"spf":false,"handicap_spf":null,"score":null,"goals":null,"half_full":null}
is_settled:  false
```

---

## 四、预测维度说明

共 5 个预测维度：

| 维度 Key | 名称 | 可选值 | 对应赔率字段 |
|----------|------|--------|-------------|
| `spf` | 胜平负 | 胜 / 平 / 负 | `odds.spf.win` / `odds.spf.draw` / `odds.spf.lose` |
| `handicap_spf` | 让球胜平负 | 让胜 / 让平 / 让负 | `odds.handicap_spf.win` / `odds.handicap_spf.draw` / `odds.handicap_spf.lose` |
| `score` | 比分 | 如 `2-1`、`1-0` | 无独立赔率 |
| `goals` | 进球数 | 整数（0-7+） | 无独立赔率 |
| `half_full` | 半全场 | 胜胜/胜平/.../负负（9种） | 无独立赔率 |

---

## 五、数据统计

### 5.1 比赛统计

| 指标 | 数值 |
|------|------|
| 总比赛数 | 43 |
| 已确认（已结束） | 26 |
| 待比赛 | 8 |
| 在售中 | 9 |
| 日期范围 | 2026-06-12 ~ 2026-07-16 |

### 5.2 预测统计

| 指标 | 数值 |
|------|------|
| 总预测数 | 10 |
| 已结算 | 0 |
| 参与 AI 数 | 8 |

### 5.3 盈亏计算规则

- 每维度每场投入 1 单位
- 命中收益 = `赔率 - 1`（使用对应维度的赔率）
- 未中亏损 = `-1`
- 无赔率维度（score/goals/half_full）使用 SPF 赔率作为参考

---

## 六、索引与约束

```sql
-- 主键
ALTER TABLE matches ADD PRIMARY KEY (id);
ALTER TABLE predictions ADD PRIMARY KEY (id);

-- 外键
ALTER TABLE predictions ADD CONSTRAINT fk_predictions_match 
  FOREIGN KEY (match_id) REFERENCES matches(id);
```

---

## 七、常见查询示例

### 获取某场比赛的所有 AI 预测

```sql
SELECT p.ai_name, p.prediction, p.hit_status, p.is_settled
FROM predictions p
WHERE p.match_id = '周五029';
```

### 获取已确认比赛的完整信息（含赔率）

```sql
SELECT m.id, m.home_team, m.away_team, m.home_score, m.away_score,
       m.odds->'spf'->>'win' AS win_odds,
       m.odds->'spf'->>'draw' AS draw_odds,
       m.odds->'spf'->>'lose' AS lose_odds
FROM matches m
WHERE m.status = '已确认'
ORDER BY m.match_date DESC;
```

### 获取某 AI 的命中统计

```sql
SELECT 
  p.ai_name,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE (p.hit_status->>'spf')::boolean = true) AS spf_hits,
  COUNT(*) FILTER (WHERE (p.hit_status->>'handicap_spf')::boolean = true) AS handicap_hits
FROM predictions p
WHERE p.is_settled = true
GROUP BY p.ai_name;
```
