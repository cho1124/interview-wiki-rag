"""L2 캐시: 검색 결과 캐시 (query hash + search params -> chunks).

동일한 쿼리+파라미터 조합의 검색 결과를 재사용.
임베딩 API 호출을 절약한다.
"""

import hashlib
import json
import time
from typing import Any


class RetrievalCache:
    """L2 retrieval results cache (in-memory dict)."""

    def __init__(self, ttl_seconds: int = 1800):
        self._store: dict[str, dict[str, Any]] = {}
        self._ttl = ttl_seconds

    @staticmethod
    def _make_key(query: str, params: dict | None = None) -> str:
        """쿼리 + 검색 파라미터로 캐시 키 생성."""
        normalized = " ".join(query.lower().strip().split())
        key_data = {"query": normalized, "params": params or {}}
        raw = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, query: str, params: dict | None = None) -> list[dict] | None:
        """캐시에서 검색 결과 조회."""
        key = self._make_key(query, params)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry["timestamp"] > self._ttl:
            del self._store[key]
            return None
        return entry["value"]

    def set(self, query: str, chunks: list[dict], params: dict | None = None) -> None:
        """검색 결과를 캐시에 저장."""
        key = self._make_key(query, params)
        self._store[key] = {
            "value": chunks,
            "timestamp": time.time(),
        }

    def invalidate_all(self) -> None:
        """전체 캐시 무효화."""
        self._store.clear()

    def size(self) -> int:
        return len(self._store)