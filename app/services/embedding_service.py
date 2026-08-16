"""
Embedding 服务 - 文本向量化
支持多种 Embedding 后端，优先使用真实API，自动降级到本地模拟
"""
import os
import math
import hashlib
import json
import logging
import time
from typing import List, Optional, Dict, Any
from collections import Counter

import httpx

logger = logging.getLogger(__name__)


class BaseEmbedding:
    """Embedding 基类"""

    dim: int = 1024
    name: str = "base"

    def encode(self, text: str) -> List[float]:
        raise NotImplementedError

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.encode(t) for t in texts]

    def is_available(self) -> bool:
        return True


class APIEmbedding(BaseEmbedding):
    """
    API 驱动的 Embedding 后端
    支持 DashScope / 智谱 / OpenAI 兼容格式
    通过环境变量配置：EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_MODEL
    """

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        dim: int = 1024,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.name = f"api({model})"
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.Client] = None
        self._text_cache: Dict[str, List[float]] = {}

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def encode(self, text: str) -> List[float]:
        cache_key = f"{self.model}:{text}"
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]

        vector = self._call_api([text])[0]
        self._text_cache[cache_key] = vector
        return vector

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        uncached = []
        uncached_indices = []
        results: List[Optional[List[float]]] = [None] * len(texts)

        for i, text in enumerate(texts):
            cache_key = f"{self.model}:{text}"
            if cache_key in self._text_cache:
                results[i] = self._text_cache[cache_key]
            else:
                uncached.append(text)
                uncached_indices.append(i)

        if uncached:
            batch_vectors = self._call_api(uncached)
            for idx, vec in zip(uncached_indices, batch_vectors):
                results[idx] = vec
                cache_key = f"{self.model}:{texts[idx]}"
                self._text_cache[cache_key] = vec

        return [r if r is not None else [0.0] * self.dim for r in results]

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                client = self._get_client()

                payload = {
                    "model": self.model,
                    "input": texts,
                    "encoding_format": "float",
                }

                response = client.post(
                    f"{self.api_base}/embeddings",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                if "data" not in data:
                    raise ValueError(f"Unexpected API response: {data}")

                vectors = []
                for item in data["data"]:
                    vector = item.get("embedding", [])
                    if not vector or len(vector) == 0:
                        vector = [0.0] * self.dim
                    elif len(vector) != self.dim:
                        vector = self._pad_or_truncate(vector, self.dim)
                    vectors.append(vector)

                return vectors

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"Embedding API error (attempt {attempt + 1}): HTTP {e.response.status_code}")
                if e.response.status_code >= 500:
                    time.sleep(1 * (attempt + 1))
                else:
                    break
            except Exception as e:
                last_error = e
                logger.warning(f"Embedding API error (attempt {attempt + 1}): {e}")
                time.sleep(1 * (attempt + 1))

        logger.error(f"Embedding API failed after {self.max_retries + 1} attempts: {last_error}")
        raise RuntimeError(f"Embedding API error: {last_error}")

    @staticmethod
    def _pad_or_truncate(vector: List[float], target_dim: int) -> List[float]:
        if len(vector) >= target_dim:
            return vector[:target_dim]
        result = vector.copy()
        result.extend([0.0] * (target_dim - len(result)))
        return result

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None


class MockEmbedding(BaseEmbedding):
    """
    本地模拟 Embedding - 基于哈希的伪向量生成
    当没有真实 Embedding 服务时使用
    """

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.name = "mock"
        self._text_cache: Dict[str, List[float]] = {}

    def encode(self, text: str) -> List[float]:
        if text in self._text_cache:
            return self._text_cache[text]

        vector = self._text_to_embedding(text)
        self._text_cache[text] = vector
        return vector

    def _text_to_embedding(self, text: str) -> List[float]:
        text_lower = text.lower().strip()
        words = self._tokenize(text_lower)

        if not words:
            return [0.0] * self.dim

        word_vectors = {}
        for word in words:
            word_vectors[word] = self._word_to_vector(word)

        aggregated = [0.0] * self.dim
        word_counts = Counter(words)
        total = len(words)

        for word, count in word_counts.items():
            wv = word_vectors[word]
            weight = count / total
            for i in range(self.dim):
                aggregated[i] += wv[i] * weight

        norm = math.sqrt(sum(x * x for x in aggregated))
        if norm > 1e-8:
            aggregated = [x / norm for x in aggregated]

        return aggregated

    def _word_to_vector(self, word: str) -> List[float]:
        hash_bytes = hashlib.sha256(word.encode('utf-8')).digest()
        vector = []
        for i in range(0, self.dim, 32):
            chunk = hash_bytes[i % len(hash_bytes):i % len(hash_bytes) + 32]
            for j in range(0, 32, 4):
                if len(vector) >= self.dim:
                    break
                val = int.from_bytes(chunk[j:j + 4], 'big')
                normalized = (val / 0xFFFFFFFF) * 2 - 1
                vector.append(normalized)

        while len(vector) < self.dim:
            vector.append(0.0)
        vector = vector[:self.dim]

        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 1e-8:
            vector = [x / norm for x in vector]
        return vector

    def _tokenize(self, text: str) -> List[str]:
        import re
        tokens = []
        english_words = re.findall(r'[a-zA-Z0-9]+', text)
        tokens.extend(english_words)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        tokens.extend(chinese_chars)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i + 1])
        return tokens


class EmbeddingService:
    """Embedding 服务管理器"""

    def __init__(self, dim: int = 1024):
        self._dim = dim
        self._embedding: BaseEmbedding = MockEmbedding(dim=dim)
        self._backend_name = "mock"

        self._try_init_api_backend()

    def _try_init_api_backend(self):
        from app.config.config import settings

        api_base = settings.EMBEDDING_API_BASE
        api_key = settings.EMBEDDING_API_KEY
        model = settings.EMBEDDING_MODEL

        if not api_base or not api_key or not model:
            logger.info("No Embedding API config found, using mock backend")
            return

        try:
            dim = int(settings.EMBEDDING_DIM or self._dim)
            api_embedding = APIEmbedding(
                api_base=api_base,
                api_key=api_key,
                model=model,
                dim=dim,
            )
            test_result = api_embedding.encode("test")
            self._embedding = api_embedding
            self._backend_name = f"api({model})"
            self._dim = dim
            logger.info(f"Embedding API backend ready: {model} (dim={dim})")
        except Exception as e:
            logger.warning(f"Embedding API init failed: {e}, using mock fallback")
            self._embedding = MockEmbedding(dim=self._dim)
            self._backend_name = "mock"

    def get_embedding(self) -> BaseEmbedding:
        return self._embedding

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def dim(self) -> int:
        return self._embedding.dim

    def encode(self, text: str) -> List[float]:
        return self._embedding.encode(text)

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        return self._embedding.encode_batch(texts)

    def switch_backend(self, backend: str) -> bool:
        if backend == "mock":
            self._embedding = MockEmbedding(dim=self._dim)
            self._backend_name = "mock"
            logger.info("Switched to mock embedding backend")
            return True

        if backend == "api":
            self._try_init_api_backend()
            return self._backend_name.startswith("api")

        logger.warning(f"Unknown embedding backend: {backend}")
        return False

    def health_check(self) -> Dict[str, Any]:
        return {
            "backend": self._backend_name,
            "dim": self._embedding.dim,
            "available": self._embedding.is_available(),
        }


_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(dim: int = 1024) -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(dim=dim)
    return _embedding_service


def reset_embedding_service():
    global _embedding_service
    if _embedding_service and isinstance(_embedding_service._embedding, APIEmbedding):
        _embedding_service._embedding.close()
    _embedding_service = None