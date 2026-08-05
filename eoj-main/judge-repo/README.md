# judge-repo — OJ 评测仓库（自研沙箱 Judge，适配 eoj-main）

基于 GitHub Actions + Docker 沙箱的在线评测（OJ）评测端，替换 eoj-main 原裸 `ulimit` 评测脚本。

> 评测代码全部运行在 GitHub-hosted runner（一次性 VM）上的 Docker 容器中，面向**教育与竞赛**的正当用途。
> 安全模型：容器只做资源控制，**VM 一次性 + 零 secrets 才是真正的安全边界**。

## 与旧 judge.sh 的关键区别（为什么换掉它）

| | 旧 judge.sh | 自研 Judge |
|---|---|---|
| 隔离 | 裸 runner + `ulimit`，无沙箱 | Docker 沙箱：`--network none` + `nobody` 用户 + 只读根文件系统 |
| 编译器 | 评测时 `apt-get` 现装（慢、可被污染） | 预构建白名单镜像（`gcc:13-bookworm`、`temurin:21` 等，见 `languages/*.yml`） |
| 资源限制 | 单层 ulimit | 容器 `--memory`/`--cpus`/`--pids-limit`/`ulimit` 多层 |
| 凭据 | 无 | 零 secrets，`GITHUB_TOKEN` 仅 `contents: read` |

## 目录

```
.github/workflows/   judge.yml(主触发，push on submissions/*) + watchdog.yml(cron 兜底)
oj-server/           评测服务器 (FastAPI)：提交 API / 队列状态机 / eoj 桥接端点 / 管理端点
judge/               worker.py 主循环 / sandbox.py 沙箱(核心) / compile.py / report.py / config.py
languages/           各语言编译运行配置（*.yml）
scripts/             entry.sh(worker 入口) + eoj_bridge.sh(EOJ 桥接) + selftest.sh(本地冒烟)
submissions/         eoj-main 后端推送的用户代码（push 到此触发评测）
```

## 评测链路

```
eoj-main 后端 ──push 源码文件──▶ submissions/{id}.{ext}
        │ push 触发 judge.yml
        ▼
runner：启动 oj-server(本机) 或 连接常驻评测机(JUDGE_SERVER_URL)
        → scripts/eoj_bridge.sh 拉取 judge-data → 上传测试数据 → 提交代码
        → worker 用 Docker 沙箱评测 → 轮询结果 → 格式转换
        ▼
eoj-main POST /api/v1/internal/callback 落库
```

## 本地冒烟测试（不触发真评测）

```bash
bash scripts/selftest.sh
```

## 部署

1. 本目录（含 `oj-server/`）推送到 GitHub，作为 eoj-main 的评测仓库。
2. 在仓库 **Settings → Secrets and variables → Actions** 配置：

   | 类型 | 名称 | 值 |
   |---|---|---|
   | Secret | `CALLBACK_SECRET` | 与 eoj-main `wrangler.toml` 中一致 |
   | Variable | `WORKER_API` | eoj-main 后端地址（如 `https://oj.example.com`） |
   | Variable | `JUDGE_SERVER_URL` | （可选）常驻评测机地址，如 `http://1.2.3.4:8000`；不设则用 runner 本机临时评测 |

3. 完整步骤见主 README「评测机部署」章节。
