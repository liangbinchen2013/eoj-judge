"""worker 回调端点：POST /api/judge/report

安全：
  - 只接受 application/json；请求体大小上限 1MB。
  - token 消费（用后即焚）→ 幂等落库。
  - compile_output / cases 视为不可信数据：写库前截断 + HTML 转义。
  - 鉴权失败返回 403；成功返回 {"ok": true}。
"""

from __future__ import annotations

import html

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import queue
from ..models import FINAL_STATUSES, JudgeResult

router = APIRouter(prefix="/api/judge", tags=["worker"])


@router.post("/report")
async def report(request: Request) -> dict:
    """接收评测结果并落库（幂等）。"""
    # 1. 校验 Content-Type
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return JSONResponse(status_code=400, content={"error": "只接受 application/json"})

    # 2. 解析请求体（带大小限制）
    try:
        body = await request.body()
        if len(body) > 1_000_000:
            return JSONResponse(status_code=400, content={"error": "payload 过大"})
    except Exception:
        return JSONResponse(status_code=400, content={"error": "无法读取请求体"})

    # 3. 解析为 JudgeResult
    try:
        import json
        data = json.loads(body)
        result = JudgeResult(**data)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"请求格式错误"})

    # 4. token 必须存在
    if not result.token:
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    # 5. 落库（token 在 report_result 内部消费）
    ok, status = queue.report_result(result)
    if not ok:
        # 可能 token 失效或重复回调
        if status and status in FINAL_STATUSES:
            return {"ok": True, "ignored": True, "status": status}
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    return {"ok": True, "status": status}
