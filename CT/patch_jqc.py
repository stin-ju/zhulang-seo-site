#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CT 进球彩"主客分开"修复补丁
目标文件: /workspace/projects/CT/traditional_lottery_predict.py（及 /workspace/、/opt/bytefaas/ 同步副本）
改动点:
  1) build_ct_prompt() 中 game_type=="进球彩" 的 prompt 模板：输出 zjq_home / zjq_away（各 "0"~"3"，3=3球或以上）
  2) parse_ct_response() 增加进球彩归一：保证字段存在、值合法、14场齐全
  3) 其他游戏类型逻辑完全不动
运行: python3 patch_jqc.py [文件路径]   不传参则自动改三个位置
"""
import sys, re, shutil, os

NEW_JQC_PROMPT = '''    elif game_type == "进球彩":
        return f"""你是专业足球预测分析师。请预测以下14场比赛的进球数。

## 比赛列表
{match_text}

## 预测要求
1. 请联网搜索每场比赛的球队近期进攻/防守数据
2. 分别预测每场比赛【主队进球数】和【客队进球数】（注意是两个独立数字，不是总进球）
3. 进球档位：0=0球，1=1球，2=2球，3=3球或以上（含3+）

## 输出格式（严格JSON数组）:
```json
[
  {{"match": "01", "zjq_home": "2", "zjq_away": "1", "analysis": "简要分析主队进2球客队进1球"}},
  ...
]
```
字段说明:
- zjq_home: 主队进球档位，只能是 "0"/"1"/"2"/"3"
- zjq_away: 客队进球档位，只能是 "0"/"1"/"2"/"3"
- 14场比赛全部要给，禁止缺场，禁止输出总进球数"""'''

# 旧 prompt 块的起止特征
OLD_START = '    elif game_type == "进球彩":'
OLD_END_MARKER = '其中 zjq: 总进球数，"0"=0球, "1"=1球, "2"=2球, "3"=3球及以上"""'

NORMALIZE_FUNC = '''
def normalize_jqc_items(items):
    """进球彩归一：保证每场有 zjq_home/zjq_away 且为合法档位 "0"~"3"。
    旧数据只有 zjq(总进球) 时不猜测拆分（合规：禁止反拆主客），
    新数据缺字段则丢弃该场（上游会按缺失处理）。"""
    def _gear(v):
        s = str(v).strip() if v is not None else ''
        if s.startswith('3'):
            return '3'
        if s in ('0', '1', '2'):
            return s
        return None
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        num = it.get('match') or it.get('num')
        h = _gear(it.get('zjq_home'))
        a = _gear(it.get('zjq_away'))
        if num is None or h is None or a is None:
            continue
        out.append({
            'match': str(num).zfill(2),
            'zjq_home': h,
            'zjq_away': a,
            'analysis': it.get('analysis', '') or ''
        })
    return out
'''

PARSE_REPLACEMENT_OLD = '''def parse_ct_response(text, game_type):
    """解析AI返回的传统彩预测JSON"""
    if not text:
        return None

    # 尝试提取JSON数组
    json_match = re.search(r'```json\\s*(\\[.*?\\])\\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass

    json_match = re.search(r'\\[\\s*\\{.*?\\}\\s*\\]', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except:
            pass

    return None'''

PARSE_REPLACEMENT_NEW = '''def parse_ct_response(text, game_type):
    """解析AI返回的传统彩预测JSON"""
    if not text:
        return None

    # 尝试提取JSON数组
    json_match = re.search(r'```json\\s*(\\[.*?\\])\\s*```', text, re.DOTALL)
    parsed = None
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
        except:
            pass

    if parsed is None:
        json_match = re.search(r'\\[\\s*\\{.*?\\}\\s*\\]', text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
            except:
                pass

    if parsed is None:
        return None

    # 进球彩主客分开归一
    if game_type == "进球彩":
        return normalize_jqc_items(parsed)
    return parsed'''


def patch_file(path):
    if not os.path.exists(path):
        print(f'[SKIP] 文件不存在: {path}')
        return False
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    orig = src
    changed = []

    # 1) 替换进球彩 prompt 块
    if 'zjq_home' in src and NEW_JQC_PROMPT.strip()[:60] in src:
        print(f'[INFO] {path}: prompt 已是新版，跳过')
    else:
        i = src.find(OLD_START)
        if i == -1:
            print(f'[WARN] {path}: 找不到进球彩 prompt 起点')
        else:
            j = src.find(OLD_END_MARKER, i)
            if j == -1:
                print(f'[WARN] {path}: 找不到进球彩 prompt 终点')
            else:
                j_end = j + len(OLD_END_MARKER)
                src = src[:i] + NEW_JQC_PROMPT + src[j_end:]
                changed.append('prompt')

    # 2) 插入归一函数（在 parse_ct_response 之前）
    if 'def normalize_jqc_items' not in src:
        anchor = 'def parse_ct_response'
        k = src.find(anchor)
        if k != -1:
            src = src[:k] + NORMALIZE_FUNC + '\n\n' + src[k:]
            changed.append('normalize_func')

    # 3) 替换 parse_ct_response 为带归一版本
    if 'normalize_jqc_items(parsed)' not in src:
        if PARSE_REPLACEMENT_OLD in src:
            src = src.replace(PARSE_REPLACEMENT_OLD, PARSE_REPLACEMENT_NEW)
            changed.append('parse_hook')
        else:
            print(f'[WARN] {path}: parse_ct_response 原文匹配失败，请人工检查')

    if src == orig:
        print(f'[NOCHANGE] {path}')
        return False
    shutil.copy2(path, path + '.bak_jqc')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'[DONE] {path} 改动: {changed}，备份: {path}.bak_jqc')
    return True


if __name__ == '__main__':
    targets = sys.argv[1:] or [
        '/workspace/projects/CT/traditional_lottery_predict.py',
        '/workspace/traditional_lottery_predict.py',
        '/opt/bytefaas/traditional_lottery_predict.py',
    ]
    for t in targets:
        patch_file(t)
    print('补丁执行完毕')
