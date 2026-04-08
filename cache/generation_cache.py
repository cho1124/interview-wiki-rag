"""L3 캐시: 생성 결과 캐시 (query hash + chunk IDs + model -> response).

동일 컨텍스트 + 동일 모델이면 LLM 호출을 생략한다.
"""

import hashlib
import json
import time
from typing import Any


class GenerationCache:
    """L3 generation cache (in-memory dict)."""

    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[str, dict[str, Any]] = {}
        self._ttl = ttl_seconds

    @staticmethod
    def _make_key(
        query: str,
        chunk_ids: list[str],
        model: str,
        prompt_version: str = "v1",
    ) -> str:
        """쿼리 + 청크 ID(점수 순서 유지) + 모델 + 프롬프트 버전으로 캐시 키 생성."""
        normalized_query = " ".join(query.lower().strip().split())
        key_data = {
            "query": normalized_query,
            "chunk_ids": chunk_ids,  # 점수 순서 유지 (정렬하지 않음)
            "model": model,
            "prompt_version": prompt_version,
        }
        raw = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(
        self,
        query: str,
        chunk_ids: list[str],
        model: str,
        prompt_version: str = "v1",
    ) -> dict | None:
        """캐시에서 생성 결과 조회."""
        key = self._make_key(query, chunk_ids, model, prompt_version)
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
        chunk_ids: list[str],
        model: str,
        value: dict,
        prompt_version: str = "v1",
    ) -> None:
        """생성 결과를 캐시에 저장."""
        key = self._make_key(query, chunk_ids, model, prompt_version)
        self._store[key] = {
            "value": value,
            "timestamp": time.time(),
        }

    def invalidate_all(self) -> None:
        """전체 캐시 무효화."""
        self._store.clear()

    def size(self) -> int:
        return len(self._store)
