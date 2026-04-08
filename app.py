"""면접위키 RAG 시스템 — Gradio 웹 UI.

Phase 2 배포: 준개발자 대상 localhost 웹 인터페이스.
HuggingFace Spaces 호환.
"""

import os
import logging

import gradio as gr

# --- Spaces 환경 감지 ---
IS_SPACES = os.environ.get("SPACE_ID") is not None

logger = logging.getLogger(__name__)

# --- LangGraph 앱 초기화 (lazy) ---
_app = None
_init_error: str | None = None


def _get_app():
    """LangGraph 앱 인스턴스를 지연 생성한다.

    Spaces에서 Supabase 미설정 등으로 초기화 실패 시
    에러 메시지를 저장하고 None을 반환한다.
    """
    global _app, _init_error
    if _app is not None:
        return _app
    if _init_error is not None:
        return None

    try:
        from graph.workflow import build_graph
        _app = build_graph()
        logger.info("LangGraph 워크플로우 초기화 완료")
    except Exception as e:
        _init_error = str(e)
        logger.warning("LangGraph 워크플로우 초기화 실패: %s", e)
    return _app


def _get_settings_info() -> str:
    """현재 설정 정보를 문자열로 반환한다.

    import 실패 시에도 안전하게 처리한다.
    """
    try:
        from config import settings
        mode = settings._resolve_mode()
        info = f"Mode: {mode}\n"
        if mode == "spaces":
            info += f"LLM: {settings.hf_model}\n"
            info += f"Embedding: {settings.local_embedding_model}"
        elif mode == "cloud":
            info += f"LLM: {settings.llm_light_model} / {settings.llm_heavy_model}\n"
            info += f"Embedding: {settings.embedding_model}"
        else:  # local
            info += f"LLM: {settings.ollama_model}\n"
            info += f"Embedding: {settings.local_embedding_model}"
        return info
    except Exception as e:
        return f"설정 로드 실패: {e}"


def chat(message: str, history: list[list[str]]) -> str:
    """사용자 메시지를 처리하고 응답을 반환한다."""
    if not message.strip():
        return "질문을 입력해주세요."

    app = _get_app()
    if app is None:
        return (
            f"시스템 초기화에 실패했습니다.\n\n"
            f"오류: {_init_error}\n\n"
            f"환경 변수(API 키 등)를 확인해주세요."
        )

    try:
        result = app.invoke({
            "query": message,
            "messages": [],
            "agent_type": "",
            "complexity": "",
            "response": "",
            "citations": {},
            "citation_validation": {},
            "gate_status": "",
            "confidence": 0.0,
            "cache_hit": "",
        })

        response = result.get("response", "응답을 생성하지 못했습니다.")
        gate = result.get("gate_status", "")
        cache_hit = result.get("cache_hit", "")
        confidence = result.get("confidence", 0.0)

        # 메타 정보 추가
        meta_parts = []
        if gate:
            meta_parts.append(f"Gate: {gate}")
        if cache_hit:
            meta_parts.append(f"Cache: {cache_hit}")
        if confidence > 0:
            meta_parts.append(f"Confidence: {confidence:.2f}")

        if meta_parts:
            response += f"\n\n---\n*{' | '.join(meta_parts)}*"

        return response

    except Exception as e:
        logger.exception("chat() 처리 중 오류")
        return f"오류가 발생했습니다: {str(e)}"


def get_cache_stats() -> str:
    """캐시 통계를 반환한다."""
    try:
        from cache.manager import get_cache_manager
        stats = get_cache_manager().stats()
        return (
            f"L1 (쿼리): {stats['l1_query_cache_size']}건\n"
            f"L2 (검색): {stats['l2_retrieval_cache_size']}건\n"
            f"L3 (생성): {stats['l3_generation_cache_size']}건"
        )
    except Exception as e:
        return f"캐시 통계 조회 실패: {e}"


def clear_cache() -> str:
    """전체 캐시를 초기화한다."""
    try:
        from cache.manager import get_cache_manager
        get_cache_manager().invalidate_all()
        return "캐시가 초기화되었습니다."
    except Exception as e:
        return f"캐시 초기화 실패: {e}"


# --- UI ---

with gr.Blocks(
    title="면접위키 RAG",
    theme=gr.themes.Soft(),
) as demo:
    gr.Markdown("# 면접위키 RAG 시스템")
    gr.Markdown("면접 준비를 위한 AI 질의응답 시스템. 검색 → 생성 → 인용 검증 파이프라인.")

    # Spaces 배너
    if IS_SPACES:
        gr.Markdown(
            "> **HuggingFace Spaces에서 실행 중** — 무료 Inference API 사용\n"
            "> 첫 질문 시 임베딩 모델 로딩으로 응답이 느릴 수 있습니다."
        )

    with gr.Row():
        with gr.Column(scale=4):
            chatbot = gr.ChatInterface(
                fn=chat,
                examples=[
                    "가상 DOM이 뭐야?",
                    "React vs Vue 비교해줘",
                    "DI를 초보자한테 설명해줘",
                    "Java 면접 문제 3개 내줘",
                    "TCP와 UDP 차이점은?",
                ],
                title="",
            )

        with gr.Column(scale=1):
            gr.Markdown("### 시스템 상태")
            stats_box = gr.Textbox(label="캐시 통계", interactive=False, lines=3)
            refresh_btn = gr.Button("통계 새로고침")
            clear_btn = gr.Button("캐시 초기화", variant="stop")
            clear_result = gr.Textbox(label="", interactive=False, lines=1)

            refresh_btn.click(fn=get_cache_stats, outputs=stats_box)
            clear_btn.click(fn=clear_cache, outputs=clear_result)

            gr.Markdown("### 설정 정보")
            gr.Textbox(
                value=_get_settings_info(),
                label="현재 설정",
                interactive=False,
                lines=4,
            )

            if _init_error:
                gr.Markdown(
                    f"### 초기화 오류\n`{_init_error}`\n\n"
                    "환경 변수를 확인해주세요."
                )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=8000)
