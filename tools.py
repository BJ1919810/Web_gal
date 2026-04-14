import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True)

COMMAND_BLACKLIST = {
    "rm", "del", "rmdir", "format", "fdisk", "diskpart",
    "mkfs", "dd", "shutdown", "reboot", "halt", "poweroff",
    "init", "systemctl stop", "service stop", "kill", "pkill",
    "curl", "wget", "ssh", "scp", "sftp", "ftp", "telnet",
    "reg", "regedit", "gpedit.msc", "lusrmgr.msc",
    ":", ">", "<", "|", "&", ";", "`", "$(", "${",
}

COMMAND_WHITELIST = {
    "dir", "type", "echo", "cd", "pwd", "mkdir", "copy", "move",
    "ls", "cd", "cp", "mv", "mkdir", "cat", "find", "grep",
    "whoami", "hostname", "date", "time", "tree", "sort",
    "head", "tail", "wc", "diff",
}

RAG_AVAILABLE = False
RAG_SEARCH_FUNC = None

try:
    from rag import init_rag, search_context
    RAG_AVAILABLE = True
    RAG_SEARCH_FUNC = search_context
except ImportError:
    pass

def _is_safe_path(path: str) -> bool:
    try:
        abs_path = Path(path).resolve()
        workspace_abs = WORKSPACE_DIR.resolve()
        return str(abs_path).startswith(str(workspace_abs))
    except Exception:
        return False

def _sanitize_path(path: str) -> str:
    path = path.strip().replace("..", "")
    if not path.startswith("/") and ":" not in path:
        return str(WORKSPACE_DIR / path)
    if _is_safe_path(path):
        return path
    return str(WORKSPACE_DIR / Path(path).name)

def read_file(path: str) -> Dict[str, Any]:
    safe_path = _sanitize_path(path)
    if not _is_safe_path(safe_path):
        return {"success": False, "error": "路径访问被拒绝：禁止访问 workspace 目录以外的文件"}
    try:
        file_path = Path(safe_path)
        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {path}"}
        if not file_path.is_file():
            return {"success": False, "error": f"路径不是文件: {path}"}
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_bytes().decode("utf-8", errors="replace")
        return {"success": True, "content": content, "path": str(file_path)}
    except Exception as exc:
        return {"success": False, "error": f"读取失败: {exc}"}

def write_file(path: str, content: str, append: bool = False) -> Dict[str, Any]:
    safe_path = _sanitize_path(path)
    if not safe_path.startswith(str(WORKSPACE_DIR.resolve())):
        return {"success": False, "error": "路径访问被拒绝：禁止在 workspace 目录以外写入文件"}
    try:
        file_path = Path(safe_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if append and file_path.exists():
            file_path.write_text(file_path.read_text(encoding="utf-8") + content, encoding="utf-8")
        else:
            file_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(file_path), "action": "append" if append else "write"}
    except Exception as exc:
        return {"success": False, "error": f"写入失败: {exc}"}

def delete_file(path: str) -> Dict[str, Any]:
    safe_path = _sanitize_path(path)
    if not _is_safe_path(safe_path):
        return {"success": False, "error": "路径访问被拒绝：禁止删除 workspace 目录以外的文件"}
    try:
        file_path = Path(safe_path)
        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {path}"}
        if file_path.is_dir():
            import shutil
            shutil.rmtree(file_path)
        else:
            file_path.unlink()
        return {"success": True, "path": str(file_path)}
    except Exception as exc:
        return {"success": False, "error": f"删除失败: {exc}"}

def list_directory(path: str = ".") -> Dict[str, Any]:
    safe_path = _sanitize_path(path)
    if not _is_safe_path(safe_path):
        return {"success": False, "error": "路径访问被拒绝：禁止访问 workspace 目录以外的位置"}
    try:
        dir_path = Path(safe_path)
        if not dir_path.exists():
            return {"success": False, "error": f"目录不存在: {path}"}
        if not dir_path.is_dir():
            return {"success": False, "error": f"路径不是目录: {path}"}
        items = []
        for item in sorted(dir_path.iterdir()):
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
        return {"success": True, "path": str(dir_path), "items": items}
    except Exception as exc:
        return {"success": False, "error": f"列出目录失败: {exc}"}

def search_files(directory: str, pattern: str, file_pattern: str = "*") -> Dict[str, Any]:
    safe_path = _sanitize_path(directory)
    if not _is_safe_path(safe_path):
        return {"success": False, "error": "路径访问被拒绝"}
    try:
        dir_path = Path(safe_path)
        if not dir_path.exists() or not dir_path.is_dir():
            return {"success": False, "error": f"目录不存在: {directory}"}
        results = []
        regex = re.compile(pattern) if pattern else None
        for file_path in dir_path.rglob(file_pattern):
            if file_path.is_file():
                if regex:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        if regex.search(content):
                            results.append({
                                "path": str(file_path.relative_to(dir_path)),
                                "name": file_path.name,
                            })
                    except Exception:
                        pass
                else:
                    results.append({
                        "path": str(file_path.relative_to(dir_path)),
                        "name": file_path.name,
                    })
        return {"success": True, "path": str(dir_path), "pattern": pattern, "results": results[:50]}
    except Exception as exc:
        return {"success": False, "error": f"搜索失败: {exc}"}


def rag_search(query: str, search_type: str = "all") -> Dict[str, Any]:
    if not RAG_AVAILABLE or RAG_SEARCH_FUNC is None:
        return {"success": False, "error": "RAG系统不可用"}
    try:
        init_rag()
        dialogue_k = 3 if search_type in ("all", "dialogue") else 0
        knowledge_k = 4 if search_type in ("all", "knowledge") else 0
        result = RAG_SEARCH_FUNC(
            query,
            dialogue_top_k=dialogue_k,
            knowledge_top_k=knowledge_k,
        )

        output = {
            "success": True,
            "query": query,
            "query_variants": result.get("query_variants", []),
        }

        if result.get("old_dialogue"):
            output["old_dialogue"] = [
                {"source": item.get("source"), "content": item.get("content")}
                for item in result["old_dialogue"]
            ]
        if result.get("knowledge"):
            output["knowledge"] = [
                {"source": item.get("source"), "content": item.get("content")}
                for item in result["knowledge"]
            ]
        return output
    except Exception as exc:
        return {"success": False, "error": f"RAG搜索失败: {exc}"}

def execute_command(command: str, working_dir: Optional[str] = None) -> Dict[str, Any]:
    original_cmd = command.strip()
    cmd_lower = original_cmd.lower()

    for black_cmd in COMMAND_BLACKLIST:
        if re.search(rf"\b{re.escape(black_cmd)}\b", cmd_lower):
            return {"success": False, "error": f"命令被黑名单拦截: {black_cmd}", "blocked": True}

    safe_path = working_dir if working_dir else str(WORKSPACE_DIR)
    if not _is_safe_path(safe_path):
        safe_path = str(WORKSPACE_DIR)

    try:
        result = subprocess.run(
            original_cmd,
            shell=True,
            cwd=safe_path,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout if result.stdout else result.stderr
        return {
            "success": result.returncode == 0,
            "command": original_cmd,
            "output": output[:5000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "命令执行超时（30秒）"}
    except Exception as exc:
        return {"success": False, "error": f"执行失败: {exc}"}

TOOLS = {
    "read_file": {
        "name": "read_file",
        "description": "读取文件内容",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径，相对于 workspace",
                }
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "创建或写入文件，自动创建父目录",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径，相对于 workspace",
                },
                "content": {
                    "type": "string",
                    "description": "文件内容",
                },
                "append": {
                    "type": "boolean",
                    "description": "追加模式，否则覆盖",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        },
    },
    "delete_file": {
        "name": "delete_file",
        "description": "删除文件或目录，删除后无法恢复",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件或目录路径，相对于 workspace",
                },
            },
            "required": ["path"],
        },
    },
    "list_directory": {
        "name": "list_directory",
        "description": "列出目录内容",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径，相对于 workspace，默认为根目录",
                    "default": ".",
                },
            },
        },
    },
    "search_files": {
        "name": "search_files",
        "description": "搜索文件或内容，支持正则表达式",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "搜索目录，相对于 workspace",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "搜索内容（正则表达式），留空则只按 file_pattern 过滤",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件名匹配模式，如 '*.py'",
                    "default": "*",
                },
            },
        },
    },
    "rag_search": {
        "name": "rag_search",
        "description": "搜索知识库和对话历史",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询",
                },
                "search_type": {
                    "type": "string",
                    "description": "搜索范围：all/knowledge/dialogue",
                    "enum": ["all", "knowledge", "dialogue"],
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    },
    "execute_command": {
        "name": "execute_command",
        "description": "执行系统命令，仅限只读操作（危险操作已被拦截）",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令",
                },
                "working_dir": {
                    "type": "string",
                    "description": "工作目录，默认为 workspace",
                },
            },
            "required": ["command"],
        },
    },
}

TOOL_FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "delete_file": delete_file,
    "list_directory": list_directory,
    "search_files": search_files,
    "rag_search": rag_search,
    "execute_command": execute_command,
}

def get_tools_schema() -> List[Dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in TOOLS.values()
    ]

def call_tool_function(tool_name: str, arguments: Dict[str, Any]) -> Any:
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return {"success": False, "error": f"未知工具: {tool_name}"}
    try:
        return func(**arguments)
    except TypeError as exc:
        return {"success": False, "error": f"工具调用参数错误: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"工具执行失败: {exc}"}
