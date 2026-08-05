"""鉴权与一次性 token（★ 安全核心）。

两种凭据体系（详见 docs/PROTOCOL.md §鉴权）：
  1. WORKER_KEY —— 服务端每次 dispatch 时经 workflow inputs 下发给 worker，
     只用于 worker 调 poll / heartbeat 接口。不入库、不落 repo、不打日志。
  2. 一次性 token —— poll 下发，随 JudgeTask 交给 worker；
     worker 用它下载 code_url / testdata_url 并回调 report；
     ★ 用后即焚：任何一次使用后立刻失效；过期即失效（TOKEN_TTL_S）。

安全实现：
  - token 生成: secrets.token_urlsafe(32)，DB 只存 SHA-256(token)。
  - consume_token 使用原子 UPDATE ... WHERE used=0，防并发重放。
  - validate_worker_key 使用 hmac.compare_digest 常量时间比较，防时序攻击。
  - 所有失败路径返回 False/403，不泄露"token 是否存在"的差异。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .config import settings
from .db import execute, query_one


def generate_worker_key() -> str:
    """生成新的 worker key（供部署脚本调用，人工写入 .env）。"""
    return secrets.token_urlsafe(32)


def generate_token() -> str:
    """生成一次性评测 token（明文只出现在 poll 响应中一次）。"""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """SHA-256 哈希，DB 只存哈希。"""
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(kind: str, submission_id: str, ttl_s: int | None = None) -> str:
    """签发并入库一次性 token（kind: download|report|poll）。
    返回明文 token；调用方负责通过安全信道传递给 worker。
    """
    if ttl_s is None:
        ttl_s = settings.token_ttl_s
    raw = generate_token()
    hashed = token_hash(raw)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_s)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    execute(
        "INSERT INTO tokens (token_hash, kind, submission_id, expires_at, used) VALUES (?, ?, ?, ?, 0)",
        (hashed, kind, submission_id, expires_at),
    )
    return raw


def consume_token(kind: str, token: str) -> bool:
    """校验并消费 token：不存在/过期/已用/类型不符 → False。

    防重放：原子 UPDATE ... WHERE used=0，同一 token 两并发请求只有一方成功。
    不区分失败原因（统一 False），防止信息泄露。
    """
    hashed = token_hash(token)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 原子消费：同时校验存在、未过期、未使用、类型匹配
    cur = execute(
        """UPDATE tokens SET used = 1
           WHERE token_hash = ?
             AND kind = ?
             AND used = 0
             AND expires_at > ?""",
        (hashed, kind, now),
    )
    return cur.rowcount > 0


def validate_worker_key(key: str) -> bool:
    """常量时间比较（hmac.compare_digest），防时序攻击。"""
    if not key or not settings.judge_worker_key:
        return False
    return hmac.compare_digest(settings.judge_worker_key, key)


def validate_admin_key(key: str) -> bool:
    """管理端密钥校验（常量时间比较）。"""
    if not key or not settings.admin_key:
        return False
    return hmac.compare_digest(settings.admin_key, key)


def cleanup_expired_tokens() -> int:
    """清理过期 token；返回清理数量。供定时任务调用。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur = execute("DELETE FROM tokens WHERE expires_at < ? AND used = 0", (now,))
    return cur.rowcount
