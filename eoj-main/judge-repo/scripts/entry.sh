#!/usr/bin/env bash
# workflow 第一步: 环境自检 + 启动 worker（judge.yml 的 run 步骤调用）
# 环境: Ubuntu (GitHub Actions ubuntu-latest)，OJ 后端拥有 root 权限。
# 用法: bash scripts/entry.sh [--watchdog]
set -euo pipefail

echo "[entry] 环境: $(uname -a)"
echo "[entry] 用户: $(whoami) (UID=$(id -u))"
echo "[entry] 环境自检..."

# 1) docker 必须可用（沙箱依赖）
if ! docker version >/dev/null 2>&1; then
  echo "[entry] FATAL: docker 不可用" >&2
  exit 1
fi
echo "[entry] docker OK: $(docker --version)"

# 2) python3 版本检查（Ubuntu 上为 python3）
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[entry] python3 version: $PYVER"
MAJOR=$(echo "$PYVER" | cut -d. -f1)
MINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
  echo "[entry] FATAL: python3 >= 3.10 required, got $PYVER" >&2
  exit 1
fi

# 3) 校验系统工具可用（Ubuntu 环境）
for tool in /usr/bin/time timeout ulimit chmod; do
  if ! command -v "$tool" &>/dev/null; then
    echo "[entry] WARN: $tool 不可用" >&2
  fi
done

# 4) 仓库零 secrets 声明
if env | grep -q '^GITHUB_TOKEN='; then
  echo "[entry] WARN: GITHUB_TOKEN 存在! 评测仓库应零 secrets (permissions: contents: read)" >&2
fi

# 5) 检查服务端 URL
if [ -z "${OJ_SERVER_URL:-}" ]; then
  echo "[entry] WARN: OJ_SERVER_URL 未设置，worker 将无法连接服务端" >&2
fi

# 6) 预拉取白名单镜像缓存（Ubuntu + Docker）
echo "[entry] 预拉取白名单镜像..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LANG_DIR="$SCRIPT_DIR/../languages"
IMAGES=""
if [ -d "$LANG_DIR" ]; then
  for yml in "$LANG_DIR"/*.yml; do
    if [ -f "$yml" ]; then
      img=$(grep -E '^image:' "$yml" | awk '{print $2}' || true)
      if [ -n "$img" ]; then
        IMAGES="$IMAGES $img"
      fi
    fi
  done
fi
# 去重
IMAGES=$(echo "$IMAGES" | tr ' ' '\n' | sort -u | tr '\n' ' ')
for img in $IMAGES; do
  echo "[entry] docker pull $img"
  docker pull "$img" || echo "[entry] WARN: pull $img 失败" >&2
done

# 7) watchdog 模式探测
if [ "${1:-}" == "--watchdog" ]; then
  echo "[entry] watchdog 模式: 探测服务端 worker 存活..."
  if [ -n "${OJ_SERVER_URL:-}" ] && [ -n "${JUDGE_WORKER_KEY:-}" ]; then
    HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 10 \
      "${OJ_SERVER_URL}/api/judge/poll?key=${JUDGE_WORKER_KEY}" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
      echo "[entry] 服务端可达 (HTTP $HTTP_CODE)"
    else
      echo "[entry] 服务端不可达 (HTTP $HTTP_CODE)"
    fi
  fi
fi

echo "[entry] 启动 worker: mode=${JUDGE_MODE:-batch}"
cd "$SCRIPT_DIR/.."
exec python3 judge/worker.py
