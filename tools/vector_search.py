"""pgvector 유사도 검색 도구."""

from langchain_core.tools import tool

from config import settings
from pipeline.fetch import get_supabase


@tool
def vector_search(query: str, category: str | None = None) -> list[dict]:
    """면접위키에서 질문과 의미적으로 유사한 콘텐츠를 검색한다.

    Args:
        query: 검색할 질문 또는 키워드
        category: 특정 카테고리로 필터링 (예: 'frontend', 'backend'). None이면 전체 검색.

    Returns:
        유사도 높은 청크 리스트 (content, heading, topic_id, category_id, similarity 포함)
    """
    supabase = get_supabase()
    embeddings_model = settings.get_embeddings()

    # 쿼리 임베딩
    query_vector = embeddings_model.embed_query(query)

    # Supabase RPC로 유사도 검색 (create_vector_table.sql의 match_chunks 함수)
    response = supabase.rpc(
        "match_chunks",
        {
            "query_embedding": str(query_vector),
            "match_threshold": settings.similarity_threshold,
            "match_count": settings.top_k,
            "filter_category": category,
        },
    ).execute()

    return response.data or []
