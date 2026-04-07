"""비교 에이전트: 두 기술/개념을 비교표와 함께 분석한다."""

from langchain_core.messages import SystemMessage

from config import settings
from tools.vector_search import vector_search
from tools.topic_lookup import topic_lookup


SYSTEM_PROMPT = """당신은 기술 비교 전문 AI입니다.

역할:
- 두 가지 이상의 기술/개념을 체계적으로 비교합니다.
- 비교표(테이블)를 포함하여 한눈에 차이를 볼 수 있게 합니다.
- 면접에서 비교 질문이 나왔을 때의 답변 전략을 제시합니다.

규칙:
- 한국어로 비교합니다.
- 구조: 한줄 요약 → 비교표 → 상세 분석 → 면접 답변 팁
- 양쪽 기술의 위키 데이터를 모두 검색하여 근거로 사용합니다.
- 객관적 비교를 하되, 용도별 추천을 합니다.
"""


def create_compare_agent(complexity: str = "heavy"):
    """비교 에이전트를 생성한다."""
    llm = settings.get_llm(complexity)
    llm_with_tools = llm.bind_tools([vector_search, topic_lookup])
    return llm_with_tools, SystemMessage(content=SYSTEM_PROMPT)