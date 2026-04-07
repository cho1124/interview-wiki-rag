"""라우터 에이전트: 사용자 의도를 분류하고 적절한 전문 에이전트를 선택한다."""

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

from config import settings


SYSTEM_PROMPT = """당신은 면접 준비 AI 시스템의 라우터입니다.
사용자의 질문을 분석하여 적절한 전문 에이전트를 선택합니다.

## 에이전트 종류

1. **search** - 특정 개념이나 기술에 대한 질문
   예: "가상 DOM이 뭐야?", "Redis의 캐싱 전략은?"

2. **quiz** - 면접 문제 출제 요청
   예: "React 면접 문제 내줘", "Java 면접 질문 5개"

3. **explain** - 깊이 있는 개념 설명 요청
   예: "DI를 초보자한테 설명해줘", "이벤트 루프를 비유로 설명해줘"

4. **compare** - 기술/개념 비교 요청
   예: "React vs Vue 비교", "TCP와 UDP 차이"

## 난이도 판단

- **light**: 단순 검색, 사실 확인, 퀴즈 출제
- **heavy**: 깊은 설명, 비유 필요, 복잡한 비교

반드시 아래 JSON 형식으로만 응답하세요:
{"agent_type": "search|quiz|explain|compare", "complexity": "light|heavy", "reason": "판단 근거"}
"""


def route_query(query: str) -> dict:
    """사용자 질문을 분석하여 에이전트 타입과 난이도를 반환한다."""
    llm = settings.get_llm("light")  # 라우팅은 항상 경량 모델
    parser = JsonOutputParser()

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=query),
    ]

    response = llm.invoke(messages)
    result = parser.invoke(response)

    # 기본값 보장
    return {
        "agent_type": result.get("agent_type", "search"),
        "complexity": result.get("complexity", "light"),
        "reason": result.get("reason", ""),
    }