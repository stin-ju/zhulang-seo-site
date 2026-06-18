#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"

cd "${COZE_WORKSPACE_PATH}"

echo "Installing dependencies..."
pnpm install --prefer-frozen-lockfile --prefer-offline --reporter=append-only

echo "Building frontend with Vite..."
pnpm vite build

echo "Build completed successfully!"
echo "Server will be run via tsx at start time (no bundling needed)."
