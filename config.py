import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Mode: "cloud" | "local" | "spaces" | "auto"
    # cloud: OpenAI/Anthropic/Supabase (기존 동작)
    # local: Ollama + 로컬 임베딩
    # spaces: HuggingFace Inference API + 로컬 sentence-transformers
    # auto: SPACE_ID 감지 시 spaces, API 키 존재 시 cloud, 없으면 local
    mode: str = "auto"

    # Supabase (local 모드에서는 불필요)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # LLM - 난이도 기반 모델 라우팅
    llm_light_provider: str = "openai"
    llm_light_model: str = "gpt-4o-mini"
    llm_heavy_provider: str = "anthropic"
    llm_heavy_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.3

    # Local Model Settings (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma2:9b-instruct"
    local_embedding_model: str = "all-MiniLM-L6-v2"

    # HuggingFace Spaces Settings
    hf_token: str = ""
    hf_model: str = "mistralai/Mistral-7B-Instruct-v0.3"

    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384

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

    # Prompt Version (캐시 키 버전 관리용)
    PROMPT_VERSION: str = "v1"

    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env"}

    def _resolve_mode(self) -> str:
        """mode 설정 + 환경 감지에 따라 'cloud' / 'local' / 'spaces' 반환"""
        if self.mode == "cloud":
            return "cloud"
        elif self.mode == "local":
            return "local"
        elif self.mode == "spaces":
            return "spaces"
        else:  # auto
            # HuggingFace Spaces 환경 자동 감지
            if os.environ.get("SPACE_ID"):
                return "spaces"
            if self.hf_token and not self.openai_api_key:
                return "spaces"
            if self.openai_api_key:
                return "cloud"
            return "local"

    def get_llm(self, complexity: str = "light"):
        """난이도에 따라 적절한 LLM 인스턴스 반환"""
        resolved = self._resolve_mode()

        if resolved == "spaces":
            from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
            llm = HuggingFaceEndpoint(
                repo_id=self.hf_model,
                huggingfacehub_api_token=self.hf_token or os.environ.get("HF_TOKEN", ""),
                temperature=self.llm_temperature,
                max_new_tokens=self.token_budget_output,
            )
            return ChatHuggingFace(llm=llm)

        if resolved == "local":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                base_url=self.ollama_base_url,
                model=self.ollama_model,
                temperature=self.llm_temperature,
            )

        # cloud 모드
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
        resolved = self._resolve_mode()
        if resolved == "spaces":
            return self.hf_model
        if resolved == "local":
            return self.ollama_model
        if complexity == "heavy":
            return self.llm_heavy_model
        return self.llm_light_model

    def get_embeddings(self):
        """임베딩 모델 인스턴스 반환"""
        resolved = self._resolve_mode()

        if resolved in ("local", "spaces"):
            # spaces 모드에서도 로컬 임베딩 사용 (무료)
            from langchain_huggingface import HuggingFaceEmbeddings
            return HuggingFaceEmbeddings(
                model_name=self.local_embedding_model,
            )

        # cloud 모드
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=self.embedding_model,
            dimensions=self.embedding_dimensions,
            api_key=self.openai_api_key,
        )


settings = Settings()
