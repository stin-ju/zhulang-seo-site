#!/bin/bash
# 一键启动脚本 - 带端口自愈功能
# 容器启动时检测5000/5001/5002端口，若未监听则清理残留进程并重启
# rebuild: 20260902-005-force-redeploy

set -e

PORTS=(5000 5001 5002)
SERVICES=("server.js" "CT/server_traditional.js" "JC/server.js")
SERVICE_NAMES=("Router" "CT" "JC")
PORT_ENVS=("" "" "")
NEED_RESTART=false

echo "=== 服务自愈检查 ==="
echo "时间: $(date)"

# Python 依赖保护：确保容器重启后 psycopg2 等模块可用
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/JC/requirements.txt" ]; then
    echo "=== 检查 Python 依赖 ==="
    if python3 -c "import psycopg2" 2>/dev/null; then
        echo "  psycopg2 ✓ 已安装"
    else
        echo "  psycopg2 ✗ 缺失，安装中..."
        pip3 install -r "$SCRIPT_DIR/JC/requirements.txt" --quiet 2>&1 || echo "  ⚠ Python 依赖安装失败（非致命，auto_predict 可能不可用）"
    fi
fi

# 检查每个端口
for i in "${!PORTS[@]}"; do
    port=${PORTS[$i]}
    if ss -tuln 2>/dev/null | grep -qE "LISTEN.*:${port}([[:space:]]|$)"; then
        echo "  端口 $port (${SERVICE_NAMES[$i]}) ✓ 已监听"
    else
        echo "  端口 $port (${SERVICE_NAMES[$i]}) ✗ 未监听"
        NEED_RESTART=true
    fi
done

if [ "$NEED_RESTART" = true ]; then
    echo ""
    echo "=== 清理残留node进程 ==="
    
    # 杀掉所有残留的node服务进程（排除codegraph等系统进程）
    for pid in $(ps aux | grep -E "node.*(server\.js|server_traditional)" | grep -v grep | grep -v codegraph | awk '{print $2}'); do
        echo "  杀掉进程 $pid"
        kill $pid 2>/dev/null || true
    done
    
    # 等待进程退出
    sleep 2
    
    # 确认端口已释放
    for port in "${PORTS[@]}"; do
        if ss -tuln 2>/dev/null | grep -qE "LISTEN.*:${port}([[:space:]]|$)"; then
            echo "  警告: 端口 $port 仍被占用，尝试强制释放..."
            fuser -k ${port}/tcp 2>/dev/null || true
            sleep 1
        fi
    done
    
    echo ""
    echo "=== 重启服务 ==="
    
    # 获取脚本所在目录作为项目根目录（兼容沙箱/FaaS环境）
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"
    echo "  工作目录: $(pwd)"
    
    # 启动根服务（会自动拉起CT和JC子服务）
    echo "  启动 Router (5000)..."
    # 确保日志目录存在（兼容沙箱/FaaS环境）
    LOG_DIR="/app/work/logs/bypass"
    if [ ! -d "$LOG_DIR" ]; then
        # FaaS环境：使用临时目录
        LOG_DIR="/tmp/logs"
        mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="."
    fi
    nohup node server.js > "$LOG_DIR/router.log" 2>&1 &
    
    # 等待服务启动
    sleep 5
    
    # 验证端口
    echo ""
    echo "=== 验证启动结果 ==="
    ALL_OK=true
    for i in "${!PORTS[@]}"; do
        port=${PORTS[$i]}
        if ss -tuln 2>/dev/null | grep -qE "LISTEN.*:${port}([[:space:]]|$)"; then
            echo "  端口 $port (${SERVICE_NAMES[$i]}) ✓ 已监听"
        else
            echo "  端口 $port (${SERVICE_NAMES[$i]}) ✗ 启动失败"
            ALL_OK=false
        fi
    done
    
    if [ "$ALL_OK" = true ]; then
        echo ""
        echo "=== 所有服务启动成功 ==="
    else
        echo ""
        echo "=== 部分服务启动失败，请检查日志 ==="
        tail -20 "$LOG_DIR/router.log" 2>/dev/null || echo "  (日志文件不可用)"
    fi
else
    echo ""
    echo "=== 所有服务正常运行，无需重启 ==="
fi

echo ""
echo "=== 当前进程状态 ==="
ps aux | grep -E "node.*(server\.js|server_traditional)" | grep -v grep | grep -v codegraph
