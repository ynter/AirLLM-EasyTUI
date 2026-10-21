"""插件接口、上下文、插件管理器。"""

from dataclasses import dataclass, field
from typing import Any, Dict


BUILTIN_COMMAND_ALIASES = {
    "help": "help",
    "h": "help",
    "?": "help",
    "quit": "quit",
    "exit": "quit",
    "q": "quit",
}


@dataclass
class AppContext:
    args: Any = None
    model: Any = None
    tokenizer: Any = None
    device: str = "cpu"
    plugins: Any = None


@dataclass
class GenerateContext:
    user_text: str = ""
    input_ids: Any = None
    attention_mask: Any = None
    sequences: Any = None
    response: str = ""
    input_len: int = 0
    new_tokens: int = 0
    system_prompt: str = ""                                     # ← 新增：编码前的 system prompt
    extra_kwargs: dict = field(default_factory=dict)            # ← 只放传给 generate() 的参数


class AirLLMPlugin:
    """所有插件必须继承此类。生命周期钩子可按需重写。"""

    name = "unnamed"
    version = "0.1.0"
    description = ""
    commands: Dict[str, str] = {}
    command_aliases: Dict[str, str] = {}

    def setup(self, args) -> None: ...
    def on_startup(self, app: AppContext) -> None: ...
    def on_before_input(self) -> None: ...
    def on_after_input(self) -> None: ...
    def on_before_generate(self, gen: GenerateContext) -> None: ...
    def on_after_generate(self, gen: GenerateContext) -> None: ...
    def on_shutdown(self) -> None: ...

    def handle_command(self, cmd: str, arg: str, app: AppContext) -> bool:
        return False


class PluginManager:
    def __init__(self):
        self.plugins = []

    def register(self, plugin: AirLLMPlugin):
        self.plugins.append(plugin)

    def all_command_names(self):
        names = set()
        for p in self.plugins:
            names.update(p.commands.keys())
        return names

    def find(self, name: str):
        for p in self.plugins:
            if p.name == name:
                return p
        return None

    def _safe_call(self, plugin, hook, *a, **kw):
        fn = getattr(plugin, hook, None)
        if fn is None:
            return
        try:
            fn(*a, **kw)
        except Exception as e:
            print(f"[插件:{plugin.name}] {hook} 出错: {type(e).__name__}: {e}")

    def call(self, hook, *a, **kw):
        for p in self.plugins:
            self._safe_call(p, hook, *a, **kw)

    def handle_command(self, cmd: str, arg: str, app: AppContext) -> bool:
        text = (cmd or "").strip().lower()
        for p in self.plugins:
            names = {
                name.strip().lower().lstrip("/")
                for name in getattr(p, "commands", {}).keys()
            }
            aliases = {
                alias.strip().lower().lstrip("/"): target.strip().lower().lstrip("/")
                for alias, target in getattr(p, "command_aliases", {}).items()
            }
            command = aliases.get(text.lstrip("/"), text.lstrip("/"))
            if command not in names:
                continue
            try:
                result = p.handle_command(command, arg, app)
                return True if result is False else result
            except Exception as e:
                print(f"[插件:{p.name}] 命令 '{cmd}' 出错: {type(e).__name__}: {e}")
                return False
        return False

    def describe_commands(self) -> str:
        builtin_aliases = {}
        for alias, command in BUILTIN_COMMAND_ALIASES.items():
            builtin_aliases.setdefault(command, []).append("/" + alias)
        lines = ["内建命令"]
        lines.append(
            f"  {', '.join(builtin_aliases['help']):<22} 显示此帮助"
        )
        lines.append(
            f"  {', '.join(builtin_aliases['quit']):<22} 退出对话"
        )
        plugin_commands = []
        for plugin in self.plugins:
            aliases = {
                alias.strip().lower().lstrip("/"): target.strip().lower().lstrip("/")
                for alias, target in getattr(plugin, "command_aliases", {}).items()
            }
            for name, description in plugin.commands.items():
                command = name.strip().lower().lstrip("/")
                command_aliases = [
                    alias for alias, target in aliases.items() if target == command
                ]
                alias_text = (
                    f"  (别名: {', '.join('/' + alias for alias in command_aliases)})"
                    if command_aliases else ""
                )
                plugin_commands.append(
                    f"  /{command:<16} {description}{alias_text}"
                )
        if plugin_commands:
            lines.extend(["插件命令", *plugin_commands])
        else:
            lines.append("  当前没有可用的插件命令")
        return "\n".join(lines)

    def describe(self) -> str:
        if not self.plugins:
            return "[插件] 未发现任何插件"
        lines = [f"[插件] 已加载 {len(self.plugins)} 个插件:"]
        for p in self.plugins:
            cmds = ", ".join(f"/{c}" for c in p.commands) or "无命令"
            lines.append(f"    · {p.name} v{p.version} — {p.description}  [{cmds}]")
        return "\n".join(lines)