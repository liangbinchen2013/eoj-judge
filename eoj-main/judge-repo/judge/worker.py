"""批量 worker 主循环 —— workflow 入口脚本调用。

环境: Ubuntu (GitHub Actions ubuntu-latest)，OJ 后端拥有 root 权限。

流程:
  poll(心跳/拉任务) → 下载 code.zip + tests.zip → 编译 → 逐用例沙箱运行
  → 汇总 → 回调 → 循环。队列空 → sleep(poll_interval_s) → 连续空 idle_exit_after_s 自动退出
  （由 watchdog cron 重启，防深夜空转）。

工作目录结构（/tmp/judge_{submission_id}/）:
  code/     → 用户代码（编译前 rw，编译后 ro）
  in/       → 测试输入（只读）
  out/      → 程序输出（唯一可写位置）
  spj       → SPJ 程序（可选）

关键设计:
  - ★ 随时被杀无副作用：任务在服务端队列保底。
  - 幂等：服务端对重复回调只认第一次。
  - 单发模式（mode=single）：拉一次指定 submission_id 即退出。
  - 编译产物自动剥离不必要的权限（500 = r-x------）。

安全:
  - 所有 HTTP 使用超时；只接受 https URL。
  - ★ 用户代码/测试数据/worker_key 一律不进日志。
  - 下载文件校验大小上限 + zip-slip 防护。
  - 工作目录每次 mkdtemp 新建，用后即删。
  - 运行可执行文件前剥离所有不必要权限。
  - 沙箱内以 nobody 用户运行（非 root）。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

from .compile import CompileResult, compile_spj_source, compile_submission, prepare_code
from .config import config
from .report import build_result, send_report
from .sandbox import CaseOutcome, check_output_diff, run_case, run_spj, strip_binary_permissions

# --- 常量 ---
_CODE_MAX_BYTES = 2_000_000
_TESTS_MAX_BYTES = 64_000_000
_POLL_TIMEOUT_S = 30.0
_DOWNLOAD_TIMEOUT_S = 60.0


def _safe_log(msg: str) -> None:
    """安全日志：前缀时间戳，脱敏 key/token。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    safe = msg.replace(config.worker_key, "***") if config.worker_key else msg
    print(f"[{ts}] {safe}", flush=True)


# --- HTTP 客户端（零依赖，标准库 urllib） ---

def _http_get(url: str, timeout_s: float = _DOWNLOAD_TIMEOUT_S,
              max_bytes: int = 0) -> bytes | None:
    """GET 请求，返回响应体字节。max_bytes=0 表示无限制。"""
    if not url.startswith("https://") and not url.startswith("http://127."):
        _safe_log(f"拒绝非 https URL")
        return None

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "oj-judge-worker/0.1")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return None
            data = resp.read()
            if max_bytes > 0 and len(data) > max_bytes:
                _safe_log(f"响应过大: {len(data)} > {max_bytes}")
                return None
            return data
    except Exception as e:
        _safe_log(f"GET 失败: {type(e).__name__}")
        return None


def _http_post(url: str, json_data: dict, timeout_s: float = 30.0) -> bool:
    """POST JSON 请求，返回是否成功（2xx）。"""
    if not url.startswith("https://") and not url.startswith("http://127."):
        _safe_log(f"拒绝非 https URL")
        return False

    try:
        data = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "oj-judge-worker/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        _safe_log(f"POST 失败: {type(e).__name__}")
        return False


# --- 主循环 ---

def main() -> int:
    """worker 入口。返回进程退出码（0=正常, 非 0=异常）。"""
    _safe_log(f"worker 启动: mode={config.mode} server={config.server_url}")

    if not config.server_url:
        _safe_log("FATAL: OJ_SERVER_URL 未设置")
        return 1
    if not config.worker_key:
        _safe_log("FATAL: JUDGE_WORKER_KEY 未设置")
        return 1

    if config.mode == "single":
        return _run_single()

    return _run_batch()


def _run_batch() -> int:
    """批量 worker 主循环。"""
    worker_id = f"gha-{os.getenv('GITHUB_RUN_ID', 'local')}-{os.getpid()}"

    # 启动心跳线程
    heartbeat_stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop, args=(worker_id, heartbeat_stop), daemon=True
    )
    heartbeat_thread.start()

    idle_count = 0
    max_idle = config.idle_exit_after_s // max(config.poll_interval_s, 1)

    try:
        while True:
            task = _poll_task()
            if task is None:
                idle_count += 1
                if idle_count >= max_idle:
                    _safe_log(f"连续 {config.idle_exit_after_s}s 无任务，自动退出")
                    break
                time.sleep(config.poll_interval_s)
                continue

            idle_count = 0
            _safe_log(f"拉取任务: {task.get('submission_id', '?')}")

            try:
                _process_task(task)
            except Exception as e:
                _safe_log(f"处理任务异常: {type(e).__name__}: {str(e)[:200]}")
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=5)

    return 0


def _run_single() -> int:
    """单发模式：只处理指定 submission_id。"""
    sid = config.submission_id
    if not sid:
        _safe_log("FATAL: single 模式需要 JUDGE_SUBMISSION_ID")
        return 1

    deadline = time.time() + 300
    while time.time() < deadline:
        task = _poll_task()
        if task and task.get("submission_id") == sid:
            _process_task(task)
            return 0
        time.sleep(config.poll_interval_s)

    _safe_log(f"超时未找到任务: {sid}")
    return 1


# --- 任务处理 ---

def _poll_task() -> dict | None:
    """GET {server}/api/judge/poll?key=...；返回任务 dict 或 None。"""
    url = f"{config.server_url}/api/judge/poll?key={config.worker_key}"
    data = _http_get(url, timeout_s=_POLL_TIMEOUT_S)
    if not data:
        return None

    try:
        resp = json.loads(data)
        task = resp.get("task")
        if not task:
            return None
        required = ["submission_id", "language", "code_url",
                    "testdata_url", "token", "callback_url"]
        for field in required:
            if field not in task:
                _safe_log(f"poll 响应缺少字段: {field}")
                return None
        return task
    except (json.JSONDecodeError, TypeError):
        return None


def _process_task(task: dict) -> None:
    """单任务全流程：下载 → 解压 → 编译 → 逐用例 → 汇总 → 回调。

    兼容 eoj-main：
      - 自动检测 tests.zip 中的 meta.json (score/is_sample) 并透传
      - SPJ 支持源码编译（testdata 中包含 spj_source.{ext} 时自动编译）
      - 生成 judge_logs 评测日志
    """
    submission_id = task["submission_id"]
    language = task["language"]
    callback_url = task["callback_url"]
    token = task["token"]
    code_url = task["code_url"]
    testdata_url = task["testdata_url"]
    time_limit_ms = task.get("time_limit_ms", 2000)
    memory_limit_mb = task.get("memory_limit_mb", 256)
    eoj_mode = task.get("eoj_mode", False)

    logs: list[dict] = []

    def _add_log(log_type: str, message: str) -> None:
        logs.append({"log_type": log_type, "message": message})

    # Ubuntu 环境：使用 /tmp 作为工作目录根
    workdir = tempfile.mkdtemp(prefix=f"judge_{submission_id}_", dir="/tmp")

    try:
        # 1. 创建目录结构
        code_dir = os.path.join(workdir, "code")
        in_dir = os.path.join(workdir, "in")
        out_dir = os.path.join(workdir, "out")
        for d in (code_dir, in_dir, out_dir):
            os.makedirs(d, exist_ok=True)
        os.chmod(code_dir, 0o755)
        os.chmod(in_dir, 0o755)
        os.chmod(out_dir, 0o755)

        # 2. 下载代码
        _add_log("info", f"开始下载代码: {submission_id}")
        code_data = _http_get(code_url, max_bytes=_CODE_MAX_BYTES)
        if not code_data:
            _send_failure(callback_url, token, submission_id, "SE", "Download code failed")
            return

        # 3. 下载测试数据
        _add_log("info", "开始下载测试数据")
        testdata = _http_get(testdata_url, max_bytes=_TESTS_MAX_BYTES)
        if not testdata:
            _send_failure(callback_url, token, submission_id, "SE", "Download tests failed")
            return

        # 4. 解压测试数据到 in/（zip-slip 防护）
        if not _extract_tests(testdata, workdir):
            _send_failure(callback_url, token, submission_id, "SE", "Bad tests.zip")
            return

        # 4.5 读取测试用例元信息（meta.json，eoj-main 格式）
        testcase_meta: list[dict] = []
        meta_path = os.path.join(workdir, "in", "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    testcase_meta = json.loads(f.read())
                _add_log("info", f"读取用例元信息: {len(testcase_meta)} 条")
            except Exception:
                pass

        # 4.6 SPJ 源码编译（eoj-main 格式：testdata 中包含 spj_source.{ext}）
        spj_available = False
        spj_executable = None
        for _spj_ext in ["spj_source.c", "spj_source.cpp", "spj_source.py",
                          "SpjSource.java", "spj_source.go", "spj_source.rs",
                          "spj_source.js"]:
            _spj_path = os.path.join(workdir, "in", _spj_ext)
            if os.path.exists(_spj_path):
                # 推断语言
                _ext_to_lang = {
                    ".c": "c", ".cpp": "cpp", ".py": "python",
                    ".java": "java", ".go": "go", ".rs": "rust", ".js": "javascript",
                }
                _found_ext = os.path.splitext(_spj_ext)[1]
                _spj_lang = _ext_to_lang.get(_found_ext, "")
                if _spj_lang:
                    _add_log("info", f"检测到 SPJ 源码 ({_spj_lang})，开始编译")
                    spj_result = compile_spj_source(workdir, _spj_lang)
                    if spj_result.ok:
                        spj_available = True
                        _add_log("info", "SPJ 编译成功")
                        # Python SPJ 特殊处理：直接执行源码
                        if _spj_lang == "python":
                            spj_executable = f"python3 spj_source.py"
                    else:
                        _add_log("error", f"SPJ 编译失败: {spj_result.compile_output[:500]}")
                        _send_failure(callback_url, token, submission_id, "SE",
                                      f"SPJ compilation failed: {spj_result.compile_output[:200]}")
                        return
                break

        # 传统 SPJ：预编译的 spj ELF 文件
        spj_path = os.path.join(workdir, "in", "spj")
        if not spj_available and os.path.exists(spj_path) and os.access(spj_path, os.X_OK):
            spj_available = True
            _add_log("info", "检测到预编译 SPJ")

        # 5. 解压代码到 code/
        source_file = prepare_code(workdir, code_data, language)
        if not source_file:
            _send_failure(callback_url, token, submission_id, "SE", "Bad code.zip")
            return

        # 6. 编译（在 Docker 沙箱内）
        _add_log("info", f"开始编译 ({language})")
        compile_result = compile_submission(workdir, language)
        if not compile_result.ok:
            _add_log("error", f"编译失败: {compile_result.compile_output[:500]}")
            result = build_result(
                submission_id, [], compile_result.compile_output, "CE",
                logs=logs, eoj_mode=eoj_mode,
            )
            send_report(callback_url, token, result)
            return
        _add_log("info", "编译成功")

        # 7. 编译成功后：code 目录设为只读
        _make_readonly(code_dir)

        # 8. 获取语言配置
        lang_config = config.get_language_config(language)
        if not lang_config:
            _send_failure(callback_url, token, submission_id, "SE", "No language config")
            return

        image = lang_config.get("image", "ubuntu:latest")
        run_cmd = lang_config.get("run", [])
        memory_factor = lang_config.get("memory_factor", 1.0)
        effective_memory_mb = int(memory_limit_mb * memory_factor)

        # 9. 逐用例运行
        cases: list[CaseOutcome] = []
        case_id = 1

        while True:
            in_file = os.path.join(workdir, "in", f"{case_id}.txt")
            if not os.path.exists(in_file):
                break

            # 确定答案文件位置（兼容多种目录结构）
            ans_file = None
            for _candidate in [
                os.path.join(workdir, "in", f"{case_id}_ans.txt"),
                os.path.join(workdir, "in", "out", f"{case_id}.txt"),
                os.path.join(workdir, "out", f"{case_id}.txt"),
            ]:
                if os.path.exists(_candidate):
                    ans_file = _candidate
                    break

            if ans_file is None and not spj_available:
                break  # 没有答案文件且非 SPJ

            out_file = os.path.join(workdir, "out", f"{case_id}_out.txt")

            _add_log("info", f"评测用例 #{case_id}")

            # 运行沙箱
            outcome = run_case(
                image=image,
                run_command=run_cmd,
                workdir=workdir,
                time_limit_ms=time_limit_ms,
                memory_limit_mb=effective_memory_mb,
                input_file=f"in/{case_id}.txt",
                output_file=f"out/{case_id}_out.txt",
            )

            # 读取用例元信息
            meta = testcase_meta[case_id - 1] if case_id - 1 < len(testcase_meta) else {}
            outcome.score = meta.get("score", 10)
            outcome.is_sample = meta.get("is_sample", False)

            # 比对输出
            if outcome.status == "AC":
                if spj_available:
                    # Special Judge
                    if spj_executable:
                        # 解释型 SPJ（如 Python）
                        spj_cmd_parts = spj_executable.split()
                        _spj_path = os.path.join(workdir, "in", spj_cmd_parts[-1])
                        spj_inner_cmd = spj_cmd_parts + [in_file, out_file, ans_file or "/dev/null"]
                    else:
                        _spj_path = os.path.join(workdir, "in", "spj")
                        spj_inner_cmd = ["./spj",
                                         os.path.basename(in_file),
                                         os.path.basename(out_file),
                                         os.path.basename(ans_file) if ans_file else "/dev/null"]

                    spj_outcome = run_spj(
                        spj_path=_spj_path if not spj_executable else os.path.join(workdir, "in", "spj_source.py"),
                        in_path=in_file,
                        out_path=out_file,
                        ans_path=ans_file or out_file,
                        time_limit_ms=max(time_limit_ms, 5000),
                        memory_limit_mb=effective_memory_mb,
                    )
                    if spj_outcome.status != "AC":
                        outcome.status = "WA"
                        outcome.detail = f"SPJ: {spj_outcome.detail or 'WA'}"
                        _add_log("info", f"用例 #{case_id}: SPJ 判定 WA")
                    else:
                        _add_log("info", f"用例 #{case_id}: SPJ 判定 AC")
                elif ans_file:
                    # 标准比对
                    ok, diff = check_output_diff(out_file, ans_file)
                    if not ok:
                        outcome.status = "WA"
                        outcome.detail = diff
                        _add_log("info", f"用例 #{case_id}: WA ({diff[:100]})")
                    else:
                        _add_log("info", f"用例 #{case_id}: AC")
                else:
                    _add_log("info", f"用例 #{case_id}: {outcome.status}")

            cases.append(outcome)
            case_id += 1

            if case_id > 512:
                break

        # 10. 汇总 + 回调
        _add_log("info", f"评测完成: {len(cases)} 个用例")
        result = build_result(
            submission_id, cases, compile_result.compile_output,
            testcase_meta=testcase_meta if testcase_meta else None,
            logs=logs, eoj_mode=eoj_mode,
        )
        send_report(callback_url, token, result)
        _safe_log(f"完成: {submission_id} → {result['status']} ({len(cases)} cases)")

    except Exception as e:
        _safe_log(f"任务异常: {submission_id}: {type(e).__name__}: {str(e)[:200]}")
        _add_log("error", f"评测异常: {type(e).__name__}: {str(e)[:500]}")
        try:
            _send_failure(callback_url, token, submission_id, "SE", str(e)[:200])
        except Exception:
            pass
    finally:
        # 清理工作目录
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


def _make_readonly(dirpath: str) -> None:
    """递归将目录设为只读（500），防止运行期修改代码。"""
    for root, dirs, files in os.walk(dirpath):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                st = os.stat(fpath)
                # 可执行文件: 500 (r-x------)
                # 普通文件: 400 (r--------)
                if st.st_mode & 0o111:
                    os.chmod(fpath, 0o500)
                else:
                    os.chmod(fpath, 0o400)
            except OSError:
                pass
        for dname in dirs:
            dpath = os.path.join(root, dname)
            try:
                os.chmod(dpath, 0o500)
            except OSError:
                pass


def _extract_tests(zip_data: bytes, workdir: str) -> bool:
    """解压测试数据到 workdir/in/（zip-slip 防护）。

    兼容两种目录结构:
      1. in/{id}.txt + out/{id}.txt (标准格式)
      2. in/{id}.txt + in/{id}_ans.txt (答案同目录)
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for info in zf.infolist():
                name = info.filename
                if os.path.isabs(name):
                    _safe_log(f"tests.zip 绝对路径: {name}")
                    return False
                if ".." in name.split("/"):
                    _safe_log(f"tests.zip 路径穿越: {name}")
                    return False
                if (info.external_attr >> 16) & 0o120000:
                    _safe_log(f"tests.zip 符号链接: {name}")
                    return False
                if info.file_size > 100_000_000:
                    _safe_log(f"tests.zip 成员过大: {name}")
                    return False
            zf.extractall(os.path.join(workdir, "in"))
        return True
    except (zipfile.BadZipFile, ValueError, OSError) as e:
        _safe_log(f"tests.zip 解压失败: {type(e).__name__}")
        return False


def _send_failure(callback_url: str, token: str, submission_id: str,
                  status: str, detail: str) -> None:
    """发送失败结果回调。"""
    result = {
        "submission_id": submission_id,
        "status": status,
        "time_ms": 0,
        "memory_kb": 0,
        "compile_output": detail[:100_000],
        "cases": [],
    }
    send_report(callback_url, token, result)


# --- 心跳 ---

def _heartbeat_loop(worker_id: str, stop: threading.Event) -> None:
    """心跳线程：每 heartbeat_interval_s 调 POST /api/judge/heartbeat。"""
    url = f"{config.server_url}/api/judge/heartbeat"
    payload = {
        "worker_id": worker_id,
        "queue_remaining": 0,
        "worker_key": config.worker_key,
    }

    while not stop.wait(config.heartbeat_interval_s):
        try:
            _http_post(url, payload, timeout_s=10.0)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
