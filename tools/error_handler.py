"""구조화된 에러 핸들링: 검색/생성 오류를 사용자 친화적으로 처리한다.

에러 유형:
- empty_results: 검색 결과 없음 -> 쿼리 재구성 제안
- low_scores: 낮은 유사도 -> 제한적 답변 + 면책문
- timeout: 타임아웃 -> 경량 모델로 재시도
- rate_limit: API 한도 -> 지수 백오프 재시도
"""

import time
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)


class SearchError:
    """검색 에러 응답 생성기."""

    @staticmethod
    def empty_results(query: str) -> dict:
        """검색 결과가 없을 때 쿼리 재구성을 제안한다."""
        suggestions = _suggest_reformulations(query)
        return {
            "error_type": "empty_results",
            "message": "문서에서 관련 내용을 찾지 못했습니다.",
            "suggestions": suggestions,
            "response": (
                "죄송합니다, 면접위키에서 관련 내용을 찾지 못했습니다.\n\n"
                "다음과 같이 질문을 바꿔보시면 도움이 될 수 있습니다:\n"
                + "\n".join(f"- {s}" for s in suggestions)
            ),
        }

    @staticmethod
    def low_scores(query: str, top_score: float) -> dict:
        """낮은 점수일 때 면책문을 포함한 응답을 생성한다."""
        return {
            "error_type": "low_scores",
            "message": f"검색 결과의 관련성이 낮습니다 (최고 점수: {top_score:.2f}).",
            "response": (
                "**참고:** 검색된 문서와의 관련성이 높지 않아 "
                "아래 답변은 제한적일 수 있습니다.\n\n"
            ),
        }

    @staticmethod
    def timeout_error() -> dict:
        """타임아웃 발생 시 응답."""
        return {
            "error_type": "timeout",
            "message": "응답 생성 시간이 초과되었습니다.",
            "response": (
                "죄송합니다, 응답 생성에 시간이 너무 오래 걸렸습니다. "
                "다시 시도해 주세요."
            ),
        }

    @staticmethod
    def rate_limit_error() -> dict:
        """Rate limit 발생 시 응답."""
        return {
            "error_type": "rate_limit",
            "message": "API 호출 한도에 도달했습니다.",
            "response": (
                "현재 요청이 많아 잠시 후 다시 시도해 주세요."
            ),
        }

    @staticmethod
    def general_error(error: Exception) -> dict:
        """일반 에러 응답."""
        logger.error(f"Unexpected error: {error}", exc_info=True)
        return {
            "error_type": "general",
            "message": str(error),
            "response": (
                "죄송합니다, 처리 중 오류가 발생했습니다. "
                "다시 시도해 주세요."
            ),
        }


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    fallback_to_light: bool = True,
):
    """지수 백오프 재시도 데코레이터.

    Args:
        max_retries: 최대 재시도 횟수
        base_delay: 기본 대기 시간 (초)
        fallback_to_light: 실패 시 경량 모델로 폴백할지 여부
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # Rate limit → 지수 백오프
                    if "rate_limit" in error_str or "429" in error_str:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Rate limit hit, retrying in {delay}s "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue

                    # Timeout → 경량 모델로 폴백
                    if "timeout" in error_str and fallback_to_light:
                        logger.warning(
                            f"Timeout, falling back to light model "
                            f"(attempt {attempt + 1})"
                        )
                        kwargs["complexity"] = "light"
                        continue

                    # 기타 에러는 재시도하지 않음
                    raise

            # 모든 재시도 실패
            raise last_error  # type: ignore[misc]

        return wrapper
    return decorator


def _suggest_reformulations(query: str) -> list[str]:
    """쿼리를 재구성하는 제안을 생성한다."""
    suggestions = []

    # 1. 더 구체적인 키워드 사용
    suggestions.append(f"'{query}' 대신 더 구체적인 기술 용어를 사용해보세요")

    # 2. 카테고리 힌트
    categories = ["frontend", "backend", "database", "devops", "cs"]
    suggestions.append(
        f"카테고리를 지정해보세요 (예: {', '.join(categories[:3])})"
    )

    # 3. 짧은 쿼리면 더 길게
    if len(query.split()) <= 2:
        suggestions.append("질문을 더 자세하게 작성해보세요")

    return suggestions