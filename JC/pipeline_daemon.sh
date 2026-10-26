#!/bin/bash
# ============================================================
# pipeline_daemon.sh - CODE 沙箱内常驻调度守护进程
# 目的：每天 00:10 / 12:10 在沙箱内直接触发 run_pipeline.sh，
#       全程零 AI 对话、零积分消耗。
# 机制：
#   1) 每 50 秒刷新心跳文件 /tmp/pipeline_daemon.hb
#   2) 命中 0010 / 1210 时用 flock 抢占锁后跑流水线
#   3) 锁与日历触发共用 /tmp/run_pipeline.lock，天然互斥防重复
# ============================================================
PROJ=/workspace/projects/JC
LOG=$PROJ/logs/daemon_$(date +%Y%m%d).log
HB=/tmp/pipeline_daemon.hb
LOCK=/tmp/run_pipeline.lock
mkdir -p "$PROJ/logs"
echo "daemon started pid=$$ at $(date '+%F %T')" >> "$LOG"

while true; do
  date +%s > "$HB"
  hm=$(date +%H%M)
  if [ "$hm" = "0010" ] || [ "$hm" = "1210" ]; then
    (
      flock -n 9 || exit 0
      echo "[$(date '+%F %T')] daemon trigger pipeline ($hm)" >> "$LOG"
      bash "$PROJ/run_pipeline.sh" >> "$LOG" 2>&1
      echo "[$(date '+%F %T')] daemon pipeline finished" >> "$LOG"
    ) 9>"$LOCK"
    sleep 120
  fi
  sleep 50
donu
done
