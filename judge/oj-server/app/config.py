"""集中配置：从环境变量 / .env 读取全部运行参数。
启动时校验关键项：GITHUB_TOKEN、JUDGE_WORKER_KEY 必须非空。
JUDGE_WORKER_KEY 只用于"服务端 → dispatch inputs → worker"单向下发，
绝不允许出现在日志中（零 secrets 原则）。

兼容 eoj-main：
  - CALLBACK_SECRET: eoj-main 回调鉴权密钥
  - EOJ_API_URL: eoj-main 后端地址
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # --- 基础 ---
    host: str = os.getenv("OJ_HOST", "0.0.0.0")
    port: int = int(os.getenv("OJ_PORT", "8000"))
    public_url: str = os.getenv("OJ_PUBLIC_URL", "http://127.0.0.1:8000")

    # --- 存储 ---
    db_path: str = os.getenv("DB_PATH", "./data/judge.db")
    storage_dir: str = os.getenv("STORAGE_DIR", "./data/storage")

    # --- GitHub ---
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    judge_repo_owner: str = os.getenv("JUDGE_REPO_OWNER", "")
    judge_repo_name: str = os.getenv("JUDGE_REPO_NAME", "")
    judge_workflow_file: str = os.getenv("JUDGE_WORKFLOW_FILE", "judge")
    judge_repo_ref: str = os.getenv("JUDGE_REPO_REF", "main")

    # --- Worker 鉴权 ---
    judge_worker_key: str = os.getenv("JUDGE_WORKER_KEY", "")

    # --- Admin 鉴权 ---
    admin_key: str = os.getenv("ADMIN_KEY", "")

    # --- eoj-main 兼容配置 ---
    eoj_api_url: str = os.getenv("EOJ_API_URL", "")
    callback_secret: str = os.getenv("CALLBACK_SECRET", "")

    # --- 限制 ---
    rate_limit_submit_interval_s: int = int(os.getenv("RATE_LIMIT_SUBMIT_INTERVAL_S", "10"))
    rate_limit_max_inflight: int = int(os.getenv("RATE_LIMIT_MAX_INFLIGHT_PER_USER", "3"))
    token_ttl_s: int = int(os.getenv("TOKEN_TTL_S", "900"))
    judge_timeout_s: int = int(os.getenv("JUDGE_TIMEOUT_S", "600"))
    max_code_bytes: int = int(os.getenv("MAX_CODE_BYTES", "1_000_000"))
    max_testdata_bytes: int = int(os.getenv("MAX_TESTDATA_BYTES", "64_000_000"))

    # --- 日志 ---
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # 重试上限
    max_retry_count: int = int(os.getenv("MAX_RETRY_COUNT", "3"))

    # 语言支持（服务端只做透传白名单校验，编译/运行细节在 judge-repo 的 languages/*.yml）
    supported_languages: list[str] = field(
        default_factory=lambda: ["c", "cpp", "python", "java", "go", "rust", "javascript"]
    )

    def validate(self) -> list[str]:
        """启动时校验关键配置项；返回错误列表（空=通过）。"""
        errors: list[str] = []
        if not self.github_token:
            errors.append("GITHUB_TOKEN 未设置 — 无法触发 GitHub Actions dispatch")
        if not self.judge_repo_owner:
            errors.append("JUDGE_REPO_OWNER 未设置")
        if not self.judge_repo_name:
            errors.append("JUDGE_REPO_NAME 未设置")
        if not self.judge_worker_key:
            errors.append("JUDGE_WORKER_KEY 未设置 — worker 鉴权将全部失败")
        if len(self.judge_worker_key) < 16:
            errors.append("JUDGE_WORKER_KEY 过短（<16 字符），安全强度不足")
        if self.public_url == "http://127.0.0.1:8000":
            # 开发环境可接受；生产须替换为公网 https URL
            pass
        return errors


settings = Settings()
