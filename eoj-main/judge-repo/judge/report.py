"""结果汇总与回调。

职责：
  - 汇总各用例 CaseOutcome → 总 status/time_ms/memory_kb：
      * 任一用例非 AC → 提交判非 AC（优先级: TLE/MLE/RE > WA）；
      * time_ms = 所有用例最大值; memory_kb = 峰值。
  - POST callback_url 回调服务端，携带一次性 token：
      ★ 回调成功(2xx) 才认为完成; 失败重试（指数退避 3 次），
        仍失败则丢弃本次结果 —— 任务在服务端队列保底，下次 dispatch 会重评（幂等）。

安全：
  - 结果中所有文本（compile_output/case detail）截断 + 转义后再发送。
  - token 只出现在 body 的专用字段，绝不写入日志、绝不拼进 URL query。
  - 回调路径只接受 https。

兼容性：
  - eoj-main 扩展字段: cases[].score, cases[].is_sample, cases[].message,
    整体 score, logs[], judge_type, spj_language。
  - 状态映射: judge 原生码(AC/WA/...) 和 eoj 码(accepted/wrong_answer/...)
    双向映射，见 STATUS_MAP。
"""

from __future__ import annotations

import html
import json
import time
import urllib.request
import urllib.error

from .config import config
from .sandbox import CaseOutcome


# 状态优先级（数值越大优先级越高，用于"首个失败用例定级"）
_STATUS_PRIORITY = {
    "AC": 0,
    "WA": 1,
    "RE": 2,
    "TLE": 3,
    "MLE": 4,
    "SE": 5,
    "CE": 10,
}

# judge → eoj 状态映射
_JUDGE_TO_EOJ = {
    "AC":  "accepted",
    "WA":  "wrong_answer",
    "TLE": "time_limit_exceeded",
    "MLE": "memory_limit_exceeded",
    "RE":  "runtime_error",
    "CE":  "compile_error",
    "SE":  "system_error",
    "SKIP":"system_error",
}


def build_result(
    submission_id: str,
    cases: list[CaseOutcome],
    compile_output: str = "",
    status_override: str = "",
    testcase_meta: list[dict] | None = None,
    logs: list[dict] | None = None,
    eoj_mode: bool = False,
) -> dict:
    """汇总用例结果 → 协议规定的结果 JSON（见 PROTOCOL.md）。

    Args:
        submission_id: 提交 ID
        cases: 每个用例的评测结果
        compile_output: 编译输出（CE 时携带）
        status_override: 覆盖状态（如 CE 时直接设 CE）
        testcase_meta: eoj-main 测试用例元信息 [{score, is_sample}, ...]
        logs: eoj-main 评测日志
        eoj_mode: 是否输出 eoj-main 兼容格式

    Returns:
        协议规定的 result dict
    """
    if status_override:
        result = {
            "submission_id": submission_id,
            "status": status_override,
            "time_ms": 0,
            "memory_kb": 0,
            "compile_output": _sanitize_text(compile_output)[:100_000],
            "cases": [],
        }
        if eoj_mode:
            result["score"] = 0
            result["logs"] = logs or []
        return result

    # 汇总策略
    if not cases:
        result = {
            "submission_id": submission_id,
            "status": "SE",
            "time_ms": 0,
            "memory_kb": 0,
            "compile_output": _sanitize_text(compile_output)[:100_000],
            "cases": [],
        }
        if eoj_mode:
            result["score"] = 0
            result["logs"] = logs or []
        return result

    # 寻找最高优先级的状态
    worst_status = "AC"
    worst_priority = 0
    max_time_ms = 0
    max_memory_kb = 0
    total_score = 0

    for case in cases:
        pri = _STATUS_PRIORITY.get(case.status, 5)
        if pri > worst_priority:
            worst_status = case.status
            worst_priority = pri
        max_time_ms = max(max_time_ms, case.time_ms)
        max_memory_kb = max(max_memory_kb, case.memory_kb)

    # 序列化 cases
    cases_json = []
    for i, case in enumerate(cases):
        entry: dict = {
            "id": i + 1,
            "status": case.status,
            "time_ms": case.time_ms,
            "memory_kb": case.memory_kb,
        }
        # eoj-main 扩展字段
        meta = {}
        if testcase_meta and i < len(testcase_meta):
            meta = testcase_meta[i]
        entry["score"] = meta.get("score", 0) if case.status == "AC" else 0
        entry["is_sample"] = meta.get("is_sample", False)
        entry["message"] = _sanitize_text(case.detail)[:2000]

        # eoj 模式：状态码转为 eoj 格式
        if eoj_mode:
            entry["status"] = _JUDGE_TO_EOJ.get(case.status, "system_error")

        cases_json.append(entry)
        if case.status == "AC" and meta.get("score"):
            total_score += meta["score"]

    # 截断到 512 条
    if len(cases_json) > 512:
        cases_json = cases_json[:512]

    result = {
        "submission_id": submission_id,
        "status": worst_status,
        "time_ms": max_time_ms,
        "memory_kb": max_memory_kb,
        "compile_output": _sanitize_text(compile_output)[:100_000],
        "cases": cases_json,
    }

    if eoj_mode:
        result["status"] = _JUDGE_TO_EOJ.get(worst_status, "system_error")
        result["score"] = total_score
        result["logs"] = logs or []

    return result


def _sanitize_text(text: str) -> str:
    """对文本做安全处理：HTML 转义 + 移除控制字符（除换行/制表）。"""
    if not text:
        return ""
    # 只保留可打印 ASCII + 换行/制表符 + 中文等 Unicode
    safe = ""
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 and cp not in (0x09, 0x0A, 0x0D):
            safe += "?"
        else:
            safe += ch
    return html.escape(safe, quote=False)


def send_report(callback_url: str, token: str, result_json: dict) -> bool:
    """回调服务端；返回是否成功（2xx）。带重试与退避。

    安全：
      - 回调路径固定为服务端下发值，只接受 https。
      - token 只出现在 body 中，不进日志。
    """
    # 校验 URL scheme
    if not callback_url.startswith("https://") and not callback_url.startswith("http://127."):
        # 仅允许 https 或本地开发 http
        return False

    # 注入 token 到结果
    payload = {**result_json, "token": token}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # 大小校验
    if len(data) > config.result_payload_limit_bytes:
        # 截断 cases 明细
        slim = {**result_json, "token": token}
        if "cases" in slim and len(slim["cases"]) > 10:
            slim["cases"] = slim["cases"][:10]
        data = json.dumps(slim, ensure_ascii=False).encode("utf-8")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                callback_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "oj-judge-worker/0.1",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return False  # token 无效，不重试
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except (urllib.error.URLError, OSError):
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return False
