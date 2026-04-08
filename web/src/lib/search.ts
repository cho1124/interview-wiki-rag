// 면접위키 데이터 검색 (BM25-like scoring)

interface Chunk {
  topic_id: string;
  category_id: string;
  content: string;
  heading: string | null;
  content_hash: string;
  chunk_index: number;
  parent_content?: string;
}

// 데이터 로드 (빌드 시 번들됨)
let chunks: Chunk[] = [];
let tokenizedCorpus: string[][] = [];
let idfCache: Map<string, number> = new Map();

function loadData() {
  if (chunks.length > 0) return;

  try {
    // data/chunks.json에서 로드
    chunks = require('@/data/chunks.json') as Chunk[];

    // 토큰화
    tokenizedCorpus = chunks.map(c => tokenize(c.content));

    // IDF 계산
    const N = chunks.length;
    const dfMap = new Map<string, number>();
    for (const tokens of tokenizedCorpus) {
      const unique = new Set(tokens);
      for (const token of unique) {
        dfMap.set(token, (dfMap.get(token) || 0) + 1);
      }
    }
    for (const [term, df] of dfMap) {
      idfCache.set(term, Math.log((N - df + 0.5) / (df + 0.5) + 1));
    }
  } catch (e) {
    console.warn('면접위키 데이터 로드 실패:', e);
    chunks = [];
  }
}

function tokenize(text: string): string[] {
  // 한국어 + 영어 간단 토큰화
  return text
    .toLowerCase()
    .replace(/[^\w\sㄱ-ㅎ가-힣]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 1);
}

function bm25Score(queryTokens: string[], docTokens: string[], k1 = 1.5, b = 0.75): number {
  const avgDl = tokenizedCorpus.reduce((sum, d) => sum + d.length, 0) / Math.max(tokenizedCorpus.length, 1);
  const dl = docTokens.length;

  let score = 0;
  const termFreq = new Map<string, number>();
  for (const token of docTokens) {
    termFreq.set(token, (termFreq.get(token) || 0) + 1);
  }

  for (const qt of queryTokens) {
    const tf = termFreq.get(qt) || 0;
    const idf = idfCache.get(qt) || 0;
    score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgDl));
  }

  return score;
}

export function searchChunks(query: string, topK: number = 5): (Chunk & { score: number })[] {
  loadData();
  if (chunks.length === 0) return [];

  const queryTokens = tokenize(query);

  const scored = chunks.map((chunk, i) => ({
    ...chunk,
    score: bm25Score(queryTokens, tokenizedCorpus[i]),
  }));

  scored.sort((a, b) => b.score - a.score);

  return scored.slice(0, topK).filter(c => c.score > 0);
}
