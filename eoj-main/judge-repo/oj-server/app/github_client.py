"""GitHub REST API 客户端。

职责：
  - dispatch 触发评测 job（workflow_dispatch）。
  - 查询 run 状态（失联检测用）。
  - 取消 run。

安全要点：
  - 本模块持有 GITHUB_TOKEN —— 整个系统唯一的密。
  - token 仅存在于内存，绝不写入日志/错误信息/回调 payload。
  - dispatch payload 只带元信息（mode + worker_key），代码/数据一律走下载 URL。
"""

from __future__ import annotations

import time
import urllib.parse

import httpx

from .config import settings


def _api_url(path: str) -> str:
    return f"https://api.github.com/repos/{settings.judge_repo_owner}/{settings.judge_repo_name}/{path}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "oj-judge-server/0.1",
    }


def _sanitize_error(msg: str) -> str:
    """脱敏：移除 GitHub token 后再返回。"""
    if settings.github_token:
        msg = msg.replace(settings.github_token, "***")
    return msg


def dispatch_workflow(mode: str = "batch", submission_id: str = "",
                      worker_key: str = "") -> bool:
    """触发评测 workflow；返回是否成功（2xx）。

    mode: "batch"（默认，批量 worker）| "single"（单发调试）。

    payload 只带元信息 + worker_key —— 代码/数据一律走下载 URL（README §7.3）。
    """
    url = _api_url(f"actions/workflows/{settings.judge_workflow_file}.yml/dispatches")
    body = {
        "ref": settings.judge_repo_ref,
        "inputs": {
            "mode": mode,
            "submission_id": submission_id,
            "worker_key": worker_key,
        },
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
                resp = client.post(url, headers=_headers(), json=body)
                if resp.status_code == 429:
                    # 速率限制：退避重试
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                        continue
                if 200 <= resp.status_code < 300:
                    return True
                # 422: payload 过大 / 参数错误 → 不再重试
                if resp.status_code == 422:
                    return False
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        except httpx.RequestError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return False


def get_recent_runs(limit: int = 20) -> list[dict]:
    """查询最近 workflow_dispatch runs（用于失联检测与对账）。"""
    url = _api_url("actions/runs")
    params = {
        "event": "workflow_dispatch",
        "per_page": min(limit, 100),
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            resp = client.get(url, headers=_headers(), params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("workflow_runs", [])
    except httpx.RequestError:
        pass
    return []


def cancel_run(run_id: int) -> bool:
    """取消指定 run（用户取消提交时用）。"""
    url = _api_url(f"actions/runs/{run_id}/cancel")
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            resp = client.post(url, headers=_headers())
            return 200 <= resp.status_code < 300
    except httpx.RequestError:
        return False


def get_run_jobs(run_id: int) -> list[dict]:
    """获取指定 run 的 jobs 列表。"""
    url = _api_url(f"actions/runs/{run_id}/jobs")
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            resp = client.get(url, headers=_headers())
            if resp.status_code == 200:
                data = resp.json()
                return data.get("jobs", [])
    except httpx.RequestError:
        pass
    return []
