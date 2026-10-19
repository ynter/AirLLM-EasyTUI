"""推理进度插件：hook 层 forward + LogitsProcessor，提供"第几层 / 第几个 token"。"""

from plugin_api import AirLLMPlugin

try:
    from transformers import LogitsProcessor
    _HAS_TRANSFORMERS = True
except ImportError:
    LogitsProcessor = object
    _HAS_TRANSFORMERS = False


class _ProgressProcessor(LogitsProcessor):
    """每个生成步骤被调用一次，用于统计已生成 token 数。"""

    def __init__(self, state):
        self.state = state

    def __call__(self, input_ids, scores):
        self.state["generated"] += 1
        return scores


class InferenceProgressPlugin(AirLLMPlugin):
    name = "inference_progress"
    version = "1.1.0"
    description = "显示推理进度（层 / token），合并到状态栏"
    commands = {
        "progress": "打印当前推理进度",
        "debug_model": "打印模型结构摘要（层定位失败时使用）",
    }

    def __init__(self):
        self.state = {
            "active": False,
            "current_layer": 0,
            "total_layers": 0,
            "generated": 0,
            "max_new_tokens": 0,
        }
        self._app = None
        self._layers = None
        self._layer_path = None
        self._hooked_ok = False

    # ---- 生命周期 ----
    def on_startup(self, app):
        self._app = app
        try:
            self._layers, self._layer_path = self._find_layers(app.model)
        except Exception as e:
            print(f"[进度] 定位层失败: {type(e).__name__}: {e}")
            self._layers = None

        if self._layers is None:
            print("[进度] 未定位到模型层，仅显示 token 进度")
            print("[进度] 可执行 /debug_model 查看模型结构")
            return

        self.state["total_layers"] = len(self._layers)
        n = self._install_layer_hooks(self._layers)
        if n > 0:
            self._hooked_ok = True
            print(f"[进度] 通过 {self._layer_path} 找到 {len(self._layers)} 层，已 hook {n} 层")
        else:
            print(f"[进度] 找到层({self._layer_path})但 hook 失败")

    def on_before_generate(self, gen):
        self.state["active"] = True
        self.state["generated"] = 0
        self.state["current_layer"] = 0
        if self._app is not None:
            self.state["max_new_tokens"] = getattr(self._app.args, "max_new_tokens", 0)

        # 如果启动时 hook 失败，在首次推理前再试一次
        if not self._hooked_ok and self._app is not None:
            try:
                layers, path = self._find_layers(self._app.model)
                if layers is not None:
                    self._layers = layers
                    self._layer_path = path
                    self.state["total_layers"] = len(layers)
                    n = self._install_layer_hooks(layers)
                    if n > 0:
                        self._hooked_ok = True
                        print(f"[进度] 延迟 hook 成功: {path} ({n} 层)")
            except Exception:
                pass

        # 注入 token 计数 processor
        if _HAS_TRANSFORMERS:
            existing = gen.extra_kwargs.get("logits_processor")
            if existing is None:
                existing = []
            elif not isinstance(existing, list):
                existing = [existing]
            gen.extra_kwargs["logits_processor"] = list(existing) + [_ProgressProcessor(self.state)]

    def on_after_generate(self, gen):
        self.state["active"] = False

    # ---- 查询 ----
    def get_progress(self):
        return dict(self.state)

    # ---- 命令 ----
    def handle_command(self, cmd, arg, app):
        if cmd == "progress":
            s = self.state
            if not s["active"]:
                print("[进度] 当前无推理进行")
            else:
                layer = f"L{s['current_layer']}/{s['total_layers']}" if s["total_layers"] else "L?/?"
                print(f"[进度] {layer} | token {s['generated']}/{s['max_new_tokens']}")
            return True
        if cmd == "debug_model":
            self._print_model_structure(app.model)
            return True
        return False

    # ---- 内部 ----
    def _find_layers(self, model):
        """在 AirLLM 模型里按属性路径定位 decoder 层列表。

        AirLLMBaseModel 不是 nn.Module，不能走 named_children；
        必须按已知的嵌套路径访问：
            AirLLMBaseModel.model (Qwen2ForCausalLM)
                .model (Qwen2Model)
                    .layers (ModuleList[Qwen2DecoderLayer])   ← 目标
        """
        def _safe_get(obj, *attrs):
            cur = obj
            for a in attrs:
                if cur is None:
                    return None
                cur = getattr(cur, a, None)
            return cur

        # 按优先级尝试各种可能的路径
        paths = [
            ("model.model.model.layers", ("model", "model", "model", "layers")),  # 标准 transformers 嵌套
            ("model.model.layers", ("model", "model", "layers")),
            ("model.layers", ("model", "layers")),
            ("layers", ("layers",)),
        ]
        for label, attrs in paths:
            layers = _safe_get(model, *attrs)
            if layers is None:
                continue
            try:
                if len(layers) >= 4:
                    return layers, label
            except TypeError:
                continue
        return None, None

    def _install_layer_hooks(self, layers):
        """给每一层的 forward 打点，每次进入某层时更新 current_layer。"""
        count = 0
        state = self.state
        for idx, layer in enumerate(layers):
            if getattr(layer, "_progress_hooked", False):
                count += 1
                continue
            original = getattr(layer, "forward", None)
            if original is None:
                continue

            def make_hook(i, orig):
                def hooked(*args, **kwargs):
                    state["current_layer"] = i + 1
                    return orig(*args, **kwargs)
                return hooked

            try:
                layer.forward = make_hook(idx, original)
                layer._progress_hooked = True
                count += 1
            except Exception:
                pass
        return count

    def _print_model_structure(self, model):
        """诊断输出：打印几个关键路径的访问结果。"""
        print(f"[进度] 模型类型: {type(model).__name__}")

        def _safe_get(obj, *attrs):
            cur = obj
            for a in attrs:
                if cur is None:
                    return None
                cur = getattr(cur, a, None)
            return cur

        probes = [
            "model",
            "model.model",
            "model.model.layers",
            "model.model.model",
            "model.model.model.layers",
            "layers",
        ]
        for path in probes:
            try:
                val = _safe_get(model, *path.split("."))
                if val is None:
                    print(f"[进度]   {path:30s} -> None")
                else:
                    try:
                        n = len(val)
                        print(f"[进度]   {path:30s} -> {type(val).__name__} (len={n})")
                    except TypeError:
                        print(f"[进度]   {path:30s} -> {type(val).__name__}")
            except Exception as e:
                print(f"[进度]   {path:30s} -> 出错: {e}")