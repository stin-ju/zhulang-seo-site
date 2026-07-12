#!/usr/bin/env python3
"""
sporttery_client.py - 体彩API客户端
提供与 sporttery.cn 的交互能力：获取比赛列表、赔率数据等。
（等待上传实际脚本）
"""
import os
import json
import requests

BASE_URL = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"

def get_matches(pool_code="HAD,HHAD"):
    """获取当前在售比赛列表及赔率"""
    params = {"poolCode": pool_code, "channel": "c"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.sporttery.cn/",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.sporttery.cn"
    }
    resp = requests.get(BASE_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise Exception(f"API error: {data.get('errorMessage')}")
    return data.get("value", {}).get("matchInfoList", [])


def parse_match(item):
    """解析单场比赛数据"""
    had = item.get("had", {})
    hhad = item.get("hhad", {})
    return {
        "id": item.get("matchNumStr", ""),
        "teams": f"{item.get('homeTeamAbbName', '')} VS {item.get('awayTeamAbbName', '')}",
        "match_time": f"{item.get('matchDate', '')} {item.get('matchTime', '')[:5]}",
        "league": item.get("leagueAbbName", ""),
        "handicap": int(float(hhad.get("goalLine", "0"))),
        "win_odds": float(had.get("h", 0)),
        "draw_odds": float(had.get("d", 0)),
        "lose_odds": float(had.get("a", 0)),
        "handicap_win_odds": float(hhad.get("h", 0)),
        "handicap_draw_odds": float(hhad.get("d", 0)),
        "handicap_lose_odds": float(hhad.get("a", 0)),
    }


if __name__ == "__main__":
    matches = get_matches()
    for day in matches:
        for m in day.get("subMatchList", []):
            parsed = parse_match(m)
            print(json.dumps(parsed, ensure_ascii=False))
