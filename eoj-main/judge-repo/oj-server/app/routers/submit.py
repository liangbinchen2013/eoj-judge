"""用户提交端点：POST /api/submit（支持 multipart 文件 或 JSON 纯文本源码）。

流程：限流 → 代码大小校验 → 语言白名单 → 源码自动打包为 zip → 落盘 → 入队 → 返回 submission_id。

兼容 eoj-main：
  - 支持纯文本 source_code（JSON body），自动按语言规则打包为 zip。
  - 支持外部传入 submission_id（eoj-main 整数 ID）。
  - 支持 time_limit_ms / memory_limit_mb 参数透传。
  - 支持 X-User-ID 请求头传递用户身份。

安全要点：
  - 代码字节流不做任何解码/执行/回显。
  - 文件名不信任用户输入，一律用服务端生成的 submission_id。
  - 语言不在白名单 → 400；限流命中 → 429。
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import time
import zipfile

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import queue, storage
from ..config import settings
from ..db import query_one
from ..models import SubmitRequest
from ..ratelimit import RateLimitExceeded, check_inflight_limit, check_submit_allowed

router = APIRouter(prefix="/api", tags=["submit"])

MAX_CODE_BYTES = 1_000_000

# 语言 → zip 内文件名映射
_LANG_SOURCE_FILES: dict[str, str] = {
    "c":          "main.c",
    "cpp":        "main.cpp",
    "python":     "main.py",
    "java":       "Main.java",
    "go":         "main.go",
    "rust":       "main.rs",
    "javascript": "main.js",
}


def _generation_id() -> str:
    """生成 submission_id: s_YYYYMMDD_seq"""
    import os
    ts = time.strftime("%Y%m%d_%H%M%S")
    rnd = os.urandom(4).hex()
    return f"s_{ts}_{rnd}"


def _get_client_ip(request: Request) -> str:
    """安全获取客户端 IP（考虑代理）。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    host = request.client.host if request.client else "unknown"
    return host[:45]


def _source_to_zip(source_code: str, language: str) -> bytes:
    """将纯文本源码打包为 code.zip（文件名按语言规则）。"""
    filename = _LANG_SOURCE_FILES.get(language, "main.txt")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, source_code)
    return buf.getvalue()


@router.post("/submit")
async def submit(
    request: Request,
    problem_id: str = Form(default="", max_length=64, min_length=0),
    language: str = Form(default="", max_length=16, min_length=0),
    code: UploadFile | None = File(default=None),
) -> dict:
    """接收提交（multipart 或 JSON），返回 {"submission_id": "s_..."} 与查询状态。

    同时兼容 eoj-main 桥接脚本通过 JSON body 提交纯文本源码：
      {"problem_id": "...", "language": "...", "source_code": "...",
       "submission_id": "...", "time_limit_ms": 2000, "memory_limit_mb": 256}
    """
    ip = _get_client_ip(request)
    content_type = request.headers.get("content-type", "")

    # --- 解析请求体 ---
    source_code: str | None = None
    code_bytes: bytes | None = None
    req_submission_id: str | None = None
    req_time_limit_ms: int = 2000
    req_memory_limit_mb: int = 256

    if "application/json" in content_type:
        # JSON 模式（eoj-main 桥接）：纯文本源码
        try:
            body = await request.body()
            data = json.loads(body)
            # 校验
            req = SubmitRequest(
                problem_id=data.get("problem_id", ""),
                language=data.get("language", ""),
                source_code=data.get("source_code", ""),
                submission_id=data.get("submission_id"),
                time_limit_ms=data.get("time_limit_ms", 2000),
                memory_limit_mb=data.get("memory_limit_mb", 256),
            )
            problem_id = req.problem_id
            language = req.language
            source_code = req.source_code or ""
            req_submission_id = req.submission_id
            req_time_limit_ms = req.time_limit_ms
            req_memory_limit_mb = req.memory_limit_mb
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"error": f"请求格式错误: {str(e)}"},
            )
    else:
        # multipart 模式（原生 judge 客户端）
        if not problem_id:
            problem_id = (await request.form()).get("problem_id", "")
            if hasattr(problem_id, "encode"):
                pass  # already str

    # --- 重新获取表单参数（multipart 模式）---
    if not problem_id or not language:
        # multipart 模式
        try:
            form = await request.form()
            problem_id = str(form.get("problem_id", ""))
            language = str(form.get("language", ""))
            req_submission_id = str(form.get("submission_id", "")) or None
            try:
                req_time_limit_ms = int(str(form.get("time_limit_ms", "2000")))
            except (ValueError, TypeError):
                req_time_limit_ms = 2000
            try:
                req_memory_limit_mb = int(str(form.get("memory_limit_mb", "256")))
            except (ValueError, TypeError):
                req_memory_limit_mb = 256
        except Exception:
            pass

    # --- 基本校验 ---
    if language not in settings.supported_languages:
        return JSONResponse(
            status_code=400,
            content={"error": f"不支持的语言: {html.escape(language)}"},
        )

    if not problem_id or not problem_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(
            status_code=400,
            content={"error": "problem_id 包含非法字符或为空"},
        )

    # --- 限流：user_id 用 X-User-ID 或 IP ---
    user_id = request.headers.get("X-User-ID", ip)
    try:
        check_submit_allowed(user_id, ip)
        check_inflight_limit(user_id)
    except RateLimitExceeded as e:
        return JSONResponse(
            status_code=429,
            content={"error": "请求过于频繁，请稍后再试", "retry_after_s": e.retry_after_s},
            headers={"Retry-After": str(e.retry_after_s)},
        )

    # --- 获取代码内容 ---
    if code_bytes is None and source_code is None:
        if code is not None:
            # multipart 文件上传（原生 zip 包）
            code_bytes = await code.read()
        elif source_code is not None:
            # JSON 纯文本源码 → 打包为 zip
            code_bytes = _source_to_zip(source_code, language)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "缺少代码内容（code 文件或 source_code 字段）"},
            )

    if code_bytes is None:
        return JSONResponse(
            status_code=400,
            content={"error": "代码不能为空"},
        )

    if len(code_bytes) > MAX_CODE_BYTES:
        return JSONResponse(
            status_code=400,
            content={"error": f"代码过大，上限 {MAX_CODE_BYTES // 1000}KB"},
        )
    if len(code_bytes) == 0:
        return JSONResponse(
            status_code=400,
            content={"error": "代码不能为空"},
        )

    # --- 生成 ID + 落盘 ---
    submission_id = req_submission_id or _generation_id()
    code_sha256 = storage.save_submission_code(code_bytes, submission_id)

    # --- 关联测试数据（若题目已有测试数据）---
    try:
        storage.save_testdata_from_problem(problem_id, submission_id)
    except FileNotFoundError:
        return JSONResponse(
            status_code=400,
            content={"error": f"题目 {html.escape(problem_id)} 不存在或测试数据未就绪"},
        )

    # --- 入队 ---
    queue.enqueue(
        submission_id=submission_id,
        problem_id=problem_id,
        user_id=user_id,
        language=language,
        time_limit_ms=req_time_limit_ms,
        memory_limit_mb=req_memory_limit_mb,
        code_sha256=code_sha256,
    )

    return {
        "submission_id": submission_id,
        "status": "QUEUED",
    }


@router.get("/submission/{submission_id}")
async def get_submission(submission_id: str) -> dict:
    """用户查询评测结果（公开接口；返回状态、汇总、用例明细、编译输出）。

    适配 eoj-main 懒轮询：返回 cases[] + compile_output + score + logs。
    """
    # 安全校验：只允许合法字符
    if not submission_id.replace("_", "").replace("-", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "非法 submission_id"})

    row = query_one(
        "SELECT submission_id, problem_id, language, status, time_ms, memory_kb, "
        "compile_output, results_json, created_at, updated_at "
        "FROM submissions WHERE submission_id = ?",
        (submission_id,),
    )
    if not row:
        return JSONResponse(status_code=404, content={"error": "提交不存在"})

    result = {
        "submission_id": row["submission_id"],
        "problem_id": row["problem_id"],
        "language": row["language"],
        "status": row["status"],
        "time_ms": row["time_ms"],
        "memory_kb": row["memory_kb"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

    # compile_output 仅终态时回显，且做 HTML 转义
    from ..models import FINAL_STATUSES
    if row["status"] in FINAL_STATUSES and row["compile_output"]:
        result["compile_output"] = html.escape(row["compile_output"][:10_000])

    # 返回用例明细（供 eoj-main 懒轮询同步）
    if row["results_json"]:
        try:
            import json
            cases = json.loads(row["results_json"])
            # 脱敏：不返回用户输出内容
            result["cases"] = [
                {
                    "id": c.get("id", 0),
                    "status": c.get("status", "SE"),
                    "time_ms": c.get("time_ms", 0),
                    "memory_kb": c.get("memory_kb", 0),
                    "score": c.get("score", 0),
                    "is_sample": c.get("is_sample", False),
                    "message": c.get("message", "")[:2000],
                }
                for c in cases
            ]
        except Exception:
            result["cases"] = []

    return result
