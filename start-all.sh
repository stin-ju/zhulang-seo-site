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
# 关键：必须用 psycopg2-binary（自带预编译wheel），不能用源码版（需libpq/编译工具）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/JC/requirements.txt" ]; then
    echo "=== 检查 Python 依赖 ==="
    
    # 确定安装目标目录（FaaS 环境用 /opt/bytefaas/site-packages）
    PIP_TARGET=""
    if [ -d "/opt/bytefaas" ]; then
        PIP_TARGET="/opt/bytefaas/site-packages"
        mkdir -p "$PIP_TARGET" 2>/dev/null || true
        # 立即设置 PYTHONPATH，确保后续所有 python3 调用都能找到包
        export PYTHONPATH="$PIP_TARGET:${PYTHONPATH:-}"
    fi
    
    # 检查 psycopg2 C 扩展是否可用（此时 PYTHONPATH 已设置）
    if python3 -c "import psycopg2._psycopg" 2>/dev/null; then
        echo "  psycopg2._psycopg ✓ C扩展正常"
    else
        echo "  psycopg2._psycopg ✗ 缺失，开始修复..."
        # 关闭 set -e，避免 pip 失败导致脚本退出
        set +e
        
        # Step 1: 彻底删除所有旧版 psycopg2
        echo "  [1/4] 清理旧版 psycopg2..."
        if [ -n "$PIP_TARGET" ]; then
            rm -rf "$PIP_TARGET"/psycopg2 "$PIP_TARGET"/psycopg2_binary* 2>/dev/null
            rm -rf "$PIP_TARGET"/psycopg2-*.dist-info "$PIP_TARGET"/psycopg2_binary-*.dist-info 2>/dev/null
            # 也清理系统级残留（如果有权限）
            pip3 uninstall psycopg2 psycopg2-binary -y 2>/dev/null || true
        else
            pip3 uninstall psycopg2 psycopg2-binary -y 2>/dev/null || true
        fi
        echo "  清理完成"
        
        # Step 2: 安装 psycopg2-binary（预编译wheel，不依赖libpq）
        echo "  [2/4] 安装 psycopg2-binary..."
        if [ -n "$PIP_TARGET" ]; then
            pip3 install --no-cache-dir --force-reinstall 'psycopg2-binary>=2.9.0' --target "$PIP_TARGET" 2>&1
        else
            pip3 install --no-cache-dir --force-reinstall 'psycopg2-binary>=2.9.0' 2>&1
        fi
        PIP_RC=$?
        echo "  pip install 返回码: $PIP_RC"
        
        # Step 3: 安装其他依赖
        echo "  [3/4] 安装其他依赖..."
        if [ -n "$PIP_TARGET" ]; then
            pip3 install --no-cache-dir 'requests>=2.31.0' 'aiohttp>=3.9.0' --target "$PIP_TARGET" --quiet 2>&1 || true
        else
            pip3 install --no-cache-dir 'requests>=2.31.0' 'aiohttp>=3.9.0' --quiet 2>&1 || true
        fi
        
        # Step 4: 验证
        echo "  [4/4] 验证安装..."
        echo "  PYTHONPATH=$PYTHONPATH"
        python3 -c "
import sys
print('  sys.path:', [p for p in sys.path if 'psycopg' in p or 'bytefaas' in p or 'site-packages' in p])
import psycopg2
print('  psycopg2 版本:', psycopg2.__version__)
print('  psycopg2 文件:', psycopg2.__file__)
import psycopg2._psycopg
print('  _psycopg 文件:', psycopg2._psycopg.__file__)
print('  PSYCOPG2_OK')
" 2>&1
        VERIFY_RC=$?
        echo "  验证返回码: $VERIFY_RC"
        
        # 恢复 set -e
        set -e
        
        if [ $VERIFY_RC -eq 0 ]; then
            echo "  ✓ psycopg2 修复成功"
        else
            echo "  ✗ psycopg2 修复失败！尝试列出已安装内容："
            pip3 list 2>/dev/null | grep -i psycopg || echo "  pip3 list 无 psycopg 相关条目"
            ls -la "$PIP_TARGET"/psycopg2* 2>/dev/null | head -10 || echo "  $PIP_TARGET 无 psycopg2 文件"
            python3 -c "import sys; print('  Python路径:', sys.path)" 2>/dev/null || true
        fi
    fi
    
    # 最终确认 PYTHONPATH（无论检查是否通过都要 export）
    if [ -n "$PIP_TARGET" ]; then
        export PYTHONPATH="$PIP_TARGET:${PYTHONPATH:-}"
        echo "  最终 PYTHONPATH=$PYTHONPATH"
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
