"""청크 리스트에 임베딩 벡터를 추가한다."""

from config import settings


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """각 청크의 content를 임베딩하여 embedding 필드를 추가한다."""
    if not chunks:
        return chunks

    embeddings_model = settings.get_embeddings()
    texts = [chunk["content"] for chunk in chunks]

    # 배치 임베딩 (한 번의 API 호출로 모든 청크 처리)
    vectors = embeddings_model.embed_documents(texts)

    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector

    return chunks