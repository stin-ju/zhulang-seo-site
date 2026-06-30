#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from datetime import datetime
from supabase import create_client

# ================================================================
# 1. 配置
# ================================================================
SUPABASE_URL = "https://br-hip-deer-b1d17b48.supabase2.aidap-global.cn-beijing.volces.com"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjMzNjI0MDA4NjgsInJvbGUiOiJhbm9uIn0.I2p7Z5mHZ0xHa0zQ8sashnT6QYhW2_ilgdPxAuPXwtM"

TABLE_NAME = "matches"
SPORT_FIELD = "sport_type"
TIME_FIELD = "match_time"

# ================================================================
# 2. 连接 Supabase 并查询数据
# ================================================================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

today = datetime.now().date()
today_start = today.strftime('%Y-%m-%d') + ' 00:00:00'
today_end = today.strftime('%Y-%m-%d') + ' 23:59:59'

print(f"📅 查询日期: {today_start} ~ {today_end}")

try:
    football_resp = supabase.table(TABLE_NAME) \
        .select('*') \
        .eq(SPORT_FIELD, 'football') \
        .gte(TIME_FIELD, today_start) \
        .lt(TIME_FIELD, today_end) \
        .execute()

    basketball_resp = supabase.table(TABLE_NAME) \
        .select('*') \
        .eq(SPORT_FIELD, 'basketball') \
        .gte(TIME_FIELD, today_start) \
        .lt(TIME_FIELD, today_end) \
        .execute()

    matches = football_resp.data + basketball_resp.data
    print(f"✅ 共获取 {len(matches)} 场比赛数据")
    print(f"   足球: {len(football_resp.data)} 场")
    print(f"   篮球: {len(basketball_resp.data)} 场")

except Exception as e:
    print(f"❌ 查询失败: {e}")
    exit(1)

# ================================================================
# 3. 生成完整 HTML (使用用户提供的代码模板)
# ================================================================
matches_json = json.dumps(matches, default=str, ensure_ascii=False)

# 读取原始 HTML 模板并注入数据
with open('calculator_template.html', 'r', encoding='utf-8') as f:
    template = f.read()

# 替换数据占位符
html = template.replace('{matches_json}', matches_json)

# ================================================================
# 4. 保存
# ================================================================
with open('calculator.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("✅ calculator.html 已生成，数据已注入！")
