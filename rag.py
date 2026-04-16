from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
from modelscope.hub.snapshot_download import snapshot_download
from sentence_transformers import CrossEncoder, SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CHROMA_DIR = BASE_DIR / "chroma_db"
HASH_FILE = KNOWLEDGE_DIR / ".hash.json"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
RERANK_MODEL = "BAAI/bge-reranker-base"
MEMORY_MD_NAME = "MEMORY.md"


class RAGSystem:
    def __init__(self, knowledge_dir: Path = KNOWLEDGE_DIR):
        self.knowledge_dir = Path(knowledge_dir)
        self.embedding_model: Optional[SentenceTransformer] = None
        self.reranker: Optional[CrossEncoder] = None
        self.chroma_client = None
        self.collection = None
        self.initialized = False

    def _iter_knowledge_files(self) -> List[Path]:
        if not self.knowledge_dir.is_dir():
            return []
        files = []
        for path in sorted(self.knowledge_dir.iterdir(), key=lambda p: p.name):
            if not path.is_file():
                continue
            if path.name == ".hash.json":
                continue
            if path.suffix not in {".txt", ".md", ".json"}:
                continue
            if path.name == MEMORY_MD_NAME:
                continue
            files.append(path)
        return files

    @staticmethod
    def _file_source_type(filename: str) -> str:
        if re.fullmatch(r"dialogue_\d{4}-\d{2}-\d{2}\.txt", filename):
            return "dialogue"
        return "knowledge"

    def compute_hash(self):
        all_content = []
        file_hashes = {}
        for path in self._iter_knowledge_files():
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                content = ""
            all_content.append(f"##FILE={path.name}\n{content}\n")
            file_hashes[path.name] = hashlib.md5(content.encode("utf-8")).hexdigest()
        all_text = "\n".join(all_content)
        return hashlib.md5(all_text.encode("utf-8")).hexdigest(), file_hashes

    def save_hash(self, knowledge_hash: str, file_hashes: Dict[str, str]):
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        HASH_FILE.write_text(
            json.dumps({"knowledge_hash": knowledge_hash, "file_hashes": file_hashes}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_hash(self) -> Optional[str]:
        if not HASH_FILE.exists():
            return None
        try:
            data = json.loads(HASH_FILE.read_text(encoding="utf-8"))
            return data.get("knowledge_hash")
        except Exception:
            return None

    def needs_rebuild(self) -> bool:
        current_hash, _ = self.compute_hash()
        saved_hash = self.load_hash()
        if saved_hash is None:
            print("[RAG] 首次构建知识库")
            return True
        if current_hash != saved_hash:
            print(f"[RAG] 知识库已更新: {saved_hash[:8]} -> {current_hash[:8]}")
            return True
        return False

    def _load_models(self):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        embedding_path = MODEL_DIR / "paraphrase-multilingual-MiniLM-L12-v2"
        if embedding_path.exists():
            self.embedding_model = SentenceTransformer(str(embedding_path))
        else:
            local_dir = snapshot_download(EMBEDDING_MODEL, cache_dir=str(MODEL_DIR))
            self.embedding_model = SentenceTransformer(local_dir)

        rerank_path = MODEL_DIR / "bge-reranker-base"
        if rerank_path.exists():
            self.reranker = CrossEncoder(str(rerank_path))
        else:
            local_dir = snapshot_download(RERANK_MODEL, cache_dir=str(MODEL_DIR))
            self.reranker = CrossEncoder(local_dir)

    def init(self):
        if self.initialized:
            return
        self._load_models()
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        if self.needs_rebuild():
            self.rebuild_index()
        else:
            try:
                self.collection = self.chroma_client.get_collection("knowledge")
                print("[RAG] 已加载现有知识库")
            except Exception:
                self.collection = self.chroma_client.create_collection("knowledge", metadata={"hnsw:space": "cosine"})
                self.build_index()
        self.initialized = True

    def unload_models(self):
        if self.embedding_model is not None:
            del self.embedding_model
            self.embedding_model = None
            print("[RAG] 卸载 embedding 模型")
        if self.reranker is not None:
            del self.reranker
            self.reranker = None
            print("[RAG] 卸载 reranker 模型")
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                print("[RAG] 清理 CUDA 缓存")
        except Exception:
            pass

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        parts = re.split(r"(?<=[。！？!?])|\n+", text)
        return [p.strip() for p in parts if p and p.strip()]

    def semantic_chunk(self, text: str, *, max_sentences: int = 6, max_chars: int = 520) -> List[str]:
        sentences = self.split_sentences(text)
        if not sentences:
            return []
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        for sent in sentences:
            sent_len = len(sent)
            if current and (len(current) >= max_sentences or current_len + sent_len > max_chars):
                chunks.append("\n".join(current).strip())
                current = []
                current_len = 0
            current.append(sent)
            current_len += sent_len
        if current:
            chunks.append("\n".join(current).strip())
        return chunks

    def build_index(self):
        documents: List[str] = []
        ids: List[str] = []
        metadatas: List[Dict] = []

        for path in self._iter_knowledge_files():
            content = path.read_text(encoding="utf-8")
            chunks = self.semantic_chunk(content)
            source_type = self._file_source_type(path.name)
            for idx, chunk in enumerate(chunks):
                documents.append(chunk)
                ids.append(f"{path.name}#{idx}")
                metadatas.append(
                    {
                        "source": path.name,
                        "chunk_id": idx,
                        "source_type": source_type,
                    }
                )

        if not documents:
            print("[RAG] 知识库为空")
            return

        print(f"[RAG] 正在写入 {len(documents)} 个知识块")
        embeddings = self.embedding_model.encode(documents, normalize_embeddings=True)
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )
        current_hash, file_hashes = self.compute_hash()
        self.save_hash(current_hash, file_hashes)
        print("[RAG] 知识库构建完成")

    def rebuild_index(self):
        try:
            self.chroma_client.delete_collection("knowledge")
        except Exception:
            pass
        self.collection = self.chroma_client.create_collection("knowledge", metadata={"hnsw:space": "cosine"})
        self.build_index()

    @staticmethod
    def expand_query(query: str) -> List[str]:
        base = query.strip()
        if not base:
            return []
        variants = [base]
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", base).strip()
        if cleaned and cleaned != base:
            variants.append(cleaned)
        squashed = cleaned.replace(" ", "") if cleaned else ""
        if squashed and squashed not in variants:
            variants.append(squashed)
        unique: List[str] = []
        seen = set()
        for item in variants:
            if item and item not in seen:
                unique.append(item)
                seen.add(item)
        return unique

    def _query_collection(self, query_variants: List[str], n_results: int = 16) -> List[Dict]:
        if not query_variants:
            return []
        query_embeddings = self.embedding_model.encode(query_variants, normalize_embeddings=True).tolist()
        results = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            include=["documents", "distances", "metadatas"],
        )
        merged: Dict[str, Dict] = {}
        documents = results.get("documents", [])
        distances = results.get("distances", [])
        metadatas = results.get("metadatas", [])
        for i in range(len(documents)):
            for j in range(len(documents[i])):
                metadata = metadatas[i][j] or {}
                source = metadata.get("source", "unknown")
                chunk_id = metadata.get("chunk_id", j)
                key = f"{source}#{chunk_id}"
                distance = float(distances[i][j])
                if key not in merged or distance < merged[key]["distance"]:
                    merged[key] = {
                        "content": documents[i][j],
                        "distance": distance,
                        "source": source,
                        "chunk_id": chunk_id,
                        "source_type": metadata.get("source_type", "knowledge"),
                    }
        return sorted(merged.values(), key=lambda x: x["distance"])

    def _rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        if len(candidates) <= 1:
            return candidates
        pairs = [[query, item["content"]] for item in candidates]
        try:
            scores = self.reranker.predict(pairs)
            for item, score in zip(candidates, scores):
                item["rerank_score"] = float(score)
            candidates.sort(key=lambda x: (x.get("rerank_score", -1e9), -x["distance"]), reverse=True)
        except Exception as exc:
            print(f"[RAG] 重排序失败，回退为向量距离排序: {exc}")
        return candidates

    @staticmethod
    def _bucket_results(results: List[Dict], dialogue_top_k: int, knowledge_top_k: int) -> Dict[str, List[Dict]]:
        old_dialogue = [r for r in results if r.get("source_type") == "dialogue"][: max(dialogue_top_k, 0)]
        knowledge = [r for r in results if r.get("source_type") == "knowledge"][: max(knowledge_top_k, 0)]
        return {"old_dialogue": old_dialogue, "knowledge": knowledge, "all": old_dialogue + knowledge}

    def _supplement_by_type(self, query_variants: List[str], source_type: str, need_count: int) -> List[Dict]:
        if need_count <= 0:
            return []
        candidates = self._query_collection(query_variants, n_results=max(need_count * 4, 8))
        return [c for c in candidates if c.get("source_type") == source_type][:need_count]

    def search_context(self, query: str, dialogue_top_k: int = 3, knowledge_top_k: int = 4) -> Dict[str, List[Dict]]:
        self.init()
        if self.needs_rebuild():
            self.rebuild_index()

        query_variants = self.expand_query(query)
        if dialogue_top_k <= 0 and knowledge_top_k <= 0:
            return {"old_dialogue": [], "knowledge": [], "all": [], "query_variants": query_variants}

        total_needed = max(dialogue_top_k, 0) + max(knowledge_top_k, 0)
        candidates = self._query_collection(query_variants, n_results=max(total_needed * 4, 12))
        candidates = self._rerank(query, candidates)
        bucketed = self._bucket_results(candidates, dialogue_top_k, knowledge_top_k)

        if len(bucketed["old_dialogue"]) < max(dialogue_top_k, 0):
            extra = self._supplement_by_type(query_variants, "dialogue", dialogue_top_k - len(bucketed["old_dialogue"]))
            existing = {f"{item['source']}#{item['chunk_id']}" for item in bucketed["old_dialogue"]}
            for item in extra:
                key = f"{item['source']}#{item['chunk_id']}"
                if key not in existing:
                    bucketed["old_dialogue"].append(item)
                    existing.add(key)

        if len(bucketed["knowledge"]) < max(knowledge_top_k, 0):
            extra = self._supplement_by_type(query_variants, "knowledge", knowledge_top_k - len(bucketed["knowledge"]))
            existing = {f"{item['source']}#{item['chunk_id']}" for item in bucketed["knowledge"]}
            for item in extra:
                key = f"{item['source']}#{item['chunk_id']}"
                if key not in existing:
                    bucketed["knowledge"].append(item)
                    existing.add(key)

        bucketed["all"] = bucketed["old_dialogue"] + bucketed["knowledge"]
        bucketed["query_variants"] = query_variants
        return bucketed

    def search_knowledge(self, query: str, top_k: int = 7) -> List[Dict]:
        context = self.search_context(query, dialogue_top_k=min(2, top_k), knowledge_top_k=top_k)
        return context["all"][:top_k]


rag_system = RAGSystem()


def init_rag():
    rag_system.init()


def search_context(query: str, dialogue_top_k: int = 3, knowledge_top_k: int = 4):
    return rag_system.search_context(query, dialogue_top_k=dialogue_top_k, knowledge_top_k=knowledge_top_k)


def search_knowledge(query: str, top_k: int = 7):
    return rag_system.search_knowledge(query, top_k=top_k)


def unload_rag():
    rag_system.unload_models()
