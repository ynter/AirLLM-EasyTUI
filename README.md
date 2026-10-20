# 🚀 AirLLM-EasyTUI

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Version](https://img.shields.io/badge/Version-1.0.0-purple.svg)

**带插件系统的 CLI 大语言模型推理接口**

一个优雅、易用的命令行界面（CLI）工具，用于运行大语言模型（LLM），支持模型压缩、智能缓存分片和丰富的插件生态系统。

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [技术架构](#-技术架构) • [插件开发](#-插件开发)

</div>

---

## 📌 项目简介

AirLLM-EasyTUI 是一个基于 Python 和 PyTorch 的智能 CLI 工具，专注于提供流畅的 LLM 交互体验。通过插件化架构，它可以轻松扩展功能，满足从个人开发到企业级应用的各种需求。

### ✨ 核心特点

- 🎯 **智能模型管理** - 支持 4bit/8bit 模型压缩，大幅降低显存占用
- 🧩 **插件化架构** - 模块化设计，轻松扩展功能
- 📊 **实时监控** - CPU、RAM、GPU 使用率实时追踪
- 🌐 **API 服务** - 兼容 OpenAI 和 Anthropic 双协议
- 💾 **持久化记忆** - 自动保存对话历史和记忆
- ⚡ **智能缓存** - 分层缓存策略，加速模型加载

---

## ✨ 功能特性

### 🔧 模型管理

| 特性 | 说明 |
|------|------|
| **多级压缩** | 支持 4bit、8bit、none 三种压缩级别 |
| **智能分片** | 自动将大模型拆分为小文件，节省存储 |
| **缓存复用** | 后续加载直接使用缓存分片 |
| **HuggingFace 集成** | 支持 HF 模型 ID 或本地路径 |

```bash
# 4bit 压缩模式
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit

# 本地模型路径
airllm-easy-tui --model ./my_local_model --compression 8bit
```

### 🧩 插件系统

内置 8 个功能丰富的插件：

#### 1. `chat_logger` - 对话日志
- 按日期分文件自动记录
- 文件路径：`log/chat-YYYY-MM-DD.log`

#### 2. `resource_monitor` - 资源监控
- 实时 CPU、RAM、GPU 监控
- 缓存状态统计
- 推理进度显示
- 终端底部状态栏

```bash
# 查看资源占用
/stats

# 查看推理进度
/progress
```

#### 3. `memory` - 持久化记忆
- 保存和检索对话记忆
- 支持固定记忆（注入到提示词）
- 自动识别 "记住：" 开头的输入

```bash
# 添加记忆
记住：我的名字是张三

# 查看所有记忆
/memories

# 固定记忆
/pin 我的爱好是编程
```

#### 4. `openai_api` - API 服务
- FastAPI 服务，兼容 OpenAI 协议
- 支持流式和非流式响应
- 跨协议消息格式转换

```bash
# 启动 API 服务
python3 start_airllm_ui.py --model Qwen/Qwen2.5-3B-Instruct --compression 4bit --api-port 8000

# 查看帮助
/api
```

#### 5. `cache_layer_monitor` - 缓存监控
- 监控缓存分片磁盘大小
- 显示缓存命中率和压缩方式

#### 6. `inference_progress` - 推理进度
- 显示当前推理层数
- 统计已生成 token 数
- 提供 `/debug_model` 命令

```bash
# 调试模型结构
/debug_model
```

#### 7. `pynvml` - GPU 监控
- NVIDIA GPU 实时监控
- 显存占用、利用率追踪

#### 8. `psutil` - 系统监控
- CPU 使用率、负载
- RAM 使用情况

### 🌐 命令行交互

```bash
# 主命令
/help          # 显示所有可用命令
/stats         # 查看资源占用
/progress      # 查看推理进度
/memories      # 列出所有记忆
/log           # 显示日志文件路径
/api           # 管理 API 服务
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11 或更高版本
- PyTorch（根据您的硬件选择 CUDA 或 CPU 版本）
- AirLLM 库
- NVIDIA GPU（可选，但推荐用于加速）

### 安装依赖

```bash
# 克隆项目
git clone https://github.com/ynter/AirLLM-EasyTUI.git
cd AirLLM-EasyTUI

# 安装依赖
pip install -r requirements.txt
```

**requirements.txt 内容示例：**
```txt
# 深度学习框架
torch>=2.0.0
airllm>=1.0.0
transformers>=4.30.0

# 系统监控
psutil>=5.9.0
pynvml>=11.0.0

# API 服务
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0

# 其他工具
python-dateutil>=2.8.0
```

### 基本用法

```bash
# 启动 LLM CLI
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit
```

启动后会进入交互式 CLI 界面：

```
Welcome to AirLLM-EasyTUI! 🚀
Model: Qwen/Qwen2.5-3B-Instruct (4bit)
Device: cuda
--------------------------------------------------
> 你好，请介绍一下你自己。
> 你好！我是基于 Qwen2.5-3B-Instruct 模型的 AI 助手...
--------------------------------------------------
```

### 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model` | HuggingFace 模型 ID 或本地路径 | `Qwen/Qwen2.5-3B-Instruct` |
| `--compression` | 模型压缩级别（`4bit`/`8bit`/`none`） | `4bit` |
| `--shards-path` | 模型分片缓存根目录 | `./airllm_shards` |
| `--max-length` | 最大上下文长度（token） | `128` |
| `--max-new-tokens` | 最大生成 token 数 | `512` |
| `--no-gpu` | 使用 CPU 而非 GPU | `False` |
| `--monitor-interval` | 资源监控间隔（秒） | `0.5` |
| `--api-port` | API 监听端口 | `8000` |
| `--log-dir` | 对话日志目录 | `./log` |
| `--memory-dir` | 记忆存储目录 | `./memory` |

### 示例

```bash
# 使用 8bit 压缩
airllm-easy-tui --model Qwen/Qwen2.5-7B-Instruct --compression 8bit

# 本地模型 + 缓存目录
airllm-easy-tui --model ./models/my-model --compression 4bit --shards-path ./my_cache

# CPU 模式
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit --no-gpu

# 启动 API 服务
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit --api-port 8000

# 禁用特定插件
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit --disable-plugin chat_logger
```

---

## 🏗️ 技术架构

### 插件系统设计

AirLLM-EasyTUI 采用插件化架构，所有插件继承自 `AirLLMPlugin` 基类。

#### 生命周期钩子

```python
class AirLLMPlugin:
    name = "plugin_name"
    version = "1.0.0"
    description = ""
    commands = {"cmd": "命令帮助"}

    def setup(self, args) -> None:
        """插件被发现时调用（模型加载之前）"""
        pass

    def on_startup(self, app: AppContext) -> None:
        """模型加载后、对话开始前调用"""
        pass

    def on_before_input(self) -> None:
        """用户输入前调用"""
        pass

    def on_after_input(self) -> None:
        """用户输入后调用"""
        pass

    def on_before_generate(self, gen: GenerateContext) -> None:
        """每次生成前调用"""
        pass

    def on_after_generate(self, gen: GenerateContext) -> None:
        """每次生成后调用"""
        pass

    def on_shutdown(self) -> None:
        """程序退出时调用"""
        pass

    def handle_command(self, cmd: str, arg: str, app: AppContext) -> bool:
        """处理自定义命令"""
        if cmd == "cmd":
            # 命令逻辑
            return True
        return False
```

#### 插件管理器

`PluginManager` 负责自动发现和管理所有插件：

- **自动发现**：从 `plugins/` 目录扫描所有插件
- **统一调用**：通过 `call(hook, *a, **kw)` 调用所有插件的钩子
- **命令路由**：通过 `handle_command()` 查找并执行插件命令

### 模型加载流程

```
1. 解析命令行参数
        ↓
2. _safe_model_dirname() 规范化模型名称
        ↓
3. resolve_shards_path() 构建缓存路径
        ↓
4. PluginManager 发现所有插件
        ↓
5. 插件 setup() 钩子（初始化）
        ↓
6. AutoModel.from_pretrained() 加载模型
        ↓
7. 插件 on_startup() 钩子
        ↓
8. 进入对话循环
```

### 缓存策略

AirLLM 使用分层缓存策略：

```
--shards-path/               # 基础缓存根目录
└── <model-name>/            # 模型子目录（规范化后）
    ├── 4bit/                # 4bit 压缩分片
    │   ├── 0.safetensors
    │   ├── 0.safetensors.done
    │   ├── 1.safetensors
    │   └── ...
    ├── 8bit/                # 8bit 压缩分片
    └── none/                # 原始压缩
```

**缓存优势**：
- 分片文件独立命名，支持并行下载
- `.done` 标记确保分片完整性
- 后续加载直接使用缓存，无需重新切分
- 按模型和压缩方式独立存储

### 核心组件

#### 1. 主程序 (`start_airllm_ui.py`)

- 命令行参数解析
- 模型加载和初始化
- 对话循环管理
- 插件生命周期协调

#### 2. 插件接口 (`plugin_api.py`)

- `AppContext`：应用级上下文
- `GenerateContext`：生成级上下文
- `AirLLMPlugin`：插件基类
- `PluginManager`：插件管理器

#### 3. 插件目录 (`plugins/`)

| 插件文件 | 功能描述 |
|---------|---------|
| `chat_logger.py` | 对话日志记录 |
| `resource_monitor.py` | CPU/RAM/GPU 监控 |
| `cache_layer_monitor.py` | 缓存状态监控 |
| `inference_progress.py` | 推理进度显示 |
| `memory.py` | 持久化记忆管理 |
| `openai_api.py` | OpenAI 兼容 API 服务 |
| `pynvml.py` | NVIDIA GPU 监控 |
| `psutil.py` | 系统资源监控 |

### 数据流

```
用户输入
    ↓
_on_before_input()
    ↓
命令派发（/command）
    ↓
tokenizer.apply_chat_template()
    ↓
_on_before_generate()
    ↓
模型推理（generate）
    ↓
_on_after_generate()
    ↓
输出响应
```

---

## 🔌 插件开发

### 创建新插件

1. 在 `plugins/` 目录创建新文件
2. 继承 `AirLLMPlugin`
3. 实现生命周期钩子
4. 在 `commands` 字典注册命令
5. 插件会自动发现和加载

### 插件示例

```python
# plugins/my_plugin.py
from plugin_api import AirLLMPlugin

class MyPlugin(AirLLMPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "我的自定义插件"
    commands = {
        "hello": "显示问候信息",
        "calc": "简单计算器"
    }

    def on_startup(self, app):
        """插件初始化"""
        print(f"[{self.name}] 插件启动！")

    def on_before_input(self):
        """输入前处理"""
        pass

    def on_after_generate(self, gen):
        """生成后处理"""
        print(f"[{self.name}] 生成完成！")

    def handle_command(self, cmd, arg, app):
        """命令处理"""
        if cmd == "hello":
            print("Hello from MyPlugin!")
            return True
        elif cmd == "calc":
            try:
                result = eval(arg)
                print(f"结果: {result}")
                return True
            except:
                print("计算错误")
                return True
        return False
```

### 错误处理

插件应该在 `setup()` 和生命周期钩子中使用 try/except：

```python
def setup(self, args):
    try:
        # 初始化代码
        pass
    except Exception as e:
        print(f"[{self.name}] 初始化失败: {e}")
        # 继续运行，不阻止其他插件
```

---

## 📦 安装说明

### 从 PyPI 安装（推荐）

```bash
# 安装包
pip install airllm-easy-tui

# 运行
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit
```

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/ynter/AirLLM-EasyTUI.git
cd AirLLM-EasyTUI

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装开发依赖
pip install -e ".[dev]"

# 运行
airllm-easy-tui --model Qwen/Qwen2.5-3B-Instruct --compression 4bit
```

**开发安装说明：**
- `pip install airllm-easy-tui` - 安装生产版本
- `pip install -e ".[dev]"` - 以可编辑模式安装（开发模式），支持代码修改实时生效

---

## 🤝 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 开发规范

- 遵循 PEP 8 代码规范
- 添加适当的文档字符串
- 为新功能编写测试
- 更新相关文档

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [AirLLM](https://github.com/yourusername/airllm) - 模型加载和推理库
- [Transformers](https://github.com/huggingface/transformers) - Hugging Face 库
- [PyTorch](https://pytorch.org/) - 深度学习框架

---

## 📮 联系方式

- 项目主页：[GitHub](https://github.com/ynter/AirLLM-EasyTUI)
- 问题反馈：[Issues](https://github.com/ynter/AirLLM-EasyTUI/issues)
- 邮箱：ynter8@163.com

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给它一个 Star！**

Made with ❤️ by [Ynter]

</div>
