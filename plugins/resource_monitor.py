"""资源监控插件：实时 CPU / 内存 / GPU + 缓存 + 推理进度，固定在终端底部。"""

import ctypes
import os
import shutil
import sys
import threading

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pynvml
    _HAS_NVML = True
except ImportError:
    pynvml = None
    _HAS_NVML = False

from plugin_api import AirLLMPlugin


def _enable_vt():
    if os.name != "nt":
        return True
    try:
        k = ctypes.windll.kernel32
        handle = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        k.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


class _StatusBar:
    def __init__(self):
        self._lock = threading.Lock()
        self._in_input = threading.Event()
        self._enabled = False
        self._rows = 0

    def enable(self):
        if not _enable_vt():
            return False
        self._enabled = True
        try:
            _, rows = shutil.get_terminal_size((80, 24))
            if rows < 4:
                self._enabled = False
                return False
            self._rows = rows
            sys.stdout.write("\n")
            sys.stdout.write(f"\033[1;{rows - 1}r")
            sys.stdout.write(f"\033[{rows - 1};1H")
            sys.stdout.flush()
        except Exception:
            self._enabled = False
            return False
        return True

    def disable(self):
        if not self._enabled:
            return
        try:
            sys.stdout.write("\033[r")
            if self._rows:
                sys.stdout.write(f"\033[{self._rows};1H\033[2K")
            sys.stdout.flush()
        except Exception:
            pass
        self._enabled = False

    def enter_input(self):
        self._in_input.set()

    def leave_input(self):
        self._in_input.clear()

    def update(self, text, skip_if_input=True):
        if not self._enabled:
            return
        if skip_if_input and self._in_input.is_set():
            return
        with self._lock:
            try:
                cols, rows = shutil.get_terminal_size((80, 24))
                if rows < 4:
                    return
                if rows != self._rows:
                    self._rows = rows
                    sys.stdout.write(f"\033[1;{rows - 1}r")
                if cols > 1:
                    text = text[: cols - 1]
                sys.stdout.write(f"\033[s\033[{rows};1H\033[2K{text}\033[u")
                sys.stdout.flush()
            except Exception:
                pass


class _Sampler:
    def __init__(self, interval=1.0):
        self.interval = interval
        self._latest = {}
        self._stop = threading.Event()
        self._thread = None
        self._gpu = False
        self._handle = None
        self._on_sample = None
        self._cache_monitor = None
        self._progress_monitor = None

        if _HAS_NVML:
            try:
                pynvml.nvmlInit()
                if pynvml.nvmlDeviceGetCount() > 0:
                    self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self._gpu = True
            except Exception:
                self._gpu = False

    def set_callback(self, fn):
        self._on_sample = fn

    def set_cache_monitor(self, monitor):
        self._cache_monitor = monitor

    def set_progress_monitor(self, monitor):
        self._progress_monitor = monitor

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if _HAS_NVML and self._gpu:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    def _loop(self):
        if psutil is not None:
            psutil.cpu_percent(interval=None)
        while not self._stop.is_set():
            snap = {
                "cpu_percent": 0.0,
                "ram_used_gb": 0.0,
                "ram_total_gb": 0.0,
                "ram_percent": 0.0,
            }
            if psutil is not None:
                vm = psutil.virtual_memory()
                snap.update({
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "ram_used_gb": vm.used / (1024 ** 3),
                    "ram_total_gb": vm.total / (1024 ** 3),
                    "ram_percent": vm.percent,
                })
            if self._gpu:
                try:
                    mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
                    util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
                    snap.update({
                        "gpu_mem_used_mb": mem.used / (1024 ** 2),
                        "gpu_mem_total_mb": mem.total / (1024 ** 2),
                        "gpu_mem_percent": mem.used / mem.total * 100,
                        "gpu_util_percent": util.gpu,
                        "gpu_temp_c": pynvml.nvmlDeviceGetTemperature(
                            self._handle, pynvml.NVML_TEMPERATURE_GPU
                        ),
                    })
                except Exception:
                    pass

            self._latest = snap
            if self._on_sample:
                try:
                    cache_snap = self._cache_monitor.get_stats() if self._cache_monitor else None
                    progress = self._progress_monitor.get_progress() if self._progress_monitor else None
                    self._on_sample(self.format_snapshot(cache_snap, progress))
                except Exception:
                    pass
            self._stop.wait(self.interval)

    def snapshot(self):
        return dict(self._latest)

    def format_snapshot(self, cache_snap=None, progress=None):
        s = self._latest
        if not s:
            return "[资源] 采样尚未就绪"

        parts = [
            f"CPU {s['cpu_percent']:.0f}%",
            f"RAM {s['ram_used_gb']:.1f}/{s['ram_total_gb']:.1f}G",
        ]
        if "gpu_mem_used_mb" in s:
            parts.append(f"VRAM {s['gpu_mem_used_mb']:.0f}/{s['gpu_mem_total_mb']:.0f}M")
            parts.append(f"GPU {s['gpu_util_percent']}%")
            if "gpu_temp_c" in s:
                parts.append(f"{s['gpu_temp_c']}°C")

        if cache_snap:
            cp = []
            if cache_snap.get("compression"):
                cp.append(cache_snap["compression"])
            if cache_snap.get("cache_size_gb", 0) > 0:
                cp.append(f"{cache_snap['cache_size_gb']:.2f}G")
            if cp:
                parts.append("[" + " ".join(cp) + "]")

        if progress and progress.get("active"):
            pp = []
            if progress.get("total_layers", 0) > 0:
                pp.append(f"L{progress['current_layer']}/{progress['total_layers']}")
            if progress.get("max_new_tokens", 0) > 0:
                pp.append(f"t{progress['generated']}/{progress['max_new_tokens']}")
            if pp:
                parts.append("[" + " ".join(pp) + "]")

        return "[资源] " + " | ".join(parts)


class ResourceMonitorPlugin(AirLLMPlugin):
    name = "resource_monitor"
    version = "1.4.0"
    description = "CPU/内存/GPU + 缓存 + 推理进度，固定在终端底部"
    commands = {"stats": "立即刷新一次状态栏"}

    def __init__(self):
        self.sampler = None
        self.statusbar = None
        self.app = None
        self._fallback = False
        self._cache_monitor = None
        self._progress_monitor = None

    def setup(self, args):
        interval = getattr(args, "monitor_interval", 1.0) or 1.0
        self.sampler = _Sampler(interval=interval)
        self.statusbar = _StatusBar()

    def on_startup(self, app):
        self.app = app
        manager = getattr(app, "plugins", None)
        if manager is not None:
            for plugin in getattr(manager, "plugins", []):
                if plugin.name == "cache_layer_monitor":
                    self._cache_monitor = plugin
                    self.sampler.set_cache_monitor(plugin)
                    print("[资源] 已与 cache_layer_monitor 集成")
                elif plugin.name == "inference_progress":
                    self._progress_monitor = plugin
                    self.sampler.set_progress_monitor(plugin)
                    print("[资源] 已与 inference_progress 集成")

        if psutil is None:
            print("[资源] 警告: psutil 未安装，资源状态栏不可用")
            self._fallback = True
            return

        if not self.statusbar.enable():
            self._fallback = True
            print("[资源] 当前终端不支持 VT100，改为命令触发显示（/stats）")
            return

        self.sampler.set_callback(self.statusbar.update)
        self.sampler.start()

    def _current_text(self):
        cache_snap = self._cache_monitor.get_stats() if self._cache_monitor else None
        progress = self._progress_monitor.get_progress() if self._progress_monitor else None
        return self.sampler.format_snapshot(cache_snap, progress)

    def on_before_input(self):
        if not self._fallback:
            self.statusbar.enter_input()

    def on_after_input(self):
        if not self._fallback:
            self.statusbar.leave_input()

    def on_before_generate(self, gen):
        if self._fallback or not self.sampler:
            return
        self.statusbar.update(self._current_text(), skip_if_input=False)

    def on_after_generate(self, gen):
        self.on_before_generate(gen)

    def handle_command(self, cmd, arg, app):
        if cmd == "stats":
            if self.sampler:
                text = self._current_text()
                if self._fallback:
                    print(text)
                else:
                    self.statusbar.update(text, skip_if_input=False)
            return True
        return False

    def on_shutdown(self):
        if self.sampler:
            self.sampler.stop()
        if self.statusbar:
            self.statusbar.disable()