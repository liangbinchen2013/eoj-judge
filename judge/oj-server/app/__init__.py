"""OJ 服务端应用包。

基于 GitHub Actions 批量 worker 模式的 OJ 评测后端：
  用户提交 → 入队 → dispatch GitHub Actions worker → 回调结果落库。

安全底线（README §8 / WRITE.md）：
  1. 评测仓库零 secrets，GITHUB_TOKEN 最小权限 —— 服务端是唯一持密方。
  2. worker 拉任务/下载数据/回调一律走"一次性 token"，用后即焚。
  3. 所有用户内容（代码、输出、日志）不做任何 shell 拼接，防注入。
"""
