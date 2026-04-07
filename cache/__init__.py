"""3-Layer 캐싱 시스템.

L1: 쿼리 완전 일치 캐시 (query SHA256 -> response)
L2: 검색 결과 캐시 (query hash + params -> chunks)
L3: 생성 캐시 (query hash + chunk IDs + model -> response)
"""

from cache.manager import CacheManager

__all__ = ["CacheManager"]