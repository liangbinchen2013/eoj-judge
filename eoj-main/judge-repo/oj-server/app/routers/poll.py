"""worker 拉取任务端点：GET /api/judge/poll?key=<worker_key>

安全：
  - key 从 query 参数取，常量时间比较。
  - 鉴权失败统一 403，不泄露任何内部信息。
  - 响应里 token/code_url 是唯一一次明文出现 —— 日志绝不打全文。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from .. import queue
from ..auth import validate_worker_key

router = APIRouter(prefix="/api/judge", tags=["worker"])


def require_worker_key(key: str) -> bool:
    """校验 worker key，返回 True/False（供其它端点复用）。"""
    return validate_worker_key(key)


@router.get("/poll")
async def poll(key: str = Query(..., min_length=1, max_length=128)) -> dict:
    """拉取一个待评测任务；无任务时 {"task": null}。"""
    if not validate_worker_key(key):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    task = queue.poll_next(key)
    if task is None:
        return {"task": None}

    return {"task": task.model_dump()}
