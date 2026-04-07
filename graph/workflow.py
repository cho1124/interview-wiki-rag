"""LangGraph StateGraph 워크플로우 정의.

흐름:
    START → router → (search | quiz | explain | compare) → END

v2 search 흐름:
    cache_check → hybrid_search → sufficiency_gate → generate → citation → cache_save → monitor
"""

from langchain_core.messages import HumanMessage, AIMessage

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from agents.router import route_query
from agents.search import create_search_agent, build_context_from_chunks
from agents.quiz import create_quiz_agent
from agents.explain import create_explain_agent
from agents.compare import create_compare_agent


# --- 노드 함수 ---

def router_node(state: AgentState) -> dict:
    """사용자 의도를 분류하고 에이전트를 선택한다."""
    query = state["query"]
    result = route_query(query)

    print(f"  [Router] → {result['agent_type']} ({result['complexity']}) | {result['reason']}")

    return {
        "agent_type": result["agent_type"],
        "complexity": result["complexity"],
    }


def _run_agent(state: AgentState, create_fn) -> dict:
    """공통 에이전트 실행 로직: 도구 호출 → 최종 응답 생성."""
    complexity = state.get("complexity", "light")
    llm_with_tools, system_msg = create_fn(complexity)

    messages = [system_msg, HumanMessage(content=state["query"])]

    # 첫 번째 호출: 도구 사용 여부 결정
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    # 도구 호출이 있으면 실행
    if response.tool_calls:
        from langchain_core.messages import ToolMessage

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            # 도구 실행
            tool_fn = _get_tool_fn(tool_name)
            tool_result = tool_fn.invoke(tool_args)

            messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"])
            )

        # 도구 결과를 바탕으로 최종 응답 생성
        response = llm_with_tools.invoke(messages)

    return {
        "response": response.content,
        "messages": [HumanMessage(content=state["query"]), AIMessage(content=response.content)],
    }


def _get_tool_fn(name: str):
    """도구 이름으로 실제 함수를 찾는다."""
    from tools.vector_search import vector_search
    from tools.topic_lookup import topic_lookup
    from tools.relation_lookup import relation_lookup
    from tools.hybrid_search import hybrid_search

    tool_map = {
        "vector_search": vector_search,
        "topic_lookup": topic_lookup,
        "relation_lookup": relation_lookup,
        "hybrid_search": hybrid_search,
    }
    return tool_map[name]


def search_node(state: AgentState) -> dict:
    """v2 검색 노드: 캐시 → 하이브리드 검색 → 게이트 → 생성 → 인용 → 모니터링."""
    from monitoring import log_query
    from cache.manager import get_cache_manager
    from tools.hybrid_search import hybrid_search
    from tools.sufficiency_gate import check_sufficiency, GATE_REJECT, GATE_LIMITED
    from tools.citation import process_response_with_citations
    from tools.error_handler import SearchError

    query = state["query"]
    complexity = state.get("complexity", "light")
    metrics = log_query(query)
    metrics.set_agent_type("search")
    cache = get_cache_manager()

    print("  [Search Agent] 검색 중...")

    try:
        # --- L1 캐시: 쿼리 완전 일치 ---
        cached_response = cache.l1.get(query)
        if cached_response:
            print("  [Cache] L1 hit")
            metrics.set_cache_hit("l1")
            metrics.save()
            return {
                "response": cached_response.get("response", ""),
                "citations": cached_response.get("citations", {}),
                "citation_validation": cached_response.get("validation", {}),
                "gate_status": cached_response.get("gate_status", "pass"),
                "confidence": cached_response.get("confidence", 1.0),
                "cache_hit": "l1",
                "messages": [
                    HumanMessage(content=query),
                    AIMessage(content=cached_response.get("response", "")),
                ],
            }

        # --- L2 캐시: 검색 결과 ---
        metrics.start_search()
        search_params = {"category": None}
        cached_chunks = cache.l2.get(query, search_params)

        if cached_chunks is not None:
            print("  [Cache] L2 hit")
            metrics.set_cache_hit("l2")
            chunks = cached_chunks
        else:
            # 하이브리드 검색 실행
            chunks = hybrid_search.invoke({"query": query, "category": None})
            cache.l2.set(query, chunks, search_params)

        metrics.end_search()

        # --- 충분성 게이트 ---
        gate_result = check_sufficiency(chunks)
        gate_status = gate_result["gate_status"]
        metrics.set_gate_status(gate_status)

        if gate_status == GATE_REJECT:
            print(f"  [Gate] REJECT (confidence: {gate_result['confidence']:.2f})")
            error_response = SearchError.empty_results(query)
            metrics.save()
            return {
                "response": error_response["response"],
                "citations": {},
                "citation_validation": {},
                "gate_status": gate_status,
                "confidence": gate_result["confidence"],
                "cache_hit": "",
                "messages": [
                    HumanMessage(content=query),
                    AIMessage(content=error_response["response"]),
                ],
            }

        filtered_chunks = gate_result["filtered_chunks"]
        print(f"  [Gate] {gate_status.upper()} (confidence: {gate_result['confidence']:.2f}, chunks: {len(filtered_chunks)})")

        # --- 토큰 예산 기반 컨텍스트 빌드 ---
        context = build_context_from_chunks(filtered_chunks)

        # --- L3 캐시: 생성 결과 ---
        from config import settings as cfg
        model_name = cfg.get_model_name(complexity)
        chunk_ids = [c.get("content_hash", str(i)) for i, c in enumerate(filtered_chunks)]

        cached_gen = cache.l3.get(query, chunk_ids, model_name)
        if cached_gen is not None:
            print("  [Cache] L3 hit")
            metrics.set_cache_hit("l3")
            metrics.save()
            return {
                "response": cached_gen.get("response", ""),
                "citations": cached_gen.get("citations", {}),
                "citation_validation": cached_gen.get("validation", {}),
                "gate_status": gate_status,
                "confidence": gate_result["confidence"],
                "cache_hit": "l3",
                "messages": [
                    HumanMessage(content=query),
                    AIMessage(content=cached_gen.get("response", "")),
                ],
            }

        # --- LLM 생성 ---
        metrics.start_generation()

        llm_with_tools, system_msg = create_search_agent(complexity)
        metrics.set_model(model_name)

        # 불확실성 프리픽스
        uncertainty_prefix = ""
        if gate_status == GATE_LIMITED:
            uncertainty_prefix = gate_result["message"] + "\n\n"

        # 컨텍스트를 포함한 사용자 메시지 구성
        user_message = (
            f"질문: {query}\n\n"
            f"아래는 면접위키에서 검색된 관련 문서입니다. "
            f"반드시 아래 문서만을 근거로 답변하고, 각 주장에 [번호] 인용을 포함하세요.\n\n"
            f"{context}"
        )

        from langchain_core.messages import HumanMessage as HM
        messages = [system_msg, HM(content=user_message)]
        response = llm_with_tools.invoke(messages)
        raw_response = response.content

        metrics.end_generation()
        metrics.set_tokens(_estimate_tokens(raw_response))

        # --- 인용 처리 ---
        citation_result = process_response_with_citations(raw_response, filtered_chunks)
        final_response = uncertainty_prefix + citation_result["response"]
        metrics.set_citation_count(len(citation_result.get("citations", {})))

        # --- 캐시 저장 ---
        cache_value = {
            "response": final_response,
            "citations": citation_result["citations"],
            "validation": citation_result["validation"],
            "gate_status": gate_status,
            "confidence": gate_result["confidence"],
        }
        cache.l1.set(query, cache_value)
        cache.l3.set(query, chunk_ids, model_name, cache_value)

        metrics.save()

        return {
            "response": final_response,
            "citations": citation_result["citations"],
            "citation_validation": citation_result["validation"],
            "gate_status": gate_status,
            "confidence": gate_result["confidence"],
            "cache_hit": "",
            "messages": [
                HumanMessage(content=query),
                AIMessage(content=final_response),
            ],
        }

    except Exception as e:
        print(f"  [Search Error] {e}")
        metrics.set_error(str(e))
        metrics.save()
        error_result = SearchError.general_error(e)
        return {
            "response": error_result["response"],
            "citations": {},
            "citation_validation": {},
            "gate_status": "error",
            "confidence": 0.0,
            "cache_hit": "",
            "messages": [
                HumanMessage(content=query),
                AIMessage(content=error_result["response"]),
            ],
        }


def _estimate_tokens(text: str) -> int:
    """간단한 토큰 수 추정."""
    return max(1, len(text) // 3)


def quiz_node(state: AgentState) -> dict:
    print("  [Quiz Agent] 문제 출제 중...")
    return _run_agent(state, create_quiz_agent)


def explain_node(state: AgentState) -> dict:
    print("  [Explain Agent] 설명 생성 중...")
    return _run_agent(state, create_explain_agent)


def compare_node(state: AgentState) -> dict:
    print("  [Compare Agent] 비교 분석 중...")
    return _run_agent(state, create_compare_agent)


# --- 라우팅 ---

def route_decision(state: AgentState) -> str:
    """Router 결과에 따라 다음 노드를 결정한다."""
    return state["agent_type"]


# --- 그래프 빌드 ---

def build_graph():
    """멀티에이전트 워크플로우 그래프를 빌드한다."""
    graph = StateGraph(AgentState)

    # 노드 등록
    graph.add_node("router", router_node)
    graph.add_node("search", search_node)
    graph.add_node("quiz", quiz_node)
    graph.add_node("explain", explain_node)
    graph.add_node("compare", compare_node)

    # 진입점
    graph.set_entry_point("router")

    # 라우터 → 전문 에이전트 (조건부 분기)
    graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "search": "search",
            "quiz": "quiz",
            "explain": "explain",
            "compare": "compare",
        },
    )

    # 각 에이전트 → 종료
    for agent in ("search", "quiz", "explain", "compare"):
        graph.add_edge(agent, END)

    return graph.compile()


# 싱글턴 앱 인스턴스
app = build_graph()