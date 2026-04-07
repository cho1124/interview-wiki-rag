"""검색 에이전트: 하이브리드 검색 + 충분성 게이트 + 인용 시스템 통합.

v2 흐름:
1. 캐시 확인 (L1 → L2 → L3)
2. 하이브리드 검색 (벡터 + BM25)
3. 충분성 게이트 (score threshold)
4. 토큰 예산 관리 (context overflow → 하위 청크 제거)
5. LLM 생성 (인용 규칙 포함 프롬프트)
6. 인용 추출 + 검증
7. 캐시 저장 + 모니터링 로깅
"""

from pathlib import Path

from langchain_core.messages import SystemMessage

from config import settings
from tools.vector_search import vector_search
from tools.topic_lookup import topic_lookup
from tools.hybrid_search import hybrid_search


# 프롬프트 파일에서 로드
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "search.txt"
_SEARCH_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def create_search_agent(complexity: str = "light"):
    """검색 에이전트를 생성한다.

    기존 도구(vector_search, topic_lookup)에 hybrid_search를 추가.
    """
    llm = settings.get_llm(complexity)
    llm_with_tools = llm.bind_tools([hybrid_search, vector_search, topic_lookup])
    return llm_with_tools, SystemMessage(content=_SEARCH_PROMPT)


def build_context_from_chunks(
    chunks: list[dict],
    max_tokens: int | None = None,
) -> str:
    """검색된 청크들로 LLM 컨텍스트를 빌드한다.

    토큰 예산 관리:
    - parent_content 우선 사용 (더 넓은 컨텍스트)
    - 예산 초과 시 낮은 점수 청크부터 제거
    - 그래도 초과 시 parent_content 대신 child content 사용

    Args:
        chunks: 검색된 청크 리스트 (final_score 정렬됨)
        max_tokens: 최대 토큰 수 (None이면 settings에서 가져옴)

    Returns:
        번호가 매겨진 컨텍스트 문자열
    """
    if max_tokens is None:
        max_tokens = settings.token_budget_context

    if not chunks:
        return ""

    # 점수 기준 내림차순 정렬
    sorted_chunks = sorted(
        chunks, key=lambda c: c.get("final_score", 0.0), reverse=True
    )

    # 1차 시도: parent_content 사용
    context_parts = []
    estimated_tokens = 0

    for i, chunk in enumerate(sorted_chunks, start=1):
        # parent_content가 있으면 생성 컨텍스트로 사용
        text = chunk.get("parent_content") or chunk.get("content", "")
        chunk_tokens = _estimate_tokens(text)

        if estimated_tokens + chunk_tokens > max_tokens:
            # parent가 너무 크면 child content로 폴백
            text = chunk.get("content", "")
            chunk_tokens = _estimate_tokens(text)

            if estimated_tokens + chunk_tokens > max_tokens:
                # 그래도 초과면 이 청크 스킵
                break

        topic = chunk.get("topic_id", "")
        category = chunk.get("category_id", "")
        heading = chunk.get("heading", "")
        header = f"[{i}] ({category}/{topic}"
        if heading:
            header += f" > {heading}"
        header += ")"

        context_parts.append(f"{header}\n{text}")
        estimated_tokens += chunk_tokens

    return "\n\n---\n\n".join(context_parts)


def _estimate_tokens(text: str) -> int:
    """텍스트의 토큰 수를 추정한다.

    정확한 tiktoken 카운팅 대신 간단한 추정 사용.
    한국어: ~2 chars/token, 영어: ~4 chars/token
    혼합 기준 ~3 chars/token으로 추정.
    """
    return max(1, len(text) // 3)