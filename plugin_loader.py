"""扫描 plugins/ 目录，自动发现并实例化插件。"""

import importlib
import inspect
import pkgutil
from pathlib import Path

from plugin_api import AirLLMPlugin, BUILTIN_COMMAND_ALIASES, PluginManager


class DiscoverPluginManager(PluginManager):
    """发现插件后，返回命令名的用户可见形式：同时支持 /cmd 和 cmd。"""

    def all_command_names(self):
        names = set()
        for alias in BUILTIN_COMMAND_ALIASES:
            names.update({alias, f"/{alias}"})
        for p in self.plugins:
            for name in p.commands.keys():
                normalized = name.strip().lower().lstrip("/")
                if normalized:
                    names.update({normalized, f"/{normalized}"})
            for alias in getattr(p, "command_aliases", {}):
                normalized = alias.strip().lower().lstrip("/")
                if normalized:
                    names.update({normalized, f"/{normalized}"})
        return names


def discover(package: str = "plugins", args=None, disabled=None) -> PluginManager:
    manager = DiscoverPluginManager()
    disabled = set(disabled or [])
    base = Path(__file__).resolve().parent / package

    if not base.exists():
        print(f"[插件] 目录 {package}/ 不存在，跳过扫描")
        return manager

    for info in pkgutil.iter_modules([str(base)]):
        mod_name = info.name
        if mod_name.startswith("_"):
            continue

        full = f"{package}.{mod_name}"
        try:
            module = importlib.import_module(full)
        except Exception as e:
            print(f"[插件] 跳过 {mod_name}: {type(e).__name__}: {e}")
            continue

        found = False
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls is AirLLMPlugin or not issubclass(cls, AirLLMPlugin):
                continue
            if cls.__module__ != module.__name__:
                continue
            if cls.name in disabled:
                print(f"[插件] 已禁用: {cls.name}")
                continue
            try:
                plugin = cls()
                plugin.setup(args)
            except Exception as e:
                print(f"[插件] {cls.name} 初始化失败: {type(e).__name__}: {e}")
                continue
            manager.register(plugin)
            found = True

        if not found:
            print(f"[插件] {mod_name} 未发现可用的插件类")

    return manager