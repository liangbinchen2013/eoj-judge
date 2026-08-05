# OJ System

这是一个基于 Cloudflare Workers 的在线判题系统，覆盖题目管理、用户认证、提交评测、竞赛、讨论、题单、后台管理与可选广告位配置。

> **UI 主题**：本仓库提供三种前端视觉风格，可通过 `frontend/config.yaml` 中的 `site.theme` 字段切换：
> - **`default`**（默认）— 暗色为主，大圆角（10px），靛蓝渐变强调色，全宽导航栏
> - **`luogu`** — 洛谷风格复刻，50px 蓝粉渐变顶栏 + 240px 左侧边栏双栏布局，9 级难度色板，3-4px 小圆角扁平设计
> - **`hydro`** — HydroOJ 风格，蓝色主调 `#5f9fd6`，完全扁平（border-radius: 0），极简设计，浅灰背景


## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite |
| 后端 | Hono (Cloudflare Workers) |
| 数据库 | Cloudflare D1 (SQLite) |
| 认证 | GitHub OAuth + CpOAuth + JWT + bcrypt |
| 状态管理 | Zustand |
| 代码编辑器 | CodeMirror 6 |
| 评测引擎 | 自研沙箱 Judge（Docker 沙箱 worker + GitHub Actions 触发） |
| 样式 | CSS Variables + 自定义 CSS |

## 部署指南

### 前置要求

- Node.js >= 18
- [Cloudflare 账号](https://dash.cloudflare.com/sign-up)
- [GitHub 账号](https://github.com)（用于 OAuth 和评测引擎）
- Wrangler CLI：`npm install -g wrangler`

### 第一步：创建 Cloudflare D1 数据库

```bash
# 登录 Cloudflare
wrangler login

# 创建 D1 数据库
wrangler d1 create oj-database
```

执行后会输出 `database_id`，记录下来。

### 第二步：配置 wrangler.toml

编辑 `backend/wrangler.toml`，填入你的配置：

```toml
name = "oj-backend"
main = "src/index.ts"
compatibility_date = "2024-01-01"
account_id = "你的 Cloudflare Account ID"

[[d1_databases]]
binding = "DB"
database_name = "oj-database"
database_id = "上一步获取的 database_id"

[assets]
directory = "./public"
binding = "ASSETS"
not_found_handling = "single-page-application"

[vars]
GITHUB_CLIENT_ID = "你的 GitHub OAuth Client ID"
GITHUB_CLIENT_SECRET = "你的 GitHub OAuth Client Secret"
CPOAUTH_CLIENT_ID = "你的 CpOAuth Client ID（可选）"
CPOAUTH_CLIENT_SECRET = "你的 CpOAuth Client Secret（可选）"
JWT_SECRET = "用 openssl rand -base64 32 生成的密钥"
CALLBACK_SECRET = "用 openssl rand -base64 32 生成的密钥"
GITHUB_TOKEN = "你的 GitHub PAT（需 repo 权限，用于触发评测）"
JUDGE_REPO = "your-username/oj-judge"
FRONTEND_URL = "https://你的域名"
REGISTRATION_OPEN = "true"
```

> **安全提示**：敏感信息（如 `GITHUB_CLIENT_SECRET`、`JWT_SECRET`）建议使用 `wrangler secret put` 设置，而非明文写在 wrangler.toml 中。

### 第三步：执行数据库迁移

```bash
cd backend
npx wrangler d1 migrations apply oj-database --remote
```

此命令会自动检测 `migrations/` 目录下未应用的迁移文件并按顺序执行。

> **注意**：迁移文件必须按编号顺序存放在 `migrations/` 目录中，Wrangler 会自动跟踪已应用的迁移。

### 第四步：创建 GitHub OAuth App

前往 [GitHub Developer Settings](https://github.com/settings/developers) 创建 OAuth App：

| 字段 | 值 |
|------|-----|
| Application name | OJ System |
| Homepage URL | `https://你的域名` |
| Authorization callback URL | `https://你的域名/api/v1/auth/github/callback` |

记录 **Client ID** 和 **Client Secret**，填入 wrangler.toml。

### 第五步：配置站点自定义（可选）

编辑 `frontend/config.yaml`：

```yaml
site:
  name: "My OJ"              # 站点名称
  short_name: "MyOJ"          # 站点简称
  description: "My Online Judge"
  icon: "default"             # "default" 使用内置图标，或填入图标 URL
  favicon: "/favicon.svg"

footer:
  enabled: true
  text: ""                    # 自定义页脚文本（支持 HTML），为空则显示 © 年份 站点名
  links:                      # 页脚链接
    - name: "GitHub"
      url: "https://github.com/your-org"

login:
  hero_title: ""              # 登录页大标题，为空使用默认
  hero_subtitle: ""           # 登录页副标题，为空使用默认
  show_github: true           # 是否显示 GitHub 登录按钮
  show_cpoauth: true          # 是否显示 CpOAuth 登录按钮

home:
  title: ""                   # 首页标题，为空使用默认
```

### 第六步：构建前端

```bash
cd frontend
npm install
npm run build:site
```

此命令会：
1. 编译 TypeScript 并构建前端
2. 将 `dist/` 内容自动复制到 `backend/public/`

### 第七步：部署后端

```bash
cd backend
npm install
npx wrangler deploy --config wrangler.toml
```

部署完成后，访问 Worker URL 即可看到完整站点。

### 第八步：配置评测仓库（自研沙箱 Judge）

本仓库内置自研评测机代码（`judge-repo/`）：**Docker 沙箱 worker + FastAPI 评测服务器**，替代原易受攻击的裸 `ulimit` 评测脚本。安全要点：

- 用户代码在 Docker 容器内运行：`--network none`（无法外联）+ `nobody` 用户 + 只读文件系统
- 评测仓库**零 secrets**，`GITHUB_TOKEN` 仅 `contents: read` —— 恶意代码即使逃逸容器，也拿不到任何凭据
- 评测按需在 GitHub 一次性 VM 上进行（或常驻评测机，见下文「评测机部署」）

1. 将 `judge-repo/` 推送到 GitHub（**建议 public**：Linux Actions 分钟数免费且无限；private 每月仅 2,000 分钟）：

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

### 第九步：初始化管理员

首次部署后，通过 D1 控制台或 SQL 将用户提升为管理员：

```sql
UPDATE users SET role = 'admin', permissions = '["contest_admin","problem_admin","list_admin","ticket_admin"]' WHERE username = '你的用户名';
```

也可通过 `__seed` 端点插入示例数据：

```bash
curl https://你的域名/__seed
```

### 评测机部署（自研 Judge）

评测机 = 运行用户代码的沙箱环境。本系统提供两种模式，任选其一。

#### 模式 A：GitHub Actions 评测（默认，零部署）

无需任何服务器。每次提交时 GitHub 在**一次性 VM** 上临时启动评测机（FastAPI judge-server + Docker 沙箱 worker），评完即销毁：

- 用户代码无法外联网络（`--network none`），无法回连内网
- 以 `nobody` 用户 + 只读根文件系统运行，权限最小化
- 评测仓库零 secrets —— 恶意代码即使逃逸容器，也只能破坏这台一次性 VM

完成第八步后即已启用，**无需任何额外操作**。

#### 模式 B：自托管评测机（常驻服务器）

适合评测量大、追求更低排队时延的场景。部署一台评测机，所有评测在其上排队执行。

**1. 准备评测机**

| 要求 | 说明 |
|------|------|
| 操作系统 | Ubuntu 22.04+（或其他 Linux） |
| Docker | ≥ 24（沙箱依赖，`docker version` 可跑通） |
| Python | ≥ 3.10 |

**2. 部署评测服务器（oj-server）**

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

### 站点设置（管理页面）

部署后，管理员可在后台 **站点设置** 标签页配置：

| 设置项 | 说明 | 默认值 |
|--------|------|--------|
| 开启注册 | 关闭后新用户无法注册 | 开启 |
| 强制填写邮箱 | 注册时邮箱为必填项 | 关闭 |
| 邮箱后缀限制 | 允许的邮箱后缀（逗号分隔），留空不限制 | 空 |

## 本地开发

```bash
# 终端 1：后端
cd backend
npm install
npm run dev
# → http://localhost:8787

# 终端 2：前端
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

本地开发时前端会自动代理 API 请求到后端。

### 本地数据库迁移

```bash
cd backend
# 查看待应用的迁移
npx wrangler d1 migrations list DB --local
# 应用迁移到本地 D1
npx wrangler d1 migrations apply DB --local
# 执行 SQL 查询
npx wrangler d1 execute DB --local --command "SELECT COUNT(*) as cnt FROM users"
```

## 功能特性

| 功能模块 | 说明 |
|---------|------|
| 题目管理 | CRUD、测试用例管理、SPJ、难度标签、通过率统计 |
| 提交评测 | 代码提交、GitHub Actions 异步判题、SPJ 支持、判题详情 |
| 竞赛系统 | ACM/IOI 计分、虚拟参赛、Rating 计算、排行榜(15s轮询)、封榜 |
| 用户系统 | GitHub/CpOAuth/密码登录、个人资料编辑、用户关注、封禁系统 |
| 题单 | 题目集合 CRUD、排序、分享 |
| 题解 | 发布、投票(赞/踩)、审核工作流 |
| 讨论区 | 题目关联讨论、全局讨论、回复 |
| 工单系统 | 分类工单、处理状态流转、管理员处理 |
| 团队功能 | 团队管理、团队竞赛、题目集 |
| 博客 | 发布/编辑、标签、评论、状态管理 |
| 代码模板 | 多语言模板保存/加载、题目编辑器集成 |
| 笔记 | 题目笔记、公开/私有 |
| 收藏集 | 题目收藏夹、自定义集合 |
| 训练计划 | 章节化训练、进度追踪 |
| AI 助手 | 流式对话、工具调用、多模型支持 |
| 通知系统 | SSE 实时推送 + 轮询回退、邮件通知 |
| 消息系统 | 站内私信、会话管理 |
| 成就系统 | 成就解锁、展示 |
| 全站搜索 | 题目/用户/博客/讨论多类型搜索、关键词高亮、搜索建议 |
| 管理后台 | 仪表盘(图表统计)、用户/题目/竞赛/工单/封禁管理、SQL 编辑器 |
| 权限体系 | 细粒度权限(problem_admin/contest_admin 等) + 超级管理员 |
| 审计日志 | 操作记录、IP/设备封禁、审计搜索 |
| 站点设置 | 注册开关、邮箱限制、OAuth 配置、广告位配置 |
| 广告位 | Adsense 集成、多位置配置 |
| 安全防护 | JWT 认证、bcrypt 密码、验证码、Rate Limit、CORS、安全响应头 |
| 多主题 | Default(暗色)/Luogu(洛谷复刻)/Hydro(HydroOJ) 三套风格 |
| 国际化 | 中英文双语 i18n |
| 密码重置 | 邮箱验证码、忘记密码/重置密码流程 |

## API 概览

所有接口返回统一格式：`{ success: true, data: {...} }` 或 `{ success: false, error: { message, code } }`

| 模块 | 路径前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/v1/auth` | GitHub/CpOAuth OAuth、注册、登录 |
| 题目 | `/api/v1/problems` | 题目 CRUD、收藏、统计 |
| 提交 | `/api/v1/submissions` | 代码提交、结果查询 |
| 用户 | `/api/v1/users` | 用户资料、已解决题目 |
| 排名 | `/api/v1/rankings` | 全站排行榜 |
| 竞赛 | `/api/v1/contests` | 竞赛管理、参与、排行 |
| 题单 | `/api/v1/lists` | 题单 CRUD |
| 题解 | `/api/v1/solutions` | 题解发布、投票 |
| 讨论 | `/api/v1/discussions` | 讨论区 |
| 工单 | `/api/v1/tickets` | 工单提交、处理 |
| 设置 | `/api/v1/settings` | 站点配置读写 |
| 管理 | `/api/v1/admin` | 管理员专用接口 |
| 内部 | `/api/v1/internal` | 评测回调（GitHub Actions 调用） |

## 数据库表

| 表名 | 说明 |
|------|------|
| users | 用户（GitHub/CpOAuth/密码认证） |
| problems | 题目 |
| testcases | 测试用例 |
| submissions | 提交记录 |
| favorites | 收藏 |
| contests | 竞赛 |
| contest_problems | 竞赛题目关联 |
| contest_participants | 竞赛参与者 |
| tickets | 工单 |
| ticket_replies | 工单回复 |
| problem_lists | 题单 |
| problem_list_items | 题单题目关联 |
| solutions | 题解 |
| solution_votes | 题解投票 |
| discussions | 讨论 |
| discussion_replies | 讨论回复 |
| rate_limits | 限流记录 |
| settings | 站点设置（键值对） |

## License

MIT
