"""로컬 검색 어댑터: ChromaDB (벡터) + rank_bm25 (BM25) + RRF 결합."""

import os
import json
from rank_bm25 import BM25Okapi

try:
    import chromadb
except ImportError:
    chromadb = None


class LocalSearchAdapter:
    """ChromaDB + BM25 + RRF 기반 로컬 하이브리드 검색."""

    def __init__(self, persist_dir: str = "./data/chroma", k: int = 60):
        self._k = k  # RRF constant
        self._persist_dir = persist_dir
        self._client = None
        self._collection = None
        self._bm25 = None
        self._corpus = []  # list of chunk dicts
        self._tokenized = []  # tokenized for BM25

    def initialize(self, chunks: list[dict], embedding_fn):
        """청크 데이터로 인덱스를 초기화한다."""
        if chromadb is None:
            raise ImportError("chromadb is required for local search")

        self._client = chromadb.PersistentClient(path=self._persist_dir)

        # Collection 생성 또는 로드
        self._collection = self._client.get_or_create_collection(
            name="interview_wiki",
            metadata={"hnsw:space": "cosine"},
        )

        self._corpus = chunks

        # ChromaDB에 청크 추가 (이미 있으면 스킵)
        if self._collection.count() == 0 and chunks:
            ids = [f"chunk_{i}" for i in range(len(chunks))]
            documents = [c["content"] for c in chunks]
            metadatas = [{
                "topic_id": c.get("topic_id", ""),
                "category_id": c.get("category_id", ""),
                "heading": c.get("heading", ""),
                "content_hash": c.get("content_hash", ""),
                "chunk_index": c.get("chunk_index", 0),
            } for c in chunks]

            # 배치 임베딩
            embeddings = embedding_fn(documents)

            self._collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )

        # BM25 인덱스 빌드
        self._tokenized = [c["content"].lower().split() for c in chunks]
        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """RRF 기반 하이브리드 검색."""
        if not self._collection or not self._bm25:
            return []

        # 1. 벡터 검색
        vec_results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 2, self._collection.count()),
        )

        # 벡터 순위 매핑 (id → rank)
        vec_ranks = {}
        if vec_results and vec_results["ids"]:
            for rank, doc_id in enumerate(vec_results["ids"][0]):
                idx = int(doc_id.split("_")[1])
                vec_ranks[idx] = rank

        # 2. BM25 검색
        query_tokens = query.lower().split()
        bm25_scores = self._bm25.get_scores(query_tokens)
        bm25_ranked = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)
        bm25_ranks = {idx: rank for rank, idx in enumerate(bm25_ranked[:top_k * 2])}

        # 3. RRF 결합
        all_indices = set(vec_ranks.keys()) | set(bm25_ranks.keys())
        rrf_scores = []
        for idx in all_indices:
            v_rank = vec_ranks.get(idx, 1000)
            b_rank = bm25_ranks.get(idx, 1000)
            score = 1.0 / (self._k + v_rank) + 1.0 / (self._k + b_rank)
            rrf_scores.append((idx, score))

        rrf_scores.sort(key=lambda x: x[1], reverse=True)

        # 4. 결과 구성
        results = []
        for idx, score in rrf_scores[:top_k]:
            if idx < len(self._corpus):
                chunk = dict(self._corpus[idx])
                chunk["final_score"] = score
                results.append(chunk)

        return results

    @classmethod
    def load_from_json(cls, json_path: str, embedding_fn, persist_dir: str = "./data/chroma"):
        """JSON 파일에서 데이터를 로드하여 인덱스를 초기화한다."""
        with open(json_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        adapter = cls(persist_dir=persist_dir)
        adapter.initialize(chunks, embedding_fn)
        return adapter
