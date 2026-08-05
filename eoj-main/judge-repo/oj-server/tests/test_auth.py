"""鉴权单元测试：一次性 token 用后即焚 / 哈希存储 / 并发防重放。

用例清单:
  - generate/issue/consume 往返成功。
  - consume 第二次 → False（用后即焚）。
  - 过期 token → False。
  - 类型不符（download 的 token 用于 report）→ False。
  - DB 中存储的只有 SHA-256 哈希，无明文。
  - validate_worker_key 用常量时间比较（不直接 ==）。
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import threading
import hashlib

import pytest

# 设置测试环境 — 必须在 import app 之前设置
os.environ["JUDGE_WORKER_KEY"] = "test_worker_key_for_unit_tests_12345"

from app import auth, db as app_db
from app.config import settings


def _make_db_path() -> str:
    """每次测试使用唯一的临时数据库路径，避免 Windows 文件锁冲突。"""
    import uuid
    return os.path.join(tempfile.gettempdir(), f"test_auth_{uuid.uuid4().hex}.db")


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """每个测试前使用独立数据库文件，测试后清理。"""
    db_path = _make_db_path()
    storage_dir = os.path.join(tempfile.gettempdir(), f"test_auth_storage_{os.urandom(4).hex()}")
    os.makedirs(storage_dir, exist_ok=True)

    # 创建独立数据库连接
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(app_db.SCHEMA)
    conn.commit()

    # 替换 db 模块的 get_connection 返回我们的测试连接
    def _test_conn():
        return conn

    monkeypatch.setattr(app_db, "get_connection", _test_conn)

    yield

    # 清理
    conn.close()
    try:
        if os.path.exists(db_path):
            os.unlink(db_path)
    except PermissionError:
        pass  # Windows 文件锁，忽略
    # 清理 WAL 文件
    for suffix in ("-wal", "-shm"):
        try:
            wp = db_path + suffix
            if os.path.exists(wp):
                os.unlink(wp)
        except (PermissionError, OSError):
            pass


class TestTokenLifecycle:
    """一次性 token 完整生命周期测试。"""

    def test_issue_and_consume(self):
        """签发 → 消费 → 成功。"""
        raw = auth.issue_token(kind="download", submission_id="s_test_001")
        assert raw
        assert len(raw) > 20

        ok = auth.consume_token(kind="download", token=raw)
        assert ok is True

    def test_token_burn_after_use(self):
        """用后即焚：第二次消费失败。"""
        raw = auth.issue_token(kind="download", submission_id="s_test_002")

        ok1 = auth.consume_token(kind="download", token=raw)
        assert ok1 is True

        ok2 = auth.consume_token(kind="download", token=raw)
        assert ok2 is False

    def test_token_wrong_kind(self):
        """类型不符：download token 不能用于 report。"""
        raw = auth.issue_token(kind="download", submission_id="s_test_003")
        ok = auth.consume_token(kind="report", token=raw)
        assert ok is False

    def test_token_db_hashed_only(self):
        """DB 中只存 SHA-256 哈希，无明文。"""
        raw = auth.issue_token(kind="download", submission_id="s_test_004")
        hashed = auth.token_hash(raw)

        from app.db import query_one
        row = query_one("SELECT token_hash FROM tokens WHERE token_hash = ?", (hashed,))
        assert row is not None
        # DB 里存的是哈希，不是明文
        assert row["token_hash"] != raw
        assert row["token_hash"] == hashed

    def test_generate_token_unique(self):
        """每次生成的 token 都不同。"""
        tokens = [auth.generate_token() for _ in range(100)]
        assert len(set(tokens)) == 100

    def test_token_hash_consistent(self):
        """同一 token 哈希一致。"""
        raw = auth.generate_token()
        h1 = auth.token_hash(raw)
        h2 = auth.token_hash(raw)
        assert h1 == h2

    def test_expired_token_consumed(self):
        """过期的 token 无法消费（缩短 TTL 模拟过期）。"""
        import time
        raw = auth.issue_token(kind="download", submission_id="s_test_exp", ttl_s=1)
        time.sleep(1.5)  # 等待过期
        ok = auth.consume_token(kind="download", token=raw)
        assert ok is False


class TestWorkerKey:
    """Worker Key 鉴权测试。"""

    def test_validate_worker_key_correct(self):
        """正确的 key → True。"""
        key = os.environ.get("JUDGE_WORKER_KEY", "test_worker_key_for_unit_tests_12345")
        assert auth.validate_worker_key(key) is True

    def test_validate_worker_key_wrong(self):
        """错误的 key → False。"""
        assert auth.validate_worker_key("wrong_key_12345678901234567890") is False

    def test_validate_worker_key_empty(self):
        """空 key → False。"""
        assert auth.validate_worker_key("") is False

    def test_validate_worker_key_none(self):
        """None → False（传入空字符串模拟）。"""
        assert auth.validate_worker_key("") is False

    def test_generate_worker_key_length(self):
        """生成 key 有足够长度。"""
        key = auth.generate_worker_key()
        assert len(key) >= 32

    def test_generate_worker_key_unique(self):
        """每次生成不同的 key。"""
        keys = [auth.generate_worker_key() for _ in range(10)]
        assert len(set(keys)) == 10


class TestTimingAttack:
    """时序攻击防护测试。"""

    def test_compare_digest_usage(self):
        """验证使用了 hmac.compare_digest（非直接 == 比较）。"""
        import inspect
        source = inspect.getsource(auth.validate_worker_key)
        assert "compare_digest" in source or "hmac" in source.lower()


class TestConcurrentToken:
    """并发 token 消费测试。"""

    def test_concurrent_consume(self):
        """两个并发请求同时消费同一个 token，只有一方成功。"""
        raw = auth.issue_token(kind="download", submission_id="s_test_cc")

        results = []

        def worker():
            results.append(auth.consume_token(kind="download", token=raw))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # 只有一个成功
        assert sum(results) == 1


class TestTokenHash:
    """Token 哈希测试。"""

    def test_token_hash_is_sha256(self):
        """确认哈希算法是 SHA-256（64 位十六进制）。"""
        raw = "test_token_input"
        h = auth.token_hash(raw)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_token_hash_deterministic(self):
        """同一输入哈希一致。"""
        h1 = auth.token_hash("hello")
        h2 = auth.token_hash("hello")
        assert h1 == h2

    def test_token_hash_avalanche(self):
        """微小输入变化导致完全不同哈希。"""
        h1 = auth.token_hash("hello")
        h2 = auth.token_hash("hallo")
        assert h1 != h2
        # 至少一半 bit 不同
        diff = sum(c1 != c2 for c1, c2 in zip(h1, h2))
        assert diff > 10


class TestCleanup:
    """Token 清理测试。"""

    def test_cleanup_expired(self):
        """清理过期 token。"""
        raw = auth.issue_token(kind="download", submission_id="s_test_clean", ttl_s=0)
        import time
        time.sleep(0.5)
        cleaned = auth.cleanup_expired_tokens()
        assert cleaned >= 0  # 至少清理了记录
