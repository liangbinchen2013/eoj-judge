"""评测队列与状态机（核心）。

状态机（submissions.status）:
  QUEUED → JUDGING → AC|WA|TLE|MLE|RE|CE|SE|SKIP

安全关键点：
  - poll_next 原子认领：单条 UPDATE ... WHERE status='QUEUED'，防两 worker 抢同一任务。
  - report_result 幂等：重复回调同一 submission 只接受第一次（防重复计分）。
  - requeue_stale：超时 JUDGING 回队，超重试上限标 SE。
  - 所有 UPDATE 带 WHERE 条件做乐观锁。
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import auth
from .config import settings
from .db import execute, query_all, query_one
from .models import FINAL_STATUSES, JudgeResult, JudgeTask


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def enqueue(submission_id: str, problem_id: str, user_id: str,
            language: str, time_limit_ms: int, memory_limit_mb: int,
            code_sha256: str) -> None:
    """入队；入队后检查是否需要 dispatch（空→非空触发）。"""
    now_str = _now()
    execute(
        """INSERT INTO submissions
           (submission_id, problem_id, user_id, language, status,
            time_limit_ms, memory_limit_mb, code_sha256, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?, ?)""",
        (submission_id, problem_id, user_id, language,
         time_limit_ms, memory_limit_mb, code_sha256, now_str, now_str),
    )

    # 触发 dispatch（异步，失败不阻塞入队）
    _maybe_dispatch()


def _maybe_dispatch() -> None:
    """检查是否需要触发 dispatch：队列非空 + 无活跃 worker。
    仅在队列从空变为非空时触发（README §2 方案 B 步骤 3）。

    当 EOJ_BRIDGE_MODE=1 时跳过 dispatch（由 push 触发器负责，
    本进程运行在 GitHub Actions runner 上，不需要额外 dispatch）。
    """
    import os
    if os.getenv("EOJ_BRIDGE_MODE", "") == "1":
        return  # 桥接模式：由 push 触发器负责，不额外 dispatch

    from . import github_client

    # 检查是否有 QUEUED 任务
    row = query_one("SELECT COUNT(*) AS cnt FROM submissions WHERE status = 'QUEUED'")
    queued = row["cnt"] if row else 0
    if queued == 0:
        return

    # 检查是否有活跃 worker（最近 120s 有心跳）
    cutoff = (datetime.now(timezone.utc).replace(second=0, microsecond=0)
              ).strftime("%Y-%m-%d %H:%M:%S")
    # 使用简单的时间比较
    row = query_one(
        "SELECT COUNT(*) AS cnt FROM workers WHERE last_heartbeat_at > datetime('now', '-120 seconds')"
    )
    active = row["cnt"] if row else 0
    if active > 0:
        return  # 已有活跃 worker

    github_client.dispatch_workflow(
        mode="batch", worker_key=settings.judge_worker_key
    )


def poll_next(worker_key: str) -> JudgeTask | None:
    """worker 拉取一个待评测任务；无任务返回 None。

    安全要求：
      - 鉴权 WORKER_KEY
      - 原子认领：UPDATE + WHERE status='QUEUED'，同一任务只能被一个 worker 认领
    """
    if not auth.validate_worker_key(worker_key):
        return None

    now_str = _now()

    # 原子认领：取最早 QUEUED 任务并原子更新为 JUDGING
    row = query_one(
        "SELECT * FROM submissions WHERE status = 'QUEUED' ORDER BY id ASC LIMIT 1"
    )
    if not row:
        return None

    submission_id = row["submission_id"]
    cur = execute(
        """UPDATE submissions SET status = 'JUDGING',
           claimed_at = ?, updated_at = ?, worker_id = ?
           WHERE submission_id = ? AND status = 'QUEUED'""",
        (now_str, now_str, worker_key[:32], submission_id),
    )
    if cur.rowcount == 0:
        return None  # 被另一个 worker 抢先了

    # 签发一次性 token（download + report 共用）
    raw_token = auth.issue_token(kind="download", submission_id=submission_id)

    # 构建下载 URL
    from .storage import build_download_url
    code_url = build_download_url("code", submission_id, raw_token)
    testdata_url = build_download_url("tests", submission_id, raw_token)
    callback_url = f"{settings.public_url.rstrip('/')}/api/judge/report"

    # 签发 report token（同一 token，kind=download 也用于 report 校验）
    # 实际：同一个 token 同时用于 download 和 report，这里重新签发一个 report token
    _ = auth.issue_token(kind="report", submission_id=submission_id, ttl_s=settings.token_ttl_s)
    # 注意：download 和 report 各自消耗独立 token
    # download token 用于 code + tests 两次下载（两次都 kind=download）
    # 所以需要签发 2 个 download token（code 和 tests 各一）
    # 简化：签发两个 download token
    code_token = auth.issue_token(kind="download", submission_id=submission_id)
    tests_token = auth.issue_token(kind="download", submission_id=submission_id)
    report_token = auth.issue_token(kind="report", submission_id=submission_id)

    code_url = build_download_url("code", submission_id, code_token)
    testdata_url = build_download_url("tests", submission_id, tests_token)
    callback_url = f"{settings.public_url.rstrip('/')}/api/judge/report"

    time_limit_ms = row["time_limit_ms"] if row["time_limit_ms"] else 2000
    memory_limit_mb = row["memory_limit_mb"] if row["memory_limit_mb"] else 256

    return JudgeTask(
        submission_id=submission_id,
        problem_id=row["problem_id"],
        language=row["language"],
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        code_url=code_url,
        testdata_url=testdata_url,
        token=report_token,
        callback_url=callback_url,
    )


def report_result(result: JudgeResult) -> tuple[bool, str]:
    """写入评测结果。返回 (是否首次落库, 状态)。

    安全：
      - 先检查幂等（已终态直接返回），再消费 token。
      - 幂等：已处于终态的 submission 不接受重复回调。
    """
    now_str = _now()

    # 1. 幂等检查：已是终态则忽略（先于 token 消费，避免浪费 token）
    row = query_one(
        "SELECT status FROM submissions WHERE submission_id = ?",
        (result.submission_id,),
    )
    if not row:
        return False, ""
    current_status = row["status"]
    if current_status in FINAL_STATUSES:
        return False, current_status  # 已有结果，幂等忽略

    # 2. 消费 token（用后即焚）
    if not auth.consume_token(kind="report", token=result.token):
        return False, ""

    # 3. 序列化 cases
    import json
    cases_json = json.dumps(
        [c.model_dump() for c in result.cases], ensure_ascii=False
    )

    # 4. 写入结果 + 更新状态
    execute(
        """UPDATE submissions
           SET status = ?, time_ms = ?, memory_kb = ?,
               compile_output = ?, results_json = ?,
               updated_at = ?
           WHERE submission_id = ? AND status = 'JUDGING'""",
        (
            result.status, result.time_ms, result.memory_kb,
            result.compile_output[:100_000], cases_json,
            now_str, result.submission_id,
        ),
    )
    return True, result.status


def register_heartbeat(worker_id: str, ip: str, queue_remaining: int) -> bool:
    """更新 worker 心跳时间。返回 dispatch_needed（是否需要触发新 worker）。"""
    now_str = _now()
    execute(
        """INSERT INTO workers (worker_id, last_heartbeat_at, queue_remaining, ip)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(worker_id) DO UPDATE SET
             last_heartbeat_at = excluded.last_heartbeat_at,
             queue_remaining = excluded.queue_remaining,
             ip = excluded.ip""",
        (worker_id, now_str, queue_remaining, ip),
    )
    # 判断是否需要新 worker：队列非空 + 无其他活跃 worker
    row = query_one("SELECT COUNT(*) AS cnt FROM submissions WHERE status = 'QUEUED'")
    queued = row["cnt"] if row else 0
    if queued == 0:
        return False
    row = query_one(
        "SELECT COUNT(*) AS cnt FROM workers WHERE last_heartbeat_at > datetime('now', '-120 seconds')"
    )
    active = row["cnt"] if row else 0
    return active <= 1  # 只有当前 worker 自己


def requeue_stale(timeout_s: int | None = None, max_retries: int | None = None) -> int:
    """扫描超时 JUDGING 任务：回队或标记 SE。返回处理数量。

    超时未完成的 JUDGING（worker 被杀/失联）→ 回 QUEUED + retry_count+1；
    重试超上限（默认 3 次）→ 标记 SE。
    """
    if timeout_s is None:
        timeout_s = settings.judge_timeout_s
    if max_retries is None:
        max_retries = settings.max_retry_count

    now_str = _now()
    processed = 0

    # 查找超时的 JUDGING 任务
    rows = query_all(
        """SELECT submission_id, retry_count FROM submissions
           WHERE status = 'JUDGING'
             AND claimed_at < datetime('now', ? || ' seconds')""",
        (f"-{timeout_s}",),
    )

    for row in rows:
        sid = row["submission_id"]
        retry = row["retry_count"]
        if retry >= max_retries:
            # 重试超限 → SE
            execute(
                "UPDATE submissions SET status = 'SE', updated_at = ? "
                "WHERE submission_id = ? AND status = 'JUDGING'",
                (now_str, sid),
            )
        else:
            # 回队重试
            execute(
                "UPDATE submissions SET status = 'QUEUED', retry_count = retry_count + 1, "
                "updated_at = ?, claimed_at = NULL, worker_id = NULL "
                "WHERE submission_id = ? AND status = 'JUDGING'",
                (now_str, sid),
            )
        processed += 1

    # 如果有任务回队，检查是否需要重新 dispatch
    if processed > 0:
        _maybe_dispatch()

    return processed


def cancel_submission(submission_id: str) -> bool:
    """取消提交：将 QUEUED/JUDGING 的任务标记为 SKIP。返回是否成功。"""
    now_str = _now()
    cur = execute(
        """UPDATE submissions SET status = 'SKIP', updated_at = ?
           WHERE submission_id = ? AND status IN ('QUEUED', 'JUDGING')""",
        (now_str, submission_id),
    )
    return cur.rowcount > 0


def get_queue_stats() -> dict:
    """获取队列统计信息。"""
    rows = query_all(
        "SELECT status, COUNT(*) AS cnt FROM submissions GROUP BY status"
    )
    stats = {r["status"]: r["cnt"] for r in rows}
    return {
        "total": sum(stats.values()),
        "by_status": stats,
    }


def get_workers_status() -> list[dict]:
    """获取 worker 心跳列表。"""
    rows = query_all(
        "SELECT worker_id, last_heartbeat_at, queue_remaining, ip FROM workers "
        "ORDER BY last_heartbeat_at DESC"
    )
    return [dict(r) for r in rows]
