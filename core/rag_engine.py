# -*- coding: utf-8 -*-
"""
RAG (Retrieval-Augmented Generation) 知识库引擎
为大学心理辅导AI平台设计的优化检索增强生成系统

包含：
- HybridRetriever: 混合检索器（向量 + BM25 + 新鲜度）
- KnowledgeBaseManager: 知识库管理器（文档加载、索引构建、增量更新）
- RAGGenerator: RAG生成器（调用LLM生成回答、带引用回答、流式回答）
- DocumentPreview: 文档预览（提取前几页内容、获取元数据）
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Generator, Tuple

import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from openai import OpenAI

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.config import (
    DASHSCOPE_API_KEY,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    CHROMA_PERSIST_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_MODEL,
    LOG_LEVEL,
)

# ============================================================
# 日志配置
# ============================================================
logger = logging.getLogger("rag_engine")
logger.setLevel(getattr(logging, LOG_LEVEL if isinstance(LOG_LEVEL, str) else "INFO"))

_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
)
if not logger.handlers:
    logger.addHandler(_handler)


# ============================================================
# 辅助工具函数
# ============================================================

def _md5(text: str) -> str:
    """计算字符串的MD5哈希，用于文档唯一标识"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _timestamp_now() -> str:
    """返回当前时间戳字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个向量的余弦相似度"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ============================================================
# 文档加载器映射
# ============================================================

_LOADER_MAP = {
    ".pdf": PyPDFLoader,
    ".txt": lambda p: TextLoader(p, encoding="utf-8"),
    ".docx": Docx2txtLoader,
    ".md": UnstructuredMarkdownLoader,
}


# ============================================================
# 1. HybridRetriever - 混合检索器
# ============================================================

class HybridRetriever:
    """
    混合检索器：融合向量相似度搜索、BM25关键词搜索和文档新鲜度评分。

    加权公式：
        final_score = 0.7 * vector_score + 0.25 * bm25_score + 0.05 * freshness_score

    支持配置 top_k 和 min_score 阈值。
    """

    DEFAULT_WEIGHTS = {
        "vector": 0.70,
        "bm25": 0.25,
        "freshness": 0.05,
    }

    def __init__(
        self,
        vector_store: Chroma,
        embeddings: DashScopeEmbeddings,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
        min_score: float = 0.0,
        weights: Optional[Dict[str, float]] = None,
    ):
        """
        初始化混合检索器。

        Args:
            vector_store: Chroma 向量数据库实例
            embeddings: DashScope 嵌入模型实例
            documents: 文档元数据列表，每项至少包含 "content"、"doc_id"、"chunk_id"、"metadata"
            top_k: 返回的最大结果数
            min_score: 最低分数阈值，低于此分的结果会被过滤
            weights: 自定义融合权重
        """
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.documents = documents
        self.top_k = top_k
        self.min_score = min_score
        self.weights = weights or self.DEFAULT_WEIGHTS

        # 校验权重之和为1
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            logger.warning("融合权重之和为 %.4f，已自动归一化为 1.0", total)
            self.weights = {k: v / total for k, v in self.weights.items()}

        # 构建 BM25 索引
        self._bm25_corpus: List[List[str]] = []
        self._bm25_index: Optional[BM25Okapi] = None
        self._build_bm25_index()

    def _build_bm25_index(self):
        """使用 jieba 中文分词构建 BM25 索引"""
        if not self.documents:
            logger.warning("文档列表为空，跳过 BM25 索引构建")
            return

        logger.info("正在构建 BM25 索引，共 %d 个文档块", len(self.documents))
        tokenized_corpus = []
        for doc in self.documents:
            tokens = list(jieba.cut(doc.get("content", "")))
            tokenized_corpus.append(tokens)

        self._bm25_corpus = tokenized_corpus
        self._bm25_index = BM25Okapi(tokenized_corpus)
        logger.info("BM25 索引构建完成")

    def rebuild_bm25(self):
        """重建 BM25 索引，在文档集合变更后调用"""
        self._build_bm25_index()

    def _vector_search(self, query: str, top_k: int) -> List[Tuple[str, float, Dict[str, Any]]]:
        """向量相似度搜索，返回 [(content, score, metadata), ...]"""
        try:
            results = self.vector_store.similarity_search_with_relevance_scores(
                query, k=top_k
            )
            scored = []
            for doc, score in results:
                meta = doc.metadata if hasattr(doc, "metadata") else {}
                scored.append((doc.page_content, score, meta))
            return scored
        except Exception as e:
            logger.error("向量搜索失败: %s", e)
            return []

    def _bm25_search(self, query: str, top_k: int) -> List[Tuple[int, float]]:
        """BM25 关键词搜索，返回 [(doc_index, bm25_score), ...]"""
        if self._bm25_index is None:
            logger.warning("BM25 索引未初始化，跳过关键词搜索")
            return []

        # 对查询做 jieba 分词
        query_tokens = list(jieba.cut(query))
        scores = self._bm25_index.get_scores(query_tokens)

        # 取 top_k 最高分
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(int(idx), float(scores[idx])) for idx in top_indices]

    def _freshness_score(self, metadata: Dict[str, Any]) -> float:
        """根据文档时间戳计算新鲜度分数 (0~1)，越新越高"""
        ts_str = metadata.get("created_at") or metadata.get("updated_at")
        if not ts_str:
            return 0.5
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            days_ago = (datetime.now() - ts).days
            # 30天内为满分，超过365天衰减到接近0
            score = max(0.0, 1.0 - (days_ago / 365.0))
            return score
        except (ValueError, TypeError):
            return 0.5

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Min-Max 归一化到 [0, 1]"""
        if not scores:
            return []
        arr = np.array(scores, dtype=float)
        min_val, max_val = arr.min(), arr.max()
        if max_val - min_val < 1e-9:
            return [1.0] * len(scores)
        return ((arr - min_val) / (max_val - min_val)).tolist()

    def search(
        self, query: str, top_k: Optional[int] = None, mode: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """
        混合检索入口。

        Args:
            query: 用户查询文本
            top_k: 返回数量
            mode: 检索模式 - "hybrid" | "vector" | "bm25"

        Returns:
            排序后的结果列表
        """
        k = top_k or self.top_k
        results: Dict[str, Dict[str, Any]] = {}

        # ---------- 向量检索 ----------
        if mode in ("hybrid", "vector"):
            vector_hits = self._vector_search(query, k * 2)
            vector_scores_raw = [s for _, s, _ in vector_hits]
            vector_scores_norm = self._normalize_scores(vector_scores_raw)

            for (content, raw_score, meta), norm_score in zip(
                vector_hits, vector_scores_norm
            ):
                key = _md5(content)
                if key not in results:
                    results[key] = {
                        "content": content,
                        "metadata": meta,
                        "vector_score": norm_score,
                        "bm25_score": 0.0,
                        "freshness_score": 0.0,
                    }
                else:
                    results[key]["vector_score"] = norm_score

        # ---------- BM25 检索 ----------
        if mode in ("hybrid", "bm25"):
            bm25_hits = self._bm25_search(query, k * 2)
            bm25_scores_raw = [s for _, s in bm25_hits]
            bm25_scores_norm = self._normalize_scores(bm25_scores_raw)

            for (doc_idx, raw_score), norm_score in zip(
                bm25_hits, bm25_scores_norm
            ):
                doc = self.documents[doc_idx]
                key = _md5(doc.get("content", ""))
                if key not in results:
                    results[key] = {
                        "content": doc.get("content", ""),
                        "metadata": doc.get("metadata", {}),
                        "vector_score": 0.0,
                        "bm25_score": norm_score,
                        "freshness_score": 0.0,
                    }
                else:
                    results[key]["bm25_score"] = norm_score

        # ---------- 新鲜度评分 ----------
        for key, item in results.items():
            item["freshness_score"] = self._freshness_score(item["metadata"])

        # ---------- 加权融合 ----------
        w = self.weights
        for key, item in results.items():
            item["score"] = (
                w["vector"] * item["vector_score"]
                + w["bm25"] * item["bm25_score"]
                + w["freshness"] * item["freshness_score"]
            )

        # 排序并过滤低分
        sorted_results = sorted(results.values(), key=lambda x: x["score"], reverse=True)
        filtered = [r for r in sorted_results if r["score"] >= self.min_score]

        logger.info(
            "检索完成 - query=%r, mode=%s, 候选=%d, 返回=%d",
            query[:50], mode, len(results), min(k, len(filtered)),
        )

        return filtered[:k]


# ============================================================
# 2. KnowledgeBaseManager - 知识库管理器
# ============================================================

class KnowledgeBaseManager:
    """
    知识库管理器：负责文档的加载、分块、向量化存储、增量更新、搜索、统计与删除。
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md"}

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = "counselor_kb",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        初始化知识库管理器。

        Args:
            persist_dir: Chroma 持久化目录
            collection_name: Chroma 集合名称
            chunk_size: 文本分块大小（字符数）
            chunk_overlap: 分块重叠字符数
        """
        self.persist_dir = persist_dir or CHROMA_PERSIST_DIR
        self.collection_name = collection_name
        self.chunk_size = chunk_size or CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or CHUNK_OVERLAP

        # 文本分割器：使用递归字符分割，对中文友好
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ".", "!", "?", " ", ""],
            length_function=len,
        )

        # DashScope 嵌入模型
        self.embeddings = DashScopeEmbeddings(
            model=EMBEDDING_MODEL,
            dashscope_api_key=DASHSCOPE_API_KEY,
        )

        # 内存中的文档元数据索引
        self._doc_index: Dict[str, Dict[str, Any]] = {}
        self._documents: List[Dict[str, Any]] = []
        self._last_updated: Optional[str] = None
        self._retriever: Optional[HybridRetriever] = None  # 缓存检索器，避免每次重建BM25

        # Chroma 向量数据库（含旧版本索引迁移失败兜底）
        self.vector_store = self._init_vector_store()

        # 加载已有索引
        self._load_existing_index()

        logger.info(
            "KnowledgeBaseManager 初始化完成 - persist_dir=%s, collection=%s",
            self.persist_dir, self.collection_name,
        )

    def _init_vector_store(self) -> Chroma:
        """初始化 Chroma 向量库，遇到旧版本索引无法迁移时自动重建。

        旧版 chromadb 持久化的索引在新版本下可能因缺少配置字段而抛
        ``KeyError: '_type'``（配置迁移失败）。此时直接删除陈旧索引、
        重建一个空的集合，避免整个知识库引擎初始化崩溃。
        """
        try:
            return Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_dir,
            )
        except Exception as e:
            logger.warning("Chroma 初始化失败（可能为旧索引不兼容），自动重建: %s", e)
            import shutil
            if os.path.isdir(self.persist_dir):
                shutil.rmtree(self.persist_dir, ignore_errors=True)
            return Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_dir,
            )

    def _load_existing_index(self):
        """从 Chroma 恢复已有的文档索引元数据"""
        try:
            collection = self.vector_store._collection
            count = collection.count()
            if count > 0:
                logger.info("检测到已有索引，共 %d 个向量，正在恢复元数据", count)
                stored = collection.get(include=["metadatas", "documents"])
                for doc_id, meta, content in zip(
                    stored["ids"], stored["metadatas"], stored["documents"]
                ):
                    self._documents.append({
                        "chunk_id": doc_id,
                        "doc_id": meta.get("doc_id", "unknown"),
                        "content": content,
                        "metadata": meta,
                    })
                for item in self._documents:
                    did = item["doc_id"]
                    if did not in self._doc_index:
                        self._doc_index[did] = {
                            "doc_id": did,
                            "chunk_count": 0,
                            "source": item["metadata"].get("source", "unknown"),
                            "created_at": item["metadata"].get("created_at", ""),
                        }
                    self._doc_index[did]["chunk_count"] += 1
                logger.info("恢复了 %d 个文档，%d 个块", len(self._doc_index), count)
        except Exception as e:
            logger.warning("加载已有索引失败（首次运行可忽略）: %s", e)

    def load_documents(self, doc_paths: List[str]) -> List[Any]:
        """
        加载指定路径的文档，支持 PDF / TXT / DOCX / MD。

        Args:
            doc_paths: 文档文件路径列表

        Returns:
            langchain Document 对象列表
        """
        all_docs = []
        for path in doc_paths:
            ext = Path(path).suffix.lower()
            if ext not in self.SUPPORTED_EXTENSIONS:
                logger.warning("不支持的文件类型 %s，跳过: %s", ext, path)
                continue

            if not os.path.exists(path):
                logger.error("文件不存在: %s", path)
                continue

            try:
                loader_cls = _LOADER_MAP[ext]
                loader = loader_cls(path)
                docs = loader.load()
                # 给每个文档添加来源元数据
                for doc in docs:
                    doc.metadata["source"] = os.path.basename(path)
                    doc.metadata["doc_path"] = path
                    doc.metadata["created_at"] = _timestamp_now()
                all_docs.extend(docs)
                logger.info("成功加载 %s，共 %d 个页面/段落", path, len(docs))
            except Exception as e:
                logger.error("加载文档失败 %s: %s", path, e)

        logger.info("总计加载 %d 个文档块（原始）", len(all_docs))
        return all_docs

    def build_index(self, chunks: List[Any]) -> Dict[str, Any]:
        """
        将文档块向量化并存入 Chroma。

        Args:
            chunks: langchain Document 列表

        Returns:
            构建结果统计
        """
        if not chunks:
            logger.warning("文档块列表为空，跳过索引构建")
            return {"status": "empty", "count": 0}

        # 文本分割
        split_docs = self.text_splitter.split_documents(chunks)
        logger.info("文本分割完成：%d 个块（chunk_size=%d, overlap=%d）",
                     len(split_docs), self.chunk_size, self.chunk_overlap)

        # 构建唯一 ID 和元数据
        ids = []
        contents = []
        metadatas = []
        doc_chunk_map: Dict[str, int] = {}

        for i, doc in enumerate(split_docs):
            chunk_id = "chunk_{}_{}".format(_md5(doc.page_content), i)
            meta = dict(doc.metadata) if doc.metadata else {}
            meta["chunk_index"] = i
            meta["built_at"] = _timestamp_now()
            doc_id = meta.get("doc_id", _md5(meta.get("source", "unknown")))

            ids.append(chunk_id)
            contents.append(doc.page_content)
            metadatas.append(meta)

            # 更新内存索引
            if doc_id not in doc_chunk_map:
                doc_chunk_map[doc_id] = 0
            doc_chunk_map[doc_id] += 1

            self._documents.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "content": doc.page_content,
                "metadata": meta,
            })

        # 写入 Chroma
        self.vector_store.add_texts(
            texts=contents,
            metadatas=metadatas,
            ids=ids,
        )

        # 更新文档索引
        for doc_id, count in doc_chunk_map.items():
            source = next(
                (m.get("source", "") for m in metadatas
                 if m.get("doc_id") == doc_id),
                "unknown",
            )
            self._doc_index[doc_id] = {
                "doc_id": doc_id,
                "chunk_count": count,
                "source": source,
                "created_at": _timestamp_now(),
            }

        self._last_updated = _timestamp_now()
        self._invalidate_retriever()
        logger.info("索引构建完成：共 %d 个文档块写入 Chroma", len(ids))

        return {
            "status": "success",
            "doc_count": len(doc_chunk_map),
            "chunk_count": len(ids),
        }

    def incremental_update(self, new_doc_path: str) -> Dict[str, Any]:
        """
        增量添加新文档到知识库，无需重建全量索引。

        Args:
            new_doc_path: 新文档路径

        Returns:
            更新结果统计
        """
        logger.info("开始增量更新: %s", new_doc_path)

        # 检查是否已存在
        doc_id = _md5(new_doc_path)
        if doc_id in self._doc_index:
            logger.info("文档已存在于索引中，跳过: %s", new_doc_path)
            return {"status": "skipped", "reason": "document already indexed"}

        # 加载并分块
        raw_docs = self.load_documents([new_doc_path])
        if not raw_docs:
            return {"status": "empty", "reason": "failed to load document"}

        split_docs = self.text_splitter.split_documents(raw_docs)
        if not split_docs:
            return {"status": "empty", "reason": "no chunks produced"}

        # 准备数据
        ids = []
        contents = []
        metadatas = []

        for i, doc in enumerate(split_docs):
            chunk_id = "chunk_{}_{}".format(_md5(doc.page_content), i)
            meta = dict(doc.metadata) if doc.metadata else {}
            meta["chunk_index"] = i
            meta["doc_id"] = doc_id
            meta["built_at"] = _timestamp_now()

            ids.append(chunk_id)
            contents.append(doc.page_content)
            metadatas.append(meta)

            self._documents.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "content": doc.page_content,
                "metadata": meta,
            })

        # 写入 Chroma
        self.vector_store.add_texts(
            texts=contents,
            metadatas=metadatas,
            ids=ids,
        )

        # 更新内存索引
        self._doc_index[doc_id] = {
            "doc_id": doc_id,
            "chunk_count": len(ids),
            "source": os.path.basename(new_doc_path),
            "created_at": _timestamp_now(),
        }

        self._last_updated = _timestamp_now()
        logger.info("增量更新完成：添加 %d 个块", len(ids))

        return {
            "status": "success",
            "doc_id": doc_id,
            "chunk_count": len(ids),
        }

    def _get_retriever(self) -> HybridRetriever:
        """获取或创建缓存的 HybridRetriever 实例（文档变更时自动重建）"""
        if self._retriever is None or len(self._retriever.documents) != len(self._documents):
            self._retriever = HybridRetriever(
                vector_store=self.vector_store,
                embeddings=self.embeddings,
                documents=self._documents,
                top_k=3,
            )
        return self._retriever

    def _invalidate_retriever(self):
        """文档变更后使检索器缓存失效"""
        self._retriever = None

    def search(
        self, query: str, top_k: int = 3, mode: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """
        在知识库中执行检索。

        Args:
            query: 查询文本
            top_k: 返回结果数
            mode: 检索模式 - "hybrid" | "vector" | "bm25"

        Returns:
            检索结果列表
        """
        retriever = self._get_retriever()
        results = retriever.search(query, top_k=top_k, mode=mode)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """返回知识库统计信息"""
        return {
            "doc_count": len(self._doc_index),
            "chunk_count": len(self._documents),
            "last_updated": self._last_updated or "never",
            "persist_dir": self.persist_dir,
            "collection_name": self.collection_name,
            "documents": list(self._doc_index.values()),
        }

    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """
        从索引中删除指定文档的所有块。

        Args:
            doc_id: 文档唯一标识

        Returns:
            删除结果
        """
        if doc_id not in self._doc_index:
            logger.warning("文档不存在于索引中: %s", doc_id)
            return {"status": "not_found", "doc_id": doc_id}

        # 收集该文档的所有 chunk_id
        chunk_ids = [
            item["chunk_id"]
            for item in self._documents
            if item["doc_id"] == doc_id
        ]

        if not chunk_ids:
            logger.warning("文档 %s 没有可删除的块", doc_id)
            return {"status": "no_chunks", "doc_id": doc_id}

        # 从 Chroma 删除
        self.vector_store._collection.delete(ids=chunk_ids)

        # 从内存索引移除
        self._documents = [d for d in self._documents if d["doc_id"] != doc_id]
        del self._doc_index[doc_id]

        self._invalidate_retriever()
        logger.info("已删除文档 %s，共 %d 个块", doc_id, len(chunk_ids))

        return {
            "status": "deleted",
            "doc_id": doc_id,
            "deleted_chunks": len(chunk_ids),
        }


# ============================================================
# 3. RAGGenerator - RAG 生成器
# ============================================================

class RAGGenerator:
    """
    RAG 生成器：将检索到的文档上下文注入 LLM 生成回答。
    支持普通回答、带引用回答和流式回答三种模式。
    """

    DEFAULT_SYSTEM_PROMPT = (
        "你是一位专业的大学心理辅导AI助手。请基于以下参考资料回答用户的问题。\n"
        "回答要求：\n"
        "1. 准确、专业、有同理心\n"
        "2. 如果参考资料不足以回答，请坦诚告知\n"
        "3. 适当引用参考资料来支持你的回答\n\n"
        "参考资料：\n{context}"
    )

    CITATION_SYSTEM_PROMPT = (
        "你是一位专业的大学心理辅导AI助手。请基于以下参考资料回答用户的问题。\n"
        "回答要求：\n"
        "1. 准确、专业、有同理心\n"
        "2. 使用 [来源X] 格式标注引用，X为参考文档编号\n"
        "3. 如果参考资料不足以回答，请坦诚告知\n\n"
        "参考资料：\n{context}"
    )

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """
        初始化 RAG 生成器。

        Args:
            model: 模型名称
            base_url: OpenAI 兼容 API 地址
            api_key: API 密钥
            temperature: 温度参数
            max_tokens: 最大生成 token 数
        """
        self.model = model or OPENAI_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = OpenAI(
            api_key=api_key or OPENAI_API_KEY,
            base_url=base_url or OPENAI_BASE_URL,
        )
        logger.info("RAGGenerator 初始化完成 - model=%s", self.model)

    def _build_context(self, context_docs: List[Dict[str, Any]]) -> str:
        """将检索到的文档拼接为上下文字符串"""
        if not context_docs:
            return "（未找到相关参考资料）"

        parts = []
        for i, doc in enumerate(context_docs, 1):
            source = doc.get("metadata", {}).get("source", "未知来源")
            content = doc.get("content", "").strip()
            score = doc.get("score", 0)
            parts.append("[来源{}] (文件: {}, 相关度: {:.2f})\n{}".format(
                i, source, score, content
            ))

        return "\n\n".join(parts)

    def _build_citation_context(self, context_docs: List[Dict[str, Any]]) -> str:
        """构建带引用编号的上下文"""
        return self._build_context(context_docs)

    def generate_answer(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> str:
        """
        基于检索上下文生成回答。

        Args:
            query: 用户问题
            context_docs: 检索到的文档列表

        Returns:
            LLM 生成的回答文本
        """
        context = self._build_context(context_docs)
        system_prompt = self.DEFAULT_SYSTEM_PROMPT.format(context=context)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            answer = response.choices[0].message.content or ""
            logger.info(
                "回答生成完成 - query=%r, tokens=%d",
                query[:50],
                response.usage.total_tokens if response.usage else 0,
            )
            return answer
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            return "抱歉，生成回答时遇到错误：{}".format(e)

    def generate_with_citations(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成带引用来源的回答。

        Returns:
            { "answer": 回答文本, "sources": [{ "index", "source", "score" }, ...] }
        """
        context = self._build_citation_context(context_docs)
        system_prompt = self.CITATION_SYSTEM_PROMPT.format(context=context)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            answer = response.choices[0].message.content or ""

            # 构建来源列表
            sources = []
            for i, doc in enumerate(context_docs, 1):
                chunk_content = doc.get("content", "")
                sources.append({
                    "index": i,
                    "source": doc.get("metadata", {}).get("source", "未知来源"),
                    "score": round(doc.get("score", 0), 4),
                    "chunk_preview": (
                        chunk_content[:100] + "..."
                        if len(chunk_content) > 100
                        else chunk_content
                    ),
                })

            logger.info("带引用回答生成完成 - query=%r", query[:50])

            return {
                "answer": answer,
                "sources": sources,
                "model": self.model,
                "query": query,
            }
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            return {
                "answer": "抱歉，生成回答时遇到错误：{}".format(e),
                "sources": [],
                "model": self.model,
                "query": query,
            }

    def stream_answer(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> Generator[str, None, None]:
        """
        流式生成回答。

        Args:
            query: 用户问题
            context_docs: 检索到的文档列表

        Yields:
            逐块生成的文本片段
        """
        context = self._build_context(context_docs)
        system_prompt = self.DEFAULT_SYSTEM_PROMPT.format(context=context)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error("流式 LLM 调用失败: %s", e)
            yield "\n\n抱歉，流式生成时遇到错误：{}".format(e)


# ============================================================
# 4. DocumentPreview - 文档预览
# ============================================================

class DocumentPreview:
    """
    文档预览工具：提取文档前几页内容并返回元数据，用于快速了解文档内容。
    支持 PDF / TXT / DOCX / MD。
    """

    def __init__(self):
        """初始化文档预览器"""
        self._page_cache: Dict[str, Any] = {}
        logger.info("DocumentPreview 初始化完成")

    def preview_document(
        self, doc_path: str, max_pages: int = 3
    ) -> Dict[str, Any]:
        """
        预览文档前几页的内容。

        Args:
            doc_path: 文档路径
            max_pages: 最大预览页数

        Returns:
            { "path", "total_pages", "preview_pages", "content_preview", "metadata" }
        """
        if not os.path.exists(doc_path):
            return {"error": "文件不存在: {}".format(doc_path)}

        ext = Path(doc_path).suffix.lower()
        if ext not in KnowledgeBaseManager.SUPPORTED_EXTENSIONS:
            return {"error": "不支持的文件类型: {}".format(ext)}

        try:
            loader_cls = _LOADER_MAP[ext]
            loader = loader_cls(doc_path)
            all_docs = loader.load()

            total_pages = len(all_docs)
            preview_docs = all_docs[:max_pages]
            content_preview = "\n\n---\n\n".join(
                "【第 {} 页/段】\n{}".format(i + 1, doc.page_content)
                for i, doc in enumerate(preview_docs)
            )

            metadata = self.get_metadata(doc_path)

            return {
                "path": doc_path,
                "filename": os.path.basename(doc_path),
                "total_pages": total_pages,
                "preview_pages": len(preview_docs),
                "content_preview": content_preview,
                "metadata": metadata,
            }
        except Exception as e:
            logger.error("预览文档失败 %s: %s", doc_path, e)
            return {"error": "预览失败: {}".format(e)}

    def get_metadata(self, doc_path: str) -> Dict[str, Any]:
        """
        获取文档元数据（文件名、大小、创建时间、修改时间等）。

        Args:
            doc_path: 文档路径

        Returns:
            元数据字典
        """
        path_obj = Path(doc_path)
        stat = path_obj.stat() if os.path.exists(path_obj) else None

        metadata = {
            "filename": path_obj.name,
            "extension": path_obj.suffix.lower(),
            "size_bytes": stat.st_size if stat else 0,
            "size_display": self._format_size(stat.st_size) if stat else "unknown",
            "created_at": (
                datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
                if stat else "unknown"
            ),
            "modified_at": (
                datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                if stat else "unknown"
            ),
        }

        # PDF 额外提取页数信息
        if path_obj.suffix.lower() == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(path_obj))
                metadata["pdf_page_count"] = doc.page_count
                metadata["pdf_title"] = doc.metadata.get("title", "")
                metadata["pdf_author"] = doc.metadata.get("author", "")
                doc.close()
            except ImportError:
                metadata["pdf_page_count"] = "需安装 PyMuPDF"
            except Exception as e:
                metadata["pdf_page_count"] = "读取失败: {}".format(e)

        return metadata

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节数格式化为可读字符串"""
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return "{:.1f} {}".format(size_bytes, unit)
            size_bytes /= 1024
        return "{:.1f} TB".format(size_bytes)


# ============================================================
# __main__ 演示入口
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  RAG 知识库引擎演示 - 聆心")
    print("=" * 70)

    # --- 1. 初始化知识库管理器 ---
    print("\n[1/6] 初始化知识库管理器...")
    kb_manager = KnowledgeBaseManager()

    # --- 2. 创建示例文档用于演示 ---
    demo_dir = os.path.join(os.path.dirname(__file__), "_demo_docs")
    os.makedirs(demo_dir, exist_ok=True)

    sample_docs = {
        "depression_intro.txt": (
            "抑郁症（Depression）是一种常见的心理健康问题，表现为持续的悲伤、\n"
            "失去兴趣或愉悦感。大学生群体中，抑郁症的发病率约为15%-30%。\n\n"
            "常见症状包括：\n"
            "1. 持续的情绪低落，每天大部分时间都感到悲伤\n"
            "2. 对曾经喜欢的活动失去兴趣\n"
            "3. 食欲变化（暴食或食欲不振）\n"
            "4. 失眠或嗜睡\n"
            "5. 注意力难以集中，学习效率下降\n"
            "6. 自我价值感降低，产生无用感\n"
            "7. 严重时可能出现自伤或自杀的想法\n\n"
            "早期识别和及时干预非常重要。大学生可以寻求心理咨询中心的帮助。"
        ),
        "anxiety_coping.txt": (
            "焦虑是大学生活中常见的情绪体验。适度的焦虑有助于提升表现，但过度的\n"
            "焦虑会影响学习和日常生活。\n\n"
            "应对焦虑的方法：\n"
            "1. 深呼吸练习：4-7-8呼吸法（吸气4秒，屏气7秒，呼气8秒）\n"
            "2. 渐进性肌肉放松：从脚趾到头部逐步放松每组肌肉\n"
            "3. 正念冥想：每天10-15分钟的专注练习\n"
            "4. 认知重构：识别并挑战不合理的消极想法\n"
            "5. 时间管理：使用番茄工作法等工具减轻学业压力\n"
            "6. 适当运动：每周至少3次有氧运动，每次30分钟以上\n"
            "7. 社交支持：与信任的朋友、家人或辅导员交流\n\n"
            "如果焦虑严重影响到日常生活，建议寻求专业心理帮助。"
        ),
        "sleep_hygiene.txt": (
            "良好的睡眠对大学生的心理健康和学业表现至关重要。\n\n"
            "健康睡眠指南：\n"
            "1. 保持规律的作息时间，每天同一时间睡觉和起床\n"
            "2. 睡前1小时避免使用电子设备（手机、电脑、平板）\n"
            "3. 营造良好的睡眠环境：安静、黑暗、温度适宜（18-22摄氏度）\n"
            "4. 避免在床上进行与睡眠无关的活动（学习、玩手机）\n"
            "5. 下午2点后避免摄入咖啡因\n"
            "6. 睡前可以进行放松活动：阅读、听轻音乐、热水泡脚\n"
            "7. 如果躺下20分钟仍无法入睡，起床做些放松的事情再回去\n\n"
            "研究表明，大学生平均睡眠时间不足7小时，但理想睡眠时间应为7-9小时。"
        ),
    }

    doc_paths = []
    for filename, content in sample_docs.items():
        path = os.path.join(demo_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        doc_paths.append(path)
        print("  已创建示例文档: {}".format(filename))

    # --- 3. 加载文档并构建索引 ---
    print("\n[2/6] 加载文档并构建向量索引...")
    raw_docs = kb_manager.load_documents(doc_paths)
    build_result = kb_manager.build_index(raw_docs)
    print("  索引构建结果: {}".format(build_result))

    # --- 4. 混合检索演示 ---
    print("\n[3/6] 混合检索演示...")
    test_queries = [
        "大学生如何缓解焦虑情绪？",
        "抑郁症有哪些表现？",
        "怎么改善睡眠质量？",
    ]
    for q in test_queries:
        print("\n  查询: {}".format(q))
        results = kb_manager.search(q, top_k=2, mode="hybrid")
        for r in results:
            preview = r["content"][:80].replace("\n", " ")
            print(
                "    -> [得分={:.4f}] (向量={:.2f}, BM25={:.2f}, 新鲜度={:.2f}) {}...".format(
                    r["score"], r["vector_score"], r["bm25_score"], r["freshness_score"], preview
                )
            )

    # --- 5. RAG 生成演示 ---
    print("\n[4/6] RAG 回答生成演示...")
    generator = RAGGenerator()
    query = "大学生如何缓解焦虑情绪？"
    context = kb_manager.search(query, top_k=3, mode="hybrid")

    # 普通回答
    print("\n  问题: {}".format(query))
    answer = generator.generate_answer(query, context)
    print("  回答:\n  {}...".format(answer[:200]))

    # 带引用回答
    print("\n  --- 带引用回答 ---")
    cited = generator.generate_with_citations(query, context)
    print("  回答:\n  {}...".format(cited["answer"][:200]))
    print("  引用来源:")
    for src in cited["sources"]:
        print("    [{}] {} (相关度: {})".format(src["index"], src["source"], src["score"]))

    # 流式回答
    print("\n  --- 流式回答 ---")
    print("  ", end="")
    for token in generator.stream_answer(query, context):
        print(token, end="", flush=True)
    print()

    # --- 6. 文档预览演示 ---
    print("\n[5/6] 文档预览演示...")
    previewer = DocumentPreview()
    preview = previewer.preview_document(doc_paths[0], max_pages=1)
    print("  文件: {}".format(preview.get("filename")))
    print("  总页数: {}".format(preview.get("total_pages")))
    preview_text = preview.get("content_preview", "")[:150]
    print("  预览内容:\n  {}...".format(preview_text))

    # --- 7. 增量更新演示 ---
    print("\n[6/6] 增量更新演示...")
    new_doc_path = os.path.join(demo_dir, "new_resource.txt")
    with open(new_doc_path, "w", encoding="utf-8") as f:
        f.write(
            "心理危机干预热线：全国24小时免费热线 400-161-9995\n"
            "北京心理危机研究与干预中心：010-82951332\n"
            "生命热线：400-821-1215"
        )

    update_result = kb_manager.incremental_update(new_doc_path)
    print("  增量更新结果: {}".format(update_result))

    # --- 统计信息 ---
    print("\n  知识库统计:")
    stats = kb_manager.get_stats()
    print("    文档数: {}".format(stats["doc_count"]))
    print("    块数: {}".format(stats["chunk_count"]))
    print("    最后更新: {}".format(stats["last_updated"]))

    # --- 清理演示文档 ---
    import shutil
    shutil.rmtree(demo_dir, ignore_errors=True)
    print("\n  演示文件已清理")

    print("\n" + "=" * 70)
    print("  演示完成！")
    print("=" * 70)

