"""퀴즈 에이전트: 면접위키 데이터 기반으로 면접 문제를 출제한다."""

from langchain_core.messages import SystemMessage

from config import settings
from tools.vector_search import vector_search
from tools.topic_lookup import topic_lookup


SYSTEM_PROMPT = """당신은 면접 문제 출제 전문 AI입니다.

역할:
- 면접위키 데이터를 기반으로 실전 면접 질문을 생성합니다.
- 각 질문에 대한 모범 답변 핵심 포인트도 함께 제공합니다.

규칙:
- 한국어로 출제합니다.
- 질문 난이도를 표시합니다 (기초/중급/심화).
- 위키에 있는 내용 범위 내에서 출제합니다.
- 형식: 번호. [난이도] 질문 → 핵심 포인트
"""


def create_quiz_agent(complexity: str = "light"):
    """퀴즈 에이전트를 생성한다."""
    llm = settings.get_llm(complexity)
    llm_with_tools = llm.bind_tools([vector_search, topic_lookup])
    return llm_with_tools, SystemMessage(content=SYSTEM_PROMPT)