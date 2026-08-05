"""worker 配置：端点、key 来源、语言表加载。

key 来源（安全设计，docs/PROTOCOL.md §鉴权）:
  - WORKER_KEY 由服务端经 workflow_dispatch inputs 下发 → 环境变量 JUDGE_WORKER_KEY。
    ★ 本仓库零 secrets，不得在任何文件中硬编码 key。
  - 回调/下载 token 由 poll 响应下发，随 JudgeTask 携带，用后即焚。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import yaml


def _load_language_config(lang: str) -> dict | None:
    """加载 languages/<lang>.yml 配置。"""
    lang_dir = os.path.join(os.path.dirname(__file__), "..", "languages")
    path = os.path.join(lang_dir, f"{lang}.yml")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class WorkerConfig:
    server_url: str = os.getenv("OJ_SERVER_URL", "")
    worker_key: str = os.getenv("JUDGE_WORKER_KEY", "")
    mode: str = os.getenv("JUDGE_MODE", "batch")
    submission_id: str = os.getenv("JUDGE_SUBMISSION_ID", "")

    # 轮询参数（空闲策略：空转即退出，由 cron 重启，防滥用）
    poll_interval_s: int = 5
    idle_exit_after_s: int = 180
    heartbeat_interval_s: int = 30

    # 输出/资源上限（防刷爆）
    output_limit_bytes: int = 10_000_000
    result_payload_limit_bytes: int = 1_000_000

    # 编译超时
    compile_timeout_s: int = 30
    compile_memory_mb: int = 512

    # 镜像白名单目录
    language_dir: str = os.path.join(os.path.dirname(__file__), "..", "languages")

    def get_language_config(self, language: str) -> dict | None:
        """获取语言配置（image, compile_cmd, run_cmd, memory_factor, source_file）。"""
        return _load_language_config(language)


# 全局配置实例
config = WorkerConfig()
