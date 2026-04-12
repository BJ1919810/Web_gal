# 纳西妲对话应用

这是一个融合了 Live2D 模型和对话功能的应用，将原本静态的纳西妲图片替换为动态的 Live2D 模型，保留了表情、动作和嘴型随声音大小变换的功能。

## 功能特点

- 动态 Live2D 模型展示（纳西妲）
- 对话交互功能（使用 DeepSeek API）
- 语音合成（GPT-SoViTS）
- 嘴型随声音大小实时变换
- 表情与动作随对话内容的推进而改变
- 背景音乐播放
- **双模式对话系统**：
  - **普通模式**：纯对话模式，只使用 system prompt 控制行为
  - **Agent 模式**：具备 function-call 功能，可调用多种工具执行复杂任务
- **工具系统**（Agent 模式）：
  - `read_file`：读取文件内容
  - `write_file`：写入或创建文件
  - `delete_file`：删除文件或目录
  - `list_directory`：列出目录内容
  - `search_files`：搜索文件和内容
  - `rag_search`：RAG 知识库检索
  - `execute_command`：执行系统命令（黑名单保护）
  - **沙箱限制**：所有文件操作仅限于 workspace 目录，禁止外泄
- **历史记录面板**：右下角浮窗查看完整对话历史
- **上下文连贯**：支持模式切换时保留对话上下文
- **流式响应**：Agent 模式实时显示中间结果

## 安装依赖

在运行应用前，请确保安装了以下依赖：

```bash
pip install flask requests librosa numpy openai python-dotenv chromadb sentence-transformers
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

## 运行步骤

1. 确保 GSV 目录下的 TTS 服务已经启动（利用该项目的 api.py 启动，端口为 9880）

2. 配置 API 密钥：
   - 在项目根目录创建 `.env` 文件
   - 添加以下内容：
   ```
   DEEPSEEK_API_KEY=your_api_key_here
   ```

3. 运行应用：

```bash
python app.py
```

4. 打开浏览器，访问 http://localhost:5000

## 使用说明

### 模式切换

页面右上角有模式切换开关：
- **普通模式**：简单的对话交互，适合闲聊
- **Agent 模式**：可调用工具执行文件操作、搜索、命令执行等任务

### Agent 模式工具使用

Agent 模式下，AI 可以自动调用合适的工具来完成任务：

- **文件操作**：读取、写入、删除文件，所有操作限制在 `workspace` 目录
- **目录浏览**：列出目录内容，搜索文件
- **知识检索**：搜索 RAG 知识库和对话历史
- **命令执行**：执行只读系统命令（危险操作已黑名单拦截）

### 历史记录

点击右下角的书本图标打开历史记录面板，可查看完整对话历史。

## 系统架构

### Agent 工具系统
- **沙箱保护**：所有文件路径被规范化和验证，禁止访问 workspace 以外目录
- **黑名单机制**：危险命令（如 rm、del、format 等）被拦截
- **白名单机制**：仅允许预定义的只读命令执行

### 流式响应
- **实时显示**：Agent 模式的中间结果实时显示在对话框
- **打字机效果**：最终回复使用打字机效果，配合 TTS 播放
- **表情动作**：流式内容正确解析并触发表情动作

### RAG 系统
- **检索引擎**：使用 ChromaDB 存储和检索对话历史与知识库
- **查询处理**：支持查询扩展，生成多个变体以提升检索覆盖率
- **重排序**：使用 BGE Reranker 对检索结果进行重排序

## 注意事项

- 如果 Live2D 模型加载失败，会尝试加载备用模型
- 确保网络连接正常，以便加载必要的 JavaScript 库
- 请确保在 `.env` 文件中填入正确的 Deepseek API key
- 请确定 GSV/api.bat 中的 python 运行环境是 GSV 自带的 runtime 还是你的系统中的默认 python 环境
- 首次运行时会下载 RAG 系统所需的模型文件（约几百 MB）
- Agent 模式下删除文件前请确认路径正确，删除后无法恢复

## 文件说明

- `app.py`: 主应用文件，包含路由、TTS、流式响应、Agent 循环等核心逻辑
- `tools.py`: Agent 工具系统，实现文件操作、命令执行等工具函数
- `memory.py`: 记忆系统，管理核心记忆文件和对话日志
- `rag.py`: RAG 检索系统，提供上下文检索、查询扩展、重排序功能
- `templates/index.html`: 前端页面
- `static/style.css`: 页面样式（包含历史记录面板样式）
- `static/js/script.js`: 前端交互、流式响应处理和 Live2D 控制逻辑
- `workspace/`: Agent 模式文件操作的沙箱目录
- `knowledge/MEMORY.md`: 核心记忆文件
- `knowledge/memory_*.txt`: 每日对话日志
- `.env`: 环境变量配置（需手动创建）
