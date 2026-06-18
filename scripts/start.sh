#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"

PORT=5000
DEPLOY_RUN_PORT="${DEPLOY_RUN_PORT:-$PORT}"

cd "${COZE_WORKSPACE_PATH}"

echo "Starting express production server on port ${DEPLOY_RUN_PORT}..."
# 直接用 tsx 运行 TS 源码，避免 tsup/esbuild 试图把 @swc/core 的所有平台 .node
# 二进制都打进 bundle 而失败（部分平台二进制不存在于 node_modules）。
PORT=$DEPLOY_RUN_PORT COZE_PROJECT_ENV=PROD pnpm exec tsx server/server.ts
