"""설명 에이전트: 깊이 있는 개념 설명을 비유와 함께 제공한다."""

from langchain_core.messages import SystemMessage

from config import settings
from tools.vector_search import vector_search
from tools.relation_lookup import relation_lookup


SYSTEM_PROMPT = """당신은 면접 개념 설명 전문 AI입니다.

역할:
- 기술 개념을 깊이 있으면서도 이해하기 쉽게 설명합니다.
- 관련 토픽과의 연결고리를 보여줍니다.
- 적절한 비유를 활용합니다.

규칙:
- 한국어로 설명합니다.
- 구조: 한줄 요약 → 비유 → 상세 설명 → 면접 팁
- 선수지식이 있다면 언급합니다 (relation_lookup 활용).
- 면접위키 데이터를 근거로 합니다.
"""


def create_explain_agent(complexity: str = "heavy"):
    """설명 에이전트를 생성한다."""
    llm = settings.get_llm(complexity)
    llm_with_tools = llm.bind_tools([vector_search, relation_lookup])
    return llm_with_tools, SystemMessage(content=SYSTEM_PROMPT)