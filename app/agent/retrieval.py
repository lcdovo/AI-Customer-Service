"""
混合检索引擎 - 向量检索 + BM25 关键词检索
Phase 3 实现
支持多路召回 + 分数融合 + Reranker 重排序
"""
import math
import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter

from app.config.config import settings

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25 关键词检索器"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[Dict[str, Any]] = []
        self.doc_lens: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Dict[str, int] = {}
        self.corpus_size: int = 0

    def add_documents(self, documents: List[Dict[str, Any]]):
        for doc in documents:
            content = f"{doc.get('title', '')} {doc.get('content', '')}"
            tokens = self._tokenize(content)
            self.documents.append(doc)
            self.doc_lens.append(len(tokens))

            for token in set(tokens):
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        self.corpus_size = len(self.documents)
        self.avg_doc_len = sum(self.doc_lens) / max(self.corpus_size, 1)

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = re.findall(r'[\w]+', text)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)

        result = tokens
        for i in range(len(chinese_chars) - 1):
            result.append(chinese_chars[i] + chinese_chars[i + 1])
        result.extend(chinese_chars)

        return result

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self.corpus_size == 0:
            return []

        query_tokens = self._tokenize(query)
        scores = []

        for doc_idx, doc in enumerate(self.documents):
            content = f"{doc.get('title', '')} {doc.get('content', '')}"
            doc_tokens = self._tokenize(content)
            doc_len = self.doc_lens[doc_idx]

            score = 0.0
            token_counts = Counter(doc_tokens)

            for token in query_tokens:
                tf = token_counts.get(token, 0)
                if tf == 0:
                    continue

                df = self.doc_freqs.get(token, 0)
                idf = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1)

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_doc_len, 1))
                score += idf * numerator / denominator

            if score > 0:
                scores.append({
                    "index": doc_idx,
                    "score": score,
                    "document": doc,
                })

        scores.sort(key=lambda x: x["score"], reverse=True)
        results = []
        for item in scores[:top_k]:
            results.append({
                **item["document"],
                "bm25_score": round(item["score"], 4),
            })

        return results


class VectorRetriever:
    """
    向量检索器
    优先使用 Milvus 向量数据库，不可用时降级到内存模拟检索
    """

    def __init__(self, use_milvus: bool = None, milvus_host: str = None,
                 milvus_port: int = None, embedding_dim: int = None):
        self.documents: List[Dict[str, Any]] = []
        self.doc_vectors: List[List[float]] = []
        self._use_milvus = use_milvus if use_milvus is not None else settings.USE_MILVUS
        self._milvus_client = None
        self._embedding_dim = embedding_dim or settings.EMBEDDING_DIM
        self._backend = "memory"

        if self._use_milvus:
            self._init_milvus(milvus_host or settings.MILVUS_HOST,
                              milvus_port or settings.MILVUS_PORT,
                              self._embedding_dim)

    def _init_milvus(self, host: str, port: int, dim: int):
        try:
            from app.utils.milvus_client import get_milvus_client
            self._milvus_client = get_milvus_client(host=host, port=port, dim=dim)
            if self._milvus_client.connect():
                self._backend = "milvus"
                logger.info(f"VectorRetriever using Milvus ({host}:{port})")
            else:
                logger.warning("Milvus connection failed, falling back to memory")
                self._backend = "memory"
                self._milvus_client = None
        except Exception as e:
            logger.warning(f"Milvus init error: {e}, using memory fallback")
            self._backend = "memory"
            self._milvus_client = None

    @property
    def backend(self) -> str:
        return self._backend

    def add_documents(self, documents: List[Dict[str, Any]]):
        if self._backend == "milvus" and self._milvus_client:
            self._index_to_milvus(documents)
        else:
            self._index_to_memory(documents)

        self.documents.extend(documents)

    def _index_to_memory(self, documents: List[Dict[str, Any]]):
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_svc = get_embedding_service(dim=self._embedding_dim)
            for doc in documents:
                content = f"{doc.get('title', '')} {doc.get('content', '')} {doc.get('keywords', '')}"
                vector = embedding_svc.encode(content)
                self.doc_vectors.append(vector)
        except Exception:
            for doc in documents:
                content = f"{doc.get('title', '')} {doc.get('content', '')} {doc.get('keywords', '')}"
                vector = self._text_to_vector(content)
                self.doc_vectors.append(vector)

    def _index_to_milvus(self, documents: List[Dict[str, Any]]):
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_svc = get_embedding_service(dim=self._embedding_dim)

            to_insert = []
            vectors = []
            for i, doc in enumerate(documents):
                content = f"{doc.get('title', '')} {doc.get('content', '')} {doc.get('keywords', '')}"
                vector = embedding_svc.encode(content)
                doc_copy = dict(doc)
                if "id" not in doc_copy:
                    doc_copy["id"] = f"doc_{int(time.time())}_{i}"
                to_insert.append(doc_copy)
                vectors.append(vector)

            self._milvus_client.insert(to_insert, vectors)
            logger.info(f"Indexed {len(to_insert)} documents to Milvus")

        except Exception as e:
            logger.error(f"Milvus indexing error: {e}, falling back to memory")
            self._backend = "memory"
            self._index_to_memory(documents)

    def _text_to_vector(self, text: str) -> List[float]:
        text = text.lower()
        words = re.findall(r'[\w]+', text)
        chinese = re.findall(r'[\u4e00-\u9fff]+', text)

        terms = words + chinese
        term_freq = Counter(terms)
        total = len(terms) if terms else 1

        vector = [0.0] * self._embedding_dim
        for term, count in term_freq.items():
            hash_bytes = __import__('hashlib').sha256(term.encode('utf-8')).digest()
            for i in range(min(32, self._embedding_dim)):
                vector[i] += (hash_bytes[i] / 255.0) * (count / total)

        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 1e-8:
            vector = [x / norm for x in vector]

        return vector

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        min_len = min(len(vec1), len(vec2))
        vec1 = vec1[:min_len]
        vec2 = vec2[:min_len]

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self._backend == "milvus" and self._milvus_client:
            return self._search_milvus(query, top_k)
        return self._search_memory(query, top_k)

    def _search_milvus(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_svc = get_embedding_service(dim=self._embedding_dim)
            query_vector = embedding_svc.encode(query)

            results = self._milvus_client.search(
                query_embedding=query_vector,
                top_k=top_k,
                score_threshold=settings.RAG_SIMILARITY_THRESHOLD,
            )

            return [
                {
                    "id": r.get("id", ""),
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "category": r.get("category", ""),
                    "keywords": r.get("keywords", ""),
                    "source": r.get("source", ""),
                    "vector_score": r.get("score", 0),
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Milvus search error: {e}, falling back to memory")
            return self._search_memory(query, top_k)

    def _search_memory(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        try:
            from app.services.embedding_service import get_embedding_service
            embedding_svc = get_embedding_service(dim=self._embedding_dim)
            query_vector = embedding_svc.encode(query)
        except Exception:
            query_vector = self._text_to_vector(query)

        scores = []
        for idx, doc_vector in enumerate(self.doc_vectors):
            similarity = self._cosine_similarity(query_vector, doc_vector)
            if similarity > 0:
                scores.append({
                    "index": idx,
                    "score": similarity,
                    "document": self.documents[idx],
                })

        scores.sort(key=lambda x: x["score"], reverse=True)
        results = []
        for item in scores[:top_k]:
            results.append({
                **item["document"],
                "vector_score": round(item["score"], 4),
            })

        return results

    def health_check(self) -> Dict[str, Any]:
        if self._backend == "milvus" and self._milvus_client:
            healthy, msg = self._milvus_client.health_check()
            return {"backend": "milvus", "healthy": healthy, "message": msg}
        return {"backend": "memory", "healthy": True, "message": "Using memory fallback"}


class Reranker:
    """重排序器 - 基于规则的 Rerank"""

    @staticmethod
    def rerank(
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        query_lower = query.lower()
        scored_candidates = []

        for candidate in candidates:
            score = 0.0

            title = candidate.get("title", "").lower()
            content = candidate.get("content", "").lower()
            category = candidate.get("category", "").lower()

            if query_lower in title:
                score += 5.0
            if query_lower in content:
                score += 2.0

            keywords = candidate.get("keywords", [])
            if isinstance(keywords, list):
                keyword_overlap = sum(
                    1 for kw in keywords if kw.lower() in query_lower or query_lower in kw.lower()
                )
                score += keyword_overlap * 1.5

            bm25_score = candidate.get("bm25_score", 0)
            vector_score = candidate.get("vector_score", 0)
            score += bm25_score * 0.4 + vector_score * 0.3

            if category:
                score += 0.1

            scored_candidates.append({
                **candidate,
                "final_score": round(score, 4),
            })

        scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)
        return scored_candidates[:top_k]


class HybridRetriever:
    """混合检索引擎"""

    def __init__(
        self,
        bm25_weight: float = None,
        vector_weight: float = None,
        use_reranker: bool = None,
        use_milvus: bool = None,
        milvus_host: str = None,
        milvus_port: int = None,
        embedding_dim: int = None,
    ):
        self.bm25 = BM25Retriever()
        self.vector = VectorRetriever(
            use_milvus=use_milvus,
            milvus_host=milvus_host,
            milvus_port=milvus_port,
            embedding_dim=embedding_dim,
        )
        self.reranker = Reranker()
        self.bm25_weight = bm25_weight or settings.RAG_BM25_WEIGHT
        self.vector_weight = vector_weight or settings.RAG_VECTOR_WEIGHT
        self.use_reranker = use_reranker if use_reranker is not None else settings.RAG_USE_RERANKER
        self.documents: List[Dict[str, Any]] = []

    def index_documents(self, documents: List[Dict[str, Any]]):
        self.documents = documents
        self.bm25.add_documents(documents)
        self.vector.add_documents(documents)
        logger.info(f"已索引 {len(documents)} 个文档")

    def search(
        self,
        query: str,
        top_k: int = 3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        bm25_results = self.bm25.search(query, top_k=top_k * 2)
        vector_results = self.vector.search(query, top_k=top_k * 2)

        merged = self._merge_results(bm25_results, vector_results, query)

        if filters:
            merged = self._apply_filters(merged, filters)

        if self.use_reranker and merged:
            final_results = self.reranker.rerank(query, merged, top_k)
        else:
            final_results = merged[:top_k]

        execution_time = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "query": query,
            "results": final_results,
            "total_candidates": len(merged),
            "execution_time_ms": execution_time,
            "search_strategy": "hybrid_bm25_vector" if self.use_reranker else "hybrid_raw",
            "meta": {
                "bm25_candidates": len(bm25_results),
                "vector_candidates": len(vector_results),
                "reranked": self.use_reranker,
            },
        }

    def _merge_results(
        self,
        bm25_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        doc_map: Dict[str, Dict[str, Any]] = {}

        for result in bm25_results:
            key = result.get("title", "")
            if key:
                doc_map[key] = {
                    **result,
                    "_scores": {"bm25": result.get("bm25_score", 0)},
                }

        for result in vector_results:
            key = result.get("title", "")
            if key in doc_map:
                doc_map[key]["_scores"]["vector"] = result.get("vector_score", 0)
                doc_map[key]["vector_score"] = result.get("vector_score", 0)
            else:
                doc_map[key] = {
                    **result,
                    "_scores": {"vector": result.get("vector_score", 0)},
                }

        merged = []
        for key, doc in doc_map.items():
            scores = doc.pop("_scores", {})
            doc["bm25_score"] = scores.get("bm25", 0)
            doc["vector_score"] = scores.get("vector", 0)

            bm25_norm = min(doc.get("bm25_score", 0) / 5.0, 1.0)
            vector_norm = min(doc.get("vector_score", 0), 1.0)
            doc["hybrid_score"] = round(
                bm25_norm * self.bm25_weight + vector_norm * self.vector_weight, 4
            )
            merged.append(doc)

        return merged

    def _apply_filters(
        self,
        results: List[Dict[str, Any]],
        filters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        filtered = []
        for result in results:
            match = True

            if "category" in filters:
                if result.get("category") != filters["category"]:
                    match = False

            if "min_score" in filters:
                score = result.get("hybrid_score", 0)
                if score < filters["min_score"]:
                    match = False

            if match:
                filtered.append(result)

        return filtered


def create_default_hybrid_retriever(
    use_milvus: bool = None,
    milvus_host: str = None,
    milvus_port: int = None,
    embedding_dim: int = None,
) -> HybridRetriever:
    retriever = HybridRetriever(
        bm25_weight=settings.RAG_BM25_WEIGHT,
        vector_weight=settings.RAG_VECTOR_WEIGHT,
        use_reranker=settings.RAG_USE_RERANKER,
        use_milvus=use_milvus,
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        embedding_dim=embedding_dim,
    )

    default_documents = [
        {
            "title": "退换货政策",
            "content": "我们支持 7 天无理由退换货。商品需保持原包装、未经使用。退款将在收到商品后 3-7 个工作日内到账。部分特殊商品不支持退换。",
            "keywords": ["退换货", "退货", "退款", "7天", "无理由", "售后", "政策"],
            "category": "售后政策",
        },
        {
            "title": "订单查询",
            "content": "您可以通过订单号或手机号查询订单状态。物流信息在发货后 24 小时内更新。支持按时间段查询历史订单，也可查询多个订单。",
            "keywords": ["订单", "物流", "查询", "发货", "快递", "状态", "历史订单"],
            "category": "订单服务",
        },
        {
            "title": "会员权益",
            "content": "VIP 会员享受 95 折优惠、专属客服优先接入、免费包邮等权益。年度会员费 199 元。新用户首次开通额外赠送 30 天会员。",
            "keywords": ["会员", "VIP", "权益", "优惠", "包邮", "折扣", "专属客服"],
            "category": "会员服务",
        },
        {
            "title": "支付方式",
            "content": "我们支持支付宝、微信支付、银联、信用卡分期（3/6/12期）等多种支付方式。大额订单支持企业对公转账，需提前申请开通。",
            "keywords": ["支付", "付款", "支付宝", "微信", "银行卡", "分期", "转账"],
            "category": "支付服务",
        },
        {
            "title": "发票开具",
            "content": "购买后 180 天内可申请开具电子发票。请在订单详情页点击'申请发票'按钮填写抬头信息。增值税专用发票需额外提交企业资质材料。",
            "keywords": ["发票", "开票", "抬头", "电子发票", "增值税", "资质"],
            "category": "财务服务",
        },
        {
            "title": "物流配送",
            "content": "全国大部分地区 1-3 个工作日送达，偏远地区可能需要 3-5 个工作日。提供顺丰、京东、中通等多家快递公司可选，支持配送时间预约。",
            "keywords": ["物流", "配送", "快递", "送达", "发货", "时效", "预约"],
            "category": "物流服务",
        },
        {
            "title": "账号安全",
            "content": "建议使用强密码（至少8位，包含大小写字母和数字）。如怀疑账号被盗，请立即通过'忘记密码'功能重置密码，并联系客服冻结账号。",
            "keywords": ["密码", "账号", "安全", "登录", "被盗", "冻结", "重置"],
            "category": "账号服务",
        },
        {
            "title": "产品使用",
            "content": "产品首次使用请先充电 2 小时。长按电源键 3 秒开机。详细使用说明请参考产品包装盒内的《快速上手指南》。支持在线升级。",
            "keywords": ["使用", "开机", "充电", "设置", "安装", "教程", "升级"],
            "category": "产品支持",
        },
        {
            "title": "售后服务",
            "content": "所有产品享受 1 年免费质保。非人为损坏可享受免费维修或更换。质保期外提供有偿维修服务，费用按故障类型评估，提供官方检测报告。",
            "keywords": ["保修", "质保", "维修", "售后", "故障", "损坏", "检测"],
            "category": "售后服务",
        },
        {
            "title": "活动规则",
            "content": "新用户首单立减 20 元。满 199 减 30，满 399 减 80。促销活动不与其他优惠同享，具体以结算页为准。部分特价商品不参与活动。",
            "keywords": ["优惠", "活动", "促销", "折扣", "满减", "券", "特价"],
            "category": "营销活动",
        },
        {
            "title": "投诉处理",
            "content": "我们承诺每个投诉都会在 24 小时内响应。投诉处理完成后会通过电话或短信告知结果。如对处理结果不满，可申请升级处理。",
            "keywords": ["投诉", "处理", "响应", "升级", "不满意", "电话", "短信"],
            "category": "客户服务",
        },
        {
            "title": "企业采购",
            "content": "企业采购支持批量优惠、专属账户管理、定制化服务。单次采购满 5000 元可享受 9 折优惠，满 20000 元可享受 85 折。需提供企业资质证明。",
            "keywords": ["企业", "采购", "批量", "优惠", "定制", "账户", "资质"],
            "category": "企业服务",
        },
    ]

    retriever.index_documents(default_documents)
    return retriever
