"""임베딩된 청크를 Supabase pgvector에 저장한다.

v2: parent_content, content_hash, parent_id 포함 저장.
chunk_metadata 테이블에 섹션 경로 매핑도 저장.
저장 후 관련 토픽의 캐시를 무효화한다.
"""

from cache.manager import get_cache_manager
from pipeline.fetch import get_supabase


def store_chunks(chunks: list[dict]) -> int:
    """청크를 topic_chunks 테이블에 저장한다.

    같은 토픽의 기존 청크를 삭제하고 새로 삽입 (멱등성 보장).
    v2: parent_content, content_hash, parent_id 컬럼 포함.

    Returns:
        저장된 청크 수
    """
    if not chunks:
        return 0

    supabase = get_supabase()

    # 같은 토픽의 기존 청크 삭제 (토픽 단위 재인덱싱)
    topic_ids_seen = set()
    for chunk in chunks:
        key = (chunk["category_id"], chunk["topic_id"])
        if key not in topic_ids_seen:
            topic_ids_seen.add(key)
            supabase.table("topic_chunks").delete().eq(
                "category_id", chunk["category_id"]
            ).eq("topic_id", chunk["topic_id"]).execute()

            # chunk_metadata도 삭제
            supabase.table("chunk_metadata").delete().eq(
                "category_id", chunk["category_id"]
            ).eq("topic_id", chunk["topic_id"]).execute()

    # 새 청크 삽입 (embedding을 문자열로 변환)
    rows = []
    metadata_rows = []
    for chunk in chunks:
        rows.append(
            {
                "topic_id": chunk["topic_id"],
                "category_id": chunk["category_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "heading": chunk["heading"],
                "tags": chunk["tags"],
                "embedding": str(chunk["embedding"]),
                "parent_id": chunk.get("parent_id"),
                "parent_content": chunk.get("parent_content"),
                "content_hash": chunk.get("content_hash"),
            }
        )

        # chunk_metadata 행 준비
        chunk_id = chunk.get("chunk_id", "")
        section_path = chunk.get("section_path", "")
        if chunk_id:
            metadata_rows.append(
                {
                    "chunk_id": chunk_id,
                    "section_path": section_path,
                    "section_title": chunk.get("heading"),
                    "topic_id": chunk["topic_id"],
                    "category_id": chunk["category_id"],
                }
            )

    # 배치 삽입: topic_chunks
    supabase.table("topic_chunks").insert(rows).execute()

    # 배치 삽입: chunk_metadata
    if metadata_rows:
        supabase.table("chunk_metadata").insert(metadata_rows).execute()

    # 저장된 토픽의 캐시 무효화
    cache_manager = get_cache_manager()
    for _category_id, topic_id in topic_ids_seen:
        cache_manager.invalidate_for_topic(topic_id)

    return len(rows)
