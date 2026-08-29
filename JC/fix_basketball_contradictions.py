#!/usr/bin/env python3
"""
修复篮球预测中胜负与胜分差方向矛盾的96条记录
规则：
a) 解析层容错：'客胜'→'负'、'主胜'→'胜'、'客负'→'胜'、'主负'→'负'
b) 写库前逻辑校验：win_loss方向必须与score_diff_range主客前缀一致
   不一致时以handicap盘口方向为准自动修正score_diff_range
"""
import os
import sys
import json
import re
import psycopg2

DB_URL = os.environ.get('DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres')


def fix_win_loss_value(wl):
    """容错映射win_loss值"""
    fix_map = {"客胜": "负", "主胜": "胜", "客负": "胜", "主负": "负"}
    return fix_map.get(wl, wl)


def fix_handicap_value(hwl):
    """容错映射handicap_win_loss值"""
    fix_map = {"客胜": "让负", "主胜": "让胜", "客负": "让胜", "主负": "让负"}
    return fix_map.get(hwl, hwl)


def normalize_sdr(sdr):
    """规范化score_diff_range格式"""
    if not sdr or not isinstance(sdr, str):
        return sdr
    sdr = sdr.strip()
    # "主1-5负" → "主1-5胜"
    sdr = re.sub(r'^(主|客)(\d+[-+]\d*)负$', r'\1\2胜', sdr)
    # "主负1-5" → "客胜1-5"
    sdr = re.sub(r'^主负(\d+[-+]\d*|\d+\+?)$', r'客胜\1', sdr)
    sdr = re.sub(r'^客负(\d+[-+]\d*|\d+\+?)$', r'主胜\1', sdr)
    # "主胜X-Y" → "主X-Y胜"
    sdr = re.sub(r'^(主|客)胜(\d+[-+]\d*|\d+\+?)$', r'\1\2胜', sdr)
    return sdr


def get_sdr_team(sdr):
    """提取score_diff_range的主/客前缀"""
    m = re.match(r'^(主|客)', sdr)
    return m.group(1) if m else None


def fix_contradiction(pred, match_spread=None):
    """修复单条预测的矛盾"""
    changes = {}
    
    # Step 1: 容错映射
    wl_orig = pred.get('win_loss', '')
    wl_fixed = fix_win_loss_value(wl_orig)
    if wl_fixed != wl_orig:
        changes['win_loss'] = (wl_orig, wl_fixed)
        pred['win_loss'] = wl_fixed
    
    hwl_orig = pred.get('handicap_win_loss', '')
    hwl_fixed = fix_handicap_value(hwl_orig)
    if hwl_fixed != hwl_orig:
        changes['handicap_win_loss'] = (hwl_orig, hwl_fixed)
        pred['handicap_win_loss'] = hwl_fixed
    
    sdr_orig = pred.get('score_diff_range', '')
    sdr_fixed = normalize_sdr(sdr_orig)
    if sdr_fixed != sdr_orig:
        changes['score_diff_range'] = (sdr_orig, sdr_fixed)
        pred['score_diff_range'] = sdr_fixed
    
    # Step 2: win_loss ↔ score_diff_range方向一致性检查
    wl = pred.get('win_loss', '')
    sdr = pred.get('score_diff_range', '')
    hwl = pred.get('handicap_win_loss', '')
    sdr_team = get_sdr_team(sdr)
    
    if wl in ('胜', '负') and sdr_team:
        if wl == '胜' and sdr_team == '客':
            # 矛盾：win_loss=胜(主队赢)但sdr=客X胜
            # 以handicap方向为准
            if hwl == '让胜':
                new_sdr = re.sub(r'^客', '主', sdr)
                changes['score_diff_range'] = (sdr, new_sdr)
                pred['score_diff_range'] = new_sdr
            elif hwl == '让负':
                changes['win_loss'] = (wl, '负')
                pred['win_loss'] = '负'
            else:
                # handicap也无法判断，以sdr为准修正win_loss
                changes['win_loss'] = (wl, '负')
                pred['win_loss'] = '负'
        
        elif wl == '负' and sdr_team == '主':
            # 矛盾：win_loss=负(主队输)但sdr=主X胜
            if hwl == '让负':
                new_sdr = re.sub(r'^主', '客', sdr)
                changes['score_diff_range'] = (sdr, new_sdr)
                pred['score_diff_range'] = new_sdr
            elif hwl == '让胜':
                changes['win_loss'] = (wl, '胜')
                pred['win_loss'] = '胜'
            else:
                changes['win_loss'] = (wl, '胜')
                pred['win_loss'] = '胜'
    
    return pred, changes


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # 查找所有篮球预测中胜负与胜分差方向矛盾的记录
    cur.execute("""
        SELECT id, match_id, ai_name, prediction
        FROM predictions
        WHERE sport_type = 'basketball'
        AND prediction IS NOT NULL
    """)
    
    rows = cur.fetchall()
    total_fixed = 0
    total_checked = 0
    
    print("=" * 60)
    print("修复篮球预测胜负与胜分差方向矛盾")
    print("=" * 60)
    
    for row_id, match_id, ai_name, pred_raw in rows:
        total_checked += 1
        pred = pred_raw if isinstance(pred_raw, dict) else json.loads(pred_raw)
        
        wl = pred.get('win_loss', '')
        sdr = pred.get('score_diff_range', '')
        sdr_team = get_sdr_team(normalize_sdr(sdr))
        
        # 先做容错映射再检查
        wl_normalized = fix_win_loss_value(wl)
        sdr_normalized = normalize_sdr(sdr)
        sdr_team_normalized = get_sdr_team(sdr_normalized)
        
        # 检查是否有矛盾或需要容错
        has_issue = False
        
        # 容错问题
        if wl_normalized != wl:
            has_issue = True
        if sdr_normalized != sdr:
            has_issue = True
        
        # 方向矛盾
        if wl_normalized in ('胜', '负') and sdr_team_normalized:
            if (wl_normalized == '胜' and sdr_team_normalized == '客') or \
               (wl_normalized == '负' and sdr_team_normalized == '主'):
                has_issue = True
        
        if not has_issue:
            continue
        
        # 修复
        fixed_pred, changes = fix_contradiction(pred)
        
        if changes:
            # 更新数据库
            pred_json = json.dumps(fixed_pred, ensure_ascii=False)
            cur.execute("""
                UPDATE predictions 
                SET prediction = %s::jsonb,
                    win_loss = %s,
                    handicap_win_loss = %s,
                    score_diff_range = %s
                WHERE id = %s
            """, (
                pred_json,
                fixed_pred.get('win_loss'),
                fixed_pred.get('handicap_win_loss'),
                fixed_pred.get('score_diff_range'),
                row_id
            ))
            
            change_desc = '; '.join([f'{k}: {v[0]}→{v[1]}' for k, v in changes.items()])
            print(f"  [{match_id}] {ai_name}: {change_desc}")
            total_fixed += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n{'=' * 60}")
    print(f"检查: {total_checked}条")
    print(f"修复: {total_fixed}条")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
