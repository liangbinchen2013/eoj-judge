"""代码 / 测试数据存取与一次性下载 URL。

安全要点：
  - 文件名统一用 submission_id 生成（不接受用户提供的文件名，防路径穿越）。
  - 所有 zip 操作前先校验成员路径（防 zip-slip）+ 大小/成员数上限（防 zip 炸弹）。
  - 下载响应加 Content-Disposition: attachment，禁止浏览器内联执行。
  - 存储目录权限 700；禁止符号链接。
  - 生产可平滑替换为对象存储（S3/R2），接口不变。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile

from .config import settings

# zip 安全限制
MAX_ZIP_MEMBERS = 10_000
MAX_ZIP_MEMBER_SIZE = 100_000_000  # 100MB
_MAX_ZIP_TOTAL_UNCOMPRESSED = 200_000_000  # 200MB 解压后总上限


def _storage_path(*parts: str) -> str:
    """构建存储路径，确保在 storage_dir 内。"""
    base = os.path.abspath(settings.storage_dir)
    target = os.path.abspath(os.path.join(base, *parts))
    # 双重校验：路径穿越防护
    if not target.startswith(base):
        raise ValueError(f"路径穿越检测: {target}")
    return target


def _ensure_storage_dir() -> None:
    """确保存储目录存在且权限正确。"""
    d = os.path.abspath(settings.storage_dir)
    os.makedirs(d, exist_ok=True)
    # 设置目录权限 700（仅 owner 可读写）
    os.chmod(d, 0o700)


def verify_zip_no_slip(data: bytes, max_members: int = MAX_ZIP_MEMBERS) -> None:
    """解压前校验：拒绝绝对路径、.. 穿越、符号链接、超限成员数（防 zip 炸弹）。

    Raises:
        ValueError: zip 内容不安全。
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > max_members:
            raise ValueError(f"zip 成员数超限: {len(infos)} > {max_members}")

        total_uncompressed = 0
        for info in infos:
            name = info.filename
            # 拒绝绝对路径
            if os.path.isabs(name):
                raise ValueError(f"zip 包含绝对路径: {name}")
            # 拒绝 .. 穿越
            if ".." in name.split("/"):
                raise ValueError(f"zip 包含路径穿越: {name}")
            # 拒绝符号链接（zip 外部属性 bit）
            if (info.external_attr >> 16) & 0o120000:
                raise ValueError(f"zip 包含符号链接: {name}")
            total_uncompressed += info.file_size
            if info.file_size > MAX_ZIP_MEMBER_SIZE:
                raise ValueError(f"zip 成员过大: {name} ({info.file_size} bytes)")

        if total_uncompressed > _MAX_ZIP_TOTAL_UNCOMPRESSED:
            raise ValueError(f"zip 解压后总大小超限: {total_uncompressed}")


def save_submission_code(code_bytes: bytes, submission_id: str) -> str:
    """用户代码打包为 code.zip 落盘。

    返回 SHA-256 哈希（审计用）。
    ★ 代码包内部文件名由 worker 语言配置决定（如 main.cpp），
      这里只存原始字节 + 计算摘要。
    """
    _ensure_storage_dir()
    sub_dir = _storage_path(submission_id)
    os.makedirs(sub_dir, exist_ok=True)
    os.chmod(sub_dir, 0o700)

    code_path = os.path.join(sub_dir, "code.zip")
    with open(code_path, "wb") as f:
        f.write(code_bytes)
    os.chmod(code_path, 0o600)

    return hashlib.sha256(code_bytes).hexdigest()


def save_testdata(zip_bytes: bytes, problem_id: str, submission_id: str) -> None:
    """测试数据 zip 落盘。

    先校验 zip 内容安全性，再复制到提交目录（供 worker 下载）。
    生产环境中 testdata 应预先按 problem_id 存储，此处为简化实现：
    对已有的题目测试数据做硬链接或复制到 submission 目录。
    """
    verify_zip_no_slip(zip_bytes)
    _ensure_storage_dir()
    sub_dir = _storage_path(submission_id)
    os.makedirs(sub_dir, exist_ok=True)
    os.chmod(sub_dir, 0o700)

    tests_path = os.path.join(sub_dir, "tests.zip")
    with open(tests_path, "wb") as f:
        f.write(zip_bytes)
    os.chmod(tests_path, 0o600)


def save_testdata_from_problem(problem_id: str, submission_id: str) -> None:
    """将题目维度的测试数据复制到 submission 目录。

    测试数据应在题目创建时由管理端上传，存储为
    storage/{problem_id}/tests.zip。
    提交时复制（或硬链接）到 storage/{submission_id}/tests.zip。
    """
    _ensure_storage_dir()
    src = _storage_path(problem_id, "tests.zip")
    if not os.path.isfile(src):
        raise FileNotFoundError(f"题目 {problem_id} 的测试数据不存在")

    sub_dir = _storage_path(submission_id)
    os.makedirs(sub_dir, exist_ok=True)
    os.chmod(sub_dir, 0o700)
    dst = os.path.join(sub_dir, "tests.zip")

    # 硬链接（节省磁盘，同文件系统），失败则复制
    try:
        os.link(src, dst)
    except OSError:
        with open(src, "rb") as fsrc:
            with open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
    os.chmod(dst, 0o600)


def load_archive(kind: str, submission_id: str) -> tuple[bytes, str]:
    """读取已存压缩包 → (bytes, 建议下载文件名)。

    kind ∈ {code, tests}
    """
    if kind not in ("code", "tests"):
        raise ValueError(f"非法 kind: {kind}")

    filepath = _storage_path(submission_id, f"{kind}.zip")
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"压缩包不存在: {submission_id}/{kind}.zip")

    with open(filepath, "rb") as f:
        data = f.read()

    filename = f"{submission_id}_{kind}.zip"
    return data, filename


def build_download_url(kind: str, submission_id: str, token: str) -> str:
    """构建一次性下载 URL（公共端点 + token 参数）。"""
    base = settings.public_url.rstrip("/")
    return f"{base}/judge/data/{submission_id}/{kind}?token={token}"


def upload_testdata_for_problem(problem_id: str, zip_bytes: bytes) -> None:
    """管理员上传题目测试数据。校验后落盘到 problem 目录。"""
    verify_zip_no_slip(zip_bytes)
    _ensure_storage_dir()
    prob_dir = _storage_path(problem_id)
    os.makedirs(prob_dir, exist_ok=True)
    os.chmod(prob_dir, 0o700)

    tests_path = os.path.join(prob_dir, "tests.zip")
    with open(tests_path, "wb") as f:
        f.write(zip_bytes)
    os.chmod(tests_path, 0o600)


def eoj_testcases_to_zip(
    testcases: list[dict],
    spj_code: str = "",
    spj_language: str = "",
) -> bytes:
    """将 eoj-main 格式的测试用例 JSON 数组转换为 tests.zip 格式。

    eoj-main 格式: [{input, expected_output, is_sample, score}, ...]
    转换为 zip 内:
      in/1.txt  in/2.txt  ...  (输入)
      out/1.txt out/2.txt ...  (预期输出)
      meta.json              (用例元信息: score/is_sample)
      spj_source.{ext}       (SPJ 源码，如果提供)

    同时保存元信息到 meta.json，供 worker 读取 score/is_sample。
    如果提供 SPJ 源码，也打包进 zip 供 worker 编译。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, tc in enumerate(testcases):
            idx = i + 1
            zf.writestr(f"in/{idx}.txt", tc.get("input", ""))
            zf.writestr(f"out/{idx}.txt", tc.get("expected_output", ""))
        # 元信息单独存储（score, is_sample）
        meta = [
            {"score": tc.get("score", 10), "is_sample": tc.get("is_sample", False)}
            for tc in testcases
        ]
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        # SPJ 源码（如果有）
        if spj_code:
            ext_map = {
                "c": "spj_source.c", "cpp": "spj_source.cpp",
                "python": "spj_source.py", "java": "SpjSource.java",
                "go": "spj_source.go", "rust": "spj_source.rs",
                "javascript": "spj_source.js",
            }
            filename = ext_map.get(spj_language, "spj_source.txt")
            zf.writestr(filename, spj_code)
    return buf.getvalue()


def save_spj_source(problem_id: str, spj_code: str, spj_language: str) -> None:
    """保存 SPJ 源码到 problem 目录（供 worker 下载后编译）。"""
    _ensure_storage_dir()
    prob_dir = _storage_path(problem_id)
    os.makedirs(prob_dir, exist_ok=True)
    os.chmod(prob_dir, 0o700)

    spj_path = os.path.join(prob_dir, "spj_source.txt")
    with open(spj_path, "w", encoding="utf-8") as f:
        f.write(spj_code)
    os.chmod(spj_path, 0o600)

    # 保存语言标记
    lang_path = os.path.join(prob_dir, "spj_language.txt")
    with open(lang_path, "w", encoding="utf-8") as f:
        f.write(spj_language)
    os.chmod(lang_path, 0o600)


def get_spj_source(problem_id: str) -> tuple[str, str] | None:
    """获取 SPJ 源码和语言。返回 (code, language) 或 None。"""
    spj_path = _storage_path(problem_id, "spj_source.txt")
    lang_path = _storage_path(problem_id, "spj_language.txt")
    if not os.path.isfile(spj_path) or not os.path.isfile(lang_path):
        return None
    with open(spj_path, "r", encoding="utf-8") as f:
        code = f.read()
    with open(lang_path, "r", encoding="utf-8") as f:
        language = f.read().strip()
    return code, language


def load_testcase_meta(problem_id: str, submission_id: str) -> list[dict]:
    """读取测试用例元信息（score/is_sample）。从 submission 目录的 tests.zip 中提取 meta.json。"""
    tests_path = _storage_path(submission_id, "tests.zip")
    if not os.path.isfile(tests_path):
        tests_path = _storage_path(problem_id, "tests.zip")
    if not os.path.isfile(tests_path):
        return []
    try:
        with zipfile.ZipFile(tests_path, "r") as zf:
            if "meta.json" in zf.namelist():
                data = zf.read("meta.json")
                import json
                return json.loads(data)
    except Exception:
        pass
    return []
