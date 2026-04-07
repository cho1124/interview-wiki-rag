-- ============================================
-- topic_chunks v3: 완전 초기화 + gte-small (384-dim)
-- Supabase SQL Editor에서 실행
-- ============================================

-- Drop old if exists
DROP TABLE IF EXISTS chunk_metadata CASCADE;
DROP TABLE IF EXISTS topic_chunks CASCADE;
DROP FUNCTION IF EXISTS match_chunks CASCADE;
DROP FUNCTION IF EXISTS match_chunks_hybrid CASCADE;
DROP FUNCTION IF EXISTS update_bm25_content CASCADE;

-- Ensure pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- topic_chunks with 384-dim vectors (gte-small)
CREATE TABLE topic_chunks (
    id BIGSERIAL PRIMARY KEY,
    topic_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    heading TEXT,
    tags TEXT[] DEFAULT '{}',
    embedding VECTOR(384),
    parent_id TEXT,
    parent_content TEXT,
    content_hash TEXT,
    bm25_content TSVECTOR,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (category_id, topic_id) REFERENCES topics(category_id, id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX topic_chunks_embedding_idx ON topic_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS topic_chunks_bm25_idx ON topic_chunks USING gin (bm25_content);
CREATE INDEX IF NOT EXISTS topic_chunks_content_hash_idx ON topic_chunks (content_hash);
CREATE INDEX IF NOT EXISTS topic_chunks_parent_id_idx ON topic_chunks (parent_id);

-- RLS
ALTER TABLE topic_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "누구나 청크 읽기" ON topic_chunks FOR SELECT USING (true);
CREATE POLICY "서비스키로 청크 쓰기" ON topic_chunks FOR INSERT WITH CHECK (true);
CREATE POLICY "서비스키로 청크 삭제" ON topic_chunks FOR DELETE USING (true);

-- BM25 auto-update trigger
CREATE OR REPLACE FUNCTION update_bm25_content()
RETURNS TRIGGER AS $$
BEGIN
    NEW.bm25_content := to_tsvector('simple', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_bm25
    BEFORE INSERT OR UPDATE OF content ON topic_chunks
    FOR EACH ROW EXECUTE FUNCTION update_bm25_content();

-- chunk_metadata table
CREATE TABLE IF NOT EXISTS chunk_metadata (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    section_path TEXT,
    section_title TEXT,
    topic_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chunk_metadata_chunk_id_idx ON chunk_metadata (chunk_id);
ALTER TABLE chunk_metadata ENABLE ROW LEVEL SECURITY;
CREATE POLICY "누구나 메타데이터 읽기" ON chunk_metadata FOR SELECT USING (true);
CREATE POLICY "서비스키로 메타데이터 쓰기" ON chunk_metadata FOR INSERT WITH CHECK (true);

-- Hybrid search RPC (vector 384-dim + BM25)
CREATE OR REPLACE FUNCTION match_chunks_hybrid(
    query_embedding VECTOR(384),
    query_text TEXT DEFAULT '',
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 5,
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
LANGUAGE plpgsql AS $$
DECLARE ts_query TSQUERY;
BEGIN
    IF query_text != '' THEN
        ts_query := plainto_tsquery('simple', query_text);
    ELSE
        ts_query := to_tsquery('simple', '');
    END IF;

    RETURN QUERY
    WITH vector_results AS (
        SELECT
            tc.id, tc.topic_id, tc.category_id, tc.chunk_index,
            tc.content, tc.heading, tc.tags,
            tc.parent_id, tc.parent_content, tc.content_hash,
            (1 - (tc.embedding <=> query_embedding))::FLOAT AS v_score,
            CASE
                WHEN query_text != '' AND tc.bm25_content @@ ts_query
                THEN ts_rank(tc.bm25_content, ts_query)::FLOAT
                ELSE 0.0
            END AS b_score
        FROM topic_chunks tc
        WHERE (filter_category IS NULL OR tc.category_id = filter_category)
    )
    SELECT
        vr.id, vr.topic_id, vr.category_id, vr.chunk_index,
        vr.content, vr.heading, vr.tags,
        vr.parent_id, vr.parent_content, vr.content_hash,
        vr.v_score, vr.b_score,
        (vector_weight * vr.v_score + bm25_weight * vr.b_score)::FLOAT AS final_score
    FROM vector_results vr
    WHERE (vector_weight * vr.v_score + bm25_weight * vr.b_score) > match_threshold
    ORDER BY (vector_weight * vr.v_score + bm25_weight * vr.b_score) DESC
    LIMIT match_count;
END;
$$;