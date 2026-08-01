#!/usr/bin/env python3
"""
sporttery_client.py - 体彩API统一请求客户端（四层容错 v2）

容错策略（按优先级）:
  方案1: curl（TLS指纹更接近浏览器，WAF拦截率低）
  方案2: Python requests（不同TLS栈做备选）
  方案3: 本地缓存兜底（24小时有效）
  方案4: 预抓取文件兜底（由日历任务通过fetch_web预存）

关键优化（2026-07-05）:
  - curl优先于requests（实测requests被WAF 403率远高于curl）
  - 每次请求失败后自动重试2次，间隔递增
  - User-Agent随机轮换，降低被WAF指纹锁定的概率

所有请求 sporttery.cn 的脚本都应使用此模块。
"""
import os
import sys
import json
import time
import random
import hashlib
import subprocess
import requests
from datetime import datetime

# User-Agent池 - 轮换使用降低WAF拦截
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]

def _get_ua():
    return random.choice(USER_AGENTS)

REQUEST_HEADERS = {
    'Accept-Encoding': 'identity',
    'Referer': 'https://www.sporttery.cn/',
    'Origin': 'https://www.sporttery.cn',
}

REQUEST_HEADERS_ODDS = {
    'Accept-Encoding': 'identity',
    'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
    'Origin': 'https://www.sporttery.cn',
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_cache')
CACHE_TTL = 86400  # 24小时
MAX_RETRIES = 2  # 每种方式最多重试2次
RETRY_DELAYS = [1, 3]  # 重试间隔（秒）


def _get_cache_key(url):
    """生成缓存key（基于URL的hash）"""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _save_cache(url, data):
    """保存数据到本地缓存"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, f"{_get_cache_key(url)}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'data': data
            }, f, ensure_ascii=False)
    except Exception as e:
        print(f"  ⚠️ 缓存保存失败: {e}")


def _load_cache(url):
    """从本地缓存加载数据（24小时有效）"""
    try:
        cache_file = os.path.join(CACHE_DIR, f"{_get_cache_key(url)}.json")
        if not os.path.exists(cache_file):
            return None
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached = json.load(f)
            cache_time = datetime.fromisoformat(cached['timestamp'])
            if (datetime.now() - cache_time).total_seconds() > CACHE_TTL:
                return None
            return cached['data']
    except Exception:
        return None


def _curl_get(url, headers=None):
    """用curl发起请求（WAF拦截率低）"""
    ua = _get_ua()
    referer = 'https://www.sporttery.cn/'
    if headers and 'Referer' in headers:
        referer = headers['Referer']
    
    curl_cmd = (
        f'curl -s --connect-timeout 15 --max-time 25 '
        f'-H "Accept-Encoding: identity" '
        f'-H "Referer: {referer}" '
        f'-H "Origin: https://www.sporttery.cn" '
        f'-H "User-Agent: {ua}" '
        f'"{url}"'
    )
    result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True, timeout=35)
    stdout = result.stdout.strip()
    
    if not stdout:
        return None
    if 'WAF' in stdout or '<html' in stdout.lower()[:100]:
        return None
    
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _requests_get(url, headers=None):
    """用Python requests发起请求"""
    req_headers = dict(headers or REQUEST_HEADERS)
    req_headers['User-Agent'] = _get_ua()
    
    try:
        r = requests.get(url, headers=req_headers, timeout=20)
        if r.status_code == 200:
            return r.json()
        else:
            return None
    except Exception:
        return None


def api_get(url, headers=None):
    """四层容错请求 sporttery.cn API（v2: curl优先+重试）
    
    返回: 解析后的 dict 或 None
    
    容错层级：
      1. curl（重试2次）- WAF拦截率最低
      2. Python requests（重试2次）- 不同TLS栈备选
      3. 本地缓存兜底（24小时有效）
      4. 预抓取文件兜底（由日历任务通过fetch_web预存）
    """
    req_headers = headers or REQUEST_HEADERS
    
    # ===== 方案1: curl（优先，WAF拦截率低）=====
    for attempt in range(MAX_RETRIES + 1):
        data = _curl_get(url, req_headers)
        if data:
            _save_cache(url, data)
            return data
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAYS[attempt])
    
    # ===== 方案2: Python requests =====
    for attempt in range(MAX_RETRIES + 1):
        data = _requests_get(url, req_headers)
        if data:
            _save_cache(url, data)
            return data
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAYS[attempt])
    
    # ===== 方案3: 本地缓存 =====
    cached = _load_cache(url)
    if cached:
        print(f"  ℹ️ curl+requests均失败，使用本地缓存数据")
        return cached
    
    # ===== 方案4: 预抓取文件兜底 =====
    prefetched = _load_prefetched(url)
    if prefetched:
        print(f"  ℹ️ 使用预抓取文件数据")
        return prefetched
    
    # 全部失败，写告警
    _write_alert(url)
    print(f"  ❌ 四层容错全部失败: {url[:80]}...")
    return None


def _load_prefetched(url):
    """从预抓取文件加载数据"""
    try:
        prefetch_file = os.path.join(CACHE_DIR, 'prefetched.json')
        if not os.path.exists(prefetch_file):
            return None
        with open(prefetch_file, 'r', encoding='utf-8') as f:
            prefetched = json.load(f)
            fetch_time = datetime.fromisoformat(prefetched.get('timestamp', '2000-01-01'))
            if (datetime.now() - fetch_time).total_seconds() > 43200:
                return None
            for item in prefetched.get('data', []):
                if item.get('url') == url:
                    return item.get('data')
            return None
    except Exception:
        return None


def _write_alert(url):
    """写告警文件，触发通知"""
    try:
        alert_file = os.path.join(CACHE_DIR, 'ALERT.json')
        alert = {
            'timestamp': datetime.now().isoformat(),
            'url': url,
            'message': '四层容错全部失败，需要人工介入'
        }
        with open(alert_file, 'w', encoding='utf-8') as f:
            json.dump(alert, f, ensure_ascii=False, indent=2)
        print(f"  🚨 已写告警文件: {alert_file}")
    except Exception:
        pass
