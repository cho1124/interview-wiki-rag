"""L1 캐시: 정규화된 쿼리의 정확 매칭 -> 응답.

가장 빠른 캐시 레이어. 동일한 질문이 반복되면 즉시 응답.
키 버전: query + complexity + model + prompt_version 으로 구성.
"""

import hashlib
import time
from typing import Any


class QueryCache:
    """L1 exact-match query cache (in-memory dict)."""

    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[str, dict[str, Any]] = {}
        self._ttl = ttl_seconds

    @staticmethod
    def _normalize_query(query: str) -> str:
        """쿼리를 정규화한다 (소문자, 공백 정리)."""
        return " ".join(query.lower().strip().split())

    @staticmethod
    def _hash_key(
        text: str,
        complexity: str = "",
        model: str = "",
        prompt_version: str = "v1",
    ) -> str:
        """쿼리 + 부가 파라미터로 캐시 키 생성."""
        raw = f"{text}:{complexity}:{model}:{prompt_version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(
        self,
        query: str,
        complexity: str = "",
        model: str = "",
        prompt_version: str = "v1",
    ) -> dict | None:
        """캐시에서 응답 조회. 만료된 항목은 삭제."""
        key = self._hash_key(
            self._normalize_query(query), complexity, model, prompt_version
        )
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry["timestamp"] > self._ttl:
            del self._store[key]
            return None
        return entry["value"]

    def set(
        self,
        query: str,
        value: dict,
        complexity: str = "",
        model: str = "",
        prompt_version: str = "v1",
        topic_ids: list[str] | None = None,
    ) -> None:
        """캐시에 응답 저장. topic_ids 메타데이터도 함께 저장."""
        key = self._hash_key(
            self._normalize_query(query), complexity, model, prompt_version
        )
        self._store[key] = {
            "value": value,
            "timestamp": time.time(),
            "topic_ids": topic_ids or [],
        }

    def invalidate(self, query: str | None = None) -> None:
        """특정 쿼리 또는 전체 캐시 무효화."""
        if query is None:
            self._store.clear()
        else:
            key = self._hash_key(self._normalize_query(query))
            self._store.pop(key, None)

    def invalidate_by_topic(self, topic_id: str) -> int:
        """특정 토픽과 관련된 캐시 항목만 무효화.

        Returns:
            삭제된 항목 수
        """
        keys_to_delete = [
            k
            for k, v in self._store.items()
            if topic_id in v.get("topic_ids", [])
        ]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    def size(self) -> int:
        return len(self._store)
