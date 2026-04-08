"""Supabase에서 면접위키 데이터를 JSON으로 내보낸다."""

import json
from pipeline.fetch import get_supabase


def export_all_chunks(output_path: str = "data/chunks.json"):
    """topic_chunks 테이블의 모든 데이터를 JSON으로 내보낸다."""
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    supabase = get_supabase()
    result = supabase.table("topic_chunks").select("*").execute()
    chunks = result.data

    # embedding 컬럼은 제외 (재임베딩 필요)
    for chunk in chunks:
        chunk.pop("embedding", None)
        chunk.pop("bm25_content", None)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(chunks)} chunks to {output_path}")
    return chunks


if __name__ == "__main__":
    export_all_chunks()
