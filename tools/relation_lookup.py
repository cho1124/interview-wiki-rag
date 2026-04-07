"""토픽 관계 조회 도구."""

from langchain_core.tools import tool

from pipeline.fetch import get_supabase


@tool
def relation_lookup(topic_id: str, category_id: str) -> dict:
    """토픽의 선수지식, 관련 토픽, 심화 토픽 관계를 조회한다.

    Args:
        topic_id: 토픽 ID (예: 'react')
        category_id: 카테고리 ID (예: 'frontend')

    Returns:
        dict with keys: prerequisites (선수지식), related (관련), extensions (심화)
    """
    supabase = get_supabase()

    # 이 토픽에서 나가는 관계
    outgoing = (
        supabase.table("topic_relations")
        .select("*")
        .eq("source_category_id", category_id)
        .eq("source_topic_id", topic_id)
        .execute()
    ).data or []

    # 이 토픽으로 들어오는 관계
    incoming = (
        supabase.table("topic_relations")
        .select("*")
        .eq("target_category_id", category_id)
        .eq("target_topic_id", topic_id)
        .execute()
    ).data or []

    result = {"prerequisites": [], "related": [], "extensions": []}

    for rel in outgoing:
        target = f"{rel['target_category_id']}/{rel['target_topic_id']}"
        if rel["relation_type"] == "prerequisite":
            result["prerequisites"].append(target)
        elif rel["relation_type"] == "related":
            result["related"].append(target)
        elif rel["relation_type"] == "extends":
            result["extensions"].append(target)

    for rel in incoming:
        source = f"{rel['source_category_id']}/{rel['source_topic_id']}"
        if rel["relation_type"] == "prerequisite":
            result["extensions"].append(source)  # 역방향: 나를 선수지식으로 가진 토픽
        elif rel["relation_type"] == "related":
            result["related"].append(source)
        elif rel["relation_type"] == "extends":
            result["prerequisites"].append(source)

    return result
