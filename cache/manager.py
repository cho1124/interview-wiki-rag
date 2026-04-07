"""캐시 매니저: 3-Layer 캐시 통합 관리 + 무효화.

문서 변경 시 전 레이어를 무효화한다.
싱글턴 패턴으로 앱 전체에서 하나의 인스턴스를 공유.
"""

from cache.query_cache import QueryCache
from cache.retrieval_cache import RetrievalCache
from cache.generation_cache import GenerationCache


class CacheManager:
    """3-Layer 캐시 통합 관리자."""

    def __init__(
        self,
        query_ttl: int = 3600,
        retrieval_ttl: int = 1800,
        generation_ttl: int = 3600,
    ):
        self.l1 = QueryCache(ttl_seconds=query_ttl)
        self.l2 = RetrievalCache(ttl_seconds=retrieval_ttl)
        self.l3 = GenerationCache(ttl_seconds=generation_ttl)

    def invalidate_all(self) -> None:
        """전체 캐시 무효화 (문서 변경 시 호출)."""
        self.l1.invalidate()
        self.l2.invalidate_all()
        self.l3.invalidate_all()

    def invalidate_for_topic(self, topic_id: str) -> None:
        """특정 토픽 관련 캐시 무효화.

        현재는 전체 무효화로 처리 (정밀 무효화는 향후 구현).
        """
        self.invalidate_all()

    def stats(self) -> dict:
        """캐시 통계 반환."""
        return {
            "l1_query_cache_size": self.l1.size(),
            "l2_retrieval_cache_size": self.l2.size(),
            "l3_generation_cache_size": self.l3.size(),
        }


# 싱글턴 인스턴스
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """캐시 매니저 싱글턴 인스턴스를 반환한다."""
    global _cache_manager
    if _cache_manager is None:
        from config import settings
        _cache_manager = CacheManager(
            query_ttl=settings.cache_query_ttl,
            retrieval_ttl=settings.cache_retrieval_ttl,
            generation_ttl=settings.cache_generation_ttl,
        )
    return _cache_manager