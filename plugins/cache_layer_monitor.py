"""缓存层监控插件：只提供 get_stats() 数据，由 resource_monitor 统一渲染。"""

import os
import time

from plugin_api import AirLLMPlugin


class CacheLayerMonitorPlugin(AirLLMPlugin):
    name = "cache_layer_monitor"
    version = "1.1.0"
    description = "缓存分片信息（磁盘文件，推理时大小不变属正常）"
    commands = {"cache": "打印一次缓存层指标"}

    def __init__(self):
        self._app = None
        self._size_cache = 0.0
        self._size_ts = 0.0
        self._size_ttl = 5.0           # 缓存大小 5 秒重算一次，避免频繁 os.walk

    def on_startup(self, app):
        self._app = app

    def get_stats(self) -> dict:
        snap = {
            "compression": "none",
            "cache_hit_ratio": None,
            "cache_size_gb": 0.0,
            "layers_vram": {},
        }
        if not self._app:
            return snap

        # 1. 压缩方式
        snap["compression"] = getattr(self._app.args, "compression", "none")

        # 2. 命中率（AirLLM 不提供，保留扩展位）
        model = getattr(self._app, "model", None)
        if model is not None and hasattr(model, "get_cache_stats"):
            try:
                stats = model.get_cache_stats()
                if stats:
                    snap["cache_hit_ratio"] = stats.get("hit_ratio")
            except Exception:
                pass

        # 3. 缓存大小（TTL 节流）
        now = time.monotonic()
        if now - self._size_ts >= self._size_ttl:
            self._size_ts = now
            path = (getattr(self._app.args, "_actual_shards_path", None)
                    or getattr(self._app.args, "shards_path", None))
            if path and os.path.isdir(path):
                total = 0
                for dirpath, _dirnames, filenames in os.walk(path):
                    for fn in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, fn))
                        except OSError:
                            pass
                self._size_cache = total / (1024 ** 3)
            else:
                self._size_cache = 0.0
        snap["cache_size_gb"] = self._size_cache

        return snap

    def handle_command(self, cmd, arg, app):
        if cmd != "cache":
            return False
        s = self.get_stats()
        parts = [f"压缩:{s['compression']}"]
        if s["cache_hit_ratio"] is not None:
            parts.append(f"比率:{s['cache_hit_ratio'] * 100:.0f}%")
        if s["cache_size_gb"] > 0:
            parts.append(f"大小:{s['cache_size_gb']:.2f}GB")
        print("[缓存层] " + " | ".join(parts))
        return True

    def on_shutdown(self):
        self._app = None