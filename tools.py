import html
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)

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
    from rag import init_rag, search_context, add_documents
    RAG_AVAILABLE = True
    RAG_SEARCH_FUNC = search_context
    RAG_ADD_DOCS_FUNC = add_documents
except ImportError:
    pass

MEMORY_AVAILABLE = False
MEMORY_RECALL_FUNC = None
MEMORY_SAVE_FUNC = None

try:
    from memory import memory_recall, memory_save, memory_list, memory_delete
    MEMORY_AVAILABLE = True
    MEMORY_RECALL_FUNC = memory_recall
    MEMORY_SAVE_FUNC = memory_save
    MEMORY_LIST_FUNC = memory_list
    MEMORY_DELETE_FUNC = memory_delete
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
    if path.startswith("memory/") or path.startswith("memory\\"):
        return str(MEMORY_DIR / path[7:])
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
    if not safe_path.startswith(str(WORKSPACE_DIR.resolve())) and not safe_path.startswith(str(MEMORY_DIR.resolve())):
        return {"success": False, "error": "路径访问被拒绝：禁止在 workspace 或 memory 目录以外写入文件"}
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


def rag_search(query: str, search_type: str = "all", scope: str = None) -> Dict[str, Any]:
    if not RAG_AVAILABLE or RAG_SEARCH_FUNC is None:
        return {"success": False, "error": "RAG系统不可用"}
    try:
        init_rag()

        if scope:
            scope_path = Path(scope)
            if scope_path.is_dir():
                files = [p for p in scope_path.iterdir() if p.is_file() and p.suffix in {".txt", ".md", ".json"}]
            elif scope_path.is_file():
                files = [scope_path]
            else:
                return {"success": False, "error": f"路径不存在: {scope}"}
            
            if files and RAG_ADD_DOCS_FUNC:
                add_result = RAG_ADD_DOCS_FUNC(files)
            else:
                add_result = {"indexed": 0}
        else:
            add_result = {"indexed": 0}

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
            "dynamic_indexed": add_result.get("indexed", 0),
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
        
        if add_result.get("indexed", 0) > 0:
            output["note"] = "新文档已加入索引，请根据内容提取重要信息并调用memory_save保存为长期记忆。"
        
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

def web_fetch(url: str) -> Dict[str, Any]:
    """获取网页内容并返回。如果是文件URL则下载到workspace。"""
    try:
        import requests
        from urllib.parse import urlparse
        from pathlib import Path

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 1000:
                safe_name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', Path(parsed.path).stem)[:50]
                filename = f"{safe_name}{ext}"
                filepath = WORKSPACE_DIR / filename
                filepath.write_bytes(resp.content)
                return {"success": True, "type": "file", "path": str(filepath), "message": f"已下载到 {filepath}"}
            return {"success": False, "error": f"下载失败，状态码: {resp.status_code}"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            content = resp.text[:8000]
            return {"success": True, "type": "html", "url": url, "content": content}
        return {"success": False, "error": f"请求失败，状态码: {resp.status_code}"}
    except Exception as exc:
        return {"success": False, "error": f"获取失败: {exc}"}

def web_search(query: str, search_type: str = "general", num_results: int = 5, size: str = "medium") -> Dict[str, Any]:
    """搜索网络获取信息。图片搜索会下载图片到 workspace/images/"""
    size_filter = {"small": "filterui:imagesize-small", "medium": "filterui:imagesize-medium", "large": "filterui:imagesize-large", "wallpaper": "filterui:imagesize-wallpaper"}.get(size, "")
    try:
        import requests
        from urllib.parse import quote, urlparse
        from ddgs import DDGS

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        if search_type == "image":
            images_dir = WORKSPACE_DIR / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', query)[:50]
            saved_paths = []
            thumbnail_keywords = ["th.jpg", "th.png", "thumbs", "thumbnail", "/small/", "/preview/", "/thumb/", "_th.", "-th."]
            page_size = 50
            pages_needed = (num_results + page_size - 1) // page_size
            all_urls = []
            for page in range(pages_needed):
                first_idx = page * page_size + 1
                q = quote(query)
                if size_filter:
                    page_url = f"https://cn.bing.com/images/search?q={q}&qft={size_filter}&first={first_idx}&count={page_size}"
                else:
                    page_url = f"https://cn.bing.com/images/search?q={q}&first={first_idx}&count={page_size}"
                try:
                    resp = requests.get(page_url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        m_attrs = re.findall(r'm="([^"]+)"', resp.text)
                        for m_val in m_attrs:
                            try:
                                unescaped = html.unescape(m_val)
                                m_data = json.loads(unescaped)
                                murl = m_data.get("murl", "") if isinstance(m_data, dict) else ""
                                if murl and murl.startswith("http") and len(murl) > 20:
                                    if not any(kw in murl.lower() for kw in thumbnail_keywords):
                                        all_urls.append(murl)
                            except Exception:
                                continue
                    if len(all_urls) >= num_results:
                        break
                except Exception:
                    continue
            all_urls = list(dict.fromkeys(all_urls))[:num_results]
            for i, img_url in enumerate(all_urls):
                try:
                    img_resp = requests.get(img_url, headers=headers, timeout=15, allow_redirects=True)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        ext = re.search(r'\.(jpg|jpeg|png|gif|webp|bmp)', img_url, re.I)
                        ext = ext.group(1) if ext else 'jpg'
                        filename = f"{safe_name}_{i+1}.{ext}"
                        filepath = images_dir / filename
                        filepath.write_bytes(img_resp.content)
                        saved_paths.append(str(filepath))
                except Exception:
                    continue
            return {
                "success": True,
                "query": query,
                "type": "image",
                "saved": saved_paths,
                "count": len(saved_paths),
                "message": f"已下载 {len(saved_paths)} 张图片到 workspace/images/" if saved_paths else "未找到图片"
            }

        if search_type == "news":
            try:
                with DDGS() as ddgs:
                    results = []
                    for r in ddgs.news(query, max_results=num_results):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "date": r.get("date", ""),
                            "body": r.get("body", "")[:200]
                        })
                    return {
                        "success": True,
                        "query": query,
                        "type": "news",
                        "results": results,
                        "message": f"找到 {len(results)} 条新闻"
                    }
            except ImportError:
                return {"success": False, "error": "需要安装 duckduckgo-search: pip install duckduckgo-search"}
            except Exception as exc:
                return {"success": False, "error": f"新闻搜索失败: {exc}"}

        try:
            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query, max_results=num_results):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")[:300]
                    })
                return {
                    "success": True,
                    "query": query,
                    "type": "general",
                    "results": results,
                    "message": f"找到 {len(results)} 条结果"
                }
        except ImportError:
            return {"success": False, "error": "需要安装 duckduckgo-search: pip install duckduckgo-search"}
        except Exception as exc:
            return {"success": False, "error": f"搜索失败: {exc}"}

    except ImportError:
        return {"success": False, "error": "web_search功能需要安装requests库，请运行: pip install requests"}
    except Exception as exc:
        return {"success": False, "error": f"搜索失败: {exc}"}

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
        "description": "搜索知识库和对话历史。"
        "如有可记录的信息，请额外调用memory_save工具将重要信息保存到长期记忆中。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询",
                },
                "search_type": {
                    "type": "string",
                    "description": "搜索类型：all（全部）/ dialogue（仅对话）/ knowledge（仅知识库）",
                    "enum": ["all", "dialogue", "knowledge"],
                    "default": "all",
                },
                "scope": {
                    "type": "string",
                    "description": "搜索范围：可为具体文件路径或文件夹路径。若提供，会先将该文件/文件夹中的文档动态索引后再搜索。留空则搜索已有索引。",
                    "default": None,
                },
            },
            "required": ["query"],
        },
    },
    "memory_list": {
        "name": "memory_list",
        "description": "列出所有记忆分类和 key，了解已有哪些记忆。"
        "使用场景：用户问'还记得...吗'或询问是否有相关记忆时先调用此工具查看已有记忆主条目，再决定下一步。"
        "保持角色沉浸感：调用时说'让我翻翻小本本'或'让我想想'。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "指定分类：人物/事件/常识/其他，为空则列出所有",
                },
                "detail_level": {
                    "type": "string",
                    "description": "详细程度：summary（只看key列表）/ full（包含部分内容）",
                    "enum": ["summary", "full"],
                    "default": "summary",
                },
            },
        },
    },
    "memory_delete": {
        "name": "memory_delete",
        "description": "删除过时或错误的记忆条目。"
        "使用场景：信息过期、用户纠正错误、重复冗余时清理。"
        "保持角色沉浸感：调用时说'这条旧信息我清理掉啦'。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "分类：人物/事件/常识/其他",
                    "enum": ["人物", "事件", "常识", "其他"],
                },
                "key": {
                    "type": "string",
                    "description": "要删除的主 key",
                },
                "sub_key": {
                    "type": "string",
                    "description": "要删除的子 key（可选）",
                },
            },
            "required": ["category", "key"],
        },
    },
    "memory_recall": {
        "name": "memory_recall",
        "description": "查询本地结构化记忆（memory/），快速 grep JSON。"
        "使用场景：用户提供具体名字/关键词时用此工具查询。"
        "若未指定具体主体，则优先使用memory_list工具列出所有记忆主条目。"
        "保持角色沉浸感：调用时说'让我想想'或'让我仔细回想一下'。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，匹配 key 或 value",
                },
                "category": {
                    "type": "string",
                    "description": "指定分类：人物/事件/常识/其他，为空则搜索全部",
                },
                "scope": {
                    "type": "string",
                    "description": "返回范围：all（完整条目）/ parent（只返回 key）",
                    "enum": ["all", "parent"],
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    },
    "memory_save": {
        "name": "memory_save",
        "description": "识别到需要或值得记录的信息后，保存记忆到本地 JSON 文件，自动创建父条目。"
        "必须保存的情况：除用户外其他人的个人信息（姓名/年龄/职业）、偏好需求、约定决定、重要事项。"
        "注意：若是用户本人的信息（个人资料、长期偏好、约定决定、重要事项），请使用write_file工具更新memory/PROFILE.md文件，不要使用此工具。"
        "保持角色沉浸感：调用时说'让我记下来'或'这个我得好好记住'。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "分类：人物/事件/常识/其他",
                    "enum": ["人物", "事件", "常识", "其他"],
                },
                "key": {
                    "type": "string",
                    "description": "记忆主 key（如人物名、事件名）",
                },
                "value": {
                    "type": "string",
                    "description": "记忆内容",
                },
                "sub_key": {
                    "type": "string",
                    "description": "子 key（如‘身份证’、‘社交账户’），用于嵌套结构",
                },
            },
            "required": ["category", "key", "value"],
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
    "web_search": {
        "name": "web_search",
        "description": "搜索网络获取大致信息。"
        "使用场景：需要查询实时信息、新闻、天气预报、百科知识等网络资源时使用。"
        "配合web_fetch工具可以获取详细内容。"
        "图片搜索会下载图片到 workspace/images/ 目录，下载完成后直接说‘图片已下载’，无需一一列出。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "search_type": {
                    "type": "string",
                    "description": "搜索类型：general（通用搜索）/ news（新闻）/ image（图片）",
                    "enum": ["general", "news", "image"],
                    "default": "general",
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认5条",
                    "default": 5,
                },
                "size": {
                    "type": "string",
                    "description": "图片尺寸：small / medium / large / wallpaper（仅图片搜索有效）",
                    "enum": ["small", "medium", "large", "wallpaper"],
                    "default": "medium",
                },
            },
            "required": ["query"],
        },
    },
    "web_fetch": {
        "name": "web_fetch",
        "description": "获取指定URL的网页内容。如果是图片文件则下载到workspace。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的网页或文件URL",
                },
            },
            "required": ["url"],
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
    "memory_recall": memory_recall,
    "memory_save": memory_save,
    "memory_list": memory_list,
    "memory_delete": memory_delete,
    "execute_command": execute_command,
    "web_search": web_search,
    "web_fetch": web_fetch,
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
