"""管理端点（ADMIN_KEY 鉴权）。

用途：
  - GET  /api/admin/queue       : 队列统计
  - POST /api/admin/requeue     : 手动回队
  - POST /api/admin/cancel      : 取消提交
  - GET  /api/admin/workers     : worker 心跳列表
  - POST /api/admin/testdata    : 上传题目测试数据
  - POST /api/admin/rejudge     : 重判（任意状态→QUEUED）

安全：
  - 所有端点必须 ADMIN_KEY 鉴权（独立密钥）。
  - 响应中绝不包含任何 token / GITHUB_TOKEN / 代码原文。
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import github_client, queue, storage
from ..auth import validate_admin_key

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_admin_key(request: Request) -> str:
    """从请求头提取 ADMIN_KEY。"""
    return request.headers.get("X-Admin-Key", "")


def _check_admin(request: Request) -> bool:
    """校验管理员密钥。"""
    return validate_admin_key(_get_admin_key(request))


@router.get("/queue")
async def queue_stats(request: Request) -> dict:
    """队列长度、各状态计数。"""
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    return queue.get_queue_stats()


@router.post("/requeue")
async def requeue(request: Request) -> dict:
    """手动把卡死的 JUDGING 回队 / 重发。

    body: {"submission_id": "s_xxx"}
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    try:
        import json
        body = await request.body()
        data = json.loads(body)
        submission_id = data.get("submission_id", "")
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求格式错误"})

    if not submission_id or not submission_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "非法 submission_id"})

    # 强制回队：将 JUDGING 重置为 QUEUED
    from ..db import execute
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur = execute(
        "UPDATE submissions SET status = 'QUEUED', claimed_at = NULL, worker_id = NULL, "
        "updated_at = ? WHERE submission_id = ? AND status = 'JUDGING'",
        (now_str, submission_id),
    )
    if cur.rowcount == 0:
        return JSONResponse(status_code=404, content={"error": "任务不在 JUDGING 状态"})

    # 触发 dispatch
    from ..config import settings
    github_client.dispatch_workflow(
        mode="batch", worker_key=settings.judge_worker_key
    )
    return {"ok": True, "submission_id": submission_id}


@router.post("/cancel")
async def cancel_submission(request: Request) -> dict:
    """取消提交（标记 SKIP）。

    body: {"submission_id": "s_xxx"}
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    try:
        import json
        body = await request.body()
        data = json.loads(body)
        submission_id = data.get("submission_id", "")
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求格式错误"})

    ok = queue.cancel_submission(submission_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "任务不存在或已终态"})

    return {"ok": True, "submission_id": submission_id}


@router.get("/workers")
async def workers(request: Request) -> list[dict]:
    """worker 心跳列表（失联排查）。"""
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    return queue.get_workers_status()


@router.post("/testdata")
async def upload_testdata(
    request: Request,
    problem_id: str = Form(..., max_length=64, min_length=1),
    tests: UploadFile = File(...),
) -> dict:
    """管理员上传题目测试数据（multipart: problem_id + tests.zip）。

    body:
      problem_id  (form)  题目 ID
      tests       (file)  tests.zip（格式见 MANUAL.md §8）
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    import html
    if not problem_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "problem_id 包含非法字符"})

    # 读取测试数据（带大小限制）
    from ..config import settings
    zip_bytes = await tests.read()
    if len(zip_bytes) > settings.max_testdata_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": f"测试数据过大，上限 {settings.max_testdata_bytes // 1_000_000}MB"},
        )
    if len(zip_bytes) == 0:
        return JSONResponse(status_code=400, content={"error": "测试数据不能为空"})

    try:
        storage.upload_testdata_for_problem(problem_id, zip_bytes)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": f"测试数据格式错误: {str(e)}"})

    return {"ok": True, "problem_id": problem_id}


@router.post("/rejudge")
async def rejudge(request: Request) -> dict:
    """重判：将任意状态的提交重置为 QUEUED 并触发 dispatch。

    与 requeue 不同：rejudge 接受终态提交，允许完全重新评测。

    body: {"submission_id": "s_xxx"}
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    try:
        import json
        body = await request.body()
        data = json.loads(body)
        submission_id = data.get("submission_id", "")
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求格式错误"})

    if not submission_id or not submission_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "非法 submission_id"})

    from ..db import execute
    from ..models import FINAL_STATUSES
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 允许终态和非终态提交都重置为 QUEUED
    # 查询当前状态
    row = execute(
        "SELECT status FROM submissions WHERE submission_id = ?",
        (submission_id,),
    )
    if not row:
        return JSONResponse(status_code=404, content={"error": "提交不存在"})

    # 重置为 QUEUED（清除评测结果字段）
    cur = execute(
        "UPDATE submissions SET status = 'QUEUED', claimed_at = NULL, worker_id = NULL, "
        "time_ms = NULL, memory_kb = NULL, compile_output = '', results_json = NULL, "
        "retry_count = 0, updated_at = ? "
        "WHERE submission_id = ?",
        (now_str, submission_id),
    )
    if cur.rowcount == 0:
        return JSONResponse(status_code=404, content={"error": "提交不存在"})

    # 触发 dispatch
    from ..config import settings
    github_client.dispatch_workflow(
        mode="batch", worker_key=settings.judge_worker_key
    )
    return {"ok": True, "submission_id": submission_id, "message": "已重置为 QUEUED"}
