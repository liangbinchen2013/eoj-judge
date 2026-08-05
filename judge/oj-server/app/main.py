"""FastAPI 入口：应用装配 + 启动钩子。

全局中间件：
  - 请求体大小限制（2MB 防超大 payload）。
  - 日志：只打路由+状态码+耗时；用户内容一律截断+转义后才可入日志。
  - 统一异常处理：RateLimitExceeded → 429；校验失败 → 400；其余 → 500（不泄栈）。
  - 后台任务：周期执行 queue.requeue_stale（超时兜底）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db

# 日志配置：用户内容一律截断后才可入日志
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("oj-server")


def _sanitize_path(path: str) -> str:
    """脱敏：移除 URL 中的 token 参数。"""
    import re
    return re.sub(r"token=[^&\s]+", "token=***", path)


_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动
    errors = settings.validate()
    if errors:
        for err in errors:
            logger.warning("配置警告: %s", err)

    init_db()
    logger.info("数据库已初始化: %s", settings.db_path)

    os.makedirs(settings.storage_dir, exist_ok=True)
    os.chmod(settings.storage_dir, 0o700)

    loop = asyncio.get_event_loop()
    task = loop.create_task(_periodic_maintenance())
    _background_tasks.append(task)

    logger.info("OJ Judge Server 启动完成: %s:%d", settings.host, settings.port)

    yield

    # 关闭
    for task in _background_tasks:
        task.cancel()
    logger.info("OJ Judge Server 已关闭")


app = FastAPI(
    title="OJ Judge Server",
    description="基于 GitHub Actions 批量 worker 的 OJ 评测后端",
    version="0.1.0",
    lifespan=lifespan,
)


# --- 全局中间件 ---

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志 + 请求体大小限制 + 耗时统计。"""
    start = time.time()

    # 请求体大小限制（2MB 全局上限）
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 2_000_000:
        return JSONResponse(
            status_code=413,
            content={"error": "请求体过大，上限 2MB"},
        )

    response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000
    path = _sanitize_path(str(request.url))
    logger.info(
        "%s %s → %d (%.0fms)",
        request.method, path, response.status_code, elapsed_ms,
    )
    return response


# --- 统一异常处理 ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理：不泄露栈信息。"""
    from .ratelimit import RateLimitExceeded

    if isinstance(exc, RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"error": "请求过于频繁", "retry_after_s": exc.retry_after_s},
            headers={"Retry-After": str(exc.retry_after_s)},
        )

    logger.error("未处理的异常: %s %s", type(exc).__name__, str(exc)[:200])
    return JSONResponse(
        status_code=500,
        content={"error": "服务内部错误"},
    )


# --- 存活探针 ---

@app.get("/healthz")
async def healthz() -> dict:
    """存活探针（无鉴权，供负载均衡/监控使用）。"""
    return {"status": "ok"}


# --- 路由挂载 ---

from .routers import submit, poll, report, heartbeat, data, admin, eoj_bridge

app.include_router(submit.router)
app.include_router(poll.router)
app.include_router(report.router)
app.include_router(heartbeat.router)
app.include_router(data.router)
app.include_router(admin.router)
app.include_router(eoj_bridge.router)


async def _periodic_maintenance():
    """后台周期性维护任务：清理过期 token + 超时任务回队。"""
    from . import auth, queue

    while True:
        try:
            await asyncio.sleep(60)  # 每 60 秒一次
            cleaned = auth.cleanup_expired_tokens()
            if cleaned > 0:
                logger.debug("清理过期 token: %d 条", cleaned)
            requeued = queue.requeue_stale()
            if requeued > 0:
                logger.info("超时任务回队: %d 条", requeued)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("后台维护异常: %s", str(e)[:200])


# --- 入口（直接运行） ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )
