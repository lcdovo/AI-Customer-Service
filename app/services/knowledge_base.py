"""
知识库服务 - 文档分块、向量化、存储、检索
支持多种分块策略：按句子、按段落、固定长度
支持混合检索：向量检索 + BM25 关键词检索
支持查询缓存与查询扩展
支持 MySQL 持久化存储
"""
import re
import time
import uuid
import logging
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import Counter

from app.config.config import settings
from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class QueryCache:
    """查询结果缓存 - 避免重复计算"""

    def __init__(self, max_size: int = 200, ttl: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, ts = self._cache[key]
        if time.time() - ts > self._ttl:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any):
        if len(self._cache) >= self._max_size:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]
        self._cache[key] = (value, time.time())

    def clear(self):
        self._cache.clear()

    @staticmethod
    def make_key(query: str, top_k: int, threshold: float) -> str:
        raw = f"{query}|{top_k}|{threshold}"
        return hashlib.md5(raw.encode()).hexdigest()


class BM25Scorer:
    """BM25 关键词检索评分器"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._corpus: List[str] = []
        self._doc_count = 0
        self._avg_dl = 0.0
        self._df: Dict[str, int] = {}

    def build_index(self, documents: List[str]):
        self._corpus = documents
        self._doc_count = len(documents)
        if not documents:
            return

        total_len = 0
        self._df = {}

        for doc in documents:
            tokens = self._tokenize(doc)
            total_len += len(tokens)
            seen = set()
            for token in tokens:
                if token not in seen:
                    self._df[token] = self._df.get(token, 0) + 1
                    seen.add(token)

        self._avg_dl = total_len / max(self._doc_count, 1)

    def score(self, query: str, doc_idx: int) -> float:
        if doc_idx >= len(self._corpus) or self._doc_count == 0:
            return 0.0

        query_tokens = self._tokenize(query)
        doc_tokens = self._tokenize(self._corpus[doc_idx])

        if not doc_tokens or not query_tokens:
            return 0.0

        tf = Counter(doc_tokens)
        doc_len = len(doc_tokens)
        score = 0.0

        for qt in set(query_tokens):
            f = tf.get(qt, 0)
            if f == 0:
                continue
            df = self._df.get(qt, 0)
            idf = (self._doc_count - df + 0.5) / (df + 0.5) + 1
            idf = max(0, idf)
            tf_norm = (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * doc_len / max(self._avg_dl, 1)))
            score += idf * tf_norm

        return score

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        text = text.lower().strip()
        tokens = []
        english = re.findall(r'[a-zA-Z0-9]+', text)
        tokens.extend(english)
        chinese = re.findall(r'[\u4e00-\u9fff]', text)
        tokens.extend(chinese)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i] + chinese[i + 1])
        return tokens


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
        self._query_cache = QueryCache(max_size=500, ttl=600)
        self._bm25 = BM25Scorer()
        self._bm25_built = False
        self._bm25_chunks = []

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
                    self._load_bm25_from_milvus()
                else:
                    logger.warning("KnowledgeBase: Milvus connection failed, using memory")
                    self._vector_store = None
            except Exception as e:
                logger.warning(f"KnowledgeBase: Milvus init error: {e}")
                self._vector_store = None
        else:
            logger.info("KnowledgeBase: Using memory-based storage")

        self._load_from_mysql()

        self._initialized = True

    def _load_from_mysql(self):
        """从 MySQL 加载文档元数据 (同步方式)"""
        try:
            from app.config.config import settings
            import pymysql

            conn = pymysql.connect(
                host=settings.MYSQL_HOST,
                port=int(settings.MYSQL_PORT),
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, title, category, chunk_count, created_at FROM knowledge_docs ORDER BY id")
                    rows = cursor.fetchall()
                    for row in rows:
                        self._documents.append({
                            "id": f"doc_mysql_{row[0]}",
                            "title": row[1],
                            "category": row[2],
                            "content": "",
                            "keywords": [],
                            "source": "mysql",
                            "chunks": [],
                            "chunk_count": row[3] or 0,
                            "created_at": str(row[4]) if row[4] else "",
                        })
                    if rows:
                        logger.info(f"Loaded {len(rows)} documents from MySQL")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to load documents from MySQL: {e}")

    def _load_bm25_from_milvus(self):
        """从Milvus加载所有chunk数据用于BM25索引"""
        if not self._vector_store:
            return
        try:
            chunks = self._vector_store.query_all(limit=10000)
            if chunks:
                self._bm25.build_index([c["content"] for c in chunks])
                self._bm25_chunks = chunks
                self._bm25_built = True
                logger.info(f"BM25 index loaded from Milvus: {len(chunks)} chunks")
        except Exception as e:
            logger.warning(f"Failed to load BM25 from Milvus: {e}")

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
        self._bm25_built = False
        self._query_cache.clear()

        if self._vector_store and self._bm25_chunks:
            for chunk in chunks:
                self._bm25_chunks.append({
                    "id": chunk["id"],
                    "title": title,
                    "content": chunk["content"],
                    "category": category,
                    "keywords": ",".join(keywords) if keywords else "",
                    "source": source,
                })
            self._bm25_built = False

        for chunk, embedding in zip(chunks, embeddings):
            chunk["_embedding"] = embedding

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
            logger.info(f"Document '{title}' stored in memory with {len(chunks)} chunks")

        self._save_to_mysql(doc_record)

        return {
            "success": True,
            "document_id": doc_record["id"],
            "chunks_count": len(chunks),
        }

    def _save_to_mysql(self, doc_record: Dict[str, Any]):
        """保存文档到 MySQL (同步方式)"""
        try:
            from app.config.config import settings
            import pymysql

            conn = pymysql.connect(
                host=settings.MYSQL_HOST,
                port=int(settings.MYSQL_PORT),
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cursor:
                    sql = """INSERT INTO knowledge_docs 
                             (title, category, content, chunk_count, version, is_published, created_at, updated_at)
                             VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())"""
                    content = doc_record["content"][:65000]
                    cursor.execute(sql, (
                        doc_record["title"],
                        doc_record.get("category", ""),
                        content,
                        len(doc_record.get("chunks", [])),
                        1,
                        True,
                    ))
                conn.commit()
                logger.info(f"Saved document '{doc_record['title']}' to MySQL")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to save document to MySQL: {e}")

    def _delete_from_mysql(self, doc_record: Dict[str, Any]):
        """从 MySQL 删除文档 (同步方式)"""
        try:
            from app.config.config import settings
            import pymysql

            conn = pymysql.connect(
                host=settings.MYSQL_HOST,
                port=int(settings.MYSQL_PORT),
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM knowledge_docs WHERE title=%s AND category=%s",
                        (doc_record.get("title", ""), doc_record.get("category", ""))
                    )
                conn.commit()
                logger.info(f"Deleted document '{doc_record.get('title', '')}' from MySQL")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to delete from MySQL: {e}")

    def _clear_mysql(self):
        """清空 MySQL 文档表 (同步方式)"""
        try:
            from app.config.config import settings
            import pymysql

            conn = pymysql.connect(
                host=settings.MYSQL_HOST,
                port=int(settings.MYSQL_PORT),
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM knowledge_docs")
                conn.commit()
                logger.info("Cleared all documents from MySQL")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to clear MySQL: {e}")

    def search(
        self,
        query: str,
        top_k: int = None,
        similarity_threshold: float = None,
    ) -> Dict[str, Any]:
        self.initialize()

        top_k = top_k or settings.RAG_TOP_K
        similarity_threshold = similarity_threshold or settings.RAG_SIMILARITY_THRESHOLD

        cache_key = QueryCache.make_key(query, top_k, similarity_threshold)
        cached = self._query_cache.get(cache_key)
        if cached:
            return {**cached, "from_cache": True}

        query_embedding = self._embedding_service.encode(query)

        if self._vector_store:
            try:
                vector_results = self._vector_store.search(
                    query_embedding=query_embedding,
                    top_k=top_k * 2,
                    score_threshold=similarity_threshold,
                )
                if not vector_results:
                    vector_results = self._memory_search(query_embedding, query, top_k, similarity_threshold)
            except Exception as e:
                logger.error(f"Milvus search error: {e}")
                vector_results = self._memory_search(query_embedding, query, top_k, similarity_threshold)
        else:
            vector_results = self._memory_search(query_embedding, query, top_k, similarity_threshold)

        bm25_results = self._bm25_search(query, top_k)

        merged = self._merge_results(vector_results, bm25_results, top_k)

        reranked = self._rerank_results(query, merged, top_k)

        strategy = "hybrid" if (vector_results and bm25_results) else (
            "vector" if vector_results else "memory"
        )
        if not vector_results and not bm25_results:
            strategy = "empty"

        result = {
            "success": True,
            "query": query,
            "results": reranked,
            "total_candidates": len(merged),
            "search_strategy": strategy,
            "from_cache": False,
        }

        self._query_cache.set(cache_key, result)
        return result

    def _bm25_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        corpus = []
        meta_chunks = []

        if self._bm25_chunks:
            meta_chunks = self._bm25_chunks
            corpus = [c["content"] for c in meta_chunks]
        elif self._documents:
            for doc in self._documents:
                for chunk in doc["chunks"]:
                    corpus.append(chunk["content"])
                    meta_chunks.append({
                        "id": chunk["id"],
                        "title": doc["title"],
                        "category": doc.get("category", ""),
                        "keywords": doc.get("keywords", []),
                        "source": doc.get("source", ""),
                    })

        if not corpus:
            return []

        if not self._bm25_built:
            self._bm25.build_index(corpus)
            self._bm25_built = True

        results = []
        for idx, meta in enumerate(meta_chunks):
            score = self._bm25.score(query, idx)
            if score > 0:
                results.append({
                    "id": meta["id"],
                    "title": meta.get("title", ""),
                    "content": corpus[idx] if idx < len(corpus) else "",
                    "category": meta.get("category", ""),
                    "keywords": meta.get("keywords", []),
                    "source": meta.get("source", ""),
                    "vector_score": 0.0,
                    "bm25_score": score,
                    "final_score": score,
                })

        results.sort(key=lambda x: x.get("bm25_score", 0), reverse=True)
        return results[:top_k * 2]

    def _merge_results(
        self,
        vector_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not bm25_results:
            return vector_results
        if not vector_results:
            return bm25_results

        merged = {}
        all_docs = vector_results + bm25_results

        max_vector = max((r.get("vector_score", 0) for r in vector_results), default=1.0)
        max_bm25 = max((r.get("bm25_score", 0) for r in bm25_results), default=1.0)

        for doc in all_docs:
            doc_id = doc.get("id", "")
            if doc_id not in merged:
                merged[doc_id] = doc.copy()
                merged[doc_id]["vector_score"] = 0.0
                merged[doc_id]["bm25_score"] = 0.0

            if "vector_score" in doc:
                normalized = doc.get("vector_score", 0) / max(max_vector, 0.001)
                merged[doc_id]["vector_score"] = max(merged[doc_id].get("vector_score", 0), normalized)

            if "bm25_score" in doc:
                normalized = doc.get("bm25_score", 0) / max(max_bm25, 0.001)
                merged[doc_id]["bm25_score"] = max(merged[doc_id].get("bm25_score", 0), normalized)

        alpha = settings.RAG_VECTOR_WEIGHT
        beta = 1.0 - alpha

        for doc_id, doc in merged.items():
            vec_s = doc.get("vector_score", 0)
            bm_s = doc.get("bm25_score", 0)
            doc["final_score"] = round(alpha * vec_s + beta * bm_s, 4)

        results = list(merged.values())
        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return results[:top_k * 2]

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
        if not candidates:
            return []

        query_lower = query.lower()
        query_tokens = BM25Scorer._tokenize(query)
        query_chars = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', query_lower))
        scored = []
        seen_contents = set()

        for candidate in candidates:
            content_hash = candidate.get("content", "")[:100]
            if content_hash in seen_contents:
                continue
            seen_contents.add(content_hash)

            score = candidate.get("final_score", candidate.get("vector_score", 0))

            title = candidate.get("title", "").lower()
            content = candidate.get("content", "").lower()

            if query_lower in title:
                score += 0.3
            elif any(t in title for t in query_chars):
                score += 0.15

            if query_lower in content:
                score += 0.2
            elif any(t in content for t in query_chars):
                score += 0.1

            title_words = set(re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]', title))
            content_words = set(re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]', content))
            token_overlap = sum(1 for t in query_tokens if t in title_words or t in content_words)
            score += min(token_overlap * 0.04, 0.2)

            keywords = candidate.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",") if k.strip()]
            if isinstance(keywords, list):
                keyword_match = sum(
                    1 for kw in keywords
                    if kw.lower() in query_lower or query_lower in kw.lower()
                )
                score += min(keyword_match * 0.1, 0.3)

            cat = candidate.get("category", "")
            if cat and cat.lower() in query_lower:
                score += 0.15

            if len(content) > 50:
                score += 0.02

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
        total_chunks = sum(d.get("chunk_count", len(d.get("chunks", []))) for d in self._documents)

        if self._vector_store:
            vector_count = self._vector_store.count()
        else:
            vector_count = total_chunks

        try:
            from app.config.config import settings
            import pymysql
            conn = pymysql.connect(
                host=settings.MYSQL_HOST,
                port=int(settings.MYSQL_PORT),
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                database=settings.MYSQL_DATABASE,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*), COALESCE(SUM(chunk_count),0) FROM knowledge_docs")
                    row = cursor.fetchone()
                    mysql_docs = row[0] or 0
                    mysql_chunks = row[1] or 0
                    if mysql_docs > 0:
                        total_docs = mysql_docs
                        total_chunks = mysql_chunks
            finally:
                conn.close()
        except Exception:
            pass

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
            if doc["id"] == document_id or doc.get("id") == document_id:
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

        self._delete_from_mysql(doc_to_remove)

        return True

    def _delete_from_mysql(self, doc_record: Dict[str, Any]):
        """从 MySQL 删除文档"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._async_delete_from_mysql(doc_record))
            else:
                loop.run_until_complete(self._async_delete_from_mysql(doc_record))
        except Exception as e:
            logger.warning(f"Failed to delete document from MySQL: {e}")

    async def _async_delete_from_mysql(self, doc_record: Dict[str, Any]):
        """异步从 MySQL 删除文档"""
        try:
            from app.utils.database import async_session
            from app.models.models import KnowledgeDoc
            from sqlalchemy import delete

            async with async_session() as session:
                title = doc_record.get("title", "")
                category = doc_record.get("category", "")
                await session.execute(
                    delete(KnowledgeDoc).where(
                        KnowledgeDoc.title == title,
                        KnowledgeDoc.category == category,
                    )
                )
                await session.commit()
                logger.info(f"Deleted document '{title}' from MySQL")
        except Exception as e:
            logger.warning(f"Failed to delete from MySQL: {e}")

    def clear_all(self) -> Dict[str, Any]:
        self._documents.clear()
        self._query_cache.clear()
        self._bm25 = BM25Scorer()
        self._bm25_built = False
        self._bm25_chunks = []

        if self._vector_store:
            try:
                self._vector_store.drop_collection()
                self._vector_store.connect()
            except Exception as e:
                logger.error(f"Failed to clear Milvus collection: {e}")

        self._clear_mysql()

        return {"success": True, "message": "Knowledge base cleared"}

    def _clear_mysql(self):
        """清空 MySQL 文档表"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._async_clear_mysql())
            else:
                loop.run_until_complete(self._async_clear_mysql())
        except Exception as e:
            logger.warning(f"Failed to clear MySQL: {e}")

    async def _async_clear_mysql(self):
        """异步清空 MySQL"""
        try:
            from app.utils.database import async_session
            from app.models.models import KnowledgeDoc
            from sqlalchemy import delete

            async with async_session() as session:
                await session.execute(delete(KnowledgeDoc))
                await session.commit()
                logger.info("Cleared all documents from MySQL")
        except Exception as e:
            logger.warning(f"Failed to clear MySQL: {e}")


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