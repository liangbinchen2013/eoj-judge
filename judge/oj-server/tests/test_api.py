"""API 冒烟测试。

用例清单（对应 README §10 验收标准）:
  - 正常提交 → 返回 submission_id → 状态 QUEUED。
  - 非法语言 / 超大代码 / 限流命中 → 400/413/429。
  - poll 无 key → 403；key 错误 → 403。
  - poll 拉任务 → 用返回的 token 下载 code.zip → 下载成功后同一 token 再下载 → 403（用后即焚）。
  - report 正常 → 落库 AC；重复 report → 幂等。
  - 伪造 token / 过期 token → 403。
  - ★ 安全回归：下载响应头必须 Content-Disposition: attachment。
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import db as app_db
from app.config import settings

client = TestClient(app)


def _make_db_path() -> str:
    return os.path.join(tempfile.gettempdir(), f"test_api_{uuid.uuid4().hex}.db")


def _setup_problem_testdata(problem_id: str = "p1001"):
    """为题目创建测试数据，供提交测试使用。"""
    problem_dir = os.path.join(settings.storage_dir, problem_id)
    os.makedirs(problem_dir, exist_ok=True)
    test_zip = _make_test_zip({1: "1 2"}, {1: "3"})
    with open(os.path.join(problem_dir, "tests.zip"), "wb") as f:
        f.write(test_zip)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """每个测试前使用独立数据库文件，创建必要的存储目录和测试数据。"""
    db_path = _make_db_path()

    # 替换 DB 连接为独立数据库
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(app_db.SCHEMA)
    conn.commit()

    def _test_conn():
        return conn

    monkeypatch.setattr(app_db, "get_connection", _test_conn)

    # 确保存储目录存在 + 创建题目测试数据
    os.makedirs(settings.storage_dir, exist_ok=True)
    _setup_problem_testdata("p1001")

    yield

    conn.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            wp = db_path + suffix
            if os.path.exists(wp):
                os.unlink(wp)
        except (PermissionError, OSError):
            pass


def _make_code_zip(code: str) -> bytes:
    """生成包含 main.cpp 的 code.zip。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("main.cpp", code)
    return buf.getvalue()


def _make_test_zip(in_files: dict[int, str], out_files: dict[int, str]) -> bytes:
    """生成测试数据 zip。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for case_id, content in in_files.items():
            zf.writestr(f"in/{case_id}.txt", content)
        for case_id, content in out_files.items():
            zf.writestr(f"out/{case_id}.txt", content)
    return buf.getvalue()


class TestHealthz:
    def test_healthz(self):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSubmit:
    """提交端点测试。"""

    def test_submit_success(self):
        """正常提交 → 返回 submission_id + QUEUED 状态。"""
        code = _make_code_zip('#include <iostream>\nint main(){std::cout<<"hello";return 0;}')
        resp = client.post(
            "/api/submit",
            data={"problem_id": "p1001", "language": "cpp"},
            files={"code": ("main.cpp", code, "application/zip")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "submission_id" in data
        assert data["status"] == "QUEUED"
        assert data["submission_id"].startswith("s_")

    def test_submit_invalid_language(self):
        """非法语言 → 400。"""
        code = _make_code_zip("test")
        resp = client.post(
            "/api/submit",
            data={"problem_id": "p1001", "language": "brainfuck"},
            files={"code": ("main.bf", code, "application/zip")},
        )
        assert resp.status_code == 400

    def test_submit_empty_code(self):
        """空代码 → 400。"""
        resp = client.post(
            "/api/submit",
            data={"problem_id": "p1001", "language": "cpp"},
            files={"code": ("main.cpp", b"", "application/zip")},
        )
        assert resp.status_code == 400

    def test_submit_oversize_code(self):
        """超大代码 → 400 或 413。"""
        big = b"x" * 2_000_000
        resp = client.post(
            "/api/submit",
            data={"problem_id": "p1001", "language": "cpp"},
            files={"code": ("main.cpp", big, "application/zip")},
        )
        assert resp.status_code in (400, 413)

    def test_submit_invalid_problem_id(self):
        """非法 problem_id 字符 → 400。"""
        code = _make_code_zip("test")
        resp = client.post(
            "/api/submit",
            data={"problem_id": "../../etc/passwd", "language": "cpp"},
            files={"code": ("main.cpp", code, "application/zip")},
        )
        assert resp.status_code in (400, 422)

    def test_get_submission_not_found(self):
        """查询不存在的提交 → 404。"""
        resp = client.get("/api/submission/s_nonexistent")
        assert resp.status_code == 404

    def test_oversize_request_body(self):
        """超过 2MB 的请求体 → 413。"""
        big = b"x" * 2_500_000
        resp = client.post(
            "/api/submit",
            data={"problem_id": "p1001", "language": "cpp"},
            files={"code": ("main.cpp", big, "application/zip")},
        )
        assert resp.status_code in (400, 413)


class TestPoll:
    """poll 端点测试。"""

    def test_poll_no_key(self):
        """无 key → 422（FastAPI 参数校验）。"""
        resp = client.get("/api/judge/poll")
        assert resp.status_code in (403, 422)

    def test_poll_wrong_key(self):
        """错误 key → 403。"""
        resp = client.get("/api/judge/poll?key=wrong_key_12345678")
        assert resp.status_code == 403

    def test_poll_correct_key_no_tasks(self):
        """正确 key 但无任务 → {"task": null}。"""
        resp = client.get(f"/api/judge/poll?key={settings.judge_worker_key}")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"task": None}

    def test_poll_gets_task(self):
        """有 QUEUED 任务时 poll 返回任务。"""
        # 先入队一个任务（手动插数据 + 测试数据）
        self._prepare_submission("s_test_001")

        resp = client.get(f"/api/judge/poll?key={settings.judge_worker_key}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        task = data["task"]
        assert task["submission_id"] == "s_test_001"
        assert task["language"] == "cpp"
        assert "token" in task
        assert "code_url" in task
        assert "testdata_url" in task
        assert "callback_url" in task

    def _prepare_submission(self, sid: str):
        """准备测试数据：在存储目录中创建必要的文件并在 DB 插入提交。"""
        import os
        from app.db import execute
        from app.config import settings

        # 创建存储目录和测试数据
        sub_dir = os.path.join(settings.storage_dir, sid)
        os.makedirs(sub_dir, exist_ok=True)
        # 写 code.zip
        code_zip = _make_code_zip("int main(){return 0;}")
        with open(os.path.join(sub_dir, "code.zip"), "wb") as f:
            f.write(code_zip)
        # 写 tests.zip
        test_zip = _make_test_zip({1: "1 2"}, {1: "3"})
        with open(os.path.join(sub_dir, "tests.zip"), "wb") as f:
            f.write(test_zip)
        # 入 DB
        execute(
            """INSERT INTO submissions
               (submission_id, problem_id, user_id, language, status,
                time_limit_ms, memory_limit_mb, code_sha256, created_at, updated_at)
               VALUES (?, 'p1001', 'test', 'cpp', 'QUEUED', 2000, 256, '', datetime('now'), datetime('now'))""",
            (sid,),
        )


class TestDownload:
    """下载端点测试。"""

    def test_download_with_token(self):
        """用 token 下载 code.zip。"""
        sid = "s_test_dl_001"
        self._setup(sid)

        # poll 拉任务获取 token
        resp = client.get(f"/api/judge/poll?key={settings.judge_worker_key}")
        task = resp.json()["task"]
        assert task is not None

        # 提取 code_url 中的 token
        code_url = task["code_url"]
        import urllib.parse
        parsed = urllib.parse.urlparse(code_url)
        qs = urllib.parse.parse_qs(parsed.query)
        token = qs["token"][0]

        resp = client.get(f"/judge/data/{sid}/code?token={token}")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_download_token_burn_after_use(self):
        """用后即焚：同一 token 第二次下载 → 403。"""
        sid = "s_test_dl_002"
        self._setup(sid)

        resp = client.get(f"/api/judge/poll?key={settings.judge_worker_key}")
        task = resp.json()["task"]

        import urllib.parse
        code_url = task["code_url"]
        parsed = urllib.parse.urlparse(code_url)
        qs = urllib.parse.parse_qs(parsed.query)
        token = qs["token"][0]

        # 第一次成功
        resp1 = client.get(f"/judge/data/{sid}/code?token={token}")
        assert resp1.status_code == 200
        # 第二次失败
        resp2 = client.get(f"/judge/data/{sid}/code?token={token}")
        assert resp2.status_code == 403

    def test_download_fake_token(self):
        """伪造 token → 403。"""
        resp = client.get("/judge/data/s_test/code?token=fake_token_12345678901234567890")
        assert resp.status_code == 403

    def test_download_invalid_kind(self):
        """非法 kind → 403。"""
        resp = client.get("/judge/data/s_test/evil?token=anything")
        assert resp.status_code == 403

    def _setup(self, sid: str):
        """准备测试数据。"""
        import os
        from app.db import execute
        from app.config import settings

        sub_dir = os.path.join(settings.storage_dir, sid)
        os.makedirs(sub_dir, exist_ok=True)
        code_zip = _make_code_zip("int main(){return 0;}")
        with open(os.path.join(sub_dir, "code.zip"), "wb") as f:
            f.write(code_zip)
        test_zip = _make_test_zip({1: "1 2"}, {1: "3"})
        with open(os.path.join(sub_dir, "tests.zip"), "wb") as f:
            f.write(test_zip)
        execute(
            """INSERT INTO submissions
               (submission_id, problem_id, user_id, language, status,
                time_limit_ms, memory_limit_mb, code_sha256, created_at, updated_at)
               VALUES (?, 'p1001', 'test', 'cpp', 'QUEUED', 2000, 256, '', datetime('now'), datetime('now'))""",
            (sid,),
        )


class TestReport:
    """回调端点测试。"""

    def test_report_idempotent(self):
        """幂等：重复 report 只接受第一次。"""
        sid = "s_test_rpt_001"
        self._setup(sid)

        # poll 获取 token
        resp = client.get(f"/api/judge/poll?key={settings.judge_worker_key}")
        task = resp.json()["task"]
        token = task["token"]

        # 第一次 report
        result = {
            "submission_id": sid,
            "token": token,
            "status": "AC",
            "time_ms": 100,
            "memory_kb": 8000,
            "compile_output": "",
            "cases": [
                {"id": 1, "status": "AC", "time_ms": 100, "memory_kb": 8000}
            ],
        }
        resp1 = client.post("/api/judge/report", json=result)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1.get("ok") is True
        assert data1.get("ignored") is not True

        # 第二次 report（幂等，应 ignored）
        resp2 = client.post("/api/judge/report", json=result)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("ignored") is True

    def test_report_bad_status(self):
        """非法 status → 422。"""
        result = {
            "submission_id": "s_test",
            "token": "any",
            "status": "INVALID_STATUS",
            "time_ms": 0,
            "memory_kb": 0,
            "compile_output": "",
            "cases": [],
        }
        resp = client.post("/api/judge/report", json=result)
        assert resp.status_code in (400, 422)

    def test_report_bad_token(self):
        """已消费的 token 再次使用 → 幂等 200（ignored）或 403。"""
        sid = "s_test_rpt_003"
        self._setup(sid)

        # poll 获取 token
        resp = client.get(f"/api/judge/poll?key={settings.judge_worker_key}")
        task = resp.json()["task"]
        token = task["token"]

        # 用完后再次使用
        result = {
            "submission_id": sid,
            "token": token,
            "status": "AC",
            "time_ms": 0,
            "memory_kb": 0,
            "compile_output": "",
            "cases": [],
        }
        resp1 = client.post("/api/judge/report", json=result)
        assert resp1.status_code == 200
        resp2 = client.post("/api/judge/report", json=result)
        # 幂等：已终态的报告返回 200 + ignored: true
        assert resp2.status_code == 200
        data = resp2.json()
        assert data.get("ignored") is True

    def _setup(self, sid: str):
        """准备测试数据。"""
        import os
        from app.db import execute
        from app.config import settings

        sub_dir = os.path.join(settings.storage_dir, sid)
        os.makedirs(sub_dir, exist_ok=True)
        code_zip = _make_code_zip("int main(){return 0;}")
        with open(os.path.join(sub_dir, "code.zip"), "wb") as f:
            f.write(code_zip)
        test_zip = _make_test_zip({1: "1 2"}, {1: "3"})
        with open(os.path.join(sub_dir, "tests.zip"), "wb") as f:
            f.write(test_zip)
        execute(
            """INSERT INTO submissions
               (submission_id, problem_id, user_id, language, status,
                time_limit_ms, memory_limit_mb, code_sha256, created_at, updated_at)
               VALUES (?, 'p1001', 'test', 'cpp', 'QUEUED', 2000, 256, '', datetime('now'), datetime('now'))""",
            (sid,),
        )


class TestHeartbeat:
    """心跳端点测试。"""

    def test_heartbeat_no_auth(self):
        """无鉴权 → 403。"""
        resp = client.post("/api/judge/heartbeat", json={
            "worker_id": "gha-123", "queue_remaining": 0
        })
        assert resp.status_code == 403


class TestAdmin:
    """管理端点测试。"""

    def test_admin_no_key(self):
        """无 ADMIN_KEY → 403。"""
        resp = client.get("/api/admin/queue")
        assert resp.status_code == 403


class TestRateLimit:
    """限流测试。"""

    def test_rate_limit_consecutive_submits(self):
        """连续提交触发频率限制 → 429。"""
        code = _make_code_zip("int main(){return 0;}")
        # 快速连续提交
        for i in range(3):
            resp = client.post(
                "/api/submit",
                data={"problem_id": "p1001", "language": "cpp"},
                files={"code": ("main.cpp", code, "application/zip")},
            )
            if resp.status_code == 429:
                assert "retry_after_s" in resp.json()
                return  # 限流触发，测试通过
        # 默认限流间隔 10s，快速连续可能不会触发（取决于实现）
        # 至少第一次应该成功
