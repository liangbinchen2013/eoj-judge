"""滥用控制：提交频率限制 + 每用户并发限制。

基于 SQLite 的轻量限流（生产环境可替换为 Redis）：
  - 提交间隔 ≥ RATE_LIMIT_SUBMIT_INTERVAL_S（按 user_id + IP 双维度滑动窗口）；
  - 每用户 JUDGING 中提交数 ≤ RATE_LIMIT_MAX_INFLIGHT_PER_USER。

关键：不限流的状态下每次提交都会触发 GitHub Actions dispatch，
恶意刷提交 = 烧 GitHub 分钟数 / 触发滥用检测，必须兜住。
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import settings
from .db import execute, query_one


class RateLimitExceeded(Exception):
    """限流命中，携带 retry_after_s。"""

    def __init__(self, retry_after_s: int):
        super().__init__(f"rate limited, retry after {retry_after_s}s")
        self.retry_after_s = retry_after_s


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def check_submit_allowed(user_id: str, ip: str) -> None:
    """提交前校验；超限抛 RateLimitExceeded。

    两个维度都检查：user_id 和 IP。
    """
    now_str = _now()
    interval = settings.rate_limit_submit_interval_s

    for key in (f"user:{user_id}", f"ip:{ip}"):
        row = query_one(
            "SELECT last_used FROM rate_limits WHERE key = ?",
            (key,),
        )
        if row:
            last_used = datetime.strptime(row["last_used"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            elapsed = (datetime.now(timezone.utc) - last_used).total_seconds()
            if elapsed < interval:
                raise RateLimitExceeded(int(interval - elapsed))

    # 更新两个维度的最后使用时间（upsert）
    for key in (f"user:{user_id}", f"ip:{ip}"):
        execute(
            "INSERT INTO rate_limits (key, last_used) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET last_used = excluded.last_used",
            (key, now_str),
        )


def check_inflight_limit(user_id: str) -> None:
    """入队前校验该用户 JUDGING 中提交数；超限抛 RateLimitExceeded。"""
    row = query_one(
        "SELECT COUNT(*) AS cnt FROM submissions WHERE user_id = ? AND status = 'JUDGING'",
        (user_id,),
    )
    if row and row["cnt"] >= settings.rate_limit_max_inflight:
        raise RateLimitExceeded(30)  # 建议 30s 后重试
