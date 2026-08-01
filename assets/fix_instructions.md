# 数据管道 Bug 修复指令

请严格按照以下修改，不要做任何额外修改，不要重新组织代码结构。

## 文件1: supabase_db.py — 修改 upsert_prediction 函数

### INSERT 语句：去掉 spf, goals, score, half_full, handicap_spf 这5列及对应参数

原代码：
```
INSERT INTO predictions (match_id, ai_name, prediction, analysis, is_settled,
    sport_type, spf_pred, goals_pred, score_pred, half_full_pred, handicap_spf_pred,
    win_loss, handicap_win_loss, total_points, score_diff_range, half_win_loss,
    spf, goals, score, half_full, handicap_spf,
    match_date)
VALUES (%s, %s, %s, %s, FALSE, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s)
```
参数：`(match_id, ai_name, json, analysis, sport_type, spf_pred, goals_pred, score_pred, half_full_pred, handicap_spf_pred, win_loss, handicap_win_loss, total_points, score_diff_range, half_win_loss, spf_pred, goals_pred, score_pred, half_full_pred, handicap_spf_pred, match_date)`

改为（删除最后5列及对应参数）：
```
INSERT INTO predictions (match_id, ai_name, prediction, analysis, is_settled,
    sport_type, spf_pred, goals_pred, score_pred, half_full_pred, handicap_spf_pred,
    win_loss, handicap_win_loss, total_points, score_diff_range, half_win_loss,
    match_date)
VALUES (%s, %s, %s, %s, FALSE, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s)
```
参数：`(match_id, ai_name, json, analysis, sport_type, spf_pred, goals_pred, score_pred, half_full_pred, handicap_spf_pred, win_loss, handicap_win_loss, total_points, score_diff_range, half_win_loss, match_date)`

### UPDATE 语句：同理去掉 spf, goals, score, half_full, handicap_spf

原代码 SET 中有 `spf = %s, goals = %s, score = %s, half_full = %s, handicap_spf = %s`，删除它们及对应参数。

## 文件2: auto_settle.py

### settle_football 函数
1. 把开头的 `return None, None` 改为 `return None, None, None`
2. 在 return 之前，新增构建 actual 字典的代码：
```python
    actual = {}
    if home_score > away_score:
        actual["spf"] = "胜"
    elif home_score == away_score:
        actual["spf"] = "平"
    else:
        actual["spf"] = "负"
    if handicap is not None:
        adjusted = home_score + float(handicap)
        if adjusted > away_score:
            actual["handicap_spf"] = "让胜"
        elif adjusted == away_score:
            actual["handicap_spf"] = "让平"
        else:
            actual["handicap_spf"] = "让负"
    actual["goals"] = home_score + away_score
    actual["score"] = f"{home_score}-{away_score}"
    half_home = md.get("half_home_score")
    half_away = md.get("half_away_score")
    if half_home is not None and half_away is not None:
        half_home = int(half_home)
        half_away = int(half_away)
        half_r = "胜" if half_home > half_away else ("平" if half_home == half_away else "负")
        full_r = "胜" if home_score > away_score else ("平" if home_score == away_score else "负")
        actual["half_full"] = f"{half_r}{full_r}"
```
3. 将 return 改为 `return (hit if hit else None), hit_cols, actual`

### settle_basketball 函数
同理：
1. 把开头的 `return None, None` 改为 `return None, None, None`
2. 在 return 之前，新增构建 actual 字典：
```python
    actual = {}
    actual["win_loss"] = "胜" if home_score > away_score else "负"
    if handicap is not None:
        adjusted = home_score + float(handicap)
        actual["handicap_win_loss"] = "让胜" if adjusted > away_score else "让负"
    total = home_score + away_score
    tp_line = md.get("total_points_line")
    if tp_line is None:
        odds = md.get("odds", {}) or {}
        tp_line = odds.get("total_points_line") or odds.get("total_line")
    if tp_line is not None:
        tp_line = float(tp_line)
        actual["total_points"] = "大" if total > tp_line else "小"
    diff = abs(home_score - away_score)
    winner_side = "主" if home_score > away_score else "客"
    suffix = "胜" if winner_side == "主" else "负"
    if diff <= 5:
        actual["score_diff_range"] = f"{winner_side}1-5{suffix}"
    elif diff <= 10:
        actual["score_diff_range"] = f"{winner_side}6-10{suffix}"
    elif diff <= 15:
        actual["score_diff_range"] = f"{winner_side}11-15{suffix}"
    elif diff <= 20:
        actual["score_diff_range"] = f"{winner_side}16-20{suffix}"
    elif diff <= 25:
        actual["score_diff_range"] = f"{winner_side}21-25{suffix}"
    else:
        actual["score_diff_range"] = f"{winner_side}26+{suffix}"
    half_home = md.get("half_home_score")
    half_away = md.get("half_away_score")
    if half_home is not None and half_away is not None:
        actual["half_win_loss"] = "胜" if int(half_home) > int(half_away) else "负"
```
3. 将 return 改为 `return (hit if hit else None), hit_cols, actual`

### 主循环 main() 修改
1. 将 `hit_dict, hit_cols = settle_football(row)` 改为 `hit_dict, hit_cols, actual = settle_football(row)`
2. 将 `hit_dict, hit_cols = settle_basketball(row)` 改为 `hit_dict, hit_cols, actual = settle_basketball(row)`
3. 在 UPDATE predictions 的 SET 子句构建处，在 hit_cols 循环之前加入：
```python
        if actual:
            for col, val in actual.items():
                set_clauses.append(f"{col} = %s")
                params.append(val)
```

## 验证
修改完后运行：
```bash
python -c "import supabase_db; print('supabase_db OK')"
python -c "import auto_settle; print('auto_settle OK')"
```
