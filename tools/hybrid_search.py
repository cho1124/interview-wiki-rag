"""하이브리드 검색 도구: 벡터 + BM25 결합.

검색 전략:
- 벡터 검색: pgvector 코사인 유사도 (의미적 유사성)
- BM25 검색: PostgreSQL tsvector/tsquery (키워드 매칭)
- 결합: final_score = 0.7 * vector_score + 0.3 * bm25_score
- Top-k 적응: 단순 질문 top_k=5, 복잡한 질문 top_k=10
"""

from langchain_core.tools import tool

from config import settings
from pipeline.fetch import get_supabase


def _estimate_query_complexity(query: str) -> str:
    """쿼리 복잡도를 간단히 추정한다.

    Returns:
        "simple" or "complex"
    """
    # 복잡한 질문 지표: 길이, 비교 키워드, 다중 개념
    complex_keywords = [
        "비교", "차이", "vs", "versus", "장단점",
        "언제", "왜", "어떻게", "설명", "원리",
        "아키텍처", "설계", "트레이드오프",
    ]
    query_lower = query.lower()

    # 긴 쿼리이거나 복잡 키워드 포함 시
    if len(query) > 50:
        return "complex"
    for kw in complex_keywords:
        if kw in query_lower:
            return "complex"
    return "simple"


@tool
def hybrid_search(
    query: str,
    category: str | None = None,
) -> list[dict]:
    """면접위키에서 벡터 + BM25 하이브리드 검색으로 관련 콘텐츠를 찾는다.

    벡터 검색(의미적 유사성)과 BM25(키워드 매칭)를 결합하여
    더 정확한 검색 결과를 반환한다.
    parent_content가 있으면 함께 반환하여 생성 컨텍스트로 활용한다.

    Args:
        query: 검색할 질문 또는 키워드
        category: 특정 카테고리로 필터링 (예: 'frontend'). None이면 전체 검색.

    Returns:
        하이브리드 스코어 기준 상위 청크 리스트
        (content, parent_content, heading, topic_id, category_id, scores 포함)
    """
    supabase = get_supabase()
    embeddings_model = settings.get_embeddings()

    # 쿼리 복잡도에 따른 top_k 조정
    complexity = _estimate_query_complexity(query)
    top_k = settings.hybrid_top_k_complex if complexity == "complex" else settings.top_k

    # 쿼리 임베딩
    query_vector = embeddings_model.embed_query(query)

    # Supabase RPC로 하이브리드 검색
    response = supabase.rpc(
        "match_chunks_hybrid",
        {
            "query_embedding": str(query_vector),
            "query_text": query,
            "match_threshold": settings.sufficiency_low_threshold,
            "match_count": top_k,
            "filter_category": category,
            "vector_weight": settings.hybrid_vector_weight,
            "bm25_weight": settings.hybrid_bm25_weight,
        },
    ).execute()

    results = response.data or []

    # 결과 정리: parent_content가 있으면 generation용으로 포함
    enriched = []
    for r in results:
        enriched.append({
            "id": r.get("id"),
            "topic_id": r.get("topic_id"),
            "category_id": r.get("category_id"),
            "chunk_index": r.get("chunk_index"),
            "content": r.get("content", ""),
            "parent_content": r.get("parent_content", ""),
            "heading": r.get("heading"),
            "tags": r.get("tags", []),
            "content_hash": r.get("content_hash", ""),
            "vector_score": r.get("vector_score", 0.0),
            "bm25_score": r.get("bm25_score", 0.0),
            "final_score": r.get("final_score", 0.0),
        })

    return enriched