"""judge worker 包：在 GitHub Actions runner（一次性 VM）上执行评测。

安全边界（README §7.5 官方立场）:
  - 容器隔离 ≠ 安全边界；VM 一次性 + 仓库零 secrets 才是安全边界。
  - 本包代码以"评测代码可能恶意"为前提编写：
    * 用户输入绝不拼接进 shell（一律 base64/文件传递）；
    * 日志只打截断摘要（防 log injection 与 secrets 泄露）。
"""
