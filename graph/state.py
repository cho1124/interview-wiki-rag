"""LangGraph 공유 상태 정의."""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """모든 에이전트가 공유하는 상태."""

    # 대화 메시지 히스토리 (LangGraph가 자동 누적)
    messages: Annotated[list, add_messages]

    # 현재 사용자 질문
    query: str

    # 라우터 결과
    agent_type: str       # search | quiz | explain | compare
    complexity: str       # light | heavy

    # 최종 응답
    response: str

    # --- v2: 인용 + 검색 메트릭 ---
    citations: dict          # 인용 메타데이터 {번호: {topic_id, heading, ...}}
    citation_validation: dict  # 인용 검증 결과
    gate_status: str         # pass | limited | reject
    confidence: float        # 최고 검색 점수
    cache_hit: str           # None | "l1" | "l2" | "l3"