from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
HISTORY_DIR = BASE_DIR / "history"
LOG_DIR = BASE_DIR / "log"


def ensure_memory_file():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _match_query(query: str, text: str) -> bool:
    query = query.lower().strip()
    text = text.lower()
    
    if query in text:
        return True
    
    query_words = re.findall(r'[\w\u4e00-\u9fa5]+', query)
    if len(query_words) > 1:
        return all(word in text for word in query_words)
    
    return False


def memory_recall(query: str, category: str = None, scope: str = "all") -> Dict[str, Any]:
    ensure_memory_file()

    categories = [category] if category else ["人物", "事件", "常识", "其他"]
    results = []

    for cat in categories:
        json_file = MEMORY_DIR / f"{cat}.json"
        if not json_file.exists():
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        def search_recursive(key_prefix: str, value: Any, depth: int = 0):
            if depth > 3:
                return
            
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    full_key = f"{key_prefix}.{sub_key}" if key_prefix else sub_key
                    search_recursive(full_key, sub_value, depth + 1)
            elif isinstance(value, (str, int, float, bool)):
                value_str = json.dumps(value, ensure_ascii=False)
                if _match_query(query, key_prefix) or _match_query(query, value_str):
                    if scope == "parent":
                        results.append({cat: key_prefix.split(".")[0] if "." in key_prefix else key_prefix})
                    else:
                        results.append({cat: {key_prefix: value}})

        for key, value in data.items():
            search_recursive(key, value)

    return {
        "success": True, 
        "query": query, 
        "results": results, 
        "count": len(results),
        "scope": scope
    }


def memory_save(category: str, key: str, value: Any, sub_key: str = None) -> Dict[str, Any]:
    if category not in ["人物", "事件", "常识", "其他"]:
        return {"success": False, "error": f"无效分类: {category}"}

    ensure_memory_file()
    json_file = MEMORY_DIR / f"{category}.json"

    data = {}
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    updated = False
    full_path = [key]
    if sub_key:
        full_path.extend(sub_key.split("/"))
    
    current = data
    for i, part in enumerate(full_path[:-1]):
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    
    final_key = full_path[-1]
    if final_key in current:
        old_value = current[final_key]
        current[final_key] = value
        updated = True
    else:
        current[final_key] = value

    json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return {
        "success": True, 
        "category": category, 
        "key": key, 
        "sub_key": sub_key, 
        "saved": value,
        "path": "/".join(full_path),
        "action": "updated" if updated else "created"
    }


def memory_list(category: str = None, detail_level: str = "summary") -> Dict[str, Any]:
    ensure_memory_file()
    
    categories = [category] if category else ["人物", "事件", "常识", "其他"]
    result = {}
    
    for cat in categories:
        json_file = MEMORY_DIR / f"{cat}.json"
        if not json_file.exists():
            result[cat] = {"count": 0, "keys": []}
            continue
        
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result[cat] = {"count": 0, "keys": [], "error": "文件解析失败"}
            continue
        
        keys = list(data.keys())
        
        if detail_level == "summary":
            result[cat] = {
                "count": len(keys),
                "keys": keys[:20]
            }
        elif detail_level == "full":
            result[cat] = {
                "count": len(keys),
                "keys": keys[:20],
                "data": {k: v for k, v in list(data.items())[:10]}
            }
    
    return {
        "success": True,
        "categories": result,
        "total": sum(v.get("count", 0) for v in result.values())
    }


def memory_delete(category: str, key: str, sub_key: str = None) -> Dict[str, Any]:
    if category not in ["人物", "事件", "常识", "其他"]:
        return {"success": False, "error": f"无效分类: {category}"}

    ensure_memory_file()
    json_file = MEMORY_DIR / f"{category}.json"
    
    if not json_file.exists():
        return {"success": False, "error": f"分类 {category} 的记忆文件不存在"}

    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"success": False, "error": "记忆文件解析失败"}

    full_path = [key]
    if sub_key:
        full_path.extend(sub_key.split("/"))
    
    current = data
    for part in full_path[:-1]:
        if part not in current:
            return {"success": False, "error": f"记忆不存在: {'/'.join(full_path)}"}
        current = current[part]
    
    final_key = full_path[-1]
    if final_key not in current:
        return {"success": False, "error": f"记忆不存在: {'/'.join(full_path)}"}
    
    deleted_value = current.pop(final_key)
    
    parent = data
    for part in full_path[:-2]:
        parent = parent[part]
    if not parent[full_path[-2]]:
        del parent[full_path[-2]]

    json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return {
        "success": True,
        "category": category,
        "key": key,
        "sub_key": sub_key,
        "path": "/".join(full_path),
        "deleted": deleted_value
    }
