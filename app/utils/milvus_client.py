"""
Milvus 客户端封装
提供向量集合管理、插入、搜索等核心能力
支持健康检查和优雅降级
"""
import logging
import time
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

VECTOR_FIELD = "embedding"
PRIMARY_FIELD = "id"


def _get_default_collection_name() -> str:
    try:
        from app.config.config import settings
        return settings.COLLECTION_NAME
    except Exception:
        return "customer_service_knowledge"


class MilvusClient:
    """Milvus 向量数据库客户端"""

    def __init__(self, host: str = "localhost", port: int = 19530, dim: int = 1024, collection_name: str = None):
        self.host = host
        self.port = port
        self.dim = dim
        self.collection_name = collection_name or _get_default_collection_name()
        self._connected = False
        self._collection = None
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        try:
            from pymilvus import connections, utility

            self._client = connections.connect(
                alias="default",
                host=self.host,
                port=str(self.port),
                timeout=10,
            )

            if not utility.has_collection(self.collection_name):
                self._create_collection()
            else:
                self._load_collection()

            self._connected = True
            logger.info(f"Connected to Milvus at {self.host}:{self.port}, collection: {self.collection_name}")
            return True

        except ImportError:
            logger.warning("pymilvus not installed, Milvus unavailable")
            self._connected = False
            return False
        except Exception as e:
            logger.warning(f"Failed to connect Milvus: {e}")
            self._connected = False
            return False

    def disconnect(self):
        try:
            from pymilvus import connections
            connections.disconnect("default")
        except Exception:
            pass
        self._connected = False
        self._collection = None

    def _create_collection(self):
        from pymilvus import CollectionSchema, FieldSchema, DataType, Collection

        fields = [
            FieldSchema(name=PRIMARY_FIELD, dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name=VECTOR_FIELD, dtype=DataType.FLOAT_VECTOR, dim=self.dim),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="keywords", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="updated_at", dtype=DataType.VARCHAR, max_length=64),
        ]

        schema = CollectionSchema(fields, description="Customer Service Knowledge Base")
        self._collection = Collection(name=self.collection_name, schema=schema)

        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256},
        }
        self._collection.create_index(field_name=VECTOR_FIELD, index_params=index_params)

        self._collection.load()
        logger.info(f"Created collection: {self.collection_name} (dim={self.dim})")

    def _load_collection(self):
        from pymilvus import Collection
        self._collection = Collection(name=self.collection_name)
        self._collection.load()
        logger.info(f"Loaded collection: {self.collection_name}")

    def insert(self, docs: List[Dict[str, Any]], embeddings: List[List[float]]) -> int:
        """插入文档及其向量"""
        if not self._connected or not self._collection:
            raise RuntimeError("Milvus not connected")

        try:
            data = []
            for i, doc in enumerate(docs):
                row = {
                    PRIMARY_FIELD: doc.get("id", str(i)),
                    VECTOR_FIELD: embeddings[i] if i < len(embeddings) else [0.0] * self.dim,
                    "title": doc.get("title", "")[:512],
                    "content": doc.get("content", "")[:65535],
                    "category": doc.get("category", "")[:128],
                    "keywords": doc.get("keywords", "")[:1024],
                    "source": doc.get("source", "")[:256],
                    "updated_at": doc.get("updated_at", str(time.time()))[:64],
                }
                data.append(row)

            self._collection.insert(data)
            self._collection.flush()
            logger.info(f"Inserted {len(data)} documents into Milvus")
            return len(data)

        except Exception as e:
            logger.error(f"Failed to insert into Milvus: {e}")
            raise

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        score_threshold: float = 0.3,
        filters: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        if not self._connected or not self._collection:
            raise RuntimeError("Milvus not connected")

        try:
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 64},
            }

            expr = filters or ""

            results = self._collection.search(
                data=[query_embedding],
                anns_field=VECTOR_FIELD,
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=["title", "content", "category", "keywords", "source", "updated_at"],
            )

            docs = []
            for hits in results:
                for hit in hits:
                    score = hit.score
                    if score >= score_threshold:
                        doc = hit.entity
                        docs.append({
                            "id": getattr(doc, PRIMARY_FIELD, hit.id),
                            "title": getattr(doc, "title", ""),
                            "content": getattr(doc, "content", ""),
                            "category": getattr(doc, "category", ""),
                            "keywords": getattr(doc, "keywords", ""),
                            "source": getattr(doc, "source", ""),
                            "updated_at": getattr(doc, "updated_at", ""),
                            "score": score,
                            "vector_score": round(score, 4),
                        })

            return docs

        except Exception as e:
            logger.error(f"Milvus search error: {e}")
            return []

    def count(self) -> int:
        if not self._collection:
            return 0
        try:
            return self._collection.num_entities
        except Exception:
            return 0

    def delete(self, ids: List[str]):
        if not self._connected or not self._collection:
            raise RuntimeError("Milvus not connected")
        try:
            expr = f'{PRIMARY_FIELD} in {ids}'
            self._collection.delete(expr)
            self._collection.flush()
            logger.info(f"Deleted {len(ids)} documents from Milvus")
        except Exception as e:
            logger.error(f"Milvus delete error: {e}")
            raise

    def drop_collection(self):
        if not self._connected:
            return
        try:
            from pymilvus import utility
            utility.drop_collection(self.collection_name)
            self._collection = None
            logger.info(f"Dropped collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to drop collection: {e}")

    def health_check(self) -> Tuple[bool, str]:
        if not self._connected:
            return False, "Not connected"
        try:
            from pymilvus import utility
            if utility.has_collection(self.collection_name):
                return True, "OK"
            return False, "Collection not found"
        except Exception as e:
            return False, str(e)


_milvus_client: Optional[MilvusClient] = None


def get_milvus_client(host: str = "localhost", port: int = 19530, dim: int = 1024) -> MilvusClient:
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient(host=host, port=port, dim=dim)
    return _milvus_client


def reset_milvus_client():
    global _milvus_client
    if _milvus_client:
        _milvus_client.disconnect()
        _milvus_client = None