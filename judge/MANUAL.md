# OJ 评测系统 — 使用手册

> 基于 GitHub Actions 批量 worker 模式的在线评测（OJ）系统。
> 评测代码在 GitHub-hosted runner（一次性 VM）的 Docker 容器中运行，
> 面向教育与竞赛的正当用途。

---

## 目录

1. [系统概览](#1-系统概览)
2. [环境要求](#2-环境要求)
3. [部署指南](#3-部署指南)
4. [配置说明](#4-配置说明)
5. [API 参考](#5-api-参考)
6. [支持的编程语言](#6-支持的编程语言)
7. [评测流程与状态](#7-评测流程与状态)
8. [测试数据格式](#8-测试数据格式)
9. [运维操作](#9-运维操作)
10. [安全模型](#10-安全模型)
11. [故障排查](#11-故障排查)

---

## 1. 系统概览

```
                ┌──────────────────────────────────────┐
用户 ──提交──▶  │            OJ 后端服务器             │
                │  • 提交 API (POST /api/submit)       │
                │  • 评测队列 (SQLite 状态机)           │
                │  • GitHub API 客户端 (dispatch)      │
                │  • 结果回调接收 (POST /api/judge/...) │
                └──────────────┬───────────────────────┘
                               │ workflow_dispatch
                               │ (payload 仅元信息)
                               ▼
                ┌──────────────────────────────────────┐
                │   GitHub Actions — judge-repo        │
                │   • ubuntu-latest (4核/16GB)         │
                │   • 批量 worker (最长 6 小时)         │
                │   • Docker 沙箱运行用户代码           │
                │   • nobody 用户 + 最小权限            │
                └──────────────┬───────────────────────┘
                               │ 结果 JSON 回调
                               │ (一次性 token 鉴权)
                               ▼
                OJ 服务端 → 落库 → 用户查看结果
```

### 核心组件

| 组件 | 位置 | 技术栈 | 职责 |
|---|---|---|---|
| OJ 服务端 | `oj-server/` | Python 3.10+ / FastAPI / SQLite | 提交 API、评测队列、GitHub 触发、结果落库 |
| 评测 Worker | `judge-repo/judge/` | Python 3 (零第三方依赖) | 拉取任务 → 编译 → 沙箱评测 → 回调 |
| 沙箱 | `judge-repo/judge/sandbox.py` | Docker + nobody 用户 | 资源限制、权限最小化、安全隔离 |
| Workflow | `judge-repo/.github/workflows/` | GitHub Actions YAML | 触发、并发控制、超时 |

---

## 2. 环境要求

### OJ 服务端

| 项目 | 要求 |
|---|---|
| 操作系统 | Linux / macOS / Windows (WSL) |
| Python | ≥ 3.10 |
| 依赖 | `pip install -r oj-server/requirements.txt` |
| 网络 | 公网可达（worker 需回调）或内网穿透 |
| 存储 | 建议 ≥ 10GB 可用空间（代码 + 测试数据） |

### 评测仓库 (judge-repo)

| 项目 | 要求 |
|---|---|
| GitHub 仓库 | **public**（推荐，分钟数无限免费） |
| Secrets | **零 secrets**（安全底线） |
| Docker | ubuntu-latest 预装，无需额外配置 |
| Python | ≥ 3.10（runner 预装） |

> **为什么选 public 仓库？** GitHub 对 public 仓库的 Actions 分钟数免费且无上限（Linux/Windows/macOS 全免）。private 仓库每月仅 2,000 分钟。

---

## 3. 部署指南

### 3.1 部署 OJ 服务端

```bash
# 1. 进入服务端目录
cd oj-server

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env —— 必须填写以下项:
#   GITHUB_TOKEN      GitHub Personal Access Token 或 GitHub App token
#   JUDGE_REPO_OWNER  GitHub 用户名/组织名
#   JUDGE_REPO_NAME   评测仓库名（如 judge-repo）
#   JUDGE_WORKER_KEY  运行 python -c "import secrets; print(secrets.token_urlsafe(32))" 生成
#   OJ_PUBLIC_URL     服务端公网地址（如 https://oj.example.com）

# 4. 创建数据目录
mkdir -p data/storage

# 5. 启动服务
python -m app.main
# 或使用 uvicorn:
# uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3.2 部署评测仓库

```bash
# 1. 进入评测仓库目录
cd judge-repo

# 2. 初始化为 Git 仓库
git init
git add .
git commit -m "init: OJ judge repo"

# 3. 推送到 GitHub（建议 public）
gh repo create judge-repo --public --source . --push
# 或手动: git remote add origin https://github.com/YOU/judge-repo.git
#         git push -u origin main

# 4. 确认仓库 Settings:
#    - Secrets: 无任何 secrets
#    - Actions > General > Workflow permissions:
#      ☑ Read repository contents permission only
```

### 3.3 部署后验证

```bash
# 1. 健康检查
curl http://127.0.0.1:8000/healthz
# 返回: {"status":"ok"}

# 2. 提交测试
curl -X POST http://127.0.0.1:8000/api/submit \
  -F "problem_id=p1001" \
  -F "language=cpp" \
  -F "code=@test_code.zip"

# 3. 查看日志
tail -f /var/log/oj-server.log  # 或查看控制台输出
```

---

## 4. 配置说明

### 服务端环境变量 (`.env`)

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OJ_HOST` | `0.0.0.0` | 监听地址 |
| `OJ_PORT` | `8000` | 监听端口 |
| `OJ_PUBLIC_URL` | `http://127.0.0.1:8000` | **公网可达地址**（worker 回调用，生产必须设） |
| `DB_PATH` | `./data/judge.db` | SQLite 数据库路径 |
| `STORAGE_DIR` | `./data/storage` | 代码/测试数据存储目录（权限 700） |
| `GITHUB_TOKEN` | — | **必填** GitHub PAT 或 App token (`actions: write`) |
| `JUDGE_REPO_OWNER` | — | **必填** GitHub 用户名 |
| `JUDGE_REPO_NAME` | — | **必填** 评测仓库名 |
| `JUDGE_WORKER_KEY` | — | **必填** Worker 鉴权密钥（≥16 字符，`secrets.token_urlsafe(32)` 生成） |
| `ADMIN_KEY` | — | 管理端点鉴权密钥（可选，未设则管理端点不可用） |
| `RATE_LIMIT_SUBMIT_INTERVAL_S` | `10` | 单用户提交最小间隔（秒） |
| `RATE_LIMIT_MAX_INFLIGHT` | `3` | 单用户最大并发评测数 |
| `TOKEN_TTL_S` | `900` | 一次性 token 有效期（秒） |
| `JUDGE_TIMEOUT_S` | `600` | 评测超时兜底（秒，超时后任务回队重试） |
| `MAX_RETRY_COUNT` | `3` | 最大重试次数（超限标记 SE） |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |

### Worker 参数（`judge-repo/judge/config.py`）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `poll_interval_s` | `5` | 轮询间隔（秒） |
| `idle_exit_after_s` | `180` | 连续空闲后自动退出（秒，防深夜空转） |
| `heartbeat_interval_s` | `30` | 心跳间隔（秒） |
| `output_limit_bytes` | `10_000_000` | 单用例输出上限（10MB，超限截断） |
| `compile_timeout_s` | `30` | 编译超时（秒） |

---

## 5. API 参考

### 用户面

#### `POST /api/submit` — 提交代码

```
Content-Type: multipart/form-data

参数:
  problem_id  (form)  题目 ID，字母数字+下划线+连字符，≤64 字符
  language    (form)  编程语言，见 §6
  code        (file)  代码 zip 包，≤ 1MB

响应 200:
  {"submission_id": "s_20260804_120000_a1b2c3d4", "status": "QUEUED"}

错误:
  400  语言不支持 / 代码为空 / 代码过大 / 题目不存在
  413  请求体超过 2MB
  429  提交过于频繁（含 Retry-After 头）
```

#### `GET /api/submission/{submission_id}` — 查询结果

```
响应 200:
  {
    "submission_id": "s_...",
    "problem_id": "p1001",
    "language": "cpp",
    "status": "AC",
    "time_ms": 356,
    "memory_kb": 12800,
    "created_at": "2026-08-04 12:00:00",
    "updated_at": "2026-08-04 12:00:05"
  }

错误:
  400  非法 submission_id
  404  提交不存在
```

### Worker 面（需要鉴权）

#### `GET /api/judge/poll?key=<worker_key>` — 拉取任务

```
鉴权: worker_key (query 参数)

响应 200:
  有任务: {"task": {submission_id, problem_id, language, time_limit_ms,
                     memory_limit_mb, code_url, testdata_url, token, callback_url}}
  无任务: {"task": null}

错误:
  403  key 无效（不区分原因）
```

#### `POST /api/judge/report` — 回调结果

```
Content-Type: application/json
鉴权: 一次性 token（body 内 "token" 字段），用后即焚

请求体:
  {
    "submission_id": "s_...",
    "token": "<一次性token>",
    "status": "AC",
    "time_ms": 356,
    "memory_kb": 12800,
    "compile_output": "",
    "cases": [{"id": 1, "status": "AC", "time_ms": 120, "memory_kb": 8000}]
  }

响应 200:
  {"ok": true, "status": "AC"}           // 首次落库
  {"ok": true, "ignored": true, ...}     // 幂等（重复回调）

错误:
  400  JSON 格式错误 / payload 过大 / status 枚举无效
  403  token 无效/已用/过期
```

#### `POST /api/judge/heartbeat` — 心跳

```
Content-Type: application/json
鉴权: worker_key（body 内 "worker_key" 字段）

请求体:
  {"worker_id": "gha-123456", "queue_remaining": 0, "worker_key": "..."}

响应 200:
  {"ok": true, "dispatch_needed": false}
```

#### `GET /judge/data/{submission_id}/{kind}?token=...` — 下载

```
kind: code | tests
鉴权: 一次性 token（query 参数），用后即焚

响应 200:
  Content-Type: application/octet-stream
  Content-Disposition: attachment; filename="s_xxx_code.zip"

错误:
  403  统一 403（不区分 token 无效/文件不存在）
```

### 管理面（需要 ADMIN_KEY）

#### `GET /api/admin/queue` — 队列统计

```
请求头: X-Admin-Key: <ADMIN_KEY>
响应: {"total": 42, "by_status": {"QUEUED": 5, "JUDGING": 3, "AC": 30, ...}}
```

#### `GET /api/admin/workers` — Worker 列表

```
请求头: X-Admin-Key: <ADMIN_KEY>
响应: [{"worker_id": "gha-...", "last_heartbeat_at": "...", "queue_remaining": 0, "ip": "..."}]
```

#### `POST /api/admin/requeue` — 手动回队

```
请求头: X-Admin-Key: <ADMIN_KEY>
请求体: {"submission_id": "s_xxx"}
```

#### `POST /api/admin/cancel` — 取消提交

```
请求头: X-Admin-Key: <ADMIN_KEY>
请求体: {"submission_id": "s_xxx"}
```

---

## 6. 支持的编程语言

| 标识 | 语言 | 编译命令 | 运行命令 | 内存系数 |
|---|---|---|---|---|
| `c` | C (C11) | `gcc -std=c11 -O2 -o main main.c -lm` | `./main` | 1.0 |
| `cpp` | C++ (C++17) | `g++ -std=c++17 -O2 -o main main.cpp` | `./main` | 1.0 |
| `python` | Python 3 | 无 | `python3 -B main.py` | 2.0 |
| `java` | Java | `javac Main.java` | `java -Xmx256m Main` | 1.5 |
| `go` | Go | `go build -o main main.go` | `./main` | 1.0 |
| `rust` | Rust | `rustc -O -o main main.rs` | `./main` | 1.0 |
| `javascript` | JavaScript (Node.js) | 无 | `node main.js` | 1.5 |

所有语言使用预置白名单 Docker 镜像编译运行，版本以 `judge-repo/languages/*.yml` 为准。

---

## 7. 评测流程与状态

### 状态机

```
QUEUED → JUDGING → AC|WA|TLE|MLE|RE|CE|SE|SKIP
   ↑        │
   └────────┘ (requeue_stale, retry_count < 3)
```

### 状态说明

| 状态 | 含义 | 触发条件 |
|---|---|---|
| `QUEUED` | 排队中 | 提交后立即进入 |
| `JUDGING` | 评测中 | Worker 认领后 |
| `AC` | 通过 | 所有用例通过 |
| `WA` | 答案错误 | 输出与预期不符 |
| `TLE` | 超时 | 运行超过时间限制 |
| `MLE` | 内存超限 | 内存超过限制 |
| `RE` | 运行错误 | 非零退出码（除零/段错误等） |
| `CE` | 编译错误 | 编译失败 |
| `SE` | 系统错误 | 重试超限 / Worker 失联 |
| `SKIP` | 已取消 | 用户或管理员取消 |

### 超时体系（三层）

| 层级 | 手段 | 作用 |
|---|---|---|
| 单用例 | 容器内 `ulimit -t` + `timeout -s KILL` | 毫秒级时间限制 |
| 整次评测 | job `timeout-minutes`（batch: 360 / single: 10） | 防 worker 卡死 |
| 服务端 | `requeue_stale`（JUDGING 超时 → 回队） | 防 worker 失联 |

---

## 8. 测试数据格式

### code.zip

```
main.cpp     (或其他语言的 source_file)
```

文件名由 `languages/<lang>.yml` 的 `source_file` 字段指定。

### tests.zip

标准格式：
```
in/1.txt      ← 第 1 个用例的输入
out/1.txt     ← 第 1 个用例的预期输出
in/2.txt
out/2.txt
...
```

Special Judge（SPJ）：
```
in/1.txt      ← 输入
out/1.txt     ← 预期输出
spj           ← SPJ 可执行文件（需编译为 ELF）
```

### 管理端上传测试数据

```bash
# 将 tests.zip 上传为题目 p1001 的测试数据
curl -X POST http://127.0.0.1:8000/api/admin/upload_testdata \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -F "problem_id=p1001" \
  -F "tests=@tests.zip"
```

---

## 9. 运维操作

### 查看队列状态

```bash
curl http://127.0.0.1:8000/api/admin/queue \
  -H "X-Admin-Key: $ADMIN_KEY"
```

### 查看活跃 Worker

```bash
curl http://127.0.0.1:8000/api/admin/workers \
  -H "X-Admin-Key: $ADMIN_KEY"
```

### 手动触发 Worker

若队列有任务但无活跃 Worker（如 watchdog 未覆盖）：

```bash
# 重新 dispatch batch worker
curl -X POST http://127.0.0.1:8000/api/admin/requeue \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"submission_id": "s_xxx"}'
```

### 取消提交

```bash
curl -X POST http://127.0.0.1:8000/api/admin/cancel \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"submission_id": "s_xxx"}'
```

### 轮换 Worker Key

```bash
# 1. 生成新 key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. 更新 .env 中的 JUDGE_WORKER_KEY

# 3. 重启 oj-server
# 旧 key 立即失效，已 dispatch 的 worker 会因鉴权失败而退出

# 4. 队列中有任务时，下一次 requeue_stale 扫描会自动重新 dispatch
```

### 运行本地冒烟测试

```bash
cd judge-repo
# 本地验证沙箱判定正确性（需要 Docker）
bash scripts/selftest.sh
```

### 运行 API 测试

```bash
cd oj-server
pip install -r requirements.txt
python -m pytest tests/ -v
```

---

## 10. 安全模型

### 核心原则

```
容器隔离 ≠ 安全边界
VM 一次性 + 仓库零 secrets = 真正的安全边界
容器职责 = 资源计费 + 进程控制
```

### 五层防护

| 层级 | 机制 | 效果 |
|---|---|---|
| **1. 网络隔离** | `docker --network none` | 恶意代码无法外联、无法回连内网 |
| **2. 用户降权** | 容器内以 `nobody` (UID 65534) 运行 | 无 root、无 sudo、无 capabilities |
| **3. 文件系统** | 根文件系统只读 + 代码/输入只读挂载 | 无法修改系统文件、无法读取数据库/secrets |
| **4. 资源限制** | `--memory` / `--cpus` / `--pids-limit` / `ulimit` | 防资源耗尽、fork 炸弹 |
| **5. 权限剥离** | 可执行文件 `chmod 500`（r-x------） | 无法自修改、无法被其他进程读写 |

### 凭据安全

| 凭据 | 存储位置 | 使用方式 |
|---|---|---|
| `GITHUB_TOKEN` | 仅服务端 `.env`（不入库） | GitHub API 客户端 |
| `JUDGE_WORKER_KEY` | 服务端 `.env` → dispatch inputs → worker 环境变量 | 常量时间比较 |
| 一次性 `token` | DB 仅存 SHA-256 哈希 | 用后即焚，原子消费 |
| `ADMIN_KEY` | 仅服务端 `.env` | 管理端点鉴权 |
| 评测仓库 | **零 secrets** | `permissions: {contents: read}` |

### 审计建议

- 定期检查 GitHub Actions 分钟用量：`gh api /repos/:owner/:repo/actions/workflows`
- 监控 `/api/admin/queue` 中 QUEUED 堆积量
- 开启 `LOG_LEVEL=DEBUG` 排查异常后及时恢复 INFO
- Worker 空闲自动退出 (`idle_exit_after_s=180`)，避免深夜空转

---

## 11. 故障排查

### Worker 不启动

```
症状: 提交后状态一直是 QUEUED
排查:
  1. 检查 GITHUB_TOKEN 是否有效: curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/repos/$OWNER/$REPO/actions/workflows
  2. 检查仓库 Settings > Actions > General > Workflow permissions 是否为 Read-only
  3. 查看 GitHub Actions 页面是否有失败的 workflow run
  4. 检查 OJ_PUBLIC_URL 是否公网可达
```

### 评测全部返回 SE

```
症状: 提交快速变为 SE
排查:
  1. Worker 下载失败: 检查 STORAGE_DIR 权限（应为 700）
  2. 测试数据是否已上传: ls data/storage/{problem_id}/tests.zip
  3. Worker 编译失败: 检查 Docker 镜像是否已拉取
  4. 查看 Worker 日志（GitHub Actions run 页面）
```

### 数据库锁定

```
症状: 服务端 500 错误
排查:
  1. SQLite 在 WAL 模式下一般无需额外操作
  2. 检查是否有多个 oj-server 进程共享同一 DB_PATH
  3. 生产环境建议迁移到 PostgreSQL
```

### Token 耗尽

```
症状: 回调持续 403
排查:
  1. 检查系统时间是否同步（token 依赖 datetime('now')）
  2. 增大 TOKEN_TTL_S（默认 900s，大测试集可能需要更长）
  3. 检查 tokens 表大小: sqlite3 data/judge.db "SELECT COUNT(*) FROM tokens"
```

---

## 参考链接

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [GitHub-hosted runners 硬件规格](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Actions 使用限制与计费](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [runner-images 预装软件清单](https://github.com/actions/runner-images)

---

*文档版本: 0.1.0 | 更新日期: 2026-08-04*
