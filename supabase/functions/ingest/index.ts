import 'jsr:@supabase/functions-js/edge-runtime.d.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const model = new Supabase.ai.Session('gte-small')

const CHUNK_SIZE = 500
const PARENT_GROUP_SIZE = 3

// --- Utility: SHA-256 hash (first 16 hex chars) ---
async function contentHash(text: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(text)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')
  return hashHex.slice(0, 16)
}

// --- Markdown chunking ---
interface Chunk {
  content: string
  heading: string | null
  chunkIndex: number
  parentId: string | null
  parentContent: string | null
  contentHash: string
}

function splitByHeaders(markdown: string): { heading: string | null; body: string }[] {
  const sections: { heading: string | null; body: string }[] = []
  const lines = markdown.split('\n')
  let currentHeading: string | null = null
  let currentLines: string[] = []

  for (const line of lines) {
    const headerMatch = line.match(/^#{1,3}\s+(.+)/)
    if (headerMatch) {
      if (currentLines.length > 0) {
        const body = currentLines.join('\n').trim()
        if (body.length > 0) {
          sections.push({ heading: currentHeading, body })
        }
      }
      currentHeading = headerMatch[1].trim()
      currentLines = []
    } else {
      currentLines.push(line)
    }
  }

  if (currentLines.length > 0) {
    const body = currentLines.join('\n').trim()
    if (body.length > 0) {
      sections.push({ heading: currentHeading, body })
    }
  }

  return sections
}

function splitSectionIntoChunks(text: string, maxSize: number): string[] {
  if (text.length <= maxSize) {
    return [text]
  }

  const paragraphs = text.split(/\n\n+/)
  const chunks: string[] = []
  let current = ''

  for (const para of paragraphs) {
    if (current.length + para.length + 2 > maxSize && current.length > 0) {
      chunks.push(current.trim())
      current = ''
    }
    if (para.length > maxSize) {
      // Split long paragraphs by sentences
      if (current.length > 0) {
        chunks.push(current.trim())
        current = ''
      }
      const sentences = para.split(/(?<=[.!?。])\s+/)
      for (const sentence of sentences) {
        if (current.length + sentence.length + 1 > maxSize && current.length > 0) {
          chunks.push(current.trim())
          current = ''
        }
        current += (current.length > 0 ? ' ' : '') + sentence
      }
    } else {
      current += (current.length > 0 ? '\n\n' : '') + para
    }
  }

  if (current.trim().length > 0) {
    chunks.push(current.trim())
  }

  return chunks
}

async function chunkMarkdown(
  markdown: string,
  topicId: string,
  categoryId: string
): Promise<Chunk[]> {
  const sections = splitByHeaders(markdown)
  const childChunks: { content: string; heading: string | null }[] = []

  for (const section of sections) {
    const textChunks = splitSectionIntoChunks(section.body, CHUNK_SIZE)
    for (const text of textChunks) {
      childChunks.push({ content: text, heading: section.heading })
    }
  }

  // Build parent-child structure
  const results: Chunk[] = []
  let chunkIndex = 0

  for (let i = 0; i < childChunks.length; i += PARENT_GROUP_SIZE) {
    const group = childChunks.slice(i, i + PARENT_GROUP_SIZE)
    const parentContent = group.map((c) => c.content).join('\n\n')
    const parentId = `${categoryId}/${topicId}/p${Math.floor(i / PARENT_GROUP_SIZE)}`

    for (const child of group) {
      const hash = await contentHash(child.content)
      results.push({
        content: child.content,
        heading: child.heading,
        chunkIndex: chunkIndex++,
        parentId,
        parentContent,
        contentHash: hash,
      })
    }
  }

  return results
}

// --- Embed a single text ---
async function embedText(text: string): Promise<number[]> {
  const output = await model.run(text, { mean_pool: true, normalize: true })
  return Array.from(output)
}

// --- Main handler ---
Deno.serve(async (req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const supabase = createClient(supabaseUrl, supabaseKey)

    const body = await req.json().catch(() => ({}))
    const filterCategory: string | null = body.category_id ?? null
    const filterTopic: string | null = body.topic_id ?? null

    // 1. Fetch topics
    let query = supabase.from('topics').select('id, category_id, content')
    if (filterCategory) {
      query = query.eq('category_id', filterCategory)
    }
    if (filterTopic) {
      query = query.eq('id', filterTopic)
    }

    const { data: topics, error: fetchError } = await query
    if (fetchError) {
      return new Response(
        JSON.stringify({ error: `Failed to fetch topics: ${fetchError.message}` }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      )
    }

    if (!topics || topics.length === 0) {
      return new Response(
        JSON.stringify({ message: 'No topics found', processed: 0 }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }

    let totalChunks = 0
    const results: { topic_id: string; category_id: string; chunks: number }[] = []

    for (const topic of topics) {
      if (!topic.content || topic.content.trim().length === 0) {
        continue
      }

      // 2. Chunk the markdown
      const chunks = await chunkMarkdown(topic.content, topic.id, topic.category_id)

      if (chunks.length === 0) {
        continue
      }

      // 3. Generate embeddings for each chunk
      const rows = []
      for (const chunk of chunks) {
        const embedding = await embedText(chunk.content)
        rows.push({
          topic_id: topic.id,
          category_id: topic.category_id,
          chunk_index: chunk.chunkIndex,
          content: chunk.content,
          heading: chunk.heading,
          tags: [],
          embedding: JSON.stringify(embedding),
          parent_id: chunk.parentId,
          parent_content: chunk.parentContent,
          content_hash: chunk.contentHash,
        })
      }

      // 4. Delete old chunks for this topic
      const { error: deleteError } = await supabase
        .from('topic_chunks')
        .delete()
        .eq('topic_id', topic.id)
        .eq('category_id', topic.category_id)

      if (deleteError) {
        console.error(`Delete failed for ${topic.id}: ${deleteError.message}`)
        continue
      }

      // 5. Insert new chunks in batches of 50
      const BATCH_SIZE = 50
      for (let i = 0; i < rows.length; i += BATCH_SIZE) {
        const batch = rows.slice(i, i + BATCH_SIZE)
        const { error: insertError } = await supabase
          .from('topic_chunks')
          .insert(batch)

        if (insertError) {
          console.error(`Insert failed for ${topic.id} batch ${i}: ${insertError.message}`)
        }
      }

      totalChunks += rows.length
      results.push({
        topic_id: topic.id,
        category_id: topic.category_id,
        chunks: rows.length,
      })
    }

    return new Response(
      JSON.stringify({
        message: `Ingestion complete`,
        topics_processed: results.length,
        total_chunks: totalChunks,
        details: results,
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