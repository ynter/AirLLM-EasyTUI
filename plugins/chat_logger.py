"""对话日志插件：按日期分文件，写入 log/ 目录。"""

from datetime import datetime
from pathlib import Path

from plugin_api import AirLLMPlugin


class ChatLoggerPlugin(AirLLMPlugin):
    name = "chat_logger"
    version = "1.1.0"
    description = "把每轮对话按日期写入 log/ 目录（如 log/chat-2026-10-19.log）"
    commands = {"log": "显示日志目录与今日文件路径"}

    def __init__(self):
        self.log_dir = Path("log")
        self.prefix = "chat"          # 文件名前缀：chat-YYYY-MM-DD.log
        self._buf = {}
        self._current_date = None     # 已打开的日期，用于检测跨天
        self._current_path = None

    # ---- 生命周期 ----
    def setup(self, args):
        # 日志目录可被命令行扩展覆盖（此处留口子，后续可用 args.log_dir）
        self.log_dir = Path(getattr(args, "log_dir", "log")).resolve()
        self.prefix = getattr(args, "log_prefix", "chat")
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[日志] 创建目录失败 {self.log_dir}: {e}")

    def on_before_generate(self, gen):
        self._buf["user"] = gen.user_text

    def on_after_generate(self, gen):
        path = self._path_for_today()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] 你 > {self._buf.get('user', '')}\n")
                f.write(f"[{ts}] AI > {gen.response}\n\n")
        except OSError as e:
            print(f"[日志] 写入失败 {path}: {e}")

    # ---- 命令 ----
    def handle_command(self, cmd, arg, app):
        if cmd == "log":
            today = self._path_for_today()
            print(f"[日志] 目录: {self.log_dir}")
            print(f"[日志] 今日: {today}")
            return True
        return False

    # ---- 内部 ----
    def _path_for_today(self) -> Path:
        """跨天时自动切换到新的日期文件；目录缺失时重建。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date or self._current_path is None:
            self._current_date = today
            self._current_path = self.log_dir / f"{self.prefix}-{today}.log"
            if not self.log_dir.is_dir():
                try:
                    self.log_dir.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
        return self._current_path