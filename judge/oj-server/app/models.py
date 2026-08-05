"""Pydantic 模型：API 请求/响应 + 与 worker 的契约数据结构。

契约字段与 docs/PROTOCOL.md 保持一致 —— 两边改字段必须先改协议文档。

安全约束：
  - 所有字符串字段加 max_length 校验（防恶意大 payload 刷内存）。
  - status 枚举严格校验，不在白名单内拒绝。

兼容性：
  - 同时支持 judge 原生状态码（AC/WA/TLE/...）和 eoj-main 状态码
    （accepted/wrong_answer/time_limit_exceeded/...），双向映射见 STATUS_MAP。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# ---------- 状态枚举（与 judge-repo 共用，见 docs/PROTOCOL.md） ----------
FINAL_STATUSES = ("AC", "WA", "TLE", "MLE", "RE", "CE", "SE", "SKIP")
NON_FINAL_STATUSES = ("QUEUED", "JUDGING")
ALL_STATUSES = NON_FINAL_STATUSES + FINAL_STATUSES

# ---------- eoj-main 状态枚举 ----------
EOJ_STATUSES = (
    "accepted", "wrong_answer", "time_limit_exceeded",
    "memory_limit_exceeded", "runtime_error", "compile_error", "system_error",
)
EOJ_NON_FINAL = ("pending",)

# ---------- 双向状态映射（judge ↔ eoj） ----------
JUDGE_TO_EOJ: dict[str, str] = {
    "AC":  "accepted",
    "WA":  "wrong_answer",
    "TLE": "time_limit_exceeded",
    "MLE": "memory_limit_exceeded",
    "RE":  "runtime_error",
    "CE":  "compile_error",
    "SE":  "system_error",
    "SKIP":"system_error",  # SKIP 在 eoj 无对应，映射为 system_error
}

EOJ_TO_JUDGE: dict[str, str] = {
    "accepted":              "AC",
    "wrong_answer":          "WA",
    "time_limit_exceeded":   "TLE",
    "memory_limit_exceeded": "MLE",
    "runtime_error":         "RE",
    "compile_error":         "CE",
    "system_error":          "SE",
}


# ---------- 用户提交 ----------
class SubmitRequest(BaseModel):
    problem_id: str = Field(..., max_length=64, min_length=1)
    language: str = Field(..., max_length=16, min_length=1)
    source_code: str | None = Field(default=None, max_length=2_000_000)
    submission_id: str | None = Field(default=None, max_length=128)
    time_limit_ms: int = Field(default=2000, ge=1, le=300_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=16384)

    @field_validator("problem_id")
    @classmethod
    def problem_id_alphanum(cls, v: str) -> str:
        """只允许字母数字、下划线、连字符的 problem_id。"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("problem_id 包含非法字符")
        return v

    @field_validator("language")
    @classmethod
    def language_whitelist(cls, v: str) -> str:
        """语言必须在服务端白名单内。"""
        from .config import settings
        if v not in settings.supported_languages:
            raise ValueError(f"不支持的语言: {v}")
        return v

    @field_validator("submission_id")
    @classmethod
    def submission_id_safe(cls, v: str | None) -> str | None:
        """只允许字母数字、下划线、连字符（eoj-main 整数 ID 也兼容）。"""
        if v is None:
            return v
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("submission_id 包含非法字符")
        return v


# ---------- 任务（服务端 → worker，GET /api/judge/poll 响应） ----------
class JudgeTask(BaseModel):
    submission_id: str
    problem_id: str
    language: str
    time_limit_ms: int = Field(default=2000, ge=1, le=300_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=16384)
    code_url: str = Field(..., max_length=512)
    testdata_url: str = Field(..., max_length=512)
    token: str = Field(..., max_length=128)
    callback_url: str = Field(..., max_length=512)


# ---------- 结果（worker → 服务端，POST /api/judge/report 请求体） ----------
class CaseResult(BaseModel):
    id: int = Field(..., ge=1)
    status: str
    time_ms: int = Field(default=0, ge=0, le=300_000)
    memory_kb: int = Field(default=0, ge=0, le=100_000_000)
    # eoj-main 扩展字段（向后兼容：worker 不传时使用默认值）
    score: int = Field(default=0, ge=0, le=1000000)
    is_sample: bool = Field(default=False)
    message: str = Field(default="", max_length=2000)

    @field_validator("status")
    @classmethod
    def case_status_enum(cls, v: str) -> str:
        # 同时接受 judge 原生状态码和 eoj 状态码
        if v in ("AC", "WA", "TLE", "MLE", "RE", "SE", "SKIP"):
            return v
        if v in EOJ_STATUSES:
            return EOJ_TO_JUDGE.get(v, "SE")
        raise ValueError(f"非法用例状态: {v}")


class JudgeResult(BaseModel):
    submission_id: str = Field(..., max_length=128)
    token: str = Field(..., max_length=128)
    status: str
    time_ms: int = Field(default=0, ge=0, le=300_000)
    memory_kb: int = Field(default=0, ge=0, le=100_000_000)
    compile_output: str = Field(default="", max_length=100_000)
    cases: list[CaseResult] = Field(default_factory=list, max_length=512)
    # eoj-main 扩展字段
    score: int = Field(default=0, ge=0, le=100000000)
    logs: list[dict] = Field(default_factory=list, max_length=200)
    judge_type: str = Field(default="default", max_length=16)
    spj_language: str = Field(default="", max_length=16)

    @field_validator("status")
    @classmethod
    def status_enum(cls, v: str) -> str:
        # 同时接受 judge 原生状态码和 eoj 状态码
        if v in FINAL_STATUSES:
            return v
        if v in EOJ_STATUSES:
            return EOJ_TO_JUDGE.get(v, "SE")
        raise ValueError(f"非法评测状态: {v}")

    @field_validator("submission_id")
    @classmethod
    def submission_id_safe(cls, v: str) -> str:
        """只允许字母数字、下划线、连字符（兼容 eoj-main 整数 ID）。"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("submission_id 包含非法字符")
        return v


# ---------- 心跳（worker → 服务端） ----------
class Heartbeat(BaseModel):
    worker_id: str = Field(..., max_length=64, min_length=1)
    queue_remaining: int = Field(default=0, ge=0)

    @field_validator("worker_id")
    @classmethod
    def worker_id_safe(cls, v: str) -> str:
        """只允许字母数字、连字符。"""
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        if not all(c in allowed for c in v):
            raise ValueError("worker_id 包含非法字符")
        return v
