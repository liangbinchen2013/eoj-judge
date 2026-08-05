#!/usr/bin/env bash
# =============================================================================
# EOJ Bridge — 桥接 eoj-main (push触发) 和 自研judge (FastAPI + worker)
#
# 架构:
#   eoj-main push代码到GitHub → 触发本workflow → 本脚本:
#     1. 定位被push的提交文件 → 提取 submission_id + language
#     2. 调 eoj-main API 获取测试数据 (judge-data)
#     3. 上传测试数据到本地 judge-server (JSON→zip)
#     4. 提交代码到本地 judge-server
#     5. 运行 worker 评测
#     6. 轮询结果
#     7. 转换格式并回调 eoj-main /api/v1/internal/callback
#
# 环境变量依赖:
#   EOJ_API_URL      eoj-main 后端地址
#   CALLBACK_SECRET   eoj-main 回调鉴权密钥
#   ADMIN_KEY        judge-server 管理密钥
#   JUDGE_SERVER_URL 本地 judge-server 地址 (默认 http://127.0.0.1:8000)
# =============================================================================
set -euo pipefail

EOJ_API_URL="${EOJ_API_URL:-https://eoj.example.com}"
CALLBACK_SECRET="${CALLBACK_SECRET:-}"
ADMIN_KEY="${ADMIN_KEY:-${CALLBACK_SECRET}}"
JUDGE_SERVER_URL="${JUDGE_SERVER_URL:-http://127.0.0.1:8000}"

# 回调成功标记文件
CALLBACK_SUCCESS_FILE="/tmp/eoj_callback_success"
SUBMISSION_ID_FILE="/tmp/eoj_submission_id"

log() { echo "[bridge] $(date '+%H:%M:%S') $*" >&2; }

# =============================================================================
# 1. 定位提交文件
# =============================================================================
log "定位提交文件..."

# 获取 push 事件中变更的文件
CHANGED_FILES=$(git diff --name-only HEAD^ HEAD 2>/dev/null || git diff --name-only HEAD~1 HEAD 2>/dev/null || echo "")
if [ -z "$CHANGED_FILES" ]; then
  # 备选：查找 submissions/ 下最新文件
  CHANGED_FILES=$(find submissions/ -type f 2>/dev/null | head -1 || echo "")
fi

SUBMISSION_FILE=""
for f in $CHANGED_FILES; do
  if [[ "$f" == submissions/* ]]; then
    SUBMISSION_FILE="$f"
    break
  fi
done

if [ -z "$SUBMISSION_FILE" ]; then
  log "FATAL: 未找到提交文件"
  exit 1
fi

log "提交文件: $SUBMISSION_FILE"

# 解析 submission_id 和语言
FILENAME=$(basename "$SUBMISSION_FILE")
SUBMISSION_ID="${FILENAME%.*}"  # 去掉扩展名
EXT="${FILENAME##*.}"

# 扩展名 → 语言映射
case "$EXT" in
  py)   LANGUAGE="python" ;;
  cpp|cc|cxx) LANGUAGE="cpp" ;;
  java) LANGUAGE="java" ;;
  js)   LANGUAGE="javascript" ;;
  c)    LANGUAGE="c" ;;
  go)   LANGUAGE="go" ;;
  rs)   LANGUAGE="rust" ;;
  *)    log "WARN: 未知扩展名 $EXT，默认 cpp"; LANGUAGE="cpp" ;;
esac

log "submission_id=$SUBMISSION_ID language=$LANGUAGE"
echo "$SUBMISSION_ID" > "$SUBMISSION_ID_FILE"

# =============================================================================
# 2. 从 eoj-main 获取评测数据
# =============================================================================
log "获取评测数据..."

JUDGE_DATA=$(curl -sf \
  "${EOJ_API_URL}/api/v1/internal/judge-data?submission_id=${SUBMISSION_ID}" \
  -H "Authorization: Bearer ${CALLBACK_SECRET}" \
  --max-time 30 2>&1) || {
    log "FATAL: 获取评测数据失败"
    exit 1
  }

# eoj-main 返回格式: {"success": true, "data": {...}}
# 提取 data 字段
JUDGE_DATA_INNER=$(echo "$JUDGE_DATA" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if data.get('success'):
    print(json.dumps(data['data']))
else:
    print('{}')
" 2>/dev/null || echo "{}")

if [ "$JUDGE_DATA_INNER" = "{}" ] || [ -z "$JUDGE_DATA_INNER" ]; then
  log "FATAL: 评测数据为空"
  exit 1
fi

log "评测数据获取成功"

# =============================================================================
# 3. 提取评测参数
# =============================================================================
PROBLEM_SLUG=$(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problem = data.get('problem', {})
print(problem.get('slug', 'unknown'))
")

TIME_LIMIT=$(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problem = data.get('problem', {})
print(problem.get('time_limit', 1000))
")

MEMORY_LIMIT=$(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problem = data.get('problem', {})
print(problem.get('memory_limit', 256))
")

JUDGE_TYPE=$(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problem = data.get('problem', {})
print(problem.get('judge_type', 'default'))
")

SPJ_LANGUAGE=$(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problem = data.get('problem', {})
spj_lang = problem.get('spj_language', '')
print(spj_lang or '')
")

log "problem=$PROBLEM_SLUG time_limit=$TIME_LIMIT ms memory_limit=$MEMORY_LIMIT MB judge_type=$JUDGE_TYPE spj_lang=$SPJ_LANGUAGE"

# =============================================================================
# 4. 上传测试数据到本地 judge-server
# =============================================================================
log "上传测试数据到 judge-server..."

# 从 judge_data 提取 testcases 数组
TESTCASES_JSON=$(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
testcases = data.get('testcases', [])
print(json.dumps(testcases))
")

TESTCASE_COUNT=$(echo "$TESTCASES_JSON" | python3 -c "
import json, sys
print(len(json.load(sys.stdin)))
")

log "测试用例数: $TESTCASE_COUNT"

# 调 judge-server eoj 桥接端点上传测试数据
curl -sf -X POST "${JUDGE_SERVER_URL}/api/eoj/judge-data" \
  -H "X-Admin-Key: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"problem_id\": \"${PROBLEM_SLUG}\",
    \"testcases\": ${TESTCASES_JSON},
    \"spj_code\": $(echo "$JUDGE_DATA_INNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
spj = data.get('spj_code', '')
print(json.dumps(spj) if spj else 'null')
"),
    \"spj_language\": $(echo "$SPJ_LANGUAGE" | python3 -c "import sys; s=sys.stdin.read().strip(); print('null' if not s else '\"'+s+'\"')"),
    \"time_limit_ms\": ${TIME_LIMIT},
    \"memory_limit_mb\": ${MEMORY_LIMIT}
  }" || {
    log "FATAL: 上传测试数据失败"
    exit 1
  }

log "测试数据上传成功"

# =============================================================================
# 5. 提交代码到 judge-server
# =============================================================================
log "提交代码到 judge-server..."

# 读取源代码
SOURCE_CODE=$(cat "$SUBMISSION_FILE")

curl -sf -X POST "${JUDGE_SERVER_URL}/api/submit" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: eoj-user" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'problem_id': '${PROBLEM_SLUG}',
    'language': '${LANGUAGE}',
    'source_code': $(echo "$SOURCE_CODE" | python3 -c "import sys; print(json.dumps(sys.stdin.read()))"),
    'submission_id': '${SUBMISSION_ID}',
    'time_limit_ms': ${TIME_LIMIT},
    'memory_limit_mb': ${MEMORY_LIMIT},
}))
")" > /tmp/submit_response.json || {
    log "FATAL: 提交失败"
    exit 1
  }

log "提交成功: $(cat /tmp/submit_response.json)"

# =============================================================================
# 6. 运行 worker 评测
# =============================================================================
log "启动 worker..."

export OJ_SERVER_URL="${JUDGE_SERVER_URL}"
export JUDGE_WORKER_KEY="${ADMIN_KEY}"
export JUDGE_MODE="single"
export JUDGE_SUBMISSION_ID="${SUBMISSION_ID}"

# 安装 worker 依赖
pip install pyyaml 2>/dev/null || true

# 运行 worker（单发模式，处理指定 submission_id 后退出）
timeout 600 python3 judge/worker.py > /tmp/worker.log 2>&1 &
WORKER_PID=$!

log "worker PID: $WORKER_PID"

# =============================================================================
# 7. 轮询结果
# =============================================================================
log "等待评测结果..."

MAX_WAIT=300  # 最长等 5 分钟
POLL_INTERVAL=2
ELAPSED=0
RESULT_STATUS=""

while [ $ELAPSED -lt $MAX_WAIT ]; do
  # 检查 worker 是否还在运行
  if ! kill -0 $WORKER_PID 2>/dev/null; then
    log "worker 已退出"
    break
  fi

  # 轮询 judge-server 结果
  RESULT=$(curl -sf "${JUDGE_SERVER_URL}/api/submission/${SUBMISSION_ID}" 2>/dev/null || echo "")
  if [ -n "$RESULT" ]; then
    RESULT_STATUS=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    # 检查是否为终态
    case "$RESULT_STATUS" in
      AC|WA|TLE|MLE|RE|CE|SE|SKIP)
        log "评测完成: status=$RESULT_STATUS"
        break
        ;;
    esac
  fi

  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

# 确保 worker 已停止
kill $WORKER_PID 2>/dev/null || true
wait $WORKER_PID 2>/dev/null || true

# =============================================================================
# 8. 获取完整结果并回调 eoj-main
# =============================================================================
log "获取完整评测结果..."

FULL_RESULT=$(curl -sf "${JUDGE_SERVER_URL}/api/submission/${SUBMISSION_ID}" 2>/dev/null || echo "{}")

if [ "$FULL_RESULT" = "{}" ] || [ -z "$FULL_RESULT" ]; then
  log "FATAL: 无法获取评测结果"
  exit 1
fi

log "评测结果: $FULL_RESULT"

# 转换为 eoj-main callback 格式
CALLBACK_PAYLOAD=$(echo "$FULL_RESULT" | python3 -c "
import json, sys

result = json.load(sys.stdin)

# 状态映射: judge → eoj
status_map = {
    'AC': 'accepted', 'WA': 'wrong_answer',
    'TLE': 'time_limit_exceeded', 'MLE': 'memory_limit_exceeded',
    'RE': 'runtime_error', 'CE': 'compile_error',
    'SE': 'system_error', 'SKIP': 'system_error',
    'QUEUED': 'system_error', 'JUDGING': 'system_error',
}

judge_status = result.get('status', 'SE')
eoj_status = status_map.get(judge_status, 'system_error')

# 计算总分（从 cases 中汇总）
cases = result.get('cases', [])
total_score = sum(c.get('score', 0) for c in cases if c.get('status') in ('AC', 'accepted'))

# 转换 details 格式
details = []
for i, c in enumerate(cases):
    details.append({
        'testcase_id': c.get('id', i+1),
        'status': status_map.get(c.get('status', 'SE'), 'system_error'),
        'time_used': c.get('time_ms', 0),
        'memory_used': c.get('memory_kb', 0),
        'score': c.get('score', 0),
        'is_sample': c.get('is_sample', False),
        'message': c.get('message', ''),
        'sort_order': i,
    })

# 构建日志
logs = result.get('logs', [])
if not logs:
    logs = [{'log_type': 'info', 'message': f'Judged by judge-repo worker. Status: {judge_status}'}]

payload = {
    'submission_id': result.get('submission_id', ''),
    'status': eoj_status,
    'score': total_score,
    'time_used': result.get('time_ms', 0),
    'memory_used': result.get('memory_kb', 0),
    'details': details,
    'github_run_id': '${GITHUB_RUN_ID}',
    'logs': logs,
}

print(json.dumps(payload))
")

log "回调 eoj-main..."

# POST 到 eoj-main callback 端点
HTTP_CODE=$(curl -s -o /tmp/callback_response.txt -w '%{http_code}' \
  -X POST "${EOJ_API_URL}/api/v1/internal/callback" \
  -H "Authorization: Bearer ${CALLBACK_SECRET}" \
  -H "Content-Type: application/json" \
  -d "$CALLBACK_PAYLOAD" 2>&1 || echo "000")

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  log "回调成功 (HTTP $HTTP_CODE)"
  touch "$CALLBACK_SUCCESS_FILE"
else
  log "回调失败 (HTTP $HTTP_CODE): $(cat /tmp/callback_response.txt 2>/dev/null)"

  # 重试一次
  sleep 2
  HTTP_CODE2=$(curl -s -o /tmp/callback_response2.txt -w '%{http_code}' \
    -X POST "${EOJ_API_URL}/api/v1/internal/callback" \
    -H "Authorization: Bearer ${CALLBACK_SECRET}" \
    -H "Content-Type: application/json" \
    -d "$CALLBACK_PAYLOAD" 2>&1 || echo "000")

  if [ "$HTTP_CODE2" = "200" ] || [ "$HTTP_CODE2" = "201" ]; then
    log "重试回调成功 (HTTP $HTTP_CODE2)"
    touch "$CALLBACK_SUCCESS_FILE"
  else
    log "重试回调也失败 (HTTP $HTTP_CODE2)"
  fi
fi

log "桥接完成"
