#!/bin/bash
VER=$(date +%Y%m%d%H%M)
echo "Build version: $VER"

# 版本化核心JS文件
cp index.js index.${VER}.js
cp api.js api.${VER}.js

# 更新index.${VER}.js中的api.js引用为版本化文件名
sed -i "s|'./api\.js'|'./api.${VER}.js'|g" "index.${VER}.js"
sed -i "s|\"./api\.js\"|\"./api.${VER}.js\"|g" "index.${VER}.js"
# 更新注释中的版本号
sed -i "s|// cache bust.*|// v=${VER} cache bust|g" "index.${VER}.js"

# 版本化页面JS文件（从HTML中抽取的独立JS）
for js in basketball.js ai-analysis.js calculator.js briefs.js; do
  if [ -f "$js" ]; then
    base="${js%.js}"
    cp "$js" "${base}.${VER}.js"
    # 更新版本化JS文件内的api引用
    sed -i "s|./api\.js|./api.${VER}.js|g" "${base}.${VER}.js"
  fi
done

# 更新HTML文件中的JS引用
for html in *.html; do
  sed -i "s|index\.[0-9]*\.js|index.${VER}.js|g" $html
  sed -i "s|api\.[0-9]*\.js|api.${VER}.js|g" $html
  sed -i "s|basketball\.[0-9]*\.js|basketball.${VER}.js|g" $html
  sed -i "s|ai-analysis\.[0-9]*\.js|ai-analysis.${VER}.js|g" $html
  sed -i "s|calculator\.[0-9]*\.js|calculator.${VER}.js|g" $html
  sed -i "s|briefs\.[0-9]*\.js|briefs.${VER}.js|g" $html
done

# 去掉JS引用中多余的?v=参数（文件名已带版本号，不需要query参数）
for html in *.html; do
  sed -i "s|\.js?v=[0-9]*\"|.js\"|g" "$html"
done

echo "Done: $VER"

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
