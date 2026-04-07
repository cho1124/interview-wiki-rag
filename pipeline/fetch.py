"""Supabase에서 면접위키 토픽 데이터를 가져온다."""

from supabase import create_client

from config import settings


def get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_key)


def fetch_all_topics() -> list[dict]:
    """모든 토픽을 카테고리 정보와 함께 가져온다."""
    supabase = get_supabase()
    response = supabase.table("topics").select("*").execute()
    return response.data


def fetch_topics_by_category(category_id: str) -> list[dict]:
    """특정 카테고리의 토픽만 가져온다."""
    supabase = get_supabase()
    response = (
        supabase.table("topics")
        .select("*")
        .eq("category_id", category_id)
        .execute()
    )
    return response.data


def fetch_single_topic(category_id: str, topic_id: str) -> dict | None:
    """단일 토픽을 가져온다."""
    supabase = get_supabase()
    response = (
        supabase.table("topics")
        .select("*")
        .eq("category_id", category_id)
        .eq("id", topic_id)
        .maybe_single()
        .execute()
    )
    return response.data