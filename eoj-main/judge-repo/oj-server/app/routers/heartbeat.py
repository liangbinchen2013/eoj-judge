"""worker 心跳端点：POST /api/judge/heartbeat（每 30s）。

安全：
  - 鉴权 WORKER_KEY；worker_id 格式校验（字符集白名单，防投毒）。
  - 心跳过期 → requeue_stale 兜底扫描（由 main.py 后台任务执行）。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import queue
from ..auth import validate_worker_key
from ..models import Heartbeat

router = APIRouter(prefix="/api/judge", tags=["worker"])


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    host = request.client.host if request.client else "unknown"
    return host[:45]


@router.post("/heartbeat")
async def heartbeat(request: Request) -> dict:
    """更新 worker 心跳；返回 {"ok": true, "dispatch_needed": bool}。"""
    # 1. 鉴权：worker_key 从 X-Worker-Key 请求头或 body 取
    worker_key = request.headers.get("X-Worker-Key", "")
    if not worker_key:
        # 尝试从 body 取
        try:
            body = await request.body()
            import json
            data = json.loads(body)
            worker_key = data.get("worker_key", "")
        except Exception:
            pass

    if not validate_worker_key(worker_key):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    # 2. 解析请求体
    try:
        body = await request.body()
        import json
        data = json.loads(body)
        hb = Heartbeat(**data)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "心跳格式错误"})

    # 3. 注册心跳
    ip = _get_client_ip(request)
    dispatch_needed = queue.register_heartbeat(hb.worker_id, ip, hb.queue_remaining)

    return {"ok": True, "dispatch_needed": dispatch_needed}
