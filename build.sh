#!/bin/bash
VER=$(date +%Y%m%d%H)
echo "Build version: $VER"

# 版本化核心JS文件
cp index.js index.${VER}.js
cp api.js api.${VER}.js

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

echo "Done: $VER"
