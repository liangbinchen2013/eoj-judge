"""各语言编译入口。

环境: Ubuntu (GitHub Actions ubuntu-latest)，OJ 后端拥有 root 权限。

流程:
  解压 code.zip → 按 languages/<lang>.yml 的 compile_cmd 编译 → 剥离可执行文件权限 → 生成入口。

安全要点:
  - 编译命令全部来自语言白名单配置，不接受任何用户输入拼接。
  - 编译在 Docker 沙箱内运行（--network none + 资源限制 + nobody 用户）。
  - 编译产物 chmod 500（仅 owner r-x，最小权限）。
  - 编译超时 30s，防编译期作恶。
  - 编译输出截断 64KB。
  - python/javascript 类语言无编译期 → 直接跳过。
  - CE 判定：编译退出码非 0 → 整个提交 CE，不再跑用例。
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass

from .config import config
from .sandbox import strip_binary_permissions


@dataclass
class CompileResult:
    ok: bool
    executable: str          # 入口文件（如 ./main 或 python3）
    compile_output: str      # 截断后的编译输出（CE 时随结果回调）
    language: str


# 编译沙箱安全参数（比运行沙箱更宽松的超时和内存）
_COMPILE_TIMEOUT_S = 30
_COMPILE_MEMORY_MB = 512
_COMPILE_SECURITY_ARGS: list[str] = [
    "--network", "none",
    "--user", "65534:65534",             # nobody 用户
    "--memory", f"{_COMPILE_MEMORY_MB}m",
    "--memory-swap", f"{_COMPILE_MEMORY_MB}m",
    "--cpus", "1",
    "--pids-limit", "64",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--read-only",
    "--tmpfs", "/tmp:rw,size=128m,nosuid,nodev,noexec",
]


def prepare_code(workdir: str, code_zip: bytes, language: str) -> str | None:
    """解压代码包到 workdir/code/（zip-slip 防护）。

    Returns:
        源码文件名（相对 workdir/code），失败返回 None。
    """
    lang_config = config.get_language_config(language)
    if not lang_config:
        return None

    source_file = lang_config.get("source_file", "")
    code_dir = os.path.join(workdir, "code")
    os.makedirs(code_dir, exist_ok=True)
    os.chmod(code_dir, 0o755)

    try:
        with zipfile.ZipFile(io.BytesIO(code_zip)) as zf:
            # zip-slip 校验
            for info in zf.infolist():
                name = info.filename
                if os.path.isabs(name):
                    raise ValueError(f"zip 包含绝对路径: {name}")
                if ".." in name.split("/"):
                    raise ValueError(f"zip 包含路径穿越: {name}")
                if (info.external_attr >> 16) & 0o120000:
                    raise ValueError(f"zip 包含符号链接: {name}")

            zf.extractall(code_dir)
    except (zipfile.BadZipFile, ValueError, OSError):
        return None

    # 验证源码文件存在
    if source_file and os.path.exists(os.path.join(code_dir, source_file)):
        return source_file

    return None


def compile_submission(workdir: str, language: str) -> CompileResult:
    """编译/准备用户代码。

    CE 时返回 CompileResult(ok=False, ...)。
    编译在 Docker 沙箱内完成，产物自动剥离不必要权限。
    """
    lang_config = config.get_language_config(language)
    if not lang_config:
        return CompileResult(
            ok=False, executable="",
            compile_output=f"Unsupported language: {language}",
            language=language,
        )

    compile_cmd = lang_config.get("compile", [])
    run_cmd_list = lang_config.get("run", [])
    image = lang_config.get("image", "ubuntu:latest")

    code_dir = os.path.join(workdir, "code")

    if not compile_cmd:
        # 无编译期（python/javascript 等）
        run_entry = run_cmd_list[0] if run_cmd_list else ""
        return CompileResult(
            ok=True,
            executable=run_entry,
            compile_output="",
            language=language,
        )

    # 在 Docker 沙箱内编译，以 nobody 用户运行
    # 挂载策略：code/ 挂为读写（编译需要产出文件），但编译完成后立即剥离权限
    docker_cmd = [
        "docker", "run", "--rm",
        *_COMPILE_SECURITY_ARGS,
        "-v", f"{code_dir}:/sandbox:rw",
        "-w", "/sandbox",
        image,
    ] + compile_cmd

    try:
        proc = subprocess.run(
            docker_cmd,
            capture_output=True,
            timeout=_COMPILE_TIMEOUT_S + 5,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(
            ok=False, executable="",
            compile_output="Compilation timed out",
            language=language,
        )

    stdout = proc.stdout.decode("utf-8", errors="replace")[:64_000]
    stderr = proc.stderr.decode("utf-8", errors="replace")[:64_000]
    compile_output = (stdout + "\n" + stderr).strip()[:64_000]

    if proc.returncode != 0:
        return CompileResult(
            ok=False,
            executable="",
            compile_output=compile_output or f"Compilation failed (exit {proc.returncode})",
            language=language,
        )

    # ★ 编译成功 → 剥离可执行文件权限（最小权限）
    # 产物通常为 main 或 a.out
    _strip_compiled_binaries(code_dir)

    # 编译成功，提取入口命令
    executable = run_cmd_list[0] if run_cmd_list else "./main"
    return CompileResult(
        ok=True,
        executable=executable,
        compile_output=compile_output[:64_000],
        language=language,
    )


def compile_spj_source(workdir: str, spj_language: str) -> CompileResult:
    """编译 SPJ 源码（从 spj_source.{ext} 编译为 spj 可执行文件）。

    SPJ 源码放在 workdir/in/ 目录下，编译产物也在同一目录。
    """
    code_dir = os.path.join(workdir, "in")
    source_file_map = {
        "c":          "spj_source.c",
        "cpp":        "spj_source.cpp",
        "python":     "spj_source.py",
        "java":       "SpjSource.java",
        "go":         "spj_source.go",
        "rust":       "spj_source.rs",
        "javascript": "spj_source.js",
    }

    source_file = source_file_map.get(spj_language, "")
    source_path = os.path.join(code_dir, source_file)

    if not os.path.exists(source_path):
        return CompileResult(
            ok=False, executable="",
            compile_output=f"SPJ 源文件不存在: {source_file}",
            language=spj_language,
        )

    # 语言编译命令映射
    compile_cmds = {
        "c":          ["gcc", "-std=c11", "-O2", "-o", "spj", source_file],
        "cpp":        ["g++", "-std=c++17", "-O2", "-o", "spj", source_file],
        "java":       ["javac", source_file],
        "go":         ["go", "build", "-o", "spj", source_file],
        "rust":       ["rustc", "-O", "-o", "spj", source_file],
        "python":     [],   # 免编译
        "javascript": [],   # 免编译
    }

    compile_cmd = compile_cmds.get(spj_language, [])
    if not compile_cmd:
        # 解释型语言免编译，直接返回
        return CompileResult(
            ok=True, executable=source_file,
            compile_output="", language=spj_language,
        )

    # 在 Docker 沙箱内编译 SPJ
    docker_cmd = [
        "docker", "run", "--rm",
        *_COMPILE_SECURITY_ARGS,
        "-v", f"{code_dir}:/sandbox:rw",
        "-w", "/sandbox",
        "gcc:13-bookworm" if spj_language in ("c", "cpp") else "ubuntu:latest",
    ] + compile_cmd

    # 根据语言选择合适的镜像
    image_map = {
        "c": "gcc:13-bookworm", "cpp": "gcc:13-bookworm",
        "java": "eclipse-temurin:21-jdk", "go": "golang:1.22-bookworm",
        "rust": "rust:1.78-bookworm",
    }
    image = image_map.get(spj_language, "ubuntu:latest")
    docker_cmd[4] = image  # replace image

    try:
        proc = subprocess.run(
            docker_cmd,
            capture_output=True,
            timeout=_COMPILE_TIMEOUT_S + 5,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(
            ok=False, executable="",
            compile_output="SPJ compilation timed out",
            language=spj_language,
        )

    stdout = proc.stdout.decode("utf-8", errors="replace")[:64_000]
    stderr = proc.stderr.decode("utf-8", errors="replace")[:64_000]
    compile_output = (stdout + "\n" + stderr).strip()[:64_000]

    if proc.returncode != 0:
        return CompileResult(
            ok=False, executable="",
            compile_output=compile_output or f"SPJ compilation failed (exit {proc.returncode})",
            language=spj_language,
        )

    # 剥离权限
    spj_bin = os.path.join(code_dir, "spj")
    if os.path.exists(spj_bin):
        strip_binary_permissions(spj_bin)
        return CompileResult(
            ok=True, executable="./spj",
            compile_output=compile_output[:64_000],
            language=spj_language,
        )

    # Java 编译产物是 .class 文件
    if spj_language == "java" and os.path.exists(os.path.join(code_dir, "SpjSource.class")):
        return CompileResult(
            ok=True, executable="java SpjSource",
            compile_output="",
            language=spj_language,
        )

    return CompileResult(
        ok=False, executable="",
        compile_output="SPJ 编译产物未找到",
        language=spj_language,
    )


def _strip_compiled_binaries(code_dir: str) -> None:
    """遍历编译目录，对所有可执行文件剥离不必要权限。

    设置 500（r-x------）：
      - owner 可读可执行
      - 不可写（防自修改）
      - group/other 无任何权限
    """
    for root, dirs, files in os.walk(code_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                st = os.stat(fpath)
                # 如果是可执行文件或有执行位，剥离权限
                if st.st_mode & 0o111:
                    strip_binary_permissions(fpath)
            except OSError:
                pass
        # 目录权限也做限制
        for dname in dirs:
            dpath = os.path.join(root, dname)
            try:
                os.chmod(dpath, 0o500)  # r-x------
            except OSError:
                pass
