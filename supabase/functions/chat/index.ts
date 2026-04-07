import 'jsr:@supabase/functions-js/edge-runtime.d.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const embedModel = new Supabase.ai.Session('gte-small')
const OLLAMA_HOST = Deno.env.get('OLLAMA_HOST') ?? Deno.env.get('AI_INFERENCE_API_HOST') ?? 'http://localhost:11434'

const SYSTEM_PROMPT = `당신은 면접위키 기반 Q&A 전문가입니다.

규칙:
1. 반드시 검색된 문서의 내용만을 기반으로 답변하세요.
2. 각 주장에 [1], [2] 형태의 인용 번호를 포함하세요.
3. 검색된 문서에 없는 내용은 절대 포함하지 마세요.
4. 근거가 부족하면 "문서에서 확인되지 않았습니다"라고 명시하세요.
5. 한국어로 답변하세요.`

// Sufficiency gate thresholds
const REJECT_THRESHOLD = 0.3
const LIMITED_THRESHOLD = 0.5

Deno.serve(async (req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const supabase = createClient(supabaseUrl, supabaseKey)

    const body = await req.json()
    const query: string = body.query
    const category: string | null = body.category_id ?? null
    const topK: number = body.top_k ?? 5
    const vectorWeight: number = body.vector_weight ?? 0.7
    const bm25Weight: number = body.bm25_weight ?? 0.3

    if (!query || query.trim().length === 0) {
      return new Response(
        JSON.stringify({ error: 'query is required' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      )
    }

    // 1. Embed the query
    const queryEmbedding = await embedModel.run(query, {
      mean_pool: true,
      normalize: true,
    })
    const embeddingArray = Array.from(queryEmbedding)

    // 2. Hybrid search via RPC
    const { data: chunks, error: searchError } = await supabase.rpc(
      'match_chunks_hybrid',
      {
        query_embedding: JSON.stringify(embeddingArray),
        query_text: query,
        match_threshold: 0.1,
        match_count: topK,
        filter_category: category,
        vector_weight: vectorWeight,
        bm25_weight: bm25Weight,
      }
    )

    if (searchError) {
      return new Response(
        JSON.stringify({ error: `Search failed: ${searchError.message}` }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      )
    }

    // 3. Sufficiency gate
    const topScore = chunks && chunks.length > 0 ? chunks[0].final_score : 0

    if (topScore < REJECT_THRESHOLD) {
      return new Response(
        JSON.stringify({
          answer:
            '죄송합니다. 현재 면접위키에서 해당 질문에 대한 관련 문서를 찾을 수 없습니다. 질문을 더 구체적으로 해주시거나, 다른 키워드로 검색해 주세요.',
          sources: [],
          sufficiency: 'rejected',
          top_score: topScore,
        }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }

    const sufficiency = topScore >= LIMITED_THRESHOLD ? 'pass' : 'limited'

    // 4. Build context from chunks
    const sources: {
      index: number
      topic_id: string
      category_id: string
      heading: string | null
      score: number
      content_preview: string
    }[] = []

    let context = ''
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i]
      const refNum = i + 1
      // Use parent_content if available for richer context
      const displayContent = chunk.parent_content || chunk.content
      context += `[${refNum}] (${chunk.category_id}/${chunk.topic_id}${chunk.heading ? ' - ' + chunk.heading : ''}):\n${displayContent}\n\n`

      sources.push({
        index: refNum,
        topic_id: chunk.topic_id,
        category_id: chunk.category_id,
        heading: chunk.heading,
        score: chunk.final_score,
        content_preview: chunk.content.slice(0, 150),
      })
    }

    // 5. Build prompt
    let sufficiencyNote = ''
    if (sufficiency === 'limited') {
      sufficiencyNote =
        '\n주의: 검색된 문서의 관련성이 높지 않습니다. 가능한 범위 내에서만 답변하고, 확신이 없는 부분은 명확히 밝혀주세요.'
    }

    const fullPrompt = `${SYSTEM_PROMPT}${sufficiencyNote}

검색된 문서:
${context}

질문: ${query}

답변:`

    // 6. Call LLM (Ollama via direct HTTP)
    const ollamaRes = await fetch(`${OLLAMA_HOST}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'gemma3:4b',
        prompt: fullPrompt,
        stream: false,
      }),
    })

    if (!ollamaRes.ok) {
      const errText = await ollamaRes.text()
      return new Response(
        JSON.stringify({ error: `LLM error: ${ollamaRes.status} ${errText}` }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      )
    }

    const llmOutput = await ollamaRes.json()
    const answer = llmOutput.response ?? JSON.stringify(llmOutput)

    return new Response(
      JSON.stringify({
        answer: answer.trim(),
        sources,
        sufficiency,
        top_score: topScore,
        chunks_used: chunks.length,
      }),
      { headers: { 'Content-Type': 'application/json' } }
    )
  } catch (err) {
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    )
  }
})