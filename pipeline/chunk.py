"""마크다운 콘텐츠를 청킹한다.

전략:
1. MarkdownHeaderTextSplitter로 ## / ### 단위 분리 (면접 질문 그룹 보존)
2. RecursiveCharacterTextSplitter로 큰 섹션 추가 분할
3. 코드 블록 내부에서는 분리하지 않음
4. Parent-Child 청크 생성: 3개 연속 자식 청크를 묶어 부모 청크 생성 (~1500 tokens)
5. 각 청크에 content_hash (SHA256 first 16 chars) 부여
"""

import hashlib
import re

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from config import settings


def chunk_topic(topic: dict) -> list[dict]:
    """토픽 하나를 청크 리스트로 변환한다.

    Parent-child 구조:
    - child chunks: 기존 분할 로직으로 생성된 개별 청크
    - parent chunks: 연속 3개 자식 청크의 content를 합쳐 parent_content로 저장
    - 각 청크는 chunk_id (doc_id + content_hash)를 가짐

    Returns:
        list[dict]: 각 청크는 content, heading, metadata, parent_content, chunk_id,
                    content_hash를 포함
    """
    content = topic.get("content", "")
    if not content.strip():
        return []

    # 1단계: 마크다운 헤더 기준 분리
    headers_to_split = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split,
        strip_headers=False,
    )
    md_chunks = md_splitter.split_text(content)

    # 2단계: 큰 섹션은 추가 분할
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator=True,
    )

    child_chunks = []
    chunk_index = 0

    for md_chunk in md_chunks:
        text = md_chunk.page_content
        heading = _extract_heading(md_chunk.metadata)
        section_path = _build_section_path(md_chunk.metadata)

        # 코드 블록 보호: 청크 사이즈 이내면 그대로 유지
        if len(text) <= settings.chunk_size:
            child_chunks.append(
                _make_chunk(topic, text, heading, chunk_index, section_path)
            )
            chunk_index += 1
        else:
            # 코드 블록을 임시 치환 후 분할
            text_protected, code_blocks = _protect_code_blocks(text)
            sub_chunks = text_splitter.split_text(text_protected)

            for sub in sub_chunks:
                restored = _restore_code_blocks(sub, code_blocks)
                child_chunks.append(
                    _make_chunk(topic, restored, heading, chunk_index, section_path)
                )
                chunk_index += 1

    # 3단계: Parent-child 관계 생성
    _assign_parent_chunks(child_chunks, settings.parent_chunk_group_size)

    return child_chunks


def _make_chunk(
    topic: dict,
    content: str,
    heading: str | None,
    index: int,
    section_path: str = "",
) -> dict:
    """개별 청크 딕셔너리를 생성한다."""
    content_stripped = content.strip()
    content_hash = _compute_content_hash(content_stripped)
    doc_id = f"{topic['category_id']}_{topic['id']}"
    chunk_id = f"{doc_id}_{content_hash}"

    return {
        "topic_id": topic["id"],
        "category_id": topic["category_id"],
        "chunk_index": index,
        "content": content_stripped,
        "heading": heading,
        "tags": topic.get("tags", []),
        "chunk_id": chunk_id,
        "content_hash": content_hash,
        "section_path": section_path,
        # parent 관련 필드는 _assign_parent_chunks에서 채움
        "parent_id": None,
        "parent_content": None,
    }


def _assign_parent_chunks(chunks: list[dict], group_size: int = 3) -> None:
    """연속된 자식 청크를 그룹으로 묶어 부모 청크를 생성한다.

    group_size개의 연속 자식 청크의 content를 합쳐 parent_content로 저장.
    같은 그룹의 자식 청크들은 동일한 parent_id를 공유한다.

    Args:
        chunks: 자식 청크 리스트 (in-place 수정)
        group_size: 부모 당 자식 청크 수
    """
    if not chunks:
        return

    for i in range(0, len(chunks), group_size):
        group = chunks[i : i + group_size]

        # 부모 콘텐츠 = 그룹 내 자식들의 content 합침
        parent_content = "\n\n".join(c["content"] for c in group)
        parent_hash = _compute_content_hash(parent_content)

        # 첫 번째 청크의 doc_id 기반으로 parent_id 생성
        doc_id = f"{group[0]['category_id']}_{group[0]['topic_id']}"
        parent_id = f"{doc_id}_parent_{parent_hash}"

        for chunk in group:
            chunk["parent_id"] = parent_id
            chunk["parent_content"] = parent_content


def _compute_content_hash(content: str) -> str:
    """콘텐츠의 SHA256 해시 앞 16자를 반환한다."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _extract_heading(metadata: dict) -> str | None:
    """MarkdownHeaderTextSplitter 메타데이터에서 가장 하위 헤딩 추출."""
    for key in ("h3", "h2", "h1"):
        if key in metadata:
            return metadata[key]
    return None


def _build_section_path(metadata: dict) -> str:
    """메타데이터에서 섹션 경로를 빌드한다 (h1 > h2 > h3)."""
    parts = []
    for key in ("h1", "h2", "h3"):
        if key in metadata:
            parts.append(metadata[key])
    return " > ".join(parts) if parts else ""


def _protect_code_blocks(text: str) -> tuple[str, list[str]]:
    """코드 블록을 플레이스홀더로 치환하여 분할 시 깨지지 않게 보호."""
    code_blocks = []
    pattern = re.compile(r"```[\s\S]*?```", re.MULTILINE)

    def replacer(match):
        code_blocks.append(match.group())
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    protected = pattern.sub(replacer, text)
    return protected, code_blocks


def _restore_code_blocks(text: str, code_blocks: list[str]) -> str:
    """플레이스홀더를 원래 코드 블록으로 복원."""
    for i, block in enumerate(code_blocks):
        text = text.replace(f"__CODE_BLOCK_{i}__", block)
    return text