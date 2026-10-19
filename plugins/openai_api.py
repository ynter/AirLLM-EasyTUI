"""OpenAI + Anthropic 双协议兼容的 AirLLM API 插件。"""

import asyncio
import json
import threading
import time
import uuid
from typing import Any, AsyncGenerator, List, Optional

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

from plugin_api import AirLLMPlugin


# ---------------------------------------------------------------------------
# OpenAI 格式模型
# ---------------------------------------------------------------------------
if _HAS_FASTAPI:
    class ChatMessage(BaseModel):
        role: str
        content: Any = None
        name: Optional[str] = None
        tool_calls: Optional[List[dict]] = None
        tool_call_id: Optional[str] = None

    class ChatCompletionRequest(BaseModel):
        model: str = "airllm"
        messages: List[ChatMessage]
        max_tokens: Optional[int] = None
        temperature: Optional[float] = 0.3
        top_p: Optional[float] = 0.9
        stream: bool = False
        stop: Optional[Any] = None
        n: int = 1

    # -----------------------------------------------------------------------
    # Anthropic 格式模型
    # -----------------------------------------------------------------------
    class AnthropicContentBlock(BaseModel):
        type: str
        text: Optional[str] = None

    class AnthropicMessage(BaseModel):
        role: str                         # user / assistant / system（放宽）
        content: Any = None               # str 或 list[block]

    class AnthropicMessagesRequest(BaseModel):
        model: str = "airllm"
        max_tokens: int = 512
        messages: List[AnthropicMessage]
        system: Optional[Any] = None      # str 或 list[block]
        temperature: Optional[float] = 0.3
        top_p: Optional[float] = 0.9
        stream: bool = False
        stop_sequences: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# 工具：归一化 content（str 或 block list 都能处理）
# ---------------------------------------------------------------------------
def _flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    parts.append(str(block.get("content", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# 插件
# ---------------------------------------------------------------------------
class OpenAIApiPlugin(AirLLMPlugin):
    name = "openai_api"
    version = "1.2.0"
    description = "OpenAI + Anthropic 双协议 API 服务（按需启动）"
    commands = {"api": "管理 API 服务：/api [start|stop|restart|status|help]"}

    def __init__(self):
        self.app = None
        self.host = "127.0.0.1"
        self.port = 8000
        self.model_name = "airllm"
        self._server = None
        self._thread = None
        self._fastapi = None
        self._running = False

    # ---- 生命周期 ----
    def setup(self, args):
        self.host = getattr(args, "api_host", "127.0.0.1")
        self.port = getattr(args, "api_port", 8000)
        self.model_name = getattr(args, "api_model", "airllm")
        if not _HAS_FASTAPI:
            print("[API] 缺少依赖: pip install fastapi uvicorn pydantic")

    def on_startup(self, app):
        if not _HAS_FASTAPI:
            print("[API] 依赖未安装，/api start 不可用")
            return
        self.app = app
        self._build_app()
        print(f"[API] 插件就绪，/api start 启动（{self.host}:{self.port}）")

    def on_shutdown(self):
        if self._running or self._server is not None:
            self._stop_server()

    # ---- 命令 ----
    def handle_command(self, cmd, arg, app):
        if cmd != "api":
            return False
        sub = (arg or "").strip().lower()
        if sub in ("", "status"):
            self._cmd_status()
        elif sub == "start":
            self._start_server()
        elif sub == "stop":
            self._stop_server()
        elif sub == "restart":
            self._stop_server()
            time.sleep(0.2)
            self._start_server()
        elif sub in ("help", "-h", "--help"):
            self._cmd_help()
        else:
            print(f"[API] 未知子命令: {sub}")
            self._cmd_help()
        return True

    def _cmd_status(self):
        if not _HAS_FASTAPI:
            print("[API] 未安装依赖：pip install fastapi uvicorn pydantic")
            return
        if self._running:
            print(f"[API] 运行中: http://{self.host}:{self.port}")
            print(f"[API] OpenAI 端点:    POST /v1/chat/completions")
            print(f"[API] Anthropic 端点: POST /v1/messages")
            print(f"[API] 模型名称: {self.model_name}")
            print("[API] 停止: /api stop    重启: /api restart")
        else:
            print(f"[API] 未启动。配置为监听 {self.host}:{self.port}")
            print("[API] 启动: /api start    帮助: /api help")

    def _cmd_help(self):
        print("[API] 命令：/api | /api start | /api stop | /api restart | /api help")
        print()
        print("[API] Claude Code 配置：")
        print(f"  export ANTHROPIC_BASE_URL=http://{self.host}:{self.port}")
        print(f"  export ANTHROPIC_API_KEY=any-string")
        print(f"  export ANTHROPIC_MODEL={self.model_name}")
        print()
        print("[API] Codex / OpenAI SDK 配置：")
        print(f'  openai_base_url = "http://{self.host}:{self.port}/v1"')

    # ---- 服务生命周期 ----
    def _start_server(self) -> bool:
        if not _HAS_FASTAPI:
            print("[API] 缺少依赖: pip install fastapi uvicorn pydantic")
            return False
        if self._running:
            print("[API] 服务已在运行。如需重启请用 /api restart")
            return True
        if self._fastapi is None:
            if self.app is None:
                print("[API] 模型尚未加载，无法启动服务")
                return False
            self._build_app()

        try:
            config = uvicorn.Config(
                self._fastapi, host=self.host, port=self.port, log_level="warning"
            )
            self._server = uvicorn.Server(config)
        except Exception as e:
            print(f"[API] 构建服务失败: {type(e).__name__}: {e}")
            return False

        def run():
            try:
                self._server.run()
            except Exception as e:
                print(f"[API] 服务运行出错: {type(e).__name__}: {e}")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

        for _ in range(50):
            time.sleep(0.1)
            if getattr(self._server, "started", False):
                self._running = True
                print(f"[API] 服务已启动: http://{self.host}:{self.port}")
                print(f"[API]   OpenAI:    POST /v1/chat/completions")
                print(f"[API]   Anthropic: POST /v1/messages")
                return True

        print("[API] 启动超时（端口可能被占用）")
        self._stop_server()
        return False

    def _stop_server(self):
        if self._server is not None:
            try:
                self._server.should_exit = True
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._server = None
        self._thread = None
        if self._running:
            print("[API] 服务已停止")
        self._running = False

    # ---- FastAPI 应用 ----
    def _build_app(self):
        fastapi = FastAPI(title="AirLLM Dual Protocol API")
        fastapi.add_middleware(
            CORSMiddleware, allow_origins=["*"],
            allow_methods=["*"], allow_headers=["*"],
        )

        # -------- OpenAI 端点 --------
        @fastapi.get("/v1/models")
        async def list_models():
            return {
                "object": "list",
                "data": [{"id": self.model_name, "object": "model",
                          "created": int(time.time()), "owned_by": "airllm"}],
            }

        @fastapi.post("/v1/chat/completions")
        async def chat_completions(req: ChatCompletionRequest):
            if req.stream:
                return StreamingResponse(self._stream_openai_chat(req),
                                         media_type="text/event-stream")
            return await self._non_stream_openai_chat(req)

        # -------- Anthropic 端点（Claude Code 原生） --------
        @fastapi.post("/v1/messages")
        async def anthropic_messages(req: AnthropicMessagesRequest):
            if req.stream:
                return StreamingResponse(self._stream_anthropic(req),
                                         media_type="text/event-stream")
            return await self._non_stream_anthropic(req)

        self._fastapi = fastapi

    # =======================================================================
    # Anthropic 请求 → 内部 prompt
    # =======================================================================
    def _anthropic_to_prompt(self, req: AnthropicMessagesRequest):
        """把 Anthropic 格式请求转成 (system_prompt, user_text)。

        关键兼容：Claude Code 新版本会把 system 塞进 messages[]，
        这里统一“提升”到顶层 system_prompt。
        """
        # 1. 顶层 system
        system_parts = []
        if req.system is not None:
            system_parts.append(_flatten_content(req.system))

        # 2. 遍历 messages，收集 system / user / assistant
        dialog_lines = []
        for m in req.messages:
            text = _flatten_content(m.content)
            if m.role == "system":
                # 提升：把内联 system 并入顶层 system prompt
                system_parts.append(text)
            elif m.role == "user":
                dialog_lines.append(f"用户: {text}")
            elif m.role == "assistant":
                dialog_lines.append(f"助手: {text}")
            # 其他角色忽略

        system_prompt = "\n".join(p for p in system_parts if p.strip()) or None
        user_text = "\n".join(dialog_lines) or "你好"
        return system_prompt, user_text

    # =======================================================================
    # 推理核心（两种协议共用）
    # =======================================================================
    def _generate_sync(self, system_prompt: Optional[str], user_text: str,
                       max_new: int, temperature: float, top_p: float):
        app = self.app
        tokenizer = app.tokenizer
        model = app.model
        device = app.device

        from start_airllm_ui import _encode_chat
        max_length = getattr(app.args, "max_length", 512)
        input_ids, attention_mask = _encode_chat(
            tokenizer, user_text, max_length, system_prompt
        )

        import torch
        with torch.no_grad():
            output = model.generate(
                input_ids.to(device),
                attention_mask=attention_mask.to(device),
                max_new_tokens=max_new,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                use_cache=True,
                return_dict_in_generate=True,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=1.1,
                no_repeat_ngram_size=3,
                do_sample=True,
            )

        output_ids = output.sequences[0]
        input_len = input_ids.shape[1]
        new_ids = output_ids[input_len:]
        text = tokenizer.decode(new_ids, skip_special_tokens=True)
        return text, int(input_len), int(len(new_ids))

    # =======================================================================
    # OpenAI 非流式 / 流式
    # =======================================================================
    def _openai_build_prompt(self, messages: List[ChatMessage]):
        system_parts = []
        dialog_lines = []
        for m in messages:
            content = _flatten_content(m.content)
            if m.role == "system":
                system_parts.append(content)
            elif m.role == "user":
                dialog_lines.append(f"用户: {content}")
            elif m.role == "assistant":
                dialog_lines.append(f"助手: {content}")
            elif m.role == "tool":
                dialog_lines.append(f"工具结果: {content}")
        return ("\n".join(system_parts) or None), ("\n".join(dialog_lines) or "你好")

    async def _non_stream_openai_chat(self, req: ChatCompletionRequest):
        sys_p, user_t = self._openai_build_prompt(req.messages)
        max_new = req.max_tokens or getattr(self.app.args, "max_new_tokens", 512)
        try:
            text, p_tok, c_tok = await asyncio.to_thread(
                self._generate_sync, sys_p, user_t, max_new,
                req.temperature or 0.3, req.top_p or 0.9,
            )
        except Exception as e:
            raise HTTPException(500, detail=f"推理失败: {type(e).__name__}: {e}")

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion", "created": int(time.time()),
            "model": self.model_name,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok,
                      "total_tokens": p_tok + c_tok},
        }

    async def _stream_openai_chat(self, req: ChatCompletionRequest):
        sys_p, user_t = self._openai_build_prompt(req.messages)
        max_new = req.max_tokens or getattr(self.app.args, "max_new_tokens", 512)
        try:
            text, p_tok, c_tok = await asyncio.to_thread(
                self._generate_sync, sys_p, user_t, max_new,
                req.temperature or 0.3, req.top_p or 0.9,
            )
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        yield self._openai_sse(cid, created, delta={"role": "assistant"})
        for i, tok in enumerate(text.split()):
            piece = tok + ("" if i == len(text.split()) - 1 else " ")
            yield self._openai_sse(cid, created, delta={"content": piece})
        yield self._openai_sse(cid, created, delta={}, finish_reason="stop",
                               usage={"prompt_tokens": p_tok, "completion_tokens": c_tok,
                                      "total_tokens": p_tok + c_tok})
        yield "data: [DONE]\n\n"

    def _openai_sse(self, cid, created, delta, finish_reason=None, usage=None):
        chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                 "model": self.model_name,
                 "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
        if usage:
            chunk["usage"] = usage
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    # =======================================================================
    # Anthropic 非流式
    # =======================================================================
    async def _non_stream_anthropic(self, req: AnthropicMessagesRequest):
        sys_p, user_t = self._anthropic_to_prompt(req)
        try:
            text, p_tok, c_tok = await asyncio.to_thread(
                self._generate_sync, sys_p, user_t, req.max_tokens,
                req.temperature or 0.3, req.top_p or 0.9,
            )
        except Exception as e:
            raise HTTPException(500, detail=f"推理失败: {type(e).__name__}: {e}")

        return {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "model": self.model_name,
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": p_tok, "output_tokens": c_tok},
        }

    # =======================================================================
    # Anthropic 流式 SSE
    # 事件序列：message_start → content_block_start → content_block_delta...
    #           → content_block_stop → message_delta → message_stop
    # =======================================================================
    async def _stream_anthropic(self, req: AnthropicMessagesRequest):
        sys_p, user_t = self._anthropic_to_prompt(req)
        try:
            text, p_tok, c_tok = await asyncio.to_thread(
                self._generate_sync, sys_p, user_t, req.max_tokens,
                req.temperature or 0.3, req.top_p or 0.9,
            )
        except Exception as e:
            yield self._anthropic_sse("error", {"type": "error",
                                                "error": {"type": "api_error",
                                                          "message": str(e)}})
            return

        msg_id = f"msg_{uuid.uuid4().hex[:24]}"

        # 1. message_start
        yield self._anthropic_sse("message_start", {
            "type": "message_start",
            "message": {
                "id": msg_id, "type": "message", "role": "assistant",
                "model": self.model_name, "content": [],
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": p_tok, "output_tokens": 0},
            },
        })

        # 2. content_block_start
        yield self._anthropic_sse("content_block_start", {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        })

        # 3. content_block_delta（逐词）
        words = text.split()
        for i, tok in enumerate(words):
            piece = tok + ("" if i == len(words) - 1 else " ")
            yield self._anthropic_sse("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "text_delta", "text": piece},
            })

        # 4. content_block_stop
        yield self._anthropic_sse("content_block_stop", {
            "type": "content_block_stop", "index": 0,
        })

        # 5. message_delta（携带最终 usage 与 stop_reason）
        yield self._anthropic_sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": c_tok},
        })

        # 6. message_stop
        yield self._anthropic_sse("message_stop", {"type": "message_stop"})

    def _anthropic_sse(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"