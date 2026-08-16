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
    def _extract_query_terms(query: str) -> List[str]:
        terms = []
        english_words = re.findall(r'[a-zA-Z0-9]+', query.lower())
        terms.extend(english_words)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', query)
        terms.extend(chinese_chars)
        for i in range(len(chinese_chars) - 1):
            terms.append(chinese_chars[i] + chinese_chars[i + 1])
        return list(set(terms))

    @staticmethod
    def rerank(
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        query_lower = query.lower()
        query_terms = Reranker._extract_query_terms(query)
        scored_candidates = []

        for candidate in candidates:
            score = 0.0

            title = candidate.get("title", "").lower()
            content = candidate.get("content", "").lower()
            category = candidate.get("category", "").lower()

            if query_lower in title:
                score += 8.0
            if query_lower in content:
                score += 3.0

            keywords = candidate.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",") if k.strip()]
            if isinstance(keywords, list):
                keyword_text = " ".join(str(k) for k in keywords).lower()
                keyword_overlap = 0
                for kw in keywords:
                    kw_lower = str(kw).lower()
                    if kw_lower in query_lower or query_lower in kw_lower:
                        keyword_overlap += 2.0
                    else:
                        for qt in query_terms:
                            if len(qt) >= 2 and (qt in kw_lower or kw_lower in qt):
                                keyword_overlap += 0.5
                score += keyword_overlap

                for qt in query_terms:
                    if len(qt) >= 2 and qt in keyword_text:
                        score += 1.0

            bm25_score = candidate.get("bm25_score", 0)
            vector_score = candidate.get("vector_score", 0)
            hybrid_score = candidate.get("hybrid_score", 0)
            score += bm25_score * 0.3 + vector_score * 0.2 + hybrid_score * 2.0

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
        search_top_k_multiplier: int = None,
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
        self.search_top_k_multiplier = search_top_k_multiplier or settings.RAG_SEARCH_TOP_K_MULTIPLIER
        self.documents: List[Dict[str, Any]] = []

    def index_documents(self, documents: List[Dict[str, Any]]):
        self.documents = documents
        self.bm25.add_documents(documents)
        self.vector.add_documents(documents)
        logger.info(f"已索引 {len(documents)} 个文档")

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        search_k = top_k * self.search_top_k_multiplier
        bm25_results = self.bm25.search(query, top_k=search_k)
        vector_results = self.vector.search(query, top_k=search_k)

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
        search_top_k_multiplier=settings.RAG_SEARCH_TOP_K_MULTIPLIER,
        use_milvus=use_milvus,
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        embedding_dim=embedding_dim,
    )

    default_documents = [
        {
            "title": "7天无理由退换货政策",
            "content": (
                "我们支持7天无理由退换货服务。自收到商品之日起7天内，商品保持原包装完好、未经使用、不影响二次销售的情况下，均可申请退换货。"
                "退款将在收到退回商品后3-7个工作日内原路退回至您的支付账户。部分特殊商品如定制商品、食品、贴身衣物等不支持无理由退换。"
                "退货运费由买家承担，商品质量问题导致的退换除外。"
            ),
            "keywords": ["退换货", "退货", "退款", "7天", "无理由", "售后", "政策", "运费", "包装"],
            "category": "售后政策",
        },
        {
            "title": "退款处理流程",
            "content": (
                "退款流程如下：1) 在订单详情页点击'申请退款'或'申请退换货'；2) 选择退款原因并提交申请；"
                "3) 客服审核通过后，按要求寄回商品；4) 仓库收到商品并验收通过；5) 退款到账。"
                "仅退款申请将在审核通过后1-3个工作日内到账，退货退款需等待商品验收。"
                "退款金额将原路返回至付款账户，不支持退款至其他账户。"
            ),
            "keywords": ["退款", "流程", "退钱", "申请", "审核", "到账", "退货", "原路返回"],
            "category": "售后政策",
        },
        {
            "title": "订单查询与物流跟踪",
            "content": (
                "您可以通过以下方式查询订单：1) APP/官网登录后进入'我的订单'查看全部订单；"
                "2) 输入订单号或手机号在订单查询页面查询；3) 联系客服提供订单号查询。"
                "物流信息在发货后24小时内更新，可查看实时物流轨迹。支持按时间段查询历史订单，"
                "也可批量导出订单记录。如需发票，请在订单完成后180天内申请。"
            ),
            "keywords": ["订单", "物流", "查询", "跟踪", "快递", "发货", "轨迹", "手机号", "发票"],
            "category": "订单服务",
        },
        {
            "title": "VIP会员等级与权益",
            "content": (
                "我们的会员体系分为普通会员、银牌会员、金牌会员、钻石会员四个等级。"
                "普通会员：注册即可享受98折优惠。银牌会员（累计消费满1000元）：95折+专属客服。"
                "金牌会员（累计消费满5000元）：9折+免费包邮+优先发货。"
                "钻石会员（累计消费满20000元）：85折+专属活动+生日礼包+一对一客服经理。"
                "会员等级根据近12个月累计消费动态调整，每年1月1日重置计算。"
            ),
            "keywords": ["会员", "VIP", "等级", "权益", "折扣", "包邮", "优惠", "专属客服", "钻石"],
            "category": "会员服务",
        },
        {
            "title": "优惠券使用规则",
            "content": (
                "优惠券分为满减券、折扣券、无门槛券三种类型。满减券需满足指定消费金额条件，"
                "如满199减30、满399减80。折扣券直接按折扣比例结算，如8折券、9折券。"
                "无门槛券可直接抵扣现金，不受消费金额限制。使用规则：1) 单笔订单限用1张优惠券；"
                "2) 优惠券不可与其他优惠同享；3) 优惠券有效期为领取后7-30天；"
                "4) 优惠券过期自动作废，不予补发；5) 部分特价商品和预售商品不可使用优惠券。"
            ),
            "keywords": ["优惠券", "满减", "折扣", "规则", "使用", "有效期", "作废", "同享", "特价"],
            "category": "营销活动",
        },
        {
            "title": "限时促销与满减活动",
            "content": (
                "当前促销活动：1) 新用户首单立减20元（限首单，不与其他优惠同享）；"
                "2) 满199减30，满399减80，满599减150；3) 会员日（每月18日）会员享额外9折；"
                "4) 限时秒杀：每日10点、14点、20点开启，数量有限先到先得；"
                "5) 拼团优惠：邀请好友拼团，满2人享受8折。"
                "注意事项：促销活动不与其他优惠同享，具体以结算页显示为准。部分特价商品不参与任何活动。"
            ),
            "keywords": ["优惠", "活动", "促销", "折扣", "满减", "券", "特价", "秒杀", "拼团", "会员日"],
            "category": "营销活动",
        },
        {
            "title": "支付方式与安全保障",
            "content": (
                "我们支持以下支付方式：1) 支付宝（推荐，支持花呗分期）；2) 微信支付；"
                "3) 银联云闪付；4) 银行卡快捷支付（支持主流银行储蓄卡和信用卡）；"
                "5) 信用卡分期（3期、6期、12期，手续费由银行收取）；6) 企业对公转账（需提前申请）。"
                "所有支付均通过SSL加密传输，支付信息不会存储在我们的服务器上。"
                "如遇支付问题，请保存支付凭证联系客服处理。"
            ),
            "keywords": ["支付", "付款", "支付宝", "微信", "银行卡", "分期", "安全", "加密", "SSL", "花呗"],
            "category": "支付服务",
        },
        {
            "title": "发票开具与管理",
            "content": (
                "发票相关服务：1) 电子发票：购买后180天内可在订单详情页申请开具，1-3个工作日内开具完成；"
                "2) 增值税专用发票：需提供企业营业执照、税务登记证等资质，审核通过后开具；"
                "3) 发票抬头修改：未开具的订单可在订单页修改抬头信息；"
                "4) 发票遗失：电子发票可重复下载，纸质发票遗失需联系客服补办（可能产生工本费）；"
                "5) 发票内容：商品明细、服务名称等需与实际订单一致。"
            ),
            "keywords": ["发票", "开票", "抬头", "电子发票", "增值税", "资质", "营业执照", "明细", "补办"],
            "category": "财务服务",
        },
        {
            "title": "物流配送时效说明",
            "content": (
                "配送时效：1) 一线城市（北京、上海、广州、深圳等）：1-2个工作日送达；"
                "2) 省会城市及地级市：2-3个工作日送达；3) 县级市及偏远地区：3-5个工作日送达；"
                "4) 新疆、西藏、青海等特殊地区：5-7个工作日送达。"
                "我们与顺丰、京东、中通、圆通等多家快递公司合作，您可在结算时选择指定快递。"
                "支持配送时间预约（工作日/周末/指定时段），大件商品可能需要额外配送费用。"
            ),
            "keywords": ["物流", "配送", "快递", "时效", "送达", "发货", "顺丰", "京东", "偏远", "预约", "几天", "到货"],
            "category": "物流服务",
        },
        {
            "title": "账号安全与密码保护",
            "content": (
                "账号安全建议：1) 使用强密码，至少8位，包含大小写字母、数字和特殊字符；"
                "2) 定期更换密码，建议每3个月一次；3) 开启手机验证，登录时需要短信验证码；"
                "4) 不要在公共设备上勾选'记住密码'；5) 如怀疑账号被盗，立即通过'忘记密码'重置；"
                "6) 联系客服冻结账号，防止进一步损失。我们不会通过任何方式索要您的密码和验证码。"
            ),
            "keywords": ["密码", "账号", "安全", "登录", "被盗", "冻结", "重置", "验证", "短信", "强密码"],
            "category": "账号服务",
        },
        {
            "title": "产品使用与维护指南",
            "content": (
                "产品首次使用：1) 新设备首次使用请先充电2-3小时，电量充满后再开机；"
                "2) 长按电源键3秒开机，首次开机会有引导设置；3) 详细使用说明请参考包装盒内的《快速上手指南》。"
                "日常维护：1) 保持设备清洁，避免灰尘进入接口；2) 避免长时间阳光直射；"
                "3) 不使用时请定期充电，保持电池活性；4) 定期进行系统固件升级，获取最新功能和安全补丁；"
                "5) 如遇异常，可尝试恢复出厂设置（请注意备份数据）。"
            ),
            "keywords": ["使用", "开机", "充电", "设置", "安装", "教程", "升级", "维护", "清洁", "固件"],
            "category": "产品支持",
        },
        {
            "title": "产品质保与维修服务",
            "content": (
                "质保政策：1) 整机免费质保1年，自购买日起计算；2) 核心部件（如主板、屏幕等）免费质保2年；"
                "3) 质保期内，非人为损坏可享受免费维修或更换；4) 质保期外提供有偿维修服务，费用按故障类型评估。"
                "维修流程：1) 联系客服提交维修申请；2) 客服指导排查问题；3) 确认需要维修后，寄送至指定维修中心；"
                "4) 维修完成后寄回（质保期内运费由我们承担）；5) 维修周期一般为3-7个工作日。"
            ),
            "keywords": ["保修", "质保", "维修", "售后", "故障", "损坏", "检测", "更换", "免费", "部件"],
            "category": "售后服务",
        },
        {
            "title": "客服投诉处理时效",
            "content": (
                "我们承诺所有客服投诉将在24小时内首次响应，简单问题当日解决，复杂问题3个工作日内给出解决方案。"
                "处理结果将通过短信、电话或站内消息通知您。如对处理结果不满意，可通过以下方式升级："
                "1) 在投诉详情页点击'申请升级处理'；2) 拨打客服热线400-888-8888转投诉专线；"
                "3) 发送邮件至complaint@example.com。升级投诉将由高级客服专员处理。"
            ),
            "keywords": ["投诉", "时效", "响应", "升级", "处理", "客服", "不满意", "热线", "邮件"],
            "category": "客户服务",
        },
        {
            "title": "售后服务联系方式",
            "content": (
                "客服联系方式：1) 在线客服：APP/官网右下角客服图标，7x24小时服务；"
                "2) 客服热线：400-888-8888，工作日9:00-22:00，周末9:00-18:00；"
                "3) 邮件客服：support@example.com，通常24小时内回复；"
                "4) 在线客服：APP/官网'我的客服'入口；5) 社交媒体：官方微博、微信公众号。"
                "VIP会员享有专属客服通道，平均响应时间小于30秒。"
            ),
            "keywords": ["客服", "联系", "电话", "在线", "邮件", "热线", "微信", "微博", "响应", "VIP"],
            "category": "客户服务",
        },
        {
            "title": "企业采购与定制服务",
            "content": (
                "企业采购服务：1) 批量优惠：单次采购满5000元享9折，满20000元享85折，满50000元享8折；"
                "2) 专属账户：为企业分配专属客户经理和独立账户管理；"
                "3) 定制化服务：支持企业LOGO定制、包装定制、批量采购定制方案；"
                "4) 集中采购：支持年框协议、按需分批供货；5) 发票服务：支持按季度/年度统一开票。"
                "申请企业采购需提供企业营业执照、税务登记证等资质证明。"
            ),
            "keywords": ["企业", "采购", "批量", "优惠", "定制", "账户", "资质", "客户经理", "年框", "LOGO"],
            "category": "企业服务",
        },
    ]

    retriever.index_documents(default_documents)
    return retriever
