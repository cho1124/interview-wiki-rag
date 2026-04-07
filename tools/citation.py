"""인용 시스템: LLM 응답에서 인용을 추출하고 검증한다.

기능:
- [1], [2] 형태의 인라인 인용 추출
- 인용 번호를 청크 메타데이터에 매핑
- 미인용 주장 탐지 (검증)
- 구조화된 응답 + 인용 목록 생성
"""

import re


def extract_citations(response_text: str) -> list[int]:
    """응답 텍스트에서 인용 번호를 추출한다.

    Args:
        response_text: LLM 응답 텍스트 ("[1] ... [2] ..." 형태)

    Returns:
        사용된 인용 번호 리스트 (정렬, 중복 제거)
    """
    pattern = r"\[(\d+)\]"
    numbers = [int(m) for m in re.findall(pattern, response_text)]
    return sorted(set(numbers))


def build_citation_map(
    chunks: list[dict],
) -> dict[int, dict]:
    """청크 리스트를 인용 번호 -> 메타데이터 맵으로 변환한다.

    청크 순서가 인용 번호 (1-indexed).

    Args:
        chunks: 검색된 청크 리스트

    Returns:
        {1: {topic_id, category_id, heading, content_preview, ...}, ...}
    """
    citation_map = {}
    for i, chunk in enumerate(chunks, start=1):
        citation_map[i] = {
            "citation_number": i,
            "topic_id": chunk.get("topic_id", ""),
            "category_id": chunk.get("category_id", ""),
            "heading": chunk.get("heading", ""),
            "content_hash": chunk.get("content_hash", ""),
            "content_preview": chunk.get("content", "")[:100] + "...",
            "final_score": chunk.get("final_score", 0.0),
        }
    return citation_map


def validate_citations(
    response_text: str,
    citation_map: dict[int, dict],
) -> dict:
    """인용의 유효성을 검증한다.

    검증 항목:
    1. 사용된 인용 번호가 실제 소스에 매핑되는지
    2. 응답의 문장 중 인용이 없는 주장이 있는지

    Args:
        response_text: LLM 응답 텍스트
        citation_map: build_citation_map 결과

    Returns:
        dict with keys:
            - valid_citations: 유효한 인용 번호 리스트
            - invalid_citations: 소스가 없는 인용 번호 리스트
            - uncited_sentences: 인용이 없는 주장 문장 리스트
            - citation_coverage: 인용 커버리지 비율 (0~1)
    """
    used_citations = extract_citations(response_text)
    valid_numbers = set(citation_map.keys())

    valid_citations = [n for n in used_citations if n in valid_numbers]
    invalid_citations = [n for n in used_citations if n not in valid_numbers]

    # 문장 단위로 인용 여부 확인
    sentences = _split_sentences(response_text)
    uncited_sentences = []

    for sentence in sentences:
        # 짧은 문장, 인사말, 구조적 텍스트는 제외
        if len(sentence.strip()) < 15:
            continue
        if _is_structural_text(sentence):
            continue
        # 인용이 포함되지 않은 주장 문장
        if not re.search(r"\[\d+\]", sentence):
            uncited_sentences.append(sentence.strip())

    total_claim_sentences = len(sentences) - len(
        [s for s in sentences if len(s.strip()) < 15 or _is_structural_text(s)]
    )
    cited_count = total_claim_sentences - len(uncited_sentences)
    coverage = cited_count / max(total_claim_sentences, 1)

    return {
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "uncited_sentences": uncited_sentences,
        "citation_coverage": round(coverage, 2),
    }


def format_citations_footer(
    citation_map: dict[int, dict],
    used_citations: list[int],
) -> str:
    """응답 하단에 추가할 인용 목록을 포맷팅한다.

    Args:
        citation_map: build_citation_map 결과
        used_citations: 실제 사용된 인용 번호

    Returns:
        포맷팅된 인용 목록 문자열
    """
    if not used_citations:
        return ""

    lines = ["\n---\n**출처:**"]
    for num in sorted(used_citations):
        if num in citation_map:
            meta = citation_map[num]
            topic = meta["topic_id"]
            category = meta["category_id"]
            heading = meta.get("heading") or ""
            heading_str = f" > {heading}" if heading else ""
            lines.append(f"- [{num}] {category}/{topic}{heading_str}")

    return "\n".join(lines)


def process_response_with_citations(
    response_text: str,
    chunks: list[dict],
) -> dict:
    """LLM 응답에 인용 시스템을 적용하여 구조화된 결과를 반환한다.

    Args:
        response_text: LLM 응답 텍스트
        chunks: 검색된 소스 청크 리스트

    Returns:
        dict with keys:
            - response: 인용 목록이 추가된 최종 응답
            - citations: 인용 메타데이터
            - validation: 인용 검증 결과
    """
    citation_map = build_citation_map(chunks)
    used_citations = extract_citations(response_text)
    validation = validate_citations(response_text, citation_map)
    footer = format_citations_footer(citation_map, used_citations)

    final_response = response_text
    if footer:
        final_response = response_text + "\n" + footer

    return {
        "response": final_response,
        "citations": {
            num: citation_map[num]
            for num in used_citations
            if num in citation_map
        },
        "validation": validation,
    }


def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분리한다."""
    # 한국어 문장 종결 + 영문 마침표
    pattern = r"(?<=[.!?。])\s+"
    sentences = re.split(pattern, text)
    return [s for s in sentences if s.strip()]


def _is_structural_text(sentence: str) -> bool:
    """구조적 텍스트인지 확인 (인용이 필요 없는 텍스트)."""
    structural_patterns = [
        r"^#{1,3}\s",       # 마크다운 헤딩
        r"^\*\*출처",       # 출처 섹션
        r"^---",            # 구분선
        r"^[-*]\s",         # 리스트 아이템 시작 (짧은 것)
        r"^>\s",            # 인용 블록
        r"^\|",             # 테이블
    ]
    for p in structural_patterns:
        if re.match(p, sentence.strip()):
            return True
    return False