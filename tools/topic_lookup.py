"""토픽 직접 조회 도구."""

from langchain_core.tools import tool

from pipeline.fetch import get_supabase


@tool
def topic_lookup(topic_id: str, category_id: str | None = None) -> dict | None:
    """토픽 ID로 면접위키 토픽 전체 내용을 조회한다.

    Args:
        topic_id: 토픽 ID (예: 'react', 'docker', 'mysql')
        category_id: 카테고리 ID (예: 'frontend'). None이면 토픽 ID만으로 검색.

    Returns:
        토픽 데이터 (name, content, tags 등) 또는 None
    """
    supabase = get_supabase()
    query = supabase.table("topics").select("*").eq("id", topic_id)

    if category_id:
        query = query.eq("category_id", category_id)

    response = query.maybe_single().execute()
    return response.data
