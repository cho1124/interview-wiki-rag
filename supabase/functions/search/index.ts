import 'jsr:@supabase/functions-js/edge-runtime.d.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const model = new Supabase.ai.Session('gte-small')

Deno.serve(async (req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const supabase = createClient(supabaseUrl, supabaseKey)

    const body = await req.json()
    const query: string = body.query
    const category: string | null = body.category_id ?? null
    const topK: number = body.top_k ?? 5
    const threshold: number = body.threshold ?? 0.3
    const vectorWeight: number = body.vector_weight ?? 0.7
    const bm25Weight: number = body.bm25_weight ?? 0.3

    if (!query || query.trim().length === 0) {
      return new Response(
        JSON.stringify({ error: 'query is required' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      )
    }

    // 1. Embed the query
    const queryEmbedding = await model.run(query, {
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
        match_threshold: threshold,
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

    // 3. Format results
    const results = (chunks || []).map(
      (chunk: {
        id: number
        topic_id: string
        category_id: string
        chunk_index: number
        content: string
        heading: string | null
        tags: string[]
        parent_id: string | null
        parent_content: string | null
        content_hash: string
        vector_score: number
        bm25_score: number
        final_score: number
      }) => ({
        id: chunk.id,
        topic_id: chunk.topic_id,
        category_id: chunk.category_id,
        chunk_index: chunk.chunk_index,
        content: chunk.content,
        heading: chunk.heading,
        tags: chunk.tags,
        parent_id: chunk.parent_id,
        parent_content: chunk.parent_content,
        scores: {
          vector: chunk.vector_score,
          bm25: chunk.bm25_score,
          final: chunk.final_score,
        },
      })
    )

    return new Response(
      JSON.stringify({
        query,
        total_results: results.length,
        results,
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