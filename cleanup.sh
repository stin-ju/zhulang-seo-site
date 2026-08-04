#!/bin/bash
# ============================================
# CODE项目清理+重组一键脚本
# 在项目根目录执行
# ============================================
set -e
cd "$(dirname "$0")"

echo "🗑️  第一步：删除垃圾文件..."

# 根目录废弃页面
rm -f ix20260719e.html ix20260720e.html ix2.html index2.html index.htm
rm -f ia.html bb.html br.html
rm -f daily-2026-07-02.html daily-2026-07-03.html daily-2026-07-04.html daily-2026-07-05.html

# 根目录废弃Python脚本
rm -f auto_settle.py fetch_scores.py generate_calculator.py

# 废弃数据文件
rm -f chain_bets_data.json

# assets里放错的文件
rm -f assets/auto_predict.py assets/auto_settle.py assets/basketball_fixed.js assets/index_final.js

# scripts里废弃的脚本
rm -f scripts/matches_fixed.py
rm -f scripts/discover_and_predict.py
rm -f scripts/dispatch_report.py
rm -f scripts/fix_doubao.py
rm -f scripts/fix_missing_scores.py
rm -f scripts/basketball_score_client.py
rm -f scripts/titan007_client.py
rm -f scripts/settle_basketball_predictions.py
rm -f scripts/index.js
rm -rf scripts/server_jingcai
rm -rf scripts/api_cache

# 废弃目录
rm -rf src/
rm -f public/code-review-export.txt

echo "✅ 垃圾清理完成"

echo ""
echo "📁 第二步：创建JC/CT目录并移动文件..."
mkdir -p JC CT

# JC竞彩文件
mv ix.html index.js api.js styles.css JC/
mv basketball.html basketball.js JC/
mv ai-analysis.html ai-analysis.js ai-hub.html JC/
mv ia2.html bb2.html br2.html JC/
mv ca2.html ca.html JC/
mv calculator.html calculator.js JC/
mv briefs.html briefs.js JC/

# CT传统足彩文件
mv ct.html CT/
mv calculator_template.html CT/
mv server_traditional.js CT/

echo "✅ 文件归类完成"

echo ""
echo "🔧 第三步：修复BUG..."

# 修复 briefs.js: 旧版API引用
sed -i "s|./api.v20260727a.js|./api.js|g" JC/briefs.js

# 修复 briefs.html: 跳转到已删除的br.html → br2.html
sed -i 's|window.location.replace("/br.html")|window.location.replace("/br2.html")|g' JC/briefs.html

# 修复 ia2.html: 引用不存在的旧版JS
sed -i 's|./ai-analysis.202607152222.js|./ai-analysis.js|g' JC/ia2.html

# 修复 ct.html: 相对路径改为绝对路径（因为文件移到了CT/目录）
sed -i 's|href="index.html"|href="/index.html"|g' CT/ct.html
sed -i 's|href="ct.html"|href="/ct.html"|g' CT/ct.html
sed -i 's|href="ai.html"|href="/ai-hub.html"|g' CT/ct.html
sed -i 's|href="calc.html"|href="/ca.html"|g' CT/ct.html

echo "✅ BUG修复完成"

echo ""
echo "🔧 第四步：更新server.js添加URL别名..."

python3 << 'PYEOF'
with open('server.js', 'r', encoding='utf-8') as f:
    content = f.read()

if 'URL_ALIASES' in content:
    print("URL别名已存在，跳过")
else:
    alias_code = """
  // URL别名：旧路径 -> 新目录路径（文件已归类到JC/和CT/目录）
  const URL_ALIASES = {
    '/ix.html': '/JC/ix.html',
    '/api.js': '/JC/api.js',
    '/index.js': '/JC/index.js',
    '/styles.css': '/JC/styles.css',
    '/basketball.html': '/JC/basketball.html',
    '/basketball.js': '/JC/basketball.js',
    '/ai-analysis.html': '/JC/ai-analysis.html',
    '/ai-analysis.js': '/JC/ai-analysis.js',
    '/ai-hub.html': '/JC/ai-hub.html',
    '/ia2.html': '/JC/ia2.html',
    '/bb2.html': '/JC/bb2.html',
    '/br2.html': '/JC/br2.html',
    '/ca2.html': '/JC/ca2.html',
    '/ca.html': '/JC/ca.html',
    '/calculator.html': '/JC/calculator.html',
    '/calculator.js': '/JC/calculator.js',
    '/briefs.html': '/JC/briefs.html',
    '/briefs.js': '/JC/briefs.js',
    '/ct.html': '/CT/ct.html',
    '/calculator_template.html': '/CT/calculator_template.html',
  };
  if (URL_ALIASES[urlPath]) urlPath = URL_ALIASES[urlPath];
"""
    target = "if (urlPath === '/') urlPath = '/index.html';"
    content = content.replace(target, target + alias_code, 1)
    with open('server.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("server.js URL别名已添加")
PYEOF

echo ""
echo "============================================"
echo "🎉 全部完成！"
echo ""
echo "目录结构："
echo "  /JC/      竞彩前端（18个文件）"
echo "  /CT/      传统足彩（3个文件）"
echo "  /scripts/ 后端脚本（不变）"
echo "  /public/  SEO自动生成（不变）"
echo "  /assets/  图片素材（不变）"
echo "  根目录     入口+服务端+自动简报"
echo ""
echo "删除约35个垃圾文件"
echo "修复3个引用BUG"
echo "server.js加了URL别名，旧URL照常能用"
echo "============================================"
