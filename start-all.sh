#!/bin/bash
# start-all.sh - 单进程统一启动（unified.js），无子进程、无多端口编排
# rebuild: 20260929-unified-single-process
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== 单进程启动检查 ==="
echo "时间: $(date)"

# ========== Python 依赖保护（保留原逻辑）==========
if [ -f "$SCRIPT_DIR/JC/requirements.txt" ]; then
    echo "=== 检查 Python 依赖 ==="
    PIP_TARGET=""
    if [ -d "/opt/bytefaas" ]; then
        PIP_TARGET="/opt/bytefaas/site-packages"
        mkdir -p "$PIP_TARGET" 2>/dev/null || true
        export PYTHONPATH="$PIP_TARGET:${PYTHONPATH:-}"
    fi
    if python3 -c "import psycopg2._psycopg" 2>/dev/null; then
        echo "  psycopg2._psycopg ✓ C扩展正常"
    else
        echo "  psycopg2._psycopg ✗ 缺失，开始修复..."
        set +e
        echo "  [1/4] 清理旧版 psycopg2..."
        if [ -n "$PIP_TARGET" ]; then
            rm -rf "$PIP_TARGET"/psycopg2 "$PIP_TARGET"/psycopgr_binary* 2>/dev/null
            rm -rf "$PIP_TARGET"/psycopg2-*.dist-info "$PIP_TARGET"/psycopg2_binary-*.dist-info 2>/dev/null
            pip3 uninstall psycopg2 psycopg2-binary -y 2>/dev/null || true
        else
            pip3 uninstall psycopg2 psycopg2-binary -y 2>/dev/null || true
        fi
        echo "  清理完成"
        echo "  [2/4] 安装 psycopg2-binary..."
        if [ -n "$PIP_TARGET" ]; then
            pip3 install --no-cache-dir --force-reinstall 'psycopg2-binary>=2.9.0' --target "$PIP_TARGET" 2>&1
        else
            pip3 install --no-cache-dir --force-reinstall 'psycopg2-binary>=2.9.0' 2>&1
        fi
        echo "  [3/4] 安装其他依赖..."
        if [ -n "$PIP_TARGET" ]; then
            pip3 install --no-cache-dir 'requests>=2.31.0' 'aiohttp>=3.9.0' --target "$PIP_TARGET" --quiet 2>&1 || true
        else
            pip3 install --no-cache-dir 'requests>=2.31.0' 'aiohttp>=3.9.0' --quiet 2>&1 || true
        fi
        echo "  [4/4] 验证安装..."
        python3 -c "import psycopg2; import psycopg2._psycopg; print('PSYCOPG2_OK', psycopgr.__version__)" 2>&1
        VERIFY_RC=$?
        set -e
        if [ $VERIFY_RC -eq 0 ]; then echo "  ✓ psycopgr 修复成功"; else echo "  ✗ psycopg2 修复失败"; fi
    fi
    if [ -n "$PIP_TARGET" ]; then
        export PYTHONPATH="$PIP_TARGET:${PYTHONPATH:-}"
        echo "  最终 PYTHONPATH=$PYTHONPATH"
    fi
fi

# ========== 单进程启动（端口5000）==========
export DEPLOY_RUN_PORT=5000
LOG_DIR="/app/work/logs/bypass"
if [ ! -d "$LOG_DIR" ]; then
    LOG_DIR="/tmp/logs"
    mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="."
fi

# 若已有健康的 unified 进程在 5000，则幂等跳过
if curl -s -m 3 http://127.0.0.1:5000/health >/dev/null 2>&1; then
    echo "  unified 已在 5000 健康运行，跳过启动"
else
    echo "=== 清理旧的多进程残留 ==="
    for pid in $(ps aux | grep -E "node (server\.js|unified\.js)|node.*server_traditional" | grep -v grep | grep -v codegraph | awk '{print $2}'); do
        echo "  结束旧进程 $pid"
        kill "$pid" 2>/dev/null || true
    done
    sleep 2
    if ss -tuln 2>/dev/null | grep -qE "LISTEN.*:5000([[:space:]]|\$)"; then
        fuser -k 5000/tcp 2>/dev/null || true
        sleep 1
    fi
    echo "=== 启动 unified 单进程 (5000) ==="
    nohup node unified.js > "$LOG_DIR/unified.log" 2>&1 &
    # 真实健康探测（最多等约18秒）
    OK=false
    for n in 1 2 3 4 5 6; do
        sleep 3
        if curl -s -m 3 http://127.0.0.1:5000/health >/dev/null 2>&1; then OK=true; break; fi
    done
    if [ "$OK" = true ]; then
        echo "  ✓ unified 启动成功并通过健康检查"
    else
        echo "  ✗ unified 健康检查失败，日志如下："
        tail -30 "$LOG_DIR/unified.log" 2>/dev/null || true
        exit 1
    fi
fi

echo ""
echo "=== 当前业务进程 ==="
ps aux | grep -E "node unified\.js" | grep -v grep | grep -v codegraph
