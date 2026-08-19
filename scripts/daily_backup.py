#!/usr/bin/env python3
"""
每日核心数据备份脚本
- 备份 predictions、matches、betting_daily、betting_summary、match_intelligence 等核心表
- 输出为 CSV + JSON 双格式，便于恢复
- 保留最近7天备份，自动清理旧的
"""

import os
import sys
import json
import csv
import glob
import gzip
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres'
)

# 核心业务表（按重要性排序）
CRITICAL_TABLES = [
    'predictions',
    'matches',
    'betting_daily',
    'betting_summary',
    'match_intelligence',
    'chain_bets',
    'chain_bet_selections',
    'poisson_predictions',
    'traditional_predictions',
    'ai_stats',
]

# 备份保留天数
BACKUP_RETENTION_DAYS = 7

def get_backup_dir():
    """获取备份目录，优先使用项目内目录"""
    script_dir = Path(__file__).parent
    backup_dir = script_dir / 'backups'
    backup_dir.mkdir(exist_ok=True)
    return backup_dir

def backup_table(conn, table_name, backup_dir, date_str):
    """备份单张表为 gzip CSV"""
    try:
        cur = conn.cursor()
        
        # 获取表数据量
        cur.execute(f'SELECT count(*) FROM {table_name}')
        row_count = cur.fetchone()[0]
        
        if row_count == 0:
            print(f'  [{table_name}] 0行，跳过')
            return {'table': table_name, 'rows': 0, 'file': None}
        
        # 获取列名
        cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}' ORDER BY ordinal_position")
        columns = [r[0] for r in cur.fetchall()]
        
        # 导出为 gzip CSV
        filename = f'{table_name}_{date_str}.csv.gz'
        filepath = backup_dir / filename
        
        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            
            cur.execute(f'SELECT * FROM {table_name}')
            for row in cur.fetchall():
                # 处理特殊类型
                processed = []
                for val in row:
                    if isinstance(val, (dict, list)):
                        processed.append(json.dumps(val, ensure_ascii=False))
                    elif isinstance(val, datetime):
                        processed.append(val.isoformat())
                    elif hasattr(val, '__str__') and type(val).__name__ not in ('str', 'int', 'float', 'bool', 'NoneType'):
                        processed.append(str(val))
                    else:
                        processed.append(val)
                writer.writerow(processed)
        
        file_size = os.path.getsize(filepath)
        print(f'  [{table_name}] {row_count}行 → {filename} ({file_size/1024:.1f}KB)')
        
        return {'table': table_name, 'rows': row_count, 'file': str(filepath), 'size': file_size}
    
    except Exception as e:
        print(f'  [{table_name}] ERROR: {e}')
        return {'table': table_name, 'rows': 0, 'file': None, 'error': str(e)}

def check_schema_integrity(conn):
    """检查核心表结构是否被篡改"""
    issues = []
    cur = conn.cursor()
    
    for table in CRITICAL_TABLES[:5]:  # 只检查最重要的5张
        try:
            # 检查表是否存在
            cur.execute(f"SELECT count(*) FROM information_schema.columns WHERE table_name='{table}'")
            col_count = cur.fetchone()[0]
            if col_count == 0:
                issues.append(f'表 {table} 不存在！')
                continue
            
            # 检查主键名是否异常（检测表被重建）
            cur.execute(f"SELECT indexname FROM pg_indexes WHERE tablename='{table}'")
            indexes = [r[0] for r in cur.fetchall()]
            for idx in indexes:
                if '_new_' in idx:
                    issues.append(f'表 {table} 的主键名异常: {idx}（疑似表被重建）')
        
        except Exception as e:
            issues.append(f'检查 {table} 失败: {e}')
    
    return issues

def cleanup_old_backups(backup_dir):
    """清理超过保留天数的旧备份"""
    cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
    cleaned = 0
    
    for f in glob.glob(str(backup_dir / '*.csv.gz')):
        if os.path.getmtime(f) < cutoff.timestamp():
            os.remove(f)
            cleaned += 1
    
    if cleaned:
        print(f'  清理了 {cleaned} 个旧备份文件')

def main():
    date_str = datetime.now().strftime('%Y%m%d')
    backup_dir = get_backup_dir()
    
    print(f'=== 每日数据备份 {date_str} ===')
    print(f'备份目录: {backup_dir}')
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f'数据库连接失败: {e}')
        sys.exit(1)
    
    try:
        # 1. 备份核心表
        print('\n[1/3] 备份核心表...')
        results = []
        for table in CRITICAL_TABLES:
            result = backup_table(conn, table, backup_dir, date_str)
            results.append(result)
        
        # 2. 检查表结构完整性
        print('\n[2/3] 检查表结构完整性...')
        issues = check_schema_integrity(conn)
        if issues:
            print('  ⚠️ 发现异常:')
            for issue in issues:
                print(f'    - {issue}')
        else:
            print('  ✓ 所有核心表结构正常')
        
        # 3. 清理旧备份
        print('\n[3/3] 清理旧备份...')
        cleanup_old_backups(backup_dir)
        
        # 生成备份清单
        manifest = {
            'date': date_str,
            'timestamp': datetime.now().isoformat(),
            'tables': results,
            'schema_issues': issues,
            'total_rows': sum(r['rows'] for r in results),
        }
        
        manifest_path = backup_dir / f'manifest_{date_str}.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        
        print(f'\n备份完成! 总行数: {manifest["total_rows"]}')
        print(f'清单: {manifest_path}')
        
        # 返回状态码
        if issues:
            print('\n⚠️ 存在结构异常，请关注！')
            return 2
        
        return 0
    
    finally:
        conn.close()

if __name__ == '__main__':
    sys.exit(main() or 0)
