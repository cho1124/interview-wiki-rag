-- ============================================
-- topic_chunks 테이블: 면접위키 토픽을 청킹하여 임베딩 저장
-- Supabase SQL Editor에서 실행
-- ============================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE topic_chunks (
    id BIGSERIAL PRIMARY KEY,
    topic_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    heading TEXT,
    tags TEXT[] DEFAULT '{}',
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (category_id, topic_id)
        REFERENCES topics(category_id, id) ON DELETE CASCADE
);

-- HNSW 인덱스: 코사인 유사도 기반 근사 최근접 이웃 검색
CREATE INDEX topic_chunks_embedding_idx
    ON topic_chunks USING hnsw (embedding vector_cosine_ops);

-- RLS 정책
ALTER TABLE topic_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "누구나 청크 읽기" ON topic_chunks FOR SELECT USING (true);

-- 유사도 검색 함수
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5,
    filter_category TEXT DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    topic_id TEXT,
    category_id TEXT,
    chunk_index INTEGER,
    content TEXT,
    heading TEXT,
    tags TEXT[],
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        tc.id,
        tc.topic_id,
        tc.category_id,
        tc.chunk_index,
        tc.content,
        tc.heading,
        tc.tags,
        1 - (tc.embedding <=> query_embedding) AS similarity
    FROM topic_chunks tc
    WHERE
        1 - (tc.embedding <=> query_embedding) > match_threshold
        AND (filter_category IS NULL OR tc.category_id = filter_category)
    ORDER BY tc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;