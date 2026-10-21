#!/usr/bin/env python3
"""AirLLM CLI —— 带插件系统。"""

import argparse
import ctypes
import hashlib
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore", message=".*pynvml.*", category=FutureWarning)

import torch

from plugin_api import BUILTIN_COMMAND_ALIASES, AppContext, GenerateContext
from plugin_loader import discover


DEFAULT_MODEL = "Qwen/Qwen2.5-3B-Instruct"
DEFAULT_MAX_LENGTH = 128
DEFAULT_MAX_NEW_TOKENS = 512
DEFAULT_COMPRESSION = "4bit"
DEFAULT_SHARDS_PATH = "./airllm_shards"

PROMPT_PREFIX = "你是一个严谨的助手。请只基于确凿的事实回答。如果不确定，请直接回答‘我不知道’，不要猜测或编造。"

_COLOR_ENABLED = False
_COLORS = {
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "dim": "\033[2m",
    "bold": "\033[1m",
}
_RESET = "\033[0m"


def _setup_terminal_colors() -> bool:
    if "NO_COLOR" in os.environ or os.environ.get("TERM", "").lower() == "dumb":
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            get_std_handle = kernel32.GetStdHandle
            get_std_handle.argtypes = [ctypes.c_uint32]
            get_std_handle.restype = ctypes.c_void_p
            handle = get_std_handle(ctypes.c_uint32(-11).value)
            mode = ctypes.c_uint32()
            get_console_mode = kernel32.GetConsoleMode
            get_console_mode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            get_console_mode.restype = ctypes.c_int
            if not get_console_mode(handle, ctypes.byref(mode)):
                return False
            set_console_mode = kernel32.SetConsoleMode
            set_console_mode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            set_console_mode.restype = ctypes.c_int
            if not set_console_mode(handle, mode.value | 0x0004):
                return False
        except (AttributeError, OSError):
            return False
    return True


def _paint(text: str, color: str) -> str:
    if not _COLOR_ENABLED or color not in _COLORS:
        return text
    return f"{_COLORS[color]}{text}{_RESET}"


def _print_startup_banner(args, device: str) -> None:
    rule = "━" * 54
    print(_paint(rule, "cyan"))
    print(_paint("  AirLLM-EasyTUI", "bold"))
    print(f"  模型       {_paint(args.model, 'cyan')}")
    print(f"  压缩 / 设备  {_paint(args.compression, 'green')}  ·  {device}")
    print(f"  上下文     {args.max_length} tokens  ·  生成上限 {args.max_new_tokens} tokens")
    print(_paint(rule, "cyan"))
    print(f"  输入 {_paint('/help', 'yellow')} 查看命令，输入 {_paint('quit', 'yellow')} 退出")
    print()


def _print_help(plugins) -> None:
    print(_paint("可用命令", "bold"))
    print(plugins.describe_commands())


# ---------------------------------------------------------------------------
# 缓存路径工具
# ---------------------------------------------------------------------------

def _safe_component(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', "--", name or "")
    name = name.strip("-._")
    return name or "model"


def _short_hash(path: str, length: int = 8) -> str:
    norm = os.path.normcase(os.path.abspath(os.path.expanduser(path)))
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:length]


def _safe_model_dirname(model_name: str) -> str:
    raw = (model_name or "").strip()
    if not raw:
        return "default_model"

    expanded = os.path.expanduser(raw.rstrip("/\\"))
    is_existing_dir = os.path.isdir(expanded)
    looks_like_path = (
        os.path.isabs(expanded)
        or expanded.startswith(".")
        or "\\" in expanded
        or expanded.count("/") >= 2
    )

    if is_existing_dir or looks_like_path:
        abs_path = os.path.abspath(expanded)
        base = os.path.basename(abs_path) or "model"
        return f"{_safe_component(base)}-{_short_hash(abs_path)}"

    return _safe_component(expanded)


def resolve_shards_path(base_path: str, model_name: str,
                        compression: str | None = None) -> str:
    parts = [base_path, _safe_model_dirname(model_name)]
    parts.append(compression if compression else "none")
    return os.path.join(*parts)


# ---------------------------------------------------------------------------
# 命令行参数
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="AirLLM CLI - 小显存大模型对话工具")
    parser.add_argument("--model", "-m", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--compression", type=str, default=DEFAULT_COMPRESSION,
                        choices=["4bit", "8bit", "none"])
    parser.add_argument("--shards-path", type=str, default=DEFAULT_SHARDS_PATH,
                        help="分层缓存的根目录；实际路径会按 模型名/压缩方式 再细分")
    parser.add_argument("--no-gpu", action="store_true")
    parser.add_argument("--monitor-interval", type=float, default=0.5,
                        help="资源采样间隔（秒），resource_monitor 插件使用")
    parser.add_argument("--disable-plugin", action="append", default=[],
                        metavar="NAME", help="禁用指定插件，可多次使用")
    parser.add_argument("--log-dir", type=str, default="log",
                        help="对话日志目录（chat_logger 插件使用）")
    parser.add_argument("--log-prefix", type=str, default="chat",
                        help="日志文件名前缀（默认 chat）")
    parser.add_argument("--memory-dir", type=str, default="memory",
                        help="持久化记忆目录（memory 插件使用）")
    parser.add_argument("--api-host", type=str, default="127.0.0.1",
                        help="OpenAI API 监听地址（openai_api 插件使用）")
    parser.add_argument("--api-port", type=int, default=8000,
                        help="OpenAI API 监听端口（默认 8000）")
    parser.add_argument("--api-model", type=str, default="airllm",
                        help="API 对外暴露的模型名称（默认 airllm）")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 模型加载
# ---------------------------------------------------------------------------

def load_model(args):
    from airllm import AutoModel

    compression = None if args.compression == "none" else args.compression

    # 按 <模型名>/<压缩方式> 细分缓存目录
    shards_path = resolve_shards_path(args.shards_path, args.model, compression)
    os.makedirs(shards_path, exist_ok=True)

    # 关键：回写实际路径，供 cache_layer_monitor 统计当前模型的缓存大小
    args._actual_shards_path = shards_path

    print(_paint("[模型] 开始加载", "blue"))
    print(f"  模型       {args.model}")
    print(f"  压缩方式   {args.compression}")
    print(f"  最大上下文 {args.max_length} tokens")
    print(f"  缓存目录   {shards_path}")
    print(_paint("  首次加载可能需要较长时间，请耐心等待。", "dim"))

    kwargs = {"compression": compression, "layer_shards_saving_path": shards_path}
    if args.no_gpu:
        kwargs["device"] = "cpu"

    model = AutoModel.from_pretrained(args.model, **kwargs)
    print(_paint("[模型] 加载完成\n", "green"))
    return model


# ---------------------------------------------------------------------------
# 命令派发与对话编码
# ---------------------------------------------------------------------------

def _dispatch_command(plugins, user_input, app):
    text = user_input.strip()
    if not text:
        return False
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd in plugins.all_command_names() or f"/{cmd}" in plugins.all_command_names():
            return plugins.handle_command(cmd, arg, app)
        return False
    low = text.lower()
    if low in plugins.all_command_names():
        return plugins.handle_command(low, "", app)
    return False


def _encode_chat(tokenizer, user_input, max_length, system_prompt=None):
    system_prompt = system_prompt or PROMPT_PREFIX
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    chat_template = getattr(tokenizer, "chat_template", None)
    if chat_template:
        input_ids = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
        )
        if not isinstance(input_ids, torch.Tensor):
            input_ids = torch.tensor([input_ids], dtype=torch.long)
        attention_mask = torch.ones_like(input_ids)
        return input_ids, attention_mask

    prompt = system_prompt + "\n" + user_input
    encoded = tokenizer(
        [prompt],
        return_tensors="pt",
        return_attention_mask=True,
        truncation=True,
        max_length=max_length,
        padding=False,
    )
    return encoded["input_ids"], encoded["attention_mask"]


# ---------------------------------------------------------------------------
# 交互循环
# ---------------------------------------------------------------------------

def chat(model, args, plugins):
    device = "cpu" if args.no_gpu else ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = model.tokenizer
    eos_token_id = tokenizer.eos_token_id
    pad_token_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_token_id

    # 关键：把 plugins 传进 AppContext，插件之间才能互相查找
    app = AppContext(args=args, model=model, tokenizer=tokenizer,
                     device=device, plugins=plugins)
    plugins.call("on_startup", app)

    _print_startup_banner(args, device)

    while True:
        plugins.call("on_before_input")
        try:
            user_input = input(
                f"{_paint('你', 'green')} "
                f"{_paint('(输入 /help 查看命令)', 'dim')} > "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_paint('会话已结束。', 'dim')}")
            break
        finally:
            plugins.call("on_after_input")

        if not user_input:
            continue
        command_text = user_input.lstrip("/").split(maxsplit=1)[0].lower()
        builtin = BUILTIN_COMMAND_ALIASES.get(command_text)
        if builtin == "quit" and (
            user_input.startswith("/") or user_input.lower() in ("quit", "exit", "q")
        ):
            print(_paint("会话已结束。", "dim"))
            break
        if builtin == "help" and (
            user_input.startswith("/") or user_input.lower() == "help"
        ):
            _print_help(plugins)
            continue

        if _dispatch_command(plugins, user_input, app):
            continue
        if user_input.startswith("/"):
            print(_paint(
                f"[命令] 未知命令: {user_input.split(maxsplit=1)[0]}。输入 /help 查看可用命令。",
                "yellow",
            ))
            continue
        
        gen = GenerateContext(user_text=user_input, system_prompt=PROMPT_PREFIX)
        plugins.call("on_before_generate", gen)

        system_prompt = gen.system_prompt or PROMPT_PREFIX
        input_ids, attention_mask = _encode_chat(
            tokenizer, user_input, args.max_length, system_prompt
        )
        gen.input_ids = input_ids
        gen.attention_mask = attention_mask

        print(_paint("AI 正在思考…", "dim"))
        try:
            with torch.no_grad():
                output = model.generate(
                    gen.input_ids.to(device),
                    attention_mask=gen.attention_mask.to(device),
                    max_new_tokens=args.max_new_tokens,
                    eos_token_id=eos_token_id,
                    pad_token_id=pad_token_id,
                    use_cache=True,
                    return_dict_in_generate=True,
                    temperature=0.3,
                    top_p=0.9,
                    repetition_penalty=1.1,
                    no_repeat_ngram_size=3,
                    do_sample=True,
                    **gen.extra_kwargs,
                )
        except torch.cuda.OutOfMemoryError:
            print(_paint("[错误] 显存不足，请尝试降低 --max-length。", "red"))
            torch.cuda.empty_cache()
            continue
        except Exception as e:
            print(_paint(f"[错误] 推理失败: {type(e).__name__}: {e}", "red"))
            continue

        output_ids = output.sequences[0]
        input_len = gen.input_ids.shape[1]
        new_ids = output_ids[input_len:]
        gen.sequences = output.sequences
        gen.input_len = input_len
        gen.new_tokens = len(new_ids)
        gen.response = tokenizer.decode(new_ids, skip_special_tokens=True)

        plugins.call("on_after_generate", gen)
        print(f"{_paint('AI', 'blue')} > {gen.response}\n")

        if gen.new_tokens >= args.max_new_tokens:
            if len(new_ids) > 0 and int(new_ids[-1]) != eos_token_id:
                print(_paint(
                    f"[提示] 回答达到 --max-new-tokens={args.max_new_tokens}，可能已截断。\n",
                    "yellow",
                ))


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    global _COLOR_ENABLED
    _COLOR_ENABLED = _setup_terminal_colors()

    args = parse_args()
    if not torch.cuda.is_available() and not args.no_gpu:
        print(_paint("[警告] 未检测到 CUDA，将回退到 CPU 推理。", "yellow"))

    plugins = discover(args=args, disabled=args.disable_plugin)
    print(_paint("已加载插件", "bold"))
    print(plugins.describe())
    print()

    try:
        model = load_model(args)
        chat(model, args, plugins)
    finally:
        plugins.call("on_shutdown")


if __name__ == "__main__":
    main()