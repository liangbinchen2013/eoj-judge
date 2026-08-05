# eoj-judge

eoj的后端评测机。

# 配置评测仓库（自研沙箱 Judge）

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
