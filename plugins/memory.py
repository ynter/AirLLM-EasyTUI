"""持久化记忆插件：保存关键信息、跨会话保留、可固定到提示词。"""

"""
使用演示:

你 > 记住：我叫张三，住在北京，喜欢简洁的回答
[记忆] 自动保存 #1: 我叫张三，住在北京，喜欢简洁的回答

AI > 好的，我记住了。

你 > /pin 1
[记忆] 已固定 #1: 我叫张三，住在北京，喜欢简洁的回答

你 > /memories
[记忆] 共 1 条：
  📌 #1   我叫张三，住在北京，喜欢简洁的回答
"""

import json
import re
from datetime import datetime
from pathlib import Path

from plugin_api import AirLLMPlugin


class MemoryPlugin(AirLLMPlugin):
    name = "memory"
    version = "1.0.0"
    description = "持久化记忆：保存关键信息、固定到提示词、跨会话保留"
    commands = {
        "remember": "添加记忆：/remember <内容>",
        "memories": "列出所有记忆",
        "pin": "固定记忆到提示词：/pin <id>",
        "unpin": "取消固定：/unpin <id>",
        "forget": "删除记忆：/forget <id>",
        "memory-help": "显示记忆命令帮助",
    }

    # 注入到 system prompt 时最多占多少字符（防止挤爆上下文）
    MAX_PINNED_CHARS = 600
    MAX_PINNED_COUNT = 20

    # 匹配「记住」「请记住」后跟可选标点/空格，再跟内容
    _AUTO_RE = re.compile(r"^(?:请)?记住[：:,，\s]*(.+)$")

    STORAGE_FILE = "memories.json"

    def __init__(self):
        self.storage_dir = Path("memory")
        self.storage_file = None
        self.data = {"memories": [], "next_id": 1}
        self._app = None
        self._overflow_warned = False

    # ---- 生命周期 ----
    def setup(self, args):
        self.storage_dir = Path(getattr(args, "memory_dir", "memory")).resolve()
        self.storage_file = self.storage_dir / self.STORAGE_FILE
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[记忆] 创建目录失败 {self.storage_dir}: {e}")
        self._load()

    def on_startup(self, app):
        self._app = app
        n = len(self.data["memories"])
        npin = sum(1 for m in self.data["memories"] if m.get("pinned"))
        if n:
            print(f"[记忆] 已加载 {n} 条记忆（其中 {npin} 条已固定）")

        # 上下文预算检查
        pinned_block = self._build_pinned_block()
        if pinned_block and app.tokenizer is not None:
            try:
                n_tokens = len(app.tokenizer.encode(pinned_block))
                max_len = getattr(app.args, "max_length", 0) or 0
                if max_len and n_tokens > max_len * 0.4:
                    print(f"[记忆] 警告: 固定记忆约 {n_tokens} tokens，"
                          f"占 --max-length={max_len} 的 "
                          f"{n_tokens / max_len * 100:.0f}%。"
                          f"建议调大 --max-length 或 /unpin 部分记忆")
            except Exception:
                pass

    def on_before_generate(self, gen):
        # 1. 把 pinned 记忆拼进 system prompt
        block = self._build_pinned_block()
        if block:
            base = gen.system_prompt or ""
            gen.system_prompt = (base + "\n\n" + block) if base else block

        # 2. 再检测自动保存（下一轮生效，避免与本轮输入重复）
        self._try_auto_remember(gen.user_text)

    def on_shutdown(self):
        self._save()

    # ---- 命令 ----
    def handle_command(self, cmd, arg, app):
        if cmd == "remember":
            return self._cmd_remember(arg)
        if cmd == "memories":
            return self._cmd_memories()
        if cmd == "pin":
            return self._cmd_pin(arg)
        if cmd == "unpin":
            return self._cmd_unpin(arg)
        if cmd == "forget":
            return self._cmd_forget(arg)
        if cmd == "memory-help":
            return self._cmd_help()
        return False

    # ---- 命令实现 ----
    def _cmd_remember(self, arg):
        if not arg.strip():
            print("[记忆] 用法: /remember <要记住的内容>")
            return True
        m = self._add(arg, pinned=False)
        print(f"[记忆] 已添加 #{m['id']}: {m['content']}")
        return True

    def _cmd_memories(self):
        if not self.data["memories"]:
            print("[记忆] 暂无记忆。使用 /remember <内容> 添加。")
            return True
        print(f"[记忆] 共 {len(self.data['memories'])} 条：")
        for m in self.data["memories"]:
            pin = "📌" if m.get("pinned") else "  "
            print(f"  {pin} #{m['id']:<3} {m['content']}")
        return True

    def _cmd_pin(self, arg):
        m = self._find(arg)
        if m is None:
            return True
        m["pinned"] = True
        m["updated"] = datetime.now().isoformat(timespec="seconds")
        self._save()
        print(f"[记忆] 已固定 #{m['id']}: {m['content']}")
        return True

    def _cmd_unpin(self, arg):
        m = self._find(arg)
        if m is None:
            return True
        m["pinned"] = False
        m["updated"] = datetime.now().isoformat(timespec="seconds")
        self._save()
        print(f"[记忆] 已取消固定 #{m['id']}: {m['content']}")
        return True

    def _cmd_forget(self, arg):
        m = self._find(arg)
        if m is None:
            return True
        self.data["memories"].remove(m)
        self._save()
        print(f"[记忆] 已删除 #{m['id']}: {m['content']}")
        return True

    def _cmd_help(self):
        print("[记忆] 命令：")
        print("  /remember <内容>   添加记忆（默认不固定）")
        print("  /memories          列出所有记忆")
        print("  /pin <id>          固定到提示词（每次推理注入）")
        print("  /unpin <id>        取消固定")
        print("  /forget <id>       删除指定记忆")
        print("  /memory-help       显示此帮助")
        print("[记忆] 自动：以「记住：/请记住：」开头时自动保存。")
        return True

    # ---- 内部 ----
    def _find(self, arg):
        try:
            mid = int((arg or "").strip())
        except (ValueError, AttributeError):
            print(f"[记忆] 无效 id: {arg}")
            return None
        for m in self.data["memories"]:
            if m["id"] == mid:
                return m
        print(f"[记忆] 未找到 #{mid}")
        return None

    def _add(self, content, pinned=False):
        content = content.strip()
        now = datetime.now().isoformat(timespec="seconds")
        m = {
            "id": self.data["next_id"],
            "content": content,
            "pinned": pinned,
            "created": now,
            "updated": now,
        }
        self.data["next_id"] += 1
        self.data["memories"].append(m)
        self._save()
        return m

    def _try_auto_remember(self, user_text):
        text = (user_text or "").strip()
        m = self._AUTO_RE.match(text)
        if not m:
            return
        content = m.group(1).strip()
        if not content or len(content) > 500:
            return
        # 去重
        for exist in self.data["memories"]:
            if exist["content"] == content:
                return
        added = self._add(content, pinned=False)
        print(f"[记忆] 自动保存 #{added['id']}: {content}")

    def _build_pinned_block(self):
        pinned = [m for m in self.data["memories"] if m.get("pinned")][:self.MAX_PINNED_COUNT]
        if not pinned:
            return ""

        lines = ["【重要记忆（始终参考，勿遗忘）】"]
        total = 0
        truncated = False
        for m in pinned:
            line = f"- {m['content']}"
            if total + len(line) + 1 > self.MAX_PINNED_CHARS:
                truncated = True
                break
            lines.append(line)
            total += len(line) + 1

        if truncated and not self._overflow_warned:
            self._overflow_warned = True
            print(f"[记忆] 固定记忆超过 {self.MAX_PINNED_CHARS} 字符上限，"
                  f"部分未注入。调整 MAX_PINNED_CHARS 或 /unpin 一些。")

        return "\n".join(lines) if len(lines) > 1 else ""

    # ---- 持久化 ----
    def _load(self):
        if not self.storage_file or not self.storage_file.exists():
            return
        try:
            with self.storage_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("memories"), list):
                self.data = data
                if "next_id" not in self.data:
                    self.data["next_id"] = max(
                        (m.get("id", 0) for m in self.data["memories"]), default=0
                    ) + 1
        except Exception as e:
            print(f"[记忆] 加载失败 {self.storage_file}: {type(e).__name__}: {e}")

    def _save(self):
        if not self.storage_file:
            return
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.storage_file.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.storage_file)
        except Exception as e:
            print(f"[记忆] 保存失败 {self.storage_file}: {type(e).__name__}: {e}")