"""충분성 게이트: 검색 결과의 품질을 평가하고 답변 전략을 결정한다.

3단계 임계값:
- score < 0.5 → reject: "문서에서 관련 내용을 찾지 못했습니다"
- 0.5 <= score < 0.7 → limited: 불확실성 마커 포함 제한적 답변
- score >= 0.7 → pass: 정상 답변
"""

from config import settings


# 게이트 상태 상수
GATE_PASS = "pass"
GATE_LIMITED = "limited"
GATE_REJECT = "reject"


def check_sufficiency(chunks: list[dict]) -> dict:
    """검색된 청크의 최고 점수를 기반으로 답변 전략을 결정한다.

    Args:
        chunks: hybrid_search 결과 (final_score 포함)

    Returns:
        dict with keys:
            - gate_status: "pass" | "limited" | "reject"
            - filtered_chunks: 임계값 이상의 청크만 필터링
            - confidence: 최고 점수
            - message: 게이트 상태에 따른 메시지
    """
    if not chunks:
        return {
            "gate_status": GATE_REJECT,
            "filtered_chunks": [],
            "confidence": 0.0,
            "message": "문서에서 관련 내용을 찾지 못했습니다.",
        }

    # 최고 점수 기준
    top_score = max(c.get("final_score", 0.0) for c in chunks)
    low_threshold = settings.sufficiency_low_threshold
    high_threshold = settings.sufficiency_high_threshold

    if top_score < low_threshold:
        return {
            "gate_status": GATE_REJECT,
            "filtered_chunks": [],
            "confidence": top_score,
            "message": "문서에서 관련 내용을 찾지 못했습니다.",
        }

    if top_score < high_threshold:
        # 제한적 답변: low_threshold 이상인 청크만 사용
        filtered = [c for c in chunks if c.get("final_score", 0.0) >= low_threshold]
        return {
            "gate_status": GATE_LIMITED,
            "filtered_chunks": filtered,
            "confidence": top_score,
            "message": (
                "관련 내용이 일부 발견되었으나 충분하지 않을 수 있습니다. "
                "아래 답변은 제한된 근거를 기반으로 합니다."
            ),
        }

    # 정상 답변: 모든 청크 사용
    return {
        "gate_status": GATE_PASS,
        "filtered_chunks": chunks,
        "confidence": top_score,
        "message": "",
    }