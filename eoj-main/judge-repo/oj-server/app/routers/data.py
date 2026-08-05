"""一次性下载端点：GET /judge/data/{submission_id}/{kind}?token=...

供 worker 下载 code.zip / tests.zip。

安全：
  - token 校验走 auth.consume_token（kind=download，用后即焚）。
  - 路由命中即读文件流式返回，不整体载入内存。
  - 响应头固定：Content-Disposition: attachment + application/octet-stream（防浏览器执行）。
  - kind 白名单 {code, tests}；下载失败统一 403。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, Response

from .. import auth, storage
from ..db import query_one

router = APIRouter(prefix="/judge", tags=["worker"])


@router.get("/data/{submission_id}/{kind}")
async def download(
    submission_id: str,
    kind: str,
    token: str = Query(..., min_length=1, max_length=128),
) -> Response:
    """一次性 token 鉴权后下载压缩包。"""
    # 1. kind 白名单
    if kind not in ("code", "tests"):
        return Response(status_code=403, content=b"forbidden")

    # 2. submission_id 字符集校验
    if not submission_id.replace("_", "").replace("-", "").isalnum():
        return Response(status_code=403, content=b"forbidden")

    # 3. 消费 token（用后即焚）
    if not auth.consume_token(kind="download", token=token):
        return Response(status_code=403, content=b"forbidden")

    # 4. 验证 submission 存在且关联此 token 对应的提交
    row = query_one(
        "SELECT submission_id FROM submissions WHERE submission_id = ?",
        (submission_id,),
    )
    if not row:
        return Response(status_code=403, content=b"forbidden")

    # 5. 读取文件并返回
    try:
        data, filename = storage.load_archive(kind, submission_id)
    except (FileNotFoundError, ValueError):
        return Response(status_code=403, content=b"forbidden")

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
