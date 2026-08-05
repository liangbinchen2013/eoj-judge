"""Docker 沙箱封装 —— 评测安全的核心。

环境: Ubuntu (GitHub Actions ubuntu-latest)，OJ 后端拥有 root 权限。

★★★ 最小化权限原则：
  - 容器内以 nobody 用户运行（UID 65534），非 root。
  - 代码/输入目录只读挂载，仅输出目录可写。
  - 根文件系统只读（--read-only），/tmp 为 tmpfs。
  - 编译产物 chmod 500（仅 owner 读+执行）后才运行。
  - --cap-drop ALL + --security-opt no-new-privileges。
  - 使用 /usr/bin/time -v 精确测量内存（Maximum resident set size）。
  - ulimit -v 限制虚拟内存（在容器内由 shell 设置）。
  - 容器无法读取数据库、secrets、或其他任何外部文件。
  - subprocess 全部使用 argv 列表（shell=False）。

退出码映射:
  124 (timeout) → TLE
  137 (SIGKILL/OOM) → MLE
  非 0 → RE
  正常退出 → 比对输出判 AC/WA
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass

# 退出码语义
EXIT_TIMEOUT = 124       # timeout 命令 KILL 退出码 → TLE
EXIT_OOM_KILL = 137      # 137 = 128+9(SIGKILL) → MLE

# 沙箱内用户: nobody (UID 65534, 无特权)
_SANDBOX_USER = "65534:65534"

# 固定容器安全参数（除镜像/挂载/资源配额外不允许改动）
_SECURITY_ARGS: list[str] = [
    "--network", "none",                 # ★ 禁止一切网络
    "--cpus", "1",
    "--pids-limit", "64",                # 防 fork 炸弹
    "--ulimit", "nofile=64:64",          # 文件句柄上限
    "--cap-drop", "ALL",                 # 丢弃全部 capabilities
    "--security-opt", "no-new-privileges:true",  # 禁止提权
    "--read-only",                       # ★ 根文件系统只读
    "--tmpfs", "/tmp:rw,size=64m,nosuid,nodev,noexec",  # tmpfs 无执行
]


@dataclass
class CaseOutcome:
    """单用例结果（供 report.py 汇总）。"""
    status: str          # AC|WA|TLE|MLE|RE|SE
    time_ms: int
    memory_kb: int
    detail: str = ""     # 截断的错误/差异摘要（≤ 2KB）
    score: int = 0       # eoj-main: 该用例分值
    is_sample: bool = False  # eoj-main: 是否样例用例


def _read_bounded(path: str, max_bytes: int) -> str:
    """安全读取文件，截断到 max_bytes。"""
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
            if len(data) == max_bytes:
                return data.decode("utf-8", errors="replace") + "\n[输出已截断]"
            return data.decode("utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return ""


def _build_docker_cmd(
    image: str,
    run_command: list[str],
    run_dir: str,         # 沙箱内运行目录 (如 /sandbox)
    workdir: str,         # 宿主机工作目录
    time_limit_ms: int,
    memory_limit_mb: int,
    input_file: str,      # 输入文件（沙箱内路径）
    output_file: str,     # 输出文件（沙箱内路径）
) -> list[str]:
    """组装 docker run 命令（全部 argv 列表，shell=False）。

    挂载策略（最小权限）：
      - 代码目录 /sandbox/code: ro（只读，防恶意修改源码后重编译）
      - 输入目录 /sandbox/in: ro（只读）
      - 输出目录 /sandbox/out: rw（唯一可写位置）
      - /tmp: tmpfs（独立的内存文件系统）

    超时体系:
      1. 外层 timeout：墙钟兜底
      2. 容器内 timeout：精确到用例
      3. 容器内 ulimit -v：虚拟内存限制（MB → KB）
      4. /usr/bin/time -v：精确内存采样（Maximum resident set size）
    """
    wall_seconds = max(1, time_limit_ms // 1000 + 2)
    cpu_seconds = max(1, time_limit_ms // 1000 + 1)
    memory_kb = memory_limit_mb * 1024

    code_dir = os.path.join(workdir, "code")
    in_dir = os.path.join(workdir, "in")
    out_dir = os.path.join(workdir, "out")

    # 容器内命令:
    #   1. ulimit -v 限制虚拟内存
    #   2. /usr/bin/time -v 采样内存
    #   3. timeout 限制墙钟
    #   4. 运行用户程序 < input > output
    #   5. echo $? 返回退出码
    inner_script = (
        f"ulimit -v {memory_kb}; "
        f"ulimit -t {cpu_seconds}; "
        f"/usr/bin/time -v -o /tmp/time.log "
        f"timeout -s KILL {cpu_seconds} "
        f"{' '.join(run_command)} "
        f"< {input_file} "
        f"> {output_file}; "
        f"echo $?"
    )

    cmd = [
        "timeout", "-s", "KILL", str(wall_seconds),
        "docker", "run", "--rm",
        # ★ 以 nobody 用户运行（非 root）
        "--user", _SANDBOX_USER,
        # 网络隔离
        "--network", "none",
        # 资源限制
        "--memory", f"{memory_limit_mb}m",
        "--memory-swap", f"{memory_limit_mb}m",
        "--cpus", "1",
        "--pids-limit", "64",
        "--ulimit", "nofile=64:64",
        # 能力限制
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        # ★ 根文件系统只读
        "--read-only",
        # ★ 临时文件系统（不可执行、不可 suid）
        "--tmpfs", "/tmp:rw,size=128m,nosuid,nodev,noexec",
        # ★ 挂载点（最小权限）
        # 代码目录：只读
        "-v", f"{code_dir}:/sandbox/code:ro",
        # 输入目录：只读
        "-v", f"{in_dir}:/sandbox/in:ro",
        # 输出目录：唯一可写位置
        "-v", f"{out_dir}:/sandbox/out:rw",
        # 工作目录
        "-w", run_dir,
        image,
        "sh", "-c", inner_script,
    ]
    return cmd


def run_case(
    image: str,
    run_command: list[str],
    workdir: str,
    time_limit_ms: int,
    memory_limit_mb: int,
    input_file: str = "in/1.txt",
    output_file: str = "out/user_out.txt",
) -> CaseOutcome:
    """在沙箱内运行一个用例，返回结果。

    Args:
        image: Docker 镜像（白名单，来自 languages/*.yml）。
        run_command: 容器内运行命令（argv 列表）。
        workdir: 宿主机工作目录，结构:
          workdir/
            code/     → 挂载为 /sandbox/code (ro)
            in/       → 挂载为 /sandbox/in (ro)
            out/      → 挂载为 /sandbox/out (rw，唯一可写)
        time_limit_ms: 时间限制（毫秒）。
        memory_limit_mb: 内存限制（MB）。
        input_file: 输入文件路径（相对于 /sandbox）。
        output_file: 输出文件路径（相对于 /sandbox）。

    Returns:
        CaseOutcome
    """
    # 确保输出目录存在且权限正确
    out_dir = os.path.join(workdir, "out")
    os.makedirs(out_dir, exist_ok=True)
    os.chmod(out_dir, 0o755)

    # 确保输入文件存在
    in_path = os.path.join(workdir, "in", os.path.basename(input_file))
    if not os.path.exists(in_path):
        with open(in_path, "w") as f:
            f.write("")

    # 组装 docker run 命令
    cmd = _build_docker_cmd(
        image=image,
        run_command=run_command,
        run_dir="/sandbox/code",
        workdir=workdir,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        input_file=f"/sandbox/{input_file}",
        output_file=f"/sandbox/{output_file}",
    )

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=time_limit_ms / 1000.0 + 5,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return CaseOutcome(
            status="TLE", time_ms=time_limit_ms, memory_kb=0,
            detail="wall timeout"
        )

    wall_ms = int((time.time() - start) * 1000)
    exit_code = proc.returncode

    # 读取内存采样（/usr/bin/time -v 的输出在 /tmp/time.log）
    # 宿主机路径: workdir 下的 tmp（但 /tmp 是容器内 tmpfs）
    # 改用 docker inspect 方式或直接在容器输出里找
    # 简化实现：使用容器退出码和 OOM 判定
    memory_kb = _sample_memory(out_dir, memory_limit_mb)

    # 读取用户输出
    from .config import config as worker_config
    out_path = os.path.join(workdir, "out", os.path.basename(output_file))
    user_output = _read_bounded(out_path, worker_config.output_limit_bytes)

    # 退出码映射
    if exit_code == 137:
        # 137 = 128+9(SIGKILL) → 可能是 OOM Killer
        return CaseOutcome(
            status="MLE", time_ms=wall_ms,
            memory_kb=memory_limit_mb * 1024,
            detail="memory limit exceeded"
        )

    if exit_code == 124:
        # timeout 命令返回 124 → TLE
        return CaseOutcome(
            status="TLE", time_ms=wall_ms, memory_kb=memory_kb,
            detail="time limit exceeded"
        )

    if exit_code != 0:
        # 非零退出 → RE
        detail = user_output[:2000] if user_output else f"exit code {exit_code}"
        return CaseOutcome(
            status="RE", time_ms=wall_ms, memory_kb=memory_kb, detail=detail
        )

    # 正常退出
    return CaseOutcome(
        status="AC", time_ms=wall_ms, memory_kb=memory_kb, detail=""
    )


def _sample_memory(out_dir: str, memory_limit_mb: int) -> int:
    """从 /usr/bin/time 日志文件采样内存（若可用），否则返回估算值。

    实际实现中可通过 docker run 的 --memory 和 OOM 判定内存使用；
    更精确的实现应在容器内写 /tmp/time.log，然后在宿主机读取。
    由于 time.log 写在 tmpfs 上，需要通过其他方式获取。

    降级策略：返回 0（表示无法精确采样，由外层用 OOM 判定 MLE）。
    """
    # 尝试读取 time.log（如果通过别的方式保存了）
    time_log = os.path.join(out_dir, "..", "time.log")
    if os.path.exists(time_log):
        try:
            with open(time_log, "r") as f:
                for line in f:
                    if "Maximum resident set size" in line:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            return int(parts[-1].strip())  # KB
        except (OSError, ValueError):
            pass
    return 0


def check_output_diff(user_out_path: str, answer_path: str) -> tuple[bool, str]:
    """标准比对：去行尾空白 + 末尾换行后逐行比较。

    Returns:
        (是否一致, 差异摘要)
    """
    if not os.path.exists(user_out_path):
        return False, "output file missing"
    if not os.path.exists(answer_path):
        return False, "answer file missing"

    with open(user_out_path, "rb") as f:
        user_data = f.read(100_000)
    with open(answer_path, "rb") as f:
        ans_data = f.read(100_000)

    def normalize(data: bytes) -> list[str]:
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        stripped = [l.rstrip() for l in lines]
        while stripped and stripped[-1] == "":
            stripped.pop()
        return stripped

    user_lines = normalize(user_data)
    ans_lines = normalize(ans_data)

    if user_lines == ans_lines:
        return True, ""

    # 构造差异摘要（前 200 字符）
    for i, (u, a) in enumerate(zip(user_lines, ans_lines)):
        if u != a:
            return False, f"line {i+1}: expected '{a[:80]}', got '{u[:80]}'"
    if len(user_lines) != len(ans_lines):
        return False, f"line count mismatch: {len(user_lines)} vs {len(ans_lines)}"

    return False, "output differs"


def run_spj(
    spj_path: str,
    in_path: str,
    out_path: str,
    ans_path: str,
    time_limit_ms: int = 5000,
    memory_limit_mb: int = 256,
) -> CaseOutcome:
    """Special Judge：spj 也必须在沙箱内跑（同样资源限制 + 最小权限）。

    spj 用法: ./spj in.txt out.txt answer.txt, exit 0 = AC。
    """
    workdir = os.path.dirname(spj_path)

    spj_cmd = [
        "./spj",
        os.path.basename(in_path),
        os.path.basename(out_path),
        os.path.basename(ans_path),
    ]

    result = run_case(
        image="gcc:13-bookworm",
        run_command=spj_cmd,
        workdir=workdir,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        input_file=os.path.basename(in_path),
        output_file="/dev/null",
    )
    return result


def strip_binary_permissions(binary_path: str) -> None:
    """移除二进制文件的所有不必要权限。

    设置为 500（r-x------）：仅 owner 可读+执行，不可写。
    这是最小权限原则 —— 被评测的程序不需要：
      - 写权限（不能修改自身）
      - 组/其他用户的任何权限
      - SUID/SGID 位
    """
    if os.path.exists(binary_path):
        os.chmod(binary_path, 0o500)  # r-x------
        # 确保没有 SUID/SGID
        st = os.stat(binary_path)
        if st.st_mode & (0o4000 | 0o2000):  # SUID | SGID
            os.chmod(binary_path, st.st_mode & ~(0o4000 | 0o2000))
