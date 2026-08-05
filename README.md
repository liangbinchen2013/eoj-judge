# eoj-judge

eoj的后端评测机。

## 配置评测仓库（自研沙箱 Judge）

本仓库内置自研评测机代码（`judge-repo/`）：**Docker 沙箱 worker + FastAPI 评测服务器**，替代原易受攻击的裸 `ulimit` 评测脚本。安全要点：

- 用户代码在 Docker 容器内运行：`--network none`（无法外联）+ `nobody` 用户 + 只读文件系统
- 评测仓库**零 secrets**，`GITHUB_TOKEN` 仅 `contents: read` —— 恶意代码即使逃逸容器，也拿不到任何凭据
- 评测按需在 GitHub 一次性 VM 上进行（或常驻评测机，见下文「评测机部署」）

1. 将 `judge-repo/` 推送到 GitHub：

```bash
cd judge-repo
git init
git add .
git commit -m "init: secure judge repo"
gh repo create oj-judge --public --source . --push
# 或手动: git remote add origin https://github.com/YOU/oj-judge.git && git push -u origin main
```

2. 在仓库 **Settings → Secrets and variables → Actions** 中配置：

| 类型 | 名称 | 值 |
|------|------|-----|
| Secret | `CALLBACK_SECRET` | 与 wrangler.toml 中的 `CALLBACK_SECRET` 一致 |
| Variable | `WORKER_API` | eoj-main 后端完整 URL（如 `https://oj.your-domain.com`） |
| Variable | `JUDGE_SERVER_URL` | （可选）自托管评测机地址，如 `http://1.2.3.4:8000`；留空则每次评测在 GitHub runner 上临时起评测机 |

> **注意**：`WORKER_API` 是仓库 **Variable** 而非 Secret —— 评测工作流通过 `vars.WORKER_API` 读取。

3. 在仓库 **Settings → Actions → General → Workflow permissions** 确认「Read repository contents permission only」。

4. 确保 wrangler.toml 中的 `JUDGE_REPO` 指向该仓库（如 `"your-username/oj-judge"`）。

**评测触发链路**：用户提交 → 后端把源码 push 到评测仓库 `submissions/{id}.{ext}` → `judge.yml` 被触发 → 拉取题目测试数据 → Docker 沙箱评测 → 结果回调 `/api/v1/internal/callback` 落库。

## 部署评测服务器（oj-server）

```bash
# 从评测仓库获取代码（评测机与本仓库的 judge-repo 同源）
git clone https://github.com/YOU/oj-judge.git
cd oj-judge/oj-server

pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env —— 必填项:
#   JUDGE_WORKER_KEY   运行 python -c "import secrets; print(secrets.token_urlsafe(32))" 生成
#                      （worker 轮询鉴权用；评测机无需 GitHub 相关变量）
#   ADMIN_KEY          必须与 eoj-main 的 CALLBACK_SECRET 一致！
#                      （GitHub workflow 会用它作为 X-Admin-Key 头上传测试数据）
# 可选: EOJ_BRIDGE_MODE=1  跳过 GitHub dispatch（评测机常驻 worker，无需 dispatch）

# 启动（前台验证，Ctrl+C 停止；生产用 systemd/supervisor 守护）
python -m app.main
# 或: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**3. 启动常驻 worker**

```bash
cd oj-judge
OJ_SERVER_URL=http://127.0.0.1:8000 \
JUDGE_WORKER_KEY=<与 .env 中一致> \
JUDGE_MODE=batch \
python3 judge/worker.py
```

**4. 健康检查**

```bash
curl http://127.0.0.1:8000/healthz
# → {"status":"ok"}
```

**5. 接通评测仓库**

在评测仓库 **Settings → Variables** 设置：

| Variable | 值 |
|----------|-----|
| `JUDGE_SERVER_URL` | `http://评测机IP:8000` |

之后每次提交：GitHub workflow 从 eoj-main 拉取测试数据 → 上传到评测机 → 评测机排队评测 → workflow 取回结果并回调 eoj-main。

**6. （可选）本地冒烟测试**

```bash
cd oj-judge
bash scripts/selftest.sh
# 需要 Docker；只验证沙箱判定正确性，不触发真评测
```

#### 部署后验证

```bash
# 1. 健康检查（评测机或 workflow 日志）
curl http://127.0.0.1:8000/healthz

# 2. 在 OJ 前台提交一道题，观察提交状态流转
#    pending → accepted/wrong_answer/...

# 3. 看评测仓库 Actions 页面：push 触发 judge.yml，每次提交一个 run
```
