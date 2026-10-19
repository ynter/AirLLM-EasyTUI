"""插件接口、上下文、插件管理器。"""

from dataclasses import dataclass, field
from typing import Any, Dict


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
        for p in self.plugins:
            if cmd in p.commands:
                try:
                    if p.handle_command(cmd, arg, app):
                        return True
                except Exception as e:
                    print(f"[插件:{p.name}] 命令 '{cmd}' 出错: {type(e).__name__}: {e}")
        return False

    def describe(self) -> str:
        if not self.plugins:
            return "[插件] 未发现任何插件"
        lines = [f"[插件] 已加载 {len(self.plugins)} 个插件:"]
        for p in self.plugins:
            cmds = ", ".join(f"/{c}" for c in p.commands) or "无命令"
            lines.append(f"    · {p.name} v{p.version} — {p.description}  [{cmds}]")
        return "\n".join(lines)