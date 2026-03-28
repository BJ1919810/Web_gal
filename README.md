# 纳西妲对话应用

这是一个融合了 Live2D 模型和对话功能的应用，将原本静态的纳西妲图片（其实最开始是 terminal）替换为动态的 Live2D 模型，保留了表情、动作和嘴型随声音大小变换的功能。

## 功能特点

- 动态 Live2D 模型展示（纳西妲）
- 对话交互功能（使用 DeepSeek API）
- 语音合成（GPT-SoViTS）
- 嘴型随声音大小实时变换
- 表情与动作随对话内容的推进而改变
- 背景音乐播放
- **RAG 检索增强生成**：基于 ChromaDB 的轻量级 RAG 系统，支持对话历史与知识库检索
- **用户意图识别**：智能路由系统，自动判断是否需要查询知识库或依赖历史对话
- **长期记忆系统**：自动维护核心记忆文件，记录与用户相关的长期信息
- **查询扩展与重排序**：提升检索质量，确保返回最相关的上下文

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

## 系统架构

### RAG 系统
- **检索引擎**：使用 ChromaDB 存储和检索对话历史与知识库
- **查询处理**：支持查询扩展，生成多个变体以提升检索覆盖率
- **重排序**：使用 BGE Reranker 对检索结果进行重排序，确保相关性

### 用户意图识别
- **规则路由**：基于关键词和实体识别快速判断用户意图
- **LLM 路由**：当规则无法判断时，使用 LLM 进行智能分类
- **三种类型**：
  - `none`：不需要旧对话，也不需要知识库
  - `dialogue_only`：需要依赖角色长期记忆与旧对话
  - `knowledge`：需要知识库资料来回答设定、背景等问题

### 记忆系统
- **核心记忆**：`knowledge/MEMORY.md` 存储角色身份和与用户的长期关系
- **对话日志**：自动记录每日对话到 `knowledge/memory_YYYY-MM-DD.txt`
- **自动更新**：AI 自动分析对话，提取重要信息更新核心记忆

## 注意事项

- 如果 Live2D 模型加载失败，会尝试加载备用模型
- 确保网络连接正常，以便加载必要的 JavaScript 库
- 请确保在 `.env` 文件中填入正确的 Deepseek API key
- 请确定 GSV/api.bat 中的 python 运行环境是 GSV 自带的 runtime 还是你的系统中的默认 python 环境
- 首次运行时会下载 RAG 系统所需的模型文件（约几百 MB）

## 文件说明

- `app.py`: 主应用文件，包含路由、TTS、用户意图识别等核心逻辑
- `memory.py`: 记忆系统，管理核心记忆文件和对话日志
- `rag.py`: RAG 检索系统，提供上下文检索、查询扩展、重排序功能
- `templates/index.html`: 前端页面
- `static/style.css`: 页面样式
- `static/js/script.js`: 前端交互和 Live2D 控制逻辑
- `knowledge/MEMORY.md`: 核心记忆文件
- `knowledge/memory_*.txt`: 每日对话日志
- `.env`: 环境变量配置（需手动创建）
