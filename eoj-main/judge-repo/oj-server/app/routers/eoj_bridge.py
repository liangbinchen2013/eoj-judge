"""eoj-main 桥接端点。

提供适配 eoj-main 原有接口的端点：
  - POST /api/eoj/testdata  : 上传 eoj JSON 格式测试用例 → 转为 tests.zip
  - POST /api/eoj/spj       : 上传 SPJ 源码
  - POST /api/eoj/judge-data: 批量上传测试数据 + SPJ（一次性完成题目准备）

所有端点需要 ADMIN_KEY 鉴权。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import storage
from ..auth import validate_admin_key

router = APIRouter(prefix="/api/eoj", tags=["eoj-bridge"])


def _check_admin(request: Request) -> bool:
    key = request.headers.get("X-Admin-Key", "")
    return validate_admin_key(key)


@router.post("/testdata")
async def upload_testdata(request: Request) -> dict:
    """上传 eoj-main JSON 格式测试用例，自动转为 tests.zip。

    JSON body:
      {"problem_id": "a-plus-b",
       "testcases": [{"input": "...", "expected_output": "...",
                       "is_sample": true, "score": 10}, ...]}
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    try:
        body = await request.body()
        data = json.loads(body)
        problem_id = data.get("problem_id", "")
        testcases = data.get("testcases", [])
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求格式错误"})

    if not problem_id or not problem_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "非法 problem_id"})

    if not testcases or not isinstance(testcases, list):
        return JSONResponse(status_code=400, content={"error": "testcases 必须是非空数组"})

    # 校验每条用例格式
    for i, tc in enumerate(testcases):
        if not isinstance(tc, dict):
            return JSONResponse(
                status_code=400,
                content={"error": f"testcases[{i}] 格式错误"},
            )
        if "input" not in tc:
            return JSONResponse(
                status_code=400,
                content={"error": f"testcases[{i}] 缺少 input"},
            )

    try:
        zip_bytes = storage.eoj_testcases_to_zip(testcases)
        storage.upload_testdata_for_problem(problem_id, zip_bytes)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    return {
        "ok": True,
        "problem_id": problem_id,
        "testcase_count": len(testcases),
    }


@router.post("/spj")
async def upload_spj(request: Request) -> dict:
    """上传 SPJ 源码。

    JSON body:
      {"problem_id": "a-plus-b",
       "spj_code": "#include <stdio.h>...",
       "spj_language": "cpp"}
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    try:
        body = await request.body()
        data = json.loads(body)
        problem_id = data.get("problem_id", "")
        spj_code = data.get("spj_code", "")
        spj_language = data.get("spj_language", "")
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求格式错误"})

    if not problem_id or not problem_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "非法 problem_id"})

    if not spj_code:
        return JSONResponse(status_code=400, content={"error": "spj_code 不能为空"})

    allowed = {"c", "cpp", "python", "java", "go", "rust", "javascript"}
    if spj_language not in allowed:
        return JSONResponse(status_code=400, content={"error": f"不支持的 SPJ 语言: {spj_language}"})

    if len(spj_code) > 1_000_000:
        return JSONResponse(status_code=400, content={"error": "SPJ 代码过大"})

    storage.save_spj_source(problem_id, spj_code, spj_language)
    return {"ok": True, "problem_id": problem_id, "spj_language": spj_language}


@router.post("/judge-data")
async def upload_judge_data(request: Request) -> dict:
    """一次性上传题目的测试数据 + SPJ（对应 eoj-main 的 judge-data 响应格式）。

    JSON body:
      {"problem_id": "...",
       "testcases": [{input, expected_output, is_sample, score}, ...],
       "spj_code": "..." | null,
       "spj_language": "..." | null,
       "time_limit_ms": 1000,
       "memory_limit_mb": 256}
    """
    if not _check_admin(request):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    try:
        body = await request.body()
        data = json.loads(body)
        problem_id = data.get("problem_id", "")
        testcases = data.get("testcases", [])
        spj_code = data.get("spj_code", "")
        spj_language = data.get("spj_language", "")
        time_limit_ms = data.get("time_limit_ms", 2000)
        memory_limit_mb = data.get("memory_limit_mb", 256)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "请求格式错误"})

    if not problem_id or not problem_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "非法 problem_id"})

    if not testcases:
        return JSONResponse(status_code=400, content={"error": "testcases 不能为空"})

    # 转换测试数据（含 SPJ 源码打包进 tests.zip）
    try:
        zip_bytes = storage.eoj_testcases_to_zip(
            testcases,
            spj_code=spj_code or "",
            spj_language=spj_language or "",
        )
        storage.upload_testdata_for_problem(problem_id, zip_bytes)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    # 同时单独保存 SPJ（备用）
    if spj_code and spj_language:
        storage.save_spj_source(problem_id, spj_code, spj_language)

    return {
        "ok": True,
        "problem_id": problem_id,
        "testcase_count": len(testcases),
        "has_spj": bool(spj_code),
        "time_limit_ms": time_limit_ms,
        "memory_limit_mb": memory_limit_mb,
    }
