# judge-repo — OJ 评测仓库

基于 GitHub Actions 批量 worker 模式的在线评测（OJ）沙箱端。

> 本项目与配套服务端（oj-server）构成一个面向**教育与竞赛**的在线评测系统：
> 评测代码全部运行在 GitHub-hosted runner（一次性 VM）上的 Docker 容器中，仅用于"测试软件项目"（在线判题）这一正当用途，任务量自限（服务端限流），详见主 README §8.5 的合规说明。

## 安全宣言（本仓库的底线）

1. **零 secrets**：本仓库不设置任何 repository/organization secrets；
   `GITHUB_TOKEN` 权限最小化（`contents: read`）—— 被评测的恶意代码即使逃逸容器，
   也只能破坏这一台一次性 VM，拿不到任何凭据。
2. **容器只做资源控制，VM 才是安全边界**：`--network none` + 资源限制 + 一次性 VM。
3. **代码注入防护**：用户代码一律 base64/文件方式传递，绝不拼进 shell 命令。

## 目录

```
.github/workflows/   judge.yml(主触发) + watchdog.yml(cron 兜底)
judge/               worker.py 主循环 / sandbox.py 沙箱(核心) / compile.py / report.py / config.py
languages/           各语言编译运行配置（*.yml）
scripts/             entry.sh(workflow 入口) + selftest.sh(本地冒烟)
```

## 本地冒烟测试（不触发真评测）

```bash
bash scripts/selftest.sh
```

## 部署

1. 本目录推送到 GitHub（**建议 public**：Linux 分钟数免费无限，见主 README §7.1）。
2. 服务端 `.env` 配置 `JUDGE_REPO_OWNER/NAME` 后即可 dispatch 触发。
