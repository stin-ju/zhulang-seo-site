#!/usr/bin/env node
/**
 * health_check.js - 网站健康巡检脚本
 * 
 * 在构建完成后执行，检查：
 * 1. 线上HTML页面引用的JS版本是否为最新
 * 2. /api/matches 已确认比赛是否都有比分
 * 3. /api/predictions 的 analysis 字段是否有 JSON 泄露
 * 4. 所有版本化 JS 文件是否 HTTP 200 可达
 * 
 * 用法: node health_check.js [--base-url https://xxx.dev.coze.site]
 */

const fs = require('fs');
const path = require('path');

// ─── 配置 ───────────────────────────────────────────
const BASE_URL = process.argv.find((_, i, a) => a[i - 1] === '--base-url')
  || process.env.COZE_PROJECT_DOMAIN_DEFAULT
  || process.env.DEPLOY_URL
  || 'http://localhost:5000';

// 需要巡检的 HTML 页面（短路径版本）
const HTML_PAGES = [
  'ix2.html',
  'bb2.html',
  'ia2.html',
  'br2.html',
  'ca2.html',
  'index2.html',
];

// 核心 JS 文件前缀（用于扫描最新版本号）
const JS_PREFIXES = ['index', 'api', 'basketball', 'ai-analysis', 'calculator', 'briefs'];

// analysis 字段中不应出现的 JSON 特征（说明原始 JSON 泄露到前端）
const JSON_LEAK_PATTERNS = [
  '"spf"',
  '"handicap_spf"',
  '"score_guess"',
  '"goals_prediction"',
  '"half_full"',
  '"win_loss"',
  'core_logic',
];

// ─── 工具函数 ────────────────────────────────────────
let hasError = false;
let warnings = 0;
let passes = 0;

function pass(msg) {
  passes++;
  console.log(`  ✅ ${msg}`);
}

function fail(msg) {
  hasError = true;
  console.log(`  ❌ ${msg}`);
}

function warn(msg) {
  warnings++;
  console.log(`  ⚠️  ${msg}`);
}

async function fetchText(url, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    const text = await res.text();
    return { status: res.status, text, ok: res.ok };
  } catch (err) {
    return { status: 0, text: '', ok: false, error: err.message };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(url, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    const json = await res.json();
    return { status: res.status, data: json, ok: res.ok };
  } catch (err) {
    return { status: 0, data: null, ok: false, error: err.message };
  } finally {
    clearTimeout(timer);
  }
}

// ─── 扫描本地最新版本号 ──────────────────────────────
function getLatestVersion() {
  const files = fs.readdirSync('.');
  const versionMap = {};

  for (const prefix of JS_PREFIXES) {
    const pattern = new RegExp(`^${prefix}\\.(\\d{8,})\\.js$`);
    let maxVer = '0';
    for (const f of files) {
      const m = f.match(pattern);
      if (m && m[1] > maxVer) {
        maxVer = m[1];
      }
    }
    versionMap[prefix] = maxVer;
  }

  // 取全局最新版本号（所有前缀中的最大值）
  const allVers = Object.values(versionMap).filter(v => v !== '0');
  const globalLatest = allVers.length ? allVers.reduce((a, b) => a > b ? a : b) : 'unknown';

  return { versionMap, globalLatest };
}

// ─── 检查 1: HTML 页面 JS 版本 ──────────────────────
async function checkHtmlVersions(globalLatest) {
  console.log('\n📄 [检查1] HTML页面JS版本');
  console.log(`   本地最新版本号: ${globalLatest}`);

  for (const page of HTML_PAGES) {
    const url = `${BASE_URL}/${page}`;
    const { status, text, ok, error } = await fetchText(url);

    if (!ok) {
      fail(`${page}: HTTP ${status} ${error || ''}`);
      continue;
    }

    // 提取引用的 JS 文件名（支持 ?v= query param）
    const jsRefs = text.match(/src="\.\/[^"]*\.js(\?[^"]*)?"/g) || [];
    if (jsRefs.length === 0 && page !== 'index2.html') {
      // index2.html 是重定向页，无 JS 引用
      warn(`${page}: 未发现 JS 引用`);
      continue;
    }

    let allLatest = true;
    for (const ref of jsRefs) {
      const fileName = ref.match(/\.\/([^"?]+)/)[1];
      const verMatch = fileName.match(/\.(\d{8,})\.js/);
      if (verMatch) {
        const fileVer = verMatch[1];
        if (fileVer !== globalLatest) {
          fail(`${page}: ${fileName} 版本 ${fileVer} ≠ 最新 ${globalLatest}`);
          allLatest = false;
        }
      }
    }
    if (allLatest && jsRefs.length > 0) {
      pass(`${page}: JS版本正确 (${globalLatest})`);
    }
  }
}

// ─── 检查 2: 已确认比赛比分 ─────────────────────────
async function checkMatchScores() {
  console.log('\n⚽ [检查2] 已确认比赛比分');

  const { status, data, ok, error } = await fetchJson(`${BASE_URL}/api/matches`);
  if (!ok) {
    fail(`/api/matches: HTTP ${status} ${error || ''}`);
    return;
  }

  if (!Array.isArray(data)) {
    fail(`/api/matches: 返回数据非数组`);
    return;
  }

  // 已确认的比赛（status 为 confirmed/done/finished 等）应有比分
  const confirmedMatches = data.filter(m =>
    m.status === 'confirmed' || m.status === 'done' || m.status === 'finished'
  );

  if (confirmedMatches.length === 0) {
    warn(`无已确认比赛（共 ${data.length} 场）`);
    return;
  }

  let missingScore = 0;
  for (const m of confirmedMatches) {
    const hasScore = (m.home_score != null && m.away_score != null) ||
                     (m.score && m.score !== '' && m.score !== '-');
    if (!hasScore) {
      missingScore++;
      if (missingScore <= 3) {
        fail(`比赛 ${m.id || m.match_id}: 已确认但无比分 (status=${m.status})`);
      }
    }
  }

  if (missingScore === 0) {
    pass(`已确认比赛 ${confirmedMatches.length} 场，全部有比分`);
  } else if (missingScore > 3) {
    fail(`...还有 ${missingScore - 3} 场已确认比赛缺少比分`);
  }
}

// ─── 检查 3: analysis 字段 JSON 泄露 ────────────────
async function checkAnalysisLeak() {
  console.log('\n🔍 [检查3] analysis字段JSON泄露检测');

  const { status, data, ok, error } = await fetchJson(`${BASE_URL}/api/predictions`);
  if (!ok) {
    fail(`/api/predictions: HTTP ${status} ${error || ''}`);
    return;
  }

  if (!Array.isArray(data)) {
    fail(`/api/predictions: 返回数据非数组`);
    return;
  }

  let leakCount = 0;
  const sampleSize = Math.min(data.length, 200); // 抽样检查前200条

  for (let i = 0; i < sampleSize; i++) {
    const pred = data[i];
    const analysis = pred.analysis;
    if (!analysis) continue;

    // 如果 analysis 是字符串，检查是否包含 JSON 特征
    if (typeof analysis === 'string') {
      for (const pattern of JSON_LEAK_PATTERNS) {
        if (analysis.includes(pattern)) {
          leakCount++;
          if (leakCount <= 3) {
            warn(`prediction[${i}] (AI: ${pred.ai_name}): analysis 含原始JSON特征 "${pattern}"`);
          }
          break;
        }
      }
    }
  }

  if (leakCount === 0) {
    pass(`抽样 ${sampleSize} 条预测，未发现 JSON 泄露`);
  } else {
    // 数据质量问题，降级为警告（不阻断构建）
    warn(`抽样 ${sampleSize} 条中有 ${leakCount} 条 analysis 包含原始 JSON 特征（数据质量问题，非代码bug）`);
  }
}

// ─── 检查 4: JS 文件可达性 ──────────────────────────
async function checkJsReachability(globalLatest) {
  console.log('\n🔗 [检查4] JS文件HTTP可达性');

  for (const prefix of JS_PREFIXES) {
    const fileName = `${prefix}.${globalLatest}.js`;
    const url = `${BASE_URL}/${fileName}`;
    const { status, ok, error } = await fetchText(url);

    if (ok && status === 200) {
      pass(`${fileName}: HTTP 200`);
    } else {
      fail(`${fileName}: HTTP ${status} ${error || ''}`);
    }
  }
}

// ─── 主流程 ─────────────────────────────────────────
async function main() {
  console.log('╔══════════════════════════════════════╗');
  console.log('║     🏥 网站健康巡检 (Health Check)   ║');
  console.log('╚══════════════════════════════════════╝');
  console.log(`\n🌐 Base URL: ${BASE_URL}`);
  console.log(`📂 工作目录: ${process.cwd()}`);

  // 扫描本地最新版本号
  const { versionMap, globalLatest } = getLatestVersion();
  console.log(`\n📊 本地JS版本:`);
  for (const [prefix, ver] of Object.entries(versionMap)) {
    console.log(`   ${prefix}: ${ver}`);
  }
  console.log(`   🏆 全局最新: ${globalLatest}`);

  // 执行各项检查
  await checkHtmlVersions(globalLatest);
  await checkMatchScores();
  await checkAnalysisLeak();
  await checkJsReachability(globalLatest);

  // 汇总
  console.log('\n══════════════════════════════════════');
  console.log(`📊 巡检结果: ${passes} 通过, ${warnings} 警告, ${hasError ? '❌ 有错误' : '✅ 全部通过'}`);
  console.log('══════════════════════════════════════\n');

  if (hasError) {
    console.log('⚠️  巡检发现问题，请检查上述错误项！');
    process.exit(1);
  } else if (warnings > 0) {
    console.log('ℹ️  巡检通过，但有警告项需关注。');
    process.exit(0);
  } else {
    console.log('✅ 巡检全部通过！');
    process.exit(0);
  }
}

main().catch(err => {
  console.error('💥 巡检脚本异常:', err);
  process.exit(1);
});
