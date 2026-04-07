-- ============================================
-- topic_chunks 테이블 v2: parent-child 청크 + 하이브리드 검색
-- Supabase SQL Editor에서 실행
-- 기존 테이블에 컬럼 추가 + 새 테이블/함수 생성
-- ============================================

-- 1. 기존 topic_chunks 테이블에 새 컬럼 추가
ALTER TABLE topic_chunks
    ADD COLUMN IF NOT EXISTS parent_id TEXT,
    ADD COLUMN IF NOT EXISTS parent_content TEXT,
    ADD COLUMN IF NOT EXISTS content_hash TEXT,
    ADD COLUMN IF NOT EXISTS bm25_content TSVECTOR;

-- 2. bm25_content 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_bm25_content()
RETURNS TRIGGER AS $$
BEGIN
    NEW.bm25_content := to_tsvector('simple', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_bm25 ON topic_chunks;
CREATE TRIGGER trg_update_bm25
    BEFORE INSERT OR UPDATE OF content ON topic_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_bm25_content();

-- 3. 기존 행의 bm25_content 채우기
UPDATE topic_chunks
SET bm25_content = to_tsvector('simple', COALESCE(content, ''))
WHERE bm25_content IS NULL;

-- 4. GIN 인덱스 (BM25 전문 검색용)
CREATE INDEX IF NOT EXISTS topic_chunks_bm25_idx
    ON topic_chunks USING gin (bm25_content);

-- 5. content_hash 인덱스 (중복 확인용)
CREATE INDEX IF NOT EXISTS topic_chunks_content_hash_idx
    ON topic_chunks (content_hash);

-- 6. parent_id 인덱스
CREATE INDEX IF NOT EXISTS topic_chunks_parent_id_idx
    ON topic_chunks (parent_id);

-- 7. chunk_metadata 테이블: 섹션 경로 매핑
CREATE TABLE IF NOT EXISTS chunk_metadata (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    section_path TEXT,
    section_title TEXT,
    page INTEGER,
    topic_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chunk_metadata_chunk_id_idx
    ON chunk_metadata (chunk_id);

ALTER TABLE chunk_metadata ENABLE ROW LEVEL SECURITY;
CREATE POLICY "누구나 메타데이터 읽기" ON chunk_metadata FOR SELECT USING (true);

-- 8. 하이브리드 검색 RPC 함수 (벡터 + BM25)
CREATE OR REPLACE FUNCTION match_chunks_hybrid(
    query_embedding VECTOR(1536),
    query_text TEXT DEFAULT '',
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 10,
    filter_category TEXT DEFAULT NULL,
    vector_weight FLOAT DEFAULT 0.7,
    bm25_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    id BIGINT,
    topic_id TEXT,
    category_id TEXT,
    chunk_index INTEGER,
    content TEXT,
    heading TEXT,
    tags TEXT[],
    parent_id TEXT,
    parent_content TEXT,
    content_hash TEXT,
    vector_score FLOAT,
    bm25_score FLOAT,
    final_score FLOAT
)
LANGUAGE plpgsql
AS $$
DECLARE
    ts_query TSQUERY;
BEGIN
    -- 쿼리 텍스트를 tsquery로 변환 (단어 OR 매칭)
    IF query_text != '' THEN
        ts_query := plainto_tsquery('simple', query_text);
    ELSE
        ts_query := to_tsquery('simple', '');
    END IF;

    RETURN QUERY
    WITH vector_results AS (
        SELECT
            tc.id,
            tc.topic_id,
            tc.category_id,
            tc.chunk_index,
            tc.content,
            tc.heading,
            tc.tags,
            tc.parent_id,
            tc.parent_content,
            tc.content_hash,
            (1 - (tc.embedding <=> query_embedding))::FLOAT AS v_score,
            CASE
                WHEN query_text != '' AND tc.bm25_content @@ ts_query
                THEN ts_rank(tc.bm25_content, ts_query)::FLOAT
                ELSE 0.0
            END AS b_score
        FROM topic_chunks tc
        WHERE
            (filter_category IS NULL OR tc.category_id = filter_category)
    )
    SELECT
        vr.id,
        vr.topic_id,
        vr.category_id,
        vr.chunk_index,
        vr.content,
        vr.heading,
        vr.tags,
        vr.parent_id,
        vr.parent_content,
        vr.content_hash,
        vr.v_score AS vector_score,
        vr.b_score AS bm25_score,
        (vector_weight * vr.v_score + bm25_weight * vr.b_score)::FLOAT AS final_score
    FROM vector_results vr
    WHERE (vector_weight * vr.v_score + bm25_weight * vr.b_score) > match_threshold
    ORDER BY (vector_weight * vr.v_score + bm25_weight * vr.b_score) DESC
    LIMIT match_count;
END;
$$;