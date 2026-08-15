from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    APP_NAME: str = Field(default="智能客服系统")
    APP_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=True)

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    MYSQL_HOST: str = Field(default="localhost")
    MYSQL_PORT: int = Field(default=3306)
    MYSQL_USER: str = Field(default="root")
    MYSQL_PASSWORD: str = Field(default="123456")
    MYSQL_DATABASE: str = Field(default="customer_service")

    # 如果设置了 DATABASE_URL，则优先使用
    DATABASE_URL_OVERRIDE: str = Field(default="")

    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = Field(default=0)

    LLM_API_BASE: str = Field(default="http://localhost:8001")
    LLM_API_KEY: str = Field(default="")
    LLM_MODEL: str = Field(default="gpt-4o-mini")

    # Milvus 向量数据库
    MILVUS_HOST: str = Field(default="localhost")
    MILVUS_PORT: int = Field(default=19530)
    USE_MILVUS: bool = Field(default=False)

    # Embedding 服务
    EMBEDDING_API_BASE: str = Field(default="")
    EMBEDDING_API_KEY: str = Field(default="")
    EMBEDDING_MODEL: str = Field(default="")
    EMBEDDING_DIM: int = Field(default=1024)

    # RAG 检索增强生成
    COLLECTION_NAME: str = Field(default="customer_service_knowledge")
    RAG_TOP_K: int = Field(default=3)
    RAG_SIMILARITY_THRESHOLD: float = Field(default=0.3)
    RAG_BM25_WEIGHT: float = Field(default=0.6)
    RAG_VECTOR_WEIGHT: float = Field(default=0.4)
    RAG_USE_RERANKER: bool = Field(default=True)

    # 文档分块配置
    CHUNK_SIZE: int = Field(default=500)
    CHUNK_OVERLAP: int = Field(default=50)
    CHUNK_SPLIT_PATTERN: str = Field(default="sentence")

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
