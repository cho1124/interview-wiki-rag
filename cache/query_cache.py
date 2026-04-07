"""L1 캐시: 정규화된 쿼리의 정확 매칭 -> 응답.

가장 빠른 캐시 레이어. 동일한 질문이 반복되면 즉시 응답.
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
    def _hash_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, query: str) -> dict | None:
        """캐시에서 응답 조회. 만료된 항목은 삭제."""
        key = self._hash_key(self._normalize_query(query))
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry["timestamp"] > self._ttl:
            del self._store[key]
            return None
        return entry["value"]

    def set(self, query: str, value: dict) -> None:
        """캐시에 응답 저장."""
        key = self._hash_key(self._normalize_query(query))
        self._store[key] = {
            "value": value,
            "timestamp": time.time(),
        }

    def invalidate(self, query: str | None = None) -> None:
        """특정 쿼리 또는 전체 캐시 무효화."""
        if query is None:
            self._store.clear()
        else:
            key = self._hash_key(self._normalize_query(query))
            self._store.pop(key, None)

    def size(self) -> int:
        return len(self._store)