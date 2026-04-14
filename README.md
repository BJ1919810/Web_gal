# Nahida Chat Application

[中文版](./README_zh.md)

This is an application that integrates Live2D model and dialogue functionality, replacing the originally static Nahida image with a dynamic Live2D model, retaining features such as expressions, actions, and lip movements that change with voice volume.

## Features

- Dynamic Live2D model display (Nahida)
- Dialogue interaction (using DeepSeek API)
- Speech synthesis (GPT-SoViTS)
- Real-time lip movement based on voice volume
- Expressions and actions change as dialogue progresses
- Background music playback
- **Dual-mode dialogue system**:
  - **Normal Mode**: Pure dialogue mode, uses system prompt to control behavior
  - **Agent Mode**: Has function-call capability, can call various tools to execute complex tasks
- **Tool System** (Agent Mode):
  - `read_file`: Read file content
  - `write_file`: Write or create files
  - `delete_file`: Delete files or directories
  - `list_directory`: List directory contents
  - `search_files`: Search files and content
  - `rag_search`: RAG knowledge base search
  - `execute_command`: Execute system commands (blacklist protection)
  - **Sandbox restriction**: All file operations limited to workspace directory
- **History Panel**: Floating window in bottom-right to view complete dialogue history
- **Context continuity**: Preserves dialogue context when switching modes
- **Streaming response**: Agent mode displays intermediate results in real-time

## Installation

Before running the application, ensure the following dependencies are installed:

```bash
pip install flask requests librosa numpy openai python-dotenv chromadb sentence-transformers
```

Or using requirements.txt:

```bash
pip install -r requirements.txt
```

## Getting Started

1. Ensure the TTS service under the GSV directory is running (use api.py from that project, port 9880)

2. Configure API key:
   - Create a `.env` file in the project root
   - Add the following:
   ```
   DEEPSEEK_API_KEY=your_api_key_here
   ```

3. Run the application:

```bash
python app.py
```

4. Open browser and visit http://localhost:5000

## Usage

### Mode Switching

There's a mode toggle switch in the top-right corner:
- **Normal Mode**: Simple dialogue interaction, suitable for casual chat
- **Agent Mode**: Can call tools to execute file operations, search, command execution, etc.

### Agent Mode Tools

In Agent mode, AI can automatically call appropriate tools to complete tasks:

- **File Operations**: Read, write, delete files, all operations restricted to `workspace` directory
- **Directory Browsing**: List directory contents, search files
- **Knowledge Retrieval**: Search RAG knowledge base and dialogue history
- **Command Execution**: Execute read-only system commands (dangerous operations blocked by blacklist)

### History

Click the book icon in the bottom-right corner to open the history panel and view complete dialogue history.

## System Architecture

### Agent Tool System
- **Sandbox Protection**: All file paths are normalized and validated, access to directories outside workspace is prohibited
- **Blacklist Mechanism**: Dangerous commands (like rm, del, format, etc.) are blocked
- **Whitelist Mechanism**: Only predefined read-only commands are allowed

### TTS Streaming (Important)
- **No longer pre-loading all audio**, changed to segment-by-segment background preloading
- `prepareNextAudio(index)`: Preloads 3 segments starting from current position in background
- `processNextSequenceItem()`: Sends next TTS request in parallel while playing current segment
- **Expression synced with first character**: Expression triggers when first character appears, not after "思考中..."
- **Timeout/failure handling**: `ttsFailedTexts` Set records failed texts, display text without voice
- **Text length limit**: Backend limits 500 characters, returns error if exceeded
- TTS service address: `ws://127.0.0.1:9880`

### Dialogue Sequence Segmentation
- Segmentation by **emotion tags `[xxx]`**, new segment starts when encountering a new tag
- Valid tags: `祈祷`(pray), `发光`(glow), `翻花绳`(jumprope), `好奇`(curious), `泪`(tears), `脸黑`(dark face), `脸红`(blush), `生气`(angry), `星星`(stars)
- Invalid tags are displayed as plain text

### RAG System
- **Retrieval Engine**: Uses ChromaDB to store and retrieve dialogue history and knowledge base
- **Query Processing**: Supports query expansion, generating multiple variants to improve retrieval coverage
- **Reranking**: Uses BGE Reranker to rerank retrieval results
- **GPU Memory**: Automatically unloads embedding/reranker models after Agent session ends to free VRAM

## Notes

- If Live2D model fails to load, will try to load a backup model
- Ensure stable network connection to load necessary JavaScript libraries
- Make sure to fill in the correct Deepseek API key in the `.env` file
- Make sure the python runtime in GSV/api.bat is either the runtime that comes with GSV or your system's default python environment
- First run will download RAG system model files (several hundred MB)
- In Agent mode, please confirm the path is correct before deleting files, deleted files cannot be recovered

## File Structure

- `app.py`: Main application file, contains core logic for routing, TTS, streaming response, Agent loop, etc.
- `tools.py`: Agent tool system, implements file operations, command execution, and other tool functions
- `memory.py`: Memory system, manages core memory files and dialogue logs
- `rag.py`: RAG retrieval system, provides context retrieval, query expansion, reranking
- `templates/index.html`: Frontend page
- `static/style.css`: Page styles (includes history panel styles)
- `static/js/script.js`: Frontend interaction, streaming response handling, and Live2D control logic
- `workspace/`: Sandbox directory for Agent mode file operations
- `knowledge/MEMORY.md`: Core memory file
- `knowledge/memory_*.txt`: Daily dialogue logs
- `.env`: Environment variable configuration (needs manual creation)
