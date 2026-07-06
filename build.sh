#!/bin/bash
# build.sh - 一键更新所有文件中的缓存版本号
# 用法：bash build.sh

NEW_VER="v=$(date +%Y%m%d%H)"

echo "🔧 更新缓存版本号为: $NEW_VER"

FILES=$(find . -maxdepth 1 \( -name '*.html' -o -name '*.js' \) -not -name 'build.sh' | sort)

for f in $FILES; do
    BEFORE=$(grep -oP '\?v=\d{10,}' "$f" | head -1)
    sed -i -E "s/\?v=[0-9]{10,}/?$NEW_VER/g" "$f"
    AFTER=$(grep -oP '\?v=\d{10,}' "$f" | head -1)
    if [ "$BEFORE" != "$AFTER" ] && [ -n "$AFTER" ]; then
        echo "  ✅ $f: $BEFORE → $AFTER"
    fi
done

echo ""
echo "📦 提交并推送..."
git add -A
git commit -m "chore: 自动更新缓存参数 $NEW_VER"
git push origin main
echo "✅ 完成！"
