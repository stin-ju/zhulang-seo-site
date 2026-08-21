#!/bin/bash
# 每日赛事数据流水线：抓取→让球补全→结算→质量检查
# 由crontab每日0点和12点调用
set -e

cd /workspace/projects/JC
export PYTHONPATH=/workspace/projects/JC:/workspace/projects/scripts:/workspace/projects:$PYTHONPATH
LOG_DIR=/workspace/projects/JC/logs
mkdir -p $LOG_DIR
DATE=$(date +%Y%m%d_%H%M)

echo '=== 赛事数据流水线开始 ==='
echo "时间: $(date)"

# Step 1: 抓取比赛+赔率（含让球自动提取到顶层）
echo ''
echo '【Step 1/4】抓取比赛和赔率...'
python3 discover_matches.py >> $LOG_DIR/pipeline_$DATE.log 2>&1
echo '  完成'

# Step 2: 数据质量检查（自动补全缺失的让球等）
echo ''
echo '【Step 2/4】数据质量检查与补救...'
python3 data_quality_check.py >> $LOG_DIR/pipeline_$DATE.log 2>&1
echo '  完成'

# Step 3: 自动结算（补比分+结算预测）
echo ''
echo '【Step 3/4】自动结算...'
python3 auto_settle.py >> $LOG_DIR/pipeline_$DATE.log 2>&1
echo '  完成'

# Step 4: 结算后再跑一次质量检查（确认结算完整）
echo ''
echo '【Step 4/4】结算后质量复查...'
python3 data_quality_check.py >> $LOG_DIR/pipeline_$DATE.log 2>&1
echo '  完成'

echo ''
echo "=== 流水线完成 $(date) ==="

# 清理30天前的日志
find $LOG_DIR -name 'pipeline_*.log' -mtime +30 -delete 2>/dev/null || true
