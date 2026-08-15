"""
知识库服务 - 文档分块、向量化、存储、检索
支持多种分块策略：按句子、按段落、固定长度
"""
import re
import time
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.config.config import settings
from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class DocumentChunker:
    """文档分块器 - 将长文档切分成适合向量化的小块"""

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
        split_pattern: str = None,
    ):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.split_pattern = split_pattern or settings.CHUNK_SPLIT_PATTERN

    def chunk_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not content or not content.strip():
            return []

        if self.split_pattern == "sentence":
            chunks = self._split_by_sentence(content)
        elif self.split_pattern == "paragraph":
            chunks = self._split_by_paragraph(content)
        else:
            chunks = self._split_fixed(content)

        result = []
        for i, chunk_text in enumerate(chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            chunk = {
                "id": f"chunk_{uuid.uuid4().hex[:12]}",
                "content": chunk_text,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "char_count": len(chunk_text),
                "created_at": datetime.now().isoformat(),
            }
            if metadata:
                chunk["metadata"] = metadata
            result.append(chunk)

        logger.info(f"文档分块完成: {len(content)} 字符 -> {len(result)} 个分块")
        return result

    def _split_by_sentence(self, text: str) -> List[str]:
        sentences = re.split(r'(?<=[。！？.!?；;])', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= self.chunk_size:
                current += sentence
            else:
                if current:
                    chunks.append(current)
                if len(sentence) > self.chunk_size:
                    for i in range(0, len(sentence), self.chunk_size):
                        chunk = sentence[i:i + self.chunk_size]
                        if chunk:
                            chunks.append(chunk)
                    current = ""
                else:
                    current = sentence

        if current:
            chunks.append(current)

        return chunks

    def _split_by_paragraph(self, text: str) -> List[str]:
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        for para in paragraphs:
            if len(para) <= self.chunk_size:
                chunks.append(para)
            else:
                sentences = re.split(r'(?<=[。！？.!?；;])', para)
                current = ""
                for sentence in sentences:
                    if len(current) + len(sentence) <= self.chunk_size:
                        current += sentence
                    else:
                        if current:
                            chunks.append(current)
                        current = sentence
                if current:
                    chunks.append(current)

        return chunks

    def _split_fixed(self, text: str) -> List[str]:
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        if step <= 0:
            step = self.chunk_size

        for i in range(0, len(text), step):
            chunk = text[i:i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk)

        return chunks


class KnowledgeBaseService:
    """知识库服务 - 管理文档的入库和检索"""

    def __init__(self):
        self.chunker = DocumentChunker()
        self._documents: List[Dict[str, Any]] = []
        self._embedding_service = None
        self._vector_store = None
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        self._embedding_service = get_embedding_service(dim=settings.EMBEDDING_DIM)

        use_milvus = settings.USE_MILVUS
        if use_milvus:
            try:
                from app.utils.milvus_client import get_milvus_client
                self._vector_store = get_milvus_client(
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                    dim=settings.EMBEDDING_DIM,
                )
                if self._vector_store.connect():
                    logger.info("KnowledgeBase: Milvus connected")
                else:
                    logger.warning("KnowledgeBase: Milvus connection failed, using memory")
                    self._vector_store = None
            except Exception as e:
                logger.warning(f"KnowledgeBase: Milvus init error: {e}")
                self._vector_store = None
        else:
            logger.info("KnowledgeBase: Using memory-based storage")

        self._initialized = True

    def add_document(
        self,
        title: str,
        content: str,
        category: str = "",
        keywords: Optional[List[str]] = None,
        source: str = "",
    ) -> Dict[str, Any]:
        self.initialize()

        metadata = {
            "title": title,
            "category": category,
            "keywords": keywords or [],
            "source": source,
        }

        chunks = self.chunker.chunk_document(content, metadata)
        if not chunks:
            return {"success": False, "message": "文档为空", "chunks_count": 0}

        embeddings = []
        for chunk in chunks:
            chunk_text = chunk["content"]
            embedding = self._embedding_service.encode(chunk_text)
            embeddings.append(embedding)

        doc_record = {
            "id": f"doc_{uuid.uuid4().hex[:12]}",
            "title": title,
            "content": content,
            "category": category,
            "keywords": keywords or [],
            "source": source,
            "chunks": chunks,
            "created_at": datetime.now().isoformat(),
        }

        self._documents.append(doc_record)

        if self._vector_store:
            try:
                docs_for_milvus = []
                for chunk in chunks:
                    milvus_doc = {
                        "id": chunk["id"],
                        "title": title,
                        "content": chunk["content"],
                        "category": category,
                        "keywords": ",".join(keywords) if keywords else "",
                        "source": source,
                    }
                    docs_for_milvus.append(milvus_doc)

                self._vector_store.insert(docs_for_milvus, embeddings)
                logger.info(f"Document '{title}' indexed to Milvus with {len(chunks)} chunks")
            except Exception as e:
                logger.error(f"Failed to index document to Milvus: {e}")
        else:
            for chunk, embedding in zip(chunks, embeddings):
                chunk["_embedding"] = embedding
            logger.info(f"Document '{title}' stored in memory with {len(chunks)} chunks")

        return {
            "success": True,
            "document_id": doc_record["id"],
            "chunks_count": len(chunks),
        }

    def search(
        self,
        query: str,
        top_k: int = None,
        similarity_threshold: float = None,
    ) -> Dict[str, Any]:
        self.initialize()

        top_k = top_k or settings.RAG_TOP_K
        similarity_threshold = similarity_threshold or settings.RAG_SIMILARITY_THRESHOLD

        query_embedding = self._embedding_service.encode(query)

        if self._vector_store:
            try:
                results = self._vector_store.search(
                    query_embedding=query_embedding,
                    top_k=top_k * 2,
                    score_threshold=similarity_threshold,
                )
            except Exception as e:
                logger.error(f"Milvus search error: {e}")
                results = self._memory_search(query_embedding, query, top_k, similarity_threshold)
        else:
            results = self._memory_search(query_embedding, query, top_k, similarity_threshold)

        reranked = self._rerank_results(query, results, top_k)

        return {
            "success": True,
            "query": query,
            "results": reranked,
            "total_candidates": len(results),
            "search_strategy": "vector" if self._vector_store else "memory",
        }

    def _memory_search(
        self,
        query_embedding: List[float],
        query: str,
        top_k: int,
        threshold: float,
    ) -> List[Dict[str, Any]]:
        results = []
        for doc in self._documents:
            for chunk in doc["chunks"]:
                if "_embedding" not in chunk:
                    continue

                similarity = self._cosine_similarity(query_embedding, chunk["_embedding"])
                if similarity >= threshold:
                    results.append({
                        "id": chunk["id"],
                        "title": doc["title"],
                        "content": chunk["content"],
                        "category": doc.get("category", ""),
                        "keywords": doc.get("keywords", []),
                        "source": doc.get("source", ""),
                        "vector_score": round(similarity, 4),
                        "final_score": round(similarity, 4),
                    })

        results.sort(key=lambda x: x["vector_score"], reverse=True)
        return results[:top_k * 2]

    def _rerank_results(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not settings.RAG_USE_RERANKER or not candidates:
            return candidates[:top_k]

        query_lower = query.lower()
        scored = []

        for candidate in candidates:
            score = candidate.get("vector_score", 0)

            title = candidate.get("title", "").lower()
            content = candidate.get("content", "").lower()

            if query_lower in title:
                score += 0.3
            if query_lower in content:
                score += 0.1

            keywords = candidate.get("keywords", [])
            if isinstance(keywords, list):
                keyword_match = sum(
                    1 for kw in keywords if kw.lower() in query_lower or query_lower in kw.lower()
                )
                score += keyword_match * 0.05

            candidate["final_score"] = round(score, 4)
            scored.append(candidate)

        scored.sort(key=lambda x: x["final_score"], reverse=True)
        return scored[:top_k]

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        min_len = min(len(vec1), len(vec2))
        vec1 = vec1[:min_len]
        vec2 = vec2[:min_len]

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def get_stats(self) -> Dict[str, Any]:
        self.initialize()

        total_docs = len(self._documents)
        total_chunks = sum(len(d.get("chunks", [])) for d in self._documents)

        if self._vector_store:
            vector_count = self._vector_store.count()
        else:
            vector_count = total_chunks

        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "vector_store_count": vector_count,
            "backend": "milvus" if self._vector_store else "memory",
            "collection_name": settings.COLLECTION_NAME if self._vector_store else "memory",
        }

    def delete_document(self, document_id: str) -> bool:
        self.initialize()

        doc_to_remove = None
        for i, doc in enumerate(self._documents):
            if doc["id"] == document_id:
                doc_to_remove = doc
                self._documents.pop(i)
                break

        if not doc_to_remove:
            return False

        if self._vector_store:
            try:
                chunk_ids = [chunk["id"] for chunk in doc_to_remove.get("chunks", [])]
                if chunk_ids:
                    self._vector_store.delete(chunk_ids)
            except Exception as e:
                logger.error(f"Failed to delete document from Milvus: {e}")

        return True

    def clear_all(self) -> Dict[str, Any]:
        self._documents.clear()

        if self._vector_store:
            try:
                self._vector_store.drop_collection()
            except Exception as e:
                logger.error(f"Failed to clear Milvus collection: {e}")

        return {"success": True, "message": "Knowledge base cleared"}


_knowledge_base: Optional[KnowledgeBaseService] = None


def get_knowledge_base() -> KnowledgeBaseService:
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBaseService()
        _knowledge_base.initialize()
    return _knowledge_base


def reset_knowledge_base():
    global _knowledge_base
    if _knowledge_base:
        _knowledge_base = None