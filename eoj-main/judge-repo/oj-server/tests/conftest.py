"""pytest 全局配置 — 在 collection 之前设置测试环境变量。

必须在任何 app 模块导入之前执行，因为 Settings 是 frozen dataclass。
"""

import os
import tempfile


def pytest_configure(config):
    """pytest 启动时：设置测试环境。"""
    os.environ.setdefault("JUDGE_WORKER_KEY", "test_worker_key_for_unit_tests_12345")
    os.environ.setdefault("ADMIN_KEY", "test_admin_key_12345")
    os.environ.setdefault("DB_PATH", os.path.join(tempfile.gettempdir(), "test_judge.db"))
    os.environ.setdefault("STORAGE_DIR", os.path.join(tempfile.gettempdir(), "test_storage"))
    os.environ.setdefault("GITHUB_TOKEN", "ghp_test_token_not_real")
    os.environ.setdefault("JUDGE_REPO_OWNER", "test_owner")
    os.environ.setdefault("JUDGE_REPO_NAME", "test_repo")
