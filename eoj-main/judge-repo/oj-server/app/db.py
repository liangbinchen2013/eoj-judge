"""SQLite 访问层：表结构 + 连接管理。

安全要点：
  - 全部写操作走事务；连接启用 WAL 模式提升并发。
  - token 表只存 SHA-256 哈希，泄露 DB 也不泄明文。
  - 所有 SQL 使用参数化查询，杜绝注入。
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

from .config import settings

# 表结构：submissions(评测记录+状态机) / tokens(一次性token, 用后即焚) / workers(心跳)
SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id   TEXT NOT NULL UNIQUE,
    problem_id      TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    language        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'QUEUED',
    time_limit_ms   INTEGER NOT NULL DEFAULT 2000,
    memory_limit_mb INTEGER NOT NULL DEFAULT 256,
    time_ms         INTEGER,
    memory_kb       INTEGER,
    compile_output  TEXT,
    results_json    TEXT,
    code_sha256     TEXT NOT NULL DEFAULT '',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    claimed_at      TEXT,
    worker_id       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_at);

CREATE TABLE IF NOT EXISTS tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash    TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    used          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tokens_hash ON tokens(token_hash);

CREATE TABLE IF NOT EXISTS workers (
    worker_id         TEXT PRIMARY KEY,
    last_heartbeat_at TEXT NOT NULL,
    queue_remaining   INTEGER NOT NULL DEFAULT 0,
    ip                TEXT
);

CREATE TABLE IF NOT EXISTS rate_limits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,
    last_used  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_key ON rate_limits(key);
"""

# 线程本地连接池（每个线程一个连接，WAL 模式下安全）
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（自动创建，调用方不应手动 close）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def init_db() -> None:
    """应用启动时执行：建表 + 索引；幂等（CREATE TABLE IF NOT EXISTS）。"""
    conn = get_connection()
    with conn:
        conn.executescript(SCHEMA)
    # 清理过期 token（启动时做一次）
    _cleanup_expired_tokens(conn)


def _cleanup_expired_tokens(conn: sqlite3.Connection) -> None:
    """清理已过期的 token 记录（定期执行，防止 token 表膨胀）。"""
    conn.execute(
        "DELETE FROM tokens WHERE expires_at < datetime('now') AND used = 0"
    )
    conn.commit()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """带事务的单条写操作封装。"""
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur
    except Exception:
        conn.rollback()
        raise


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """单条只读查询。"""
    conn = get_connection()
    return conn.execute(sql, params).fetchone()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """多条只读查询。"""
    conn = get_connection()
    return conn.execute(sql, params).fetchall()
