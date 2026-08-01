#!/bin/bash
echo "Build: 使用非版本化文件引用（CDN直接部署源文件）"

# ─── 健康巡检 ───────────────────────────────────────
echo ""
echo "🏥 运行健康巡检..."
if [ -f "health_check.js" ]; then
  node health_check.js
  HC_EXIT=$?
  if [ $HC_EXIT -ne 0 ]; then
    echo ""
    echo "⚠️  健康巡检发现问题（exit code: $HC_EXIT），请检查后重新部署！"
    echo "   可手动运行: pnpm run health"
  else
    echo "🏥 健康巡检通过"
  fi
else
  echo "⚠️  health_check.js 不存在，跳过巡检"
fi

echo ""
echo "Done."
