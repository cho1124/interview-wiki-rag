"""면접위키 데이터 인덱싱 파이프라인 실행.

사용법:
    python scripts/run_pipeline.py                  # 전체 토픽 인덱싱
    python scripts/run_pipeline.py --category frontend  # 특정 카테고리만
    python scripts/run_pipeline.py --topic frontend/react  # 특정 토픽만
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.fetch import fetch_all_topics, fetch_topics_by_category, fetch_single_topic
from pipeline.chunk import chunk_topic
from pipeline.embed import embed_chunks
from pipeline.store import store_chunks


def run(topics: list[dict]):
    """토픽 리스트를 인덱싱한다."""
    total_chunks = 0

    for topic in topics:
        name = topic.get("name", topic["id"])
        print(f"  [{topic['category_id']}/{topic['id']}] {name}")

        # 청킹
        chunks = chunk_topic(topic)
        print(f"    청크 {len(chunks)}개 생성")

        if not chunks:
            continue

        # 임베딩
        chunks = embed_chunks(chunks)
        print(f"    임베딩 완료 (dim={len(chunks[0]['embedding'])})")

        # 저장
        stored = store_chunks(chunks)
        print(f"    저장 완료: {stored}개")
        total_chunks += stored

    return total_chunks


def main():
    parser = argparse.ArgumentParser(description="면접위키 인덱싱 파이프라인")
    parser.add_argument("--category", help="특정 카테고리만 인덱싱")
    parser.add_argument("--topic", help="특정 토픽만 (category/topic 형식)")
    args = parser.parse_args()

    print("=== 면접위키 인덱싱 파이프라인 ===\n")

    if args.topic:
        category_id, topic_id = args.topic.split("/")
        topic = fetch_single_topic(category_id, topic_id)
        if not topic:
            print(f"토픽을 찾을 수 없습니다: {args.topic}")
            return
        topics = [topic]
        print(f"단일 토픽 인덱싱: {args.topic}")
    elif args.category:
        topics = fetch_topics_by_category(args.category)
        print(f"카테고리 인덱싱: {args.category} ({len(topics)}개 토픽)")
    else:
        topics = fetch_all_topics()
        print(f"전체 인덱싱: {len(topics)}개 토픽")

    print()
    total = run(topics)
    print(f"\n=== 완료: 총 {total}개 청크 저장 ===")


if __name__ == "__main__":
    main()
