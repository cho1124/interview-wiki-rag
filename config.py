from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str

    # LLM - 난이도 기반 모델 라우팅
    llm_light_provider: str = "openai"
    llm_light_model: str = "gpt-4o-mini"
    llm_heavy_provider: str = "anthropic"
    llm_heavy_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.3

    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Chunking
    chunk_size: int = 500
    chunk_overlap: int = 50
    parent_chunk_group_size: int = 3  # 부모 청크 생성 시 묶을 자식 청크 수

    # Retrieval
    top_k: int = 5
    similarity_threshold: float = 0.7

    # Hybrid Search
    hybrid_vector_weight: float = 0.7
    hybrid_bm25_weight: float = 0.3
    hybrid_top_k_complex: int = 10  # 복잡한 쿼리의 top_k

    # Sufficiency Gate Thresholds
    sufficiency_low_threshold: float = 0.5   # 이하 → reject
    sufficiency_high_threshold: float = 0.7  # 이상 → pass

    # Token Budget
    token_budget_system: int = 500
    token_budget_query: int = 200
    token_budget_context: int = 2800
    token_budget_output: int = 500
    token_budget_total: int = 4000

    # Cache TTL (seconds)
    cache_query_ttl: int = 3600       # L1: 1시간
    cache_retrieval_ttl: int = 1800   # L2: 30분
    cache_generation_ttl: int = 3600  # L3: 1시간

    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env"}

    def get_llm(self, complexity: str = "light"):
        """난이도에 따라 적절한 LLM 인스턴스 반환"""
        if complexity == "heavy":
            provider = self.llm_heavy_provider
            model = self.llm_heavy_model
        else:
            provider = self.llm_light_provider
            model = self.llm_light_model

        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                temperature=self.llm_temperature,
                api_key=self.openai_api_key,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model,
                temperature=self.llm_temperature,
                api_key=self.anthropic_api_key,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def get_model_name(self, complexity: str = "light") -> str:
        """난이도에 따른 모델 이름 반환."""
        if complexity == "heavy":
            return self.llm_heavy_model
        return self.llm_light_model

    def get_embeddings(self):
        """임베딩 모델 인스턴스 반환"""
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=self.embedding_model,
            dimensions=self.embedding_dimensions,
            api_key=self.openai_api_key,
        )


settings = Settings()