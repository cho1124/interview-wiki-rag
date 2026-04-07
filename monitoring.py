"""쿼리 모니터링/로깅: JSON Lines 형태로 쿼리별 메트릭을 기록한다.

기록 항목:
- query: 쿼리 텍스트
- search_time_ms: 검색 소요 시간
- generation_time_ms: 생성 소요 시간
- model: 사용된 모델
- tokens: 토큰 수 (추정)
- citation_count: 인용 수
- cache_hit: 캐시 히트 레이어 (None, "l1", "l2", "l3")
- gate_status: 충분성 게이트 상태
- timestamp: ISO 형식 타임스탬프
"""

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 로그 디렉토리 (프로젝트 루트 기준)
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "queries.jsonl"


def _ensure_log_dir():
    """로그 디렉토리가 없으면 생성."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


class QueryMetrics:
    """단일 쿼리의 메트릭을 수집하는 컨텍스트 매니저 겸 빌더."""

    def __init__(self, query: str):
        self.data = {
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "search_time_ms": 0,
            "generation_time_ms": 0,
            "model": "",
            "tokens_estimated": 0,
            "citation_count": 0,
            "cache_hit": None,
            "gate_status": "",
            "agent_type": "",
            "error": None,
        }
        self._search_start: float = 0
        self._gen_start: float = 0

    def start_search(self):
        """검색 타이머 시작."""
        self._search_start = time.time()

    def end_search(self):
        """검색 타이머 종료."""
        if self._search_start:
            self.data["search_time_ms"] = round(
                (time.time() - self._search_start) * 1000
            )

    def start_generation(self):
        """생성 타이머 시작."""
        self._gen_start = time.time()

    def end_generation(self):
        """생성 타이머 종료."""
        if self._gen_start:
            self.data["generation_time_ms"] = round(
                (time.time() - self._gen_start) * 1000
            )

    def set_model(self, model: str):
        self.data["model"] = model

    def set_tokens(self, tokens: int):
        self.data["tokens_estimated"] = tokens

    def set_citation_count(self, count: int):
        self.data["citation_count"] = count

    def set_cache_hit(self, layer: str | None):
        """캐시 히트 레이어 설정 (None, "l1", "l2", "l3")."""
        self.data["cache_hit"] = layer

    def set_gate_status(self, status: str):
        self.data["gate_status"] = status

    def set_agent_type(self, agent_type: str):
        self.data["agent_type"] = agent_type

    def set_error(self, error: str):
        self.data["error"] = error

    def save(self):
        """메트릭을 JSONL 파일에 기록한다."""
        try:
            _ensure_log_dir()
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(self.data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write query metrics: {e}")


def log_query(query: str) -> QueryMetrics:
    """쿼리 메트릭 수집기를 생성한다.

    Usage:
        metrics = log_query("React란?")
        metrics.start_search()
        # ... search ...
        metrics.end_search()
        metrics.set_model("gpt-4o-mini")
        metrics.save()
    """
    return QueryMetrics(query)